"""UI integration: edits survive navigation and drive actual exported figures."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
import pandas as pd

import ec_plotting as plotting
from ec_plot_studio import PlotStudio


class StudioStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / "output" / "tests"
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.root = Path(self.temp.name)
        (self.root / "input").mkdir()
        self.source = self.root / "input" / "synthetic.csv"
        self.source.write_text("x,a,b\n0,1,3\n1,3,2\n2,2,1\n", encoding="utf-8")
        self.book = plotting.load_table_book(self.source)
        self.specs = [
            plotting.PlotSpec("第一张", [plotting.ColumnSeries("synthetic", "x", "a", label="A"),
                                      plotting.ColumnSeries("synthetic", "x", "b", label="B")], "Time (s)", "Value"),
            plotting.PlotSpec("第二张", [plotting.ColumnSeries("synthetic", "x", "b", label="B")], "Time (s)", "Other"),
        ]
        self.studio = PlotStudio()
        self.studio._loaded(self.book, self.specs)

    def tearDown(self):
        self.wait_finished(self.studio)
        self.studio.embedded = False
        self.studio.reject()
        self.studio.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_finished(self, studio):
        end = time.monotonic() + 10
        while studio.worker is not None and time.monotonic() < end:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertIsNone(studio.worker)

    def test_unpreviewed_edits_survive_both_selectors_and_manual_tab(self):
        s = self.studio
        self.assertTrue(s.settings_panel.isHidden())
        s.show_plot_settings()
        s.xlabel_edit.setText("Edited X")
        s.style_numbers["width_cm"].setValue(10)
        s.legend_visible.setCurrentIndex(2)
        s.series_table.item(0, 0).setText("Sample one")
        s.series_table.item(1, 1).setText("#ff0000")
        s.current_preview.setCurrentIndex(1)
        self.assertEqual(s.plot_list.currentRow(), 1)
        self.assertEqual(s.auto_specs[0].xlabel, "Edited X")
        self.assertEqual(s.auto_specs[0].style["width_cm"], 10)
        self.assertFalse(s.auto_specs[0].style["legend_visible"])
        self.assertEqual(s.auto_specs[1].style, {})
        s.plot_list.setCurrentRow(0)
        self.assertEqual(s.current_preview.currentIndex(), 0)
        self.assertEqual(s.series_table.item(0, 0).text(), "Sample one")
        self.assertEqual(s.series_table.item(1, 1).text(), "#ff0000")
        self.assertIsNone(s.canvas.figure.axes[0].get_legend())
        self.assertEqual(s.canvas.figure.axes[0].get_xlabel(), "Edited X")
        s.tabs.setCurrentIndex(1)
        self.assertEqual(s.current_preview.currentText(), "按列绘图")
        s.tabs.setCurrentIndex(0)
        self.assertEqual(s.xlabel_edit.text(), "Edited X")
        self.assertEqual(s.style_numbers["width_cm"].value(), 10)

    def test_invalid_ranges_keep_current_plot_and_edits(self):
        s = self.studio
        s.range_edits["xlim"][0].setText("5")
        s.current_preview.setCurrentIndex(1)
        self.assertEqual(s.current_preview.currentIndex(), 0)
        self.assertEqual(s.plot_list.currentRow(), 0)
        self.assertEqual(s.range_edits["xlim"][0].text(), "5")
        self.assertIn("同时填写", s.status.text())
        s.range_edits["xlim"][1].setText("10")
        s.current_preview.setCurrentIndex(1)
        self.assertEqual(s.auto_specs[0].style["xlim"], [5, 10])

    def test_preview_resizing_keeps_physical_size_and_display_ratio(self):
        s = self.studio
        s.style_numbers["width_cm"].setValue(10)
        s.style_numbers["height_cm"].setValue(8)
        s._preview()
        s.show()
        for width, height, expanded in ((1180, 780, False), (900, 600, True), (1320, 900, False)):
            s.resize(width, height)
            s.settings_button.setChecked(expanded)
            self.app.processEvents()
            self.assertAlmostEqual(s.canvas.figure.get_figwidth(), 10 / 2.54)
            self.assertAlmostEqual(s.canvas.figure.get_figheight(), 8 / 2.54)
            self.assertAlmostEqual(s.canvas.width() / s.canvas.height(), 10 / 8, delta=.02)
            self.assertLessEqual(s.canvas.width(), s.preview_frame.width() + 1)
            self.assertLessEqual(s.canvas.height(), s.preview_frame.height() + 1)
        self.assertEqual(s._current_spec().style["width_cm"], 10)

    def test_recipe_precision_is_preserved_when_controls_are_not_edited(self):
        s = self.studio
        style = plotting.resolve_plot_style({"width_cm": 9.87654321, "axis_font_size": 11.23456})
        self.specs[0].style = style
        s._loaded(self.book, self.specs)
        s.xlabel_edit.setText("Only this title changed")
        s.current_preview.setCurrentIndex(1)
        self.assertEqual(s.auto_specs[0].style["width_cm"], 9.87654321)
        self.assertEqual(s.auto_specs[0].style["axis_font_size"], 11.23456)
        s.current_preview.setCurrentIndex(0)
        target = self.root / "precise-style.json"
        with patch("ec_plot_studio.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            s._save_style_template()
        self.assertEqual(plotting.load_style_template(target)["width_cm"], 9.87654321)

    def test_manual_column_change_refreshes_curve_editor_without_wrong_labels(self):
        s = self.studio
        s.tabs.setCurrentIndex(1)
        s._preview()
        self.assertEqual(s.series_table.rowCount(), 1)
        s.series_table.item(0, 0).setText("Label for previous column")
        s.style_numbers["width_cm"].setValue(12)
        for i in range(s.y_list.count()):
            s.y_list.item(i).setSelected(s.y_list.item(i).text() in ("a", "b"))
        s._preview()
        self.assertEqual(s.series_table.rowCount(), 2)
        self.assertEqual([s.series_table.item(i, 0).text() for i in range(2)], ["a", "b"])
        self.assertEqual(s._current_spec().style["width_cm"], 12)

    def test_embedded_escape_and_tab_switch_keep_canvas(self):
        host = QTabWidget()
        child = PlotStudio(host, embedded=True)
        host.addTab(child, "绘图")
        host.addTab(QWidget(), "处理")
        child._loaded(self.book, self.specs)
        host.show()
        self.app.processEvents()
        canvas = child.canvas
        child.reject()
        QTest.keyClick(child, Qt.Key_Escape)
        host.setCurrentIndex(1)
        host.setCurrentIndex(0)
        self.app.processEvents()
        self.assertFalse(child.isWindow())
        self.assertTrue(child.isVisible())
        self.assertIs(child.canvas, canvas)
        self.assertEqual(len(canvas.figure.axes), 1)
        child.embedded = False
        child.reject()
        host.close()
        host.deleteLater()

    def test_template_can_load_before_data_and_round_trip_without_source(self):
        template = self.root / "styles" / "appearance.json"
        plotting.save_style_template(template, {"width_cm": 9, "height_cm": 7,
            "font_family": "Arial", "dpi": 180, "legend_location": "lower left"})
        empty = PlotStudio()
        empty.load_style_template(str(template))
        self.assertIn("随后导入", empty.status.text())
        empty.load_path(str(self.source))
        self.wait_finished(empty)
        self.assertEqual(empty._current_spec().style["width_cm"], 9)
        self.assertEqual(empty._current_spec().style["dpi"], 180)
        target = self.root / "styles" / "saved.json"
        with patch("ec_plot_studio.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            empty._save_style_template()
        restored = plotting.load_style_template(target)
        self.assertEqual(restored["font_family"], "Arial")
        self.assertNotIn(str(self.source), target.read_text(encoding="utf-8"))
        empty.reject()
        empty.deleteLater()

    def test_empty_workspace_can_edit_and_save_default_appearance(self):
        empty = PlotStudio()
        empty.edit_style_template()
        self.assertTrue(empty.settings_panel.isEnabled())
        self.assertFalse(empty.xlabel_edit.isEnabled())
        empty.style_numbers["width_cm"].setValue(9)
        target = self.root / "before-data.json"
        with patch("ec_plot_studio.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            empty._save_style_template()
        self.assertEqual(plotting.load_style_template(target)["width_cm"], 9)
        empty.load_path(str(self.source))
        self.wait_finished(empty)
        self.assertEqual(empty._current_spec().style["width_cm"], 9)
        empty.reject()
        empty.deleteLater()

    def test_export_captures_unpreviewed_styles_and_uses_parent_destination(self):
        s = self.studio
        destination = self.root / "figures"
        s.set_output_dir(destination)
        s.xlabel_edit.setText("Elapsed seconds")
        s.range_edits["ylim"][0].setText("0")
        s.range_edits["ylim"][1].setText("4")
        s.style_numbers["width_cm"].setValue(10)
        s.style_numbers["height_cm"].setValue(8)
        s.style_numbers["dpi"].setValue(120)
        s.series_table.item(0, 0).setText("Retained label")
        s.series_table.item(0, 1).setText("#008000")
        selected = []
        class Selection:
            def __init__(inner, parent, items, folder, *args, **kwargs):
                selected.append(folder)
                inner.selection = [("0", "selected")]
                inner.formats = ["svg"]
                inner.output_dir = str(destination)
            def exec(inner):
                return True
        busy_events, completed = [], []
        s.busyChanged.connect(lambda value: busy_events.append((value, s.worker is None)))
        s.outputReady.connect(completed.append)
        with patch("ec_output_dialog.OutputSelectionDialog", Selection), patch("ec_output_dialog.offer_open_folder") as prompt:
            s._export(True)
            self.assertTrue(s._busy)
            self.wait_finished(s)
            prompt.assert_called_once()
        self.assertEqual(selected, [str(destination)])
        self.assertEqual(completed, [str(destination)])
        self.assertTrue(all(no_worker for value, no_worker in busy_events if not value))
        self.assertTrue((destination / "selected.svg").is_file())
        _, specs, _ = plotting.load_recipe(destination / "绘图配方.json")
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].xlabel, "Elapsed seconds")
        self.assertEqual(specs[0].style["ylim"], [0, 4])
        self.assertEqual(specs[0].style["series_labels"][0], "Retained label")
        self.assertEqual(specs[0].style["series_colors"][0], "#008000")
        self.assertEqual(specs[0].style["width_cm"], 10)
        self.assertEqual(specs[0].style["dpi"], 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
