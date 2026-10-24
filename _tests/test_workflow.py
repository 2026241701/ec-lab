"""Behavioral checks for responsive processing, cache validity and source safety."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ec_workflow import calculation_signature, validate_output
import ec_gui
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name, "raw")
        self.source.mkdir()
        self.measurement = self.source / "CV.txt"
        self.measurement.write_text("measurement", encoding="utf-8")
        self.cfg = {"data_dir": [str(self.source)], "mass_mg": {"CV": 1},
                    "output": {"dir": str(Path(self.tmp.name, "results"))}}
        with patch.object(ec_gui.MainWindow, "_first_run_bootstrap"), \
                patch.object(ec_gui.MainWindow, "_load_config_file"):
            self.window = ec_gui.MainWindow()
        self.window._processing_cfg = lambda **kwargs: self.cfg
        self.data = {"cfg": self.cfg, "anomalies": []}

    def tearDown(self):
        if getattr(self.window, "_worker_thread", None):
            self.window._worker_thread.join(timeout=3)
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def wait_done(self):
        deadline = time.monotonic() + 5
        while self.window._running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(self.window._running, "background job did not finish")

    def test_signature_distinguishes_numbers_from_style(self):
        first = calculation_signature(self.cfg)
        self.cfg["plot_style"] = {"color": "red"}
        self.cfg["output"]["dpi"] = 600
        self.assertEqual(first, calculation_signature(self.cfg))
        self.cfg["mass_mg"]["CV"] = 2
        self.assertNotEqual(first, calculation_signature(self.cfg))
        second = calculation_signature(self.cfg)
        self.measurement.write_text("changed measurement", encoding="utf-8")
        self.assertNotEqual(second, calculation_signature(self.cfg))

    def test_source_folder_cannot_be_output(self):
        self.cfg["output"]["dir"] = str(self.source / "results")
        with self.assertRaises(ValueError):
            validate_output(self.cfg, self.tmp.name)
        if os.name == "nt":
            self.cfg["output"]["dir"] = "E:/Data/another-experiment/results"
            with self.assertRaises(ValueError):
                validate_output(self.cfg, self.tmp.name)

    def test_processing_saves_excel_without_plotting_and_ui_keeps_ticking(self):
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        def prepare(cfg):
            time.sleep(.20)
            return self.data
        workbook = Path(self.tmp.name, "processed.xlsx")
        def export(data, cfg):
            workbook.write_bytes(b"verified export fixture")
            return str(workbook)
        with patch.object(ec_gui.eclab, "prepare", side_effect=prepare) as calc, \
                patch.object(ec_gui.eclab, "export_tables", side_effect=export), \
                patch.object(ec_gui.eclab, "render") as render:
            self.window.run_analysis()
            self.window.run_analysis()  # a repeated click must not launch another job
            self.wait_done()
            self.assertEqual(calc.call_count, 1)
            render.assert_not_called()
        timer.stop()
        self.assertGreater(len(ticks), 3)
        self.assertTrue(workbook.exists())
        self.assertEqual(self.window._last_workbook, str(workbook))

    def test_quick_export_recalculates_changed_mass(self):
        self.window._last_data = self.data
        self.window._last_signature = calculation_signature(self.cfg)
        with patch.object(ec_gui.eclab, "prepare", return_value=self.data) as calc, \
                patch.object(ec_gui.eclab, "preview_list", return_value=[("CV", "CV")]), \
                patch.object(self.window, "_choose_plot_output") as choose:
            self.window.quick_render()
            self.wait_done()
            calc.assert_not_called()
            self.cfg["mass_mg"]["CV"] = 3
            self.window.quick_render()
            self.wait_done()
            self.assertEqual(calc.call_count, 1)

    def test_failure_restores_streams_and_controls(self):
        original = sys.stdout, sys.stderr
        with patch.object(ec_gui.eclab, "prepare", side_effect=ValueError("invalid data")), \
                patch.object(ec_gui.QMessageBox, "warning") as warning:
            self.window.run_analysis()
            self.wait_done()
            warning.assert_called_once()
        self.assertIs(sys.stdout, original[0])
        self.assertIs(sys.stderr, original[1])
        self.assertTrue(self.window.centralWidget().isEnabled())
        self.assertIn("失败", self.window.statusBar().currentMessage())

    def test_scan_is_background_and_populates_results_on_ui(self):
        self.window.current_cfg = lambda **kwargs: self.cfg
        def scan(cfg):
            time.sleep(.10)
            return {"CV": [str(self.measurement)], "GCD": [], "EIS": []}, []
        with patch.object(ec_gui.eclab, "scan_files", side_effect=scan):
            self.window.scan()
            self.assertTrue(self.window._running)
            self.wait_done()
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.table.item(0, 1).text(), "CV")

    def test_stale_preview_recalculates_before_showing_current_numbers(self):
        self.window.current_cfg = lambda **kwargs: self.cfg
        self.window._last_data = self.data
        self.window._last_signature = calculation_signature(self.cfg)
        self.cfg["mass_mg"]["CV"] = 9
        fresh = {"cfg": self.cfg, "anomalies": [], "current": True}
        with patch.object(self.window, "_show_preview_dialog") as preview, \
                patch.object(ec_gui.eclab, "prepare", return_value=fresh) as prepare, \
                patch.object(ec_gui.eclab, "preview_list", return_value=[("CV", "CV")]), \
                patch.object(ec_gui.QMessageBox, "warning") as warning:
            self.window.open_preview()
            self.wait_done()
            preview.assert_called_once()
            prepare.assert_called_once()
            warning.assert_not_called()
            self.assertIs(self.window._last_data, fresh)



if __name__ == "__main__":
    unittest.main()
