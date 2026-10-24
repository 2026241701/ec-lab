"""CDI UI regressions checked in clean, isolated Qt subprocesses.

No startup-speed threshold is asserted: the responsiveness test observes a
timer while a worker is deliberately blocked. The subprocess timeout only
prevents a broken thread lifecycle from hanging the entire test suite.
"""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CDIUITests(unittest.TestCase):
    def run_isolated(self, source):
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                           OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                           PYTHONIOENCODING="utf-8")
        completed = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(source)], cwd=ROOT,
            env=environment, capture_output=True, text=True, encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("CDI_UI_OK", completed.stdout)

    def test_opening_cdi_dialog_does_not_import_processing_libraries(self):
        self.run_isolated(r'''
            import sys
            from PySide6.QtWidgets import QApplication
            from ec_legacy_ui import LegacyExcelDialog

            forbidden = {"pandas", "numpy", "scipy", "openpyxl", "ec_legacy", "ec_conductivity"}
            app = QApplication([])
            dialog = LegacyExcelDialog(mode="cdi")
            dialog.show()
            app.processEvents()
            assert dialog.isVisible()
            assert dialog.fields["volume_ml"].value() == 50
            loaded = {name.split(".")[0] for name in sys.modules} & forbidden
            assert not loaded, "Opening the CDI dialog imported heavy processing modules: " + repr(loaded)
            assert dialog.close()
            app.processEvents()
            print("CDI_UI_OK")
        ''')

    def test_timer_and_close_remain_safe_while_processing_is_blocked(self):
        self.run_isolated(r'''
            from pathlib import Path
            import sys
            import tempfile
            import threading
            import types
            from unittest.mock import Mock, patch

            from PySide6.QtCore import QEventLoop, QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox
            from shiboken6 import isValid
            import ec_legacy_ui as ui

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            root = Path("output/cdi_reference_20261024")
            root.mkdir(parents=True, exist_ok=True)
            entered = threading.Event()
            release_worker = threading.Event()
            permit_release = threading.Event()
            heartbeat_seen = threading.Event()
            worker_completed = threading.Event()
            thread_ids = {}
            main_thread_id = threading.get_ident()
            destroyed = []

            def wait_until(predicate):
                if predicate():
                    return
                loop = QEventLoop()
                poll = QTimer()
                poll.setInterval(5)
                poll.timeout.connect(lambda: loop.quit() if predicate() else None)
                poll.start()
                loop.exec()
                poll.stop()

            # Only the controller thread releases the job. The GUI first has
            # to demonstrate an independent timer tick and safe close guards.
            def controller():
                permit_release.wait()
                release_worker.set()

            control_thread = threading.Thread(target=controller, daemon=True)
            control_thread.start()
            offer = Mock()
            export_ui = types.ModuleType("ec_output_dialog")
            export_ui.offer_open_folder = offer

            with tempfile.TemporaryDirectory(dir=root) as temporary:
                folder = Path(temporary)
                source = folder / "inputs" / "sample(24mg).csv"
                source.parent.mkdir()
                source.write_text("time_s,conductivity_uS_cm\n0,100\n5,99\n", encoding="utf-8")
                destination = folder / "results"
                destination.mkdir()
                expected = {"folder": str(destination), "files": [str(destination / "sample-处理.xlsx")]}

                def blocked_job(mode, paths, output, options, progress):
                    assert mode == "cdi"
                    assert paths == [str(source)]
                    thread_ids["worker"] = threading.get_ident()
                    entered.set()
                    progress("测试作业等待放行")
                    release_worker.wait()
                    worker_completed.set()
                    return expected

                dialog = ui.LegacyExcelDialog(mode="cdi", paths=[source], mass_mg=24,
                                              output_dir=destination)
                dialog.show()
                app.processEvents()
                heartbeat = QTimer()
                heartbeat.setInterval(5)

                def tick():
                    if entered.is_set() and not release_worker.is_set():
                        thread_ids["timer"] = threading.get_ident()
                        heartbeat_seen.set()

                heartbeat.timeout.connect(tick)
                heartbeat.start()
                with patch.object(ui, "run_legacy", side_effect=blocked_job), \
                     patch.dict(sys.modules, {"ec_output_dialog": export_ui}), \
                     patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                     patch.object(QMessageBox, "information", side_effect=AssertionError("Unexpected information dialog")), \
                     patch.object(QMessageBox, "warning", side_effect=AssertionError("Unexpected warning dialog")):
                    try:
                        dialog._run()
                        wait_until(heartbeat_seen.is_set)
                        assert entered.is_set() and not worker_completed.is_set()
                        assert thread_ids["worker"] != main_thread_id
                        assert thread_ids["timer"] == main_thread_id
                        assert dialog._busy and not dialog.controls.isEnabled()
                        worker, thread = dialog._worker, dialog._thread
                        worker.destroyed.connect(lambda: destroyed.append("worker"))
                        assert thread.isRunning() and isValid(worker)

                        assert not dialog.close(), "Closing during processing must be rejected"
                        dialog.reject()  # Also covers Escape / the dialog rejection path.
                        app.processEvents()
                        assert dialog.isVisible() and dialog._busy
                        assert dialog._worker is worker and dialog._thread is thread
                        assert isValid(worker) and thread.isRunning() and not destroyed
                        assert not worker_completed.is_set()

                        permit_release.set()
                        wait_until(lambda: not dialog._busy and dialog._thread is None)
                        control_thread.join()
                        assert worker_completed.is_set()
                        assert dialog._worker is None
                        assert dialog.controls.isEnabled() and dialog.close_button.isEnabled()
                        assert dialog.result_files == expected["files"]
                        offer.assert_called_once_with(dialog, expected["folder"], 1)
                        assert dialog.close()
                        app.processEvents()
                        assert not dialog.isVisible()
                    finally:
                        heartbeat.stop()
                        permit_release.set()
                        control_thread.join()
                        if dialog._thread is not None:
                            wait_until(lambda: dialog._thread is None)
                        dialog.close()
                        app.processEvents()
            print("CDI_UI_OK")
        ''')

    def test_mass_suggestion_override_mixed_batch_and_unknown_mass(self):
        self.run_isolated(r'''
            from pathlib import Path
            import sys
            import tempfile
            import types
            from unittest.mock import Mock, patch
            from PySide6.QtCore import QEventLoop, QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox
            import ec_legacy_ui as ui

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            root = Path("output/cdi_reference_20261024")
            root.mkdir(parents=True, exist_ok=True)
            export_ui = types.ModuleType("ec_output_dialog")
            export_ui.offer_open_folder = Mock()

            def finish(dialog):
                loop = QEventLoop()
                timer = QTimer()
                timer.setInterval(5)
                timer.timeout.connect(lambda: loop.quit() if not dialog._busy else None)
                timer.start()
                loop.exec()
                timer.stop()

            with tempfile.TemporaryDirectory(dir=root) as temporary:
                folder = Path(temporary)
                source25 = folder / "FTO@C1(25mg)-200mg.csv"
                source24 = folder / "FTO@C2(24mg).csv"
                unknown = folder / "sample.csv"
                for source in (source25, source24, unknown):
                    source.write_text("time_s,conductivity_uS_cm\n0,100\n5,99\n", encoding="utf-8")
                destination = folder / "results"
                destination.mkdir()
                result = {"folder": str(destination), "files": [str(destination / "result.xlsx")]}
                dialog = ui.LegacyExcelDialog(mode="cdi", paths=[source25], output_dir=destination)
                dialog.show()
                app.processEvents()

                with patch.object(ui, "run_legacy", return_value=result) as process, \
                     patch.dict(sys.modules, {"ec_output_dialog": export_ui}), \
                     patch.object(QMessageBox, "information") as information, \
                     patch.object(QMessageBox, "warning", side_effect=AssertionError("Unexpected warning dialog")):
                    # The parenthesized 25 mg is suggested, not the later 200 mg.
                    assert dialog.fields["mass_mg"].value() == 25
                    assert "FTO@C1(25mg)-200mg" in dialog.mass_note.text()
                    assert dialog.sampling.currentData() == "auto"
                    assert not dialog.fields["cdi_step"].isVisible()
                    dialog.fields["mass_mg"].setValue(23.5)
                    assert "23.5 mg" in dialog.mass_note.text()
                    dialog._run()
                    finish(dialog)
                    assert process.call_args.args[3]["mass_mg"] == 23.5
                    assert process.call_args.args[3]["cdi_step"] == "auto"
                    information.assert_not_called()

                    # Different explicit masses must not be merged under one mass.
                    process.reset_mock()
                    dialog.files.addItem(str(source24))
                    assert dialog._mass_mixed
                    assert dialog.fields["mass_mg"].value() == 0
                    dialog.fields["mass_mg"].setValue(25)  # Manual text cannot bypass mixed input.
                    dialog._run()
                    process.assert_not_called()
                    assert information.call_args.args[1] == "请按质量分批"
                    assert not dialog._busy and dialog._thread is None

                    # A changed list cannot carry over a previous sample's mass.
                    information.reset_mock()
                    dialog.files.clear()
                    dialog.files.addItem(str(unknown))
                    assert not dialog._mass_mixed
                    assert dialog.fields["mass_mg"].value() == 0
                    dialog._run()
                    process.assert_not_called()
                    assert information.call_args.args[1] == "请填写质量"
                    assert not dialog._busy and dialog._thread is None

                    # Explicit mass and interval reach the backend unchanged.
                    information.reset_mock()
                    dialog.fields["mass_mg"].setValue(21)
                    dialog.sampling.setCurrentIndex(dialog.sampling.findData("manual"))
                    assert dialog.fields["cdi_step"].isVisible()
                    dialog.fields["cdi_step"].setValue(10)
                    dialog._run()
                    finish(dialog)
                    assert process.call_args.args[3]["mass_mg"] == 21
                    assert process.call_args.args[3]["cdi_step"] == 10
                    information.assert_not_called()
                    assert dialog.close()
                    app.processEvents()
            print("CDI_UI_OK")
        ''')

    def test_embedded_page_signals_and_template_mass_protection(self):
        self.run_isolated(r'''
            from pathlib import Path
            import json
            import sys
            import tempfile
            import types
            from unittest.mock import Mock, patch
            from PySide6.QtCore import QEventLoop, QTimer
            from PySide6.QtWidgets import QApplication, QTabWidget, QMessageBox
            import ec_legacy_ui as ui
            from ec_processing_templates import save_template

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            root = Path("output/cdi_reference_20261024")
            root.mkdir(parents=True, exist_ok=True)

            def finish(dialog):
                loop = QEventLoop()
                timer = QTimer()
                timer.setInterval(5)
                timer.timeout.connect(lambda: loop.quit() if not dialog._busy else None)
                timer.start()
                loop.exec()
                timer.stop()

            export_ui = types.ModuleType("ec_output_dialog")
            export_ui.offer_open_folder = Mock()
            with tempfile.TemporaryDirectory(dir=root) as temporary:
                folder = Path(temporary)
                source = folder / "sample(25mg).csv"
                source.write_text("time_s,conductivity_uS_cm\n0,100\n5,99", encoding="utf-8")
                parent = QTabWidget()
                dialog = ui.LegacyExcelDialog(parent, mode="cdi", paths=[source],
                                              output_dir=folder, embedded=True)
                parent.addTab(dialog, "数据处理")
                parent.show()
                app.processEvents()
                assert not dialog.isWindow()
                assert not dialog.close_button.isVisible()
                assert not dialog.parameters_container.isVisible()
                assert "50 mL" in dialog.summary.text()
                assert "自动" in dialog.summary.text()
                assert not dialog.close()
                dialog.accept()
                dialog.reject()
                assert dialog.isVisible()
                dialog.fields["mass_mg"].setValue(23.5)
                preset = folder / "template.json"
                save_template(preset, "cdi", {"mass_mg": 99, "volume_ml": 75})
                assert dialog.load_processing_template(preset)
                assert dialog.fields["mass_mg"].value() == 23.5
                assert dialog.fields["volume_ml"].value() == 75
                assert "未覆盖" in dialog.template_note.text()
                assert dialog._paths() == [str(source)]
                assert dialog.output.text() == str(folder)
                dialog.edit_processing_template()
                assert dialog.parameters_container.isVisible()
                saved = folder / "saved.json"
                assert dialog.save_processing_template(saved)
                parameters = json.loads(saved.read_text(encoding="utf-8"))["parameters"]
                assert parameters["mass_mg"] == 23.5 and parameters["volume_ml"] == 75
                assert "cdi_template" not in parameters
                assert str(source) not in saved.read_text(encoding="utf-8")

                ready, plots, busy, advanced = [], [], [], []
                dialog.resultsReady.connect(lambda files, destination: ready.append((files, destination)))
                dialog.plotRequested.connect(plots.append)
                dialog.busyChanged.connect(busy.append)
                dialog.analysisRequested.connect(lambda: advanced.append(True))
                expected = {"folder": str(folder), "files": [str(folder / "result.xlsx")]}
                with patch.object(ui, "run_legacy", return_value=expected), \
                     patch.dict(sys.modules, {"ec_output_dialog": export_ui}), \
                     patch.object(QMessageBox, "information", side_effect=AssertionError("Unexpected dialog")), \
                     patch.object(QMessageBox, "warning", side_effect=AssertionError("Unexpected warning")):
                    dialog._run()
                    finish(dialog)
                assert ready == [(expected["files"], expected["folder"])]
                assert busy == [True, False]
                dialog._plot()
                assert plots == expected["files"]
                assert "ec_plot_studio" not in sys.modules
                dialog._analysis()
                assert advanced == [True] and dialog.isVisible()
                parent.close()
                app.processEvents()
            print("CDI_UI_OK")
        ''')

    def test_folder_import_filters_duplicates_and_caps_batch(self):
        self.run_isolated(r'''
            from pathlib import Path
            import tempfile
            from PySide6.QtCore import QEventLoop, QTimer
            from PySide6.QtWidgets import QApplication
            from ec_legacy_ui import LegacyExcelDialog

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            root = Path("output/cdi_reference_20261024")
            root.mkdir(parents=True, exist_ok=True)

            def finish(dialog):
                loop = QEventLoop()
                timer = QTimer()
                timer.setInterval(5)
                timer.timeout.connect(lambda: loop.quit() if not dialog._busy else None)
                timer.start()
                loop.exec()
                timer.stop()

            with tempfile.TemporaryDirectory(dir=root) as temporary:
                folder = Path(temporary)
                nested = folder / "nested"
                nested.mkdir()
                names = ["sample(24mg).xlsx", "sample(24mg)-处理.xlsx", "~$locked.xlsx", "notes.pdf"]
                for name in names:
                    (folder / name).write_text("read only fixture", encoding="utf-8")
                raw = nested / "data(24mg).csv"
                raw.write_text("time_s,conductivity_uS_cm\n0,100", encoding="utf-8")
                before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
                dialog = LegacyExcelDialog(mode="cdi")
                dialog.show()
                dialog.add_folder(folder)
                finish(dialog)
                assert {Path(p).name for p in dialog._paths()} == {"sample(24mg).xlsx", "data(24mg).csv"}
                dialog.add_folder(folder)
                finish(dialog)
                assert dialog.files.count() == 2
                assert before == {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

                for number in range(105):
                    (nested / f"cv{number:03d}.txt").write_text("fixture", encoding="utf-8")
                dialog.files.clear()
                dialog.mode.setCurrentIndex(dialog.mode.findData("electrochem"))
                dialog.add_folder(folder)
                finish(dialog)
                assert dialog.files.count() == 100
                assert all(Path(p).suffix == ".txt" for p in dialog._paths())
                assert "100" in dialog.log.toPlainText()
                assert dialog.close()
                app.processEvents()
            print("CDI_UI_OK")
        ''')


if __name__ == "__main__":
    unittest.main()
