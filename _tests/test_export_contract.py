# -*- coding: utf-8 -*-
"""Independent export regressions: only fixtures and temporary workspace files."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import eclab
import ec_export
import make_mock


class ExportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = make_mock.sample_cfg({
            "eis": {"fit": False, "export_zview": False},
            "process": {"CV": True, "GCD": True, "EIS": True, "cycle": False},
        })
        with redirect_stdout(io.StringIO()):
            cls.data = eclab.prepare(cls.cfg)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="_export_test_", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_numeric_baseline_and_metadata(self):
        self.assertEqual([round(r["C_F_g"], 1) for r in self.data["cv"]],
                         [106.8, 82.2, 69.7, 61.0])
        self.assertEqual([round(r["metrics"]["capacitance_F_g"], 1)
                          for r in self.data["gcd"]], [95.0, 78.0])
        with patch.object(eclab.plt, "subplots", side_effect=AssertionError("must not plot")):
            output = eclab.export_tables(self.data, out_dir=self.folder)
        tables = pd.read_excel(output, sheet_name=None)
        self.assertTrue({"CV", "GCD", "EIS", "summary", "_ec_lab"}.issubset(tables))
        self.assertIn("scan_rate_mVs", tables["CV"])
        self.assertIn("mass_mg", tables["summary"])
        self.assertEqual(set(tables["GCD"]["phase"]), {"charge", "discharge"})
        self.assertEqual(set(tables["CV"]["mass_mg"]), {1})
        self.assertEqual(list(self.folder.glob("*.png")), [])
        self.assertEqual(list(self.folder.glob("*.pdf")), [])

    def test_gcd_export_matches_plot_time_including_gap(self):
        for result, table in zip(self.data["gcd"], self.data["gcd_tables"]):
            metrics = result["metrics"]
            gap = max(0.0, metrics["discharge_t_abs"][0] - metrics["charge_t_abs"][-1])
            expected = np.concatenate([
                metrics["charge_t"],
                metrics["discharge_t"] + metrics["charge_t"][-1] + gap])
            np.testing.assert_allclose(table["time_s"], expected)
            np.testing.assert_allclose(table["time_abs_s"], np.concatenate([
                metrics["charge_t_abs"], metrics["discharge_t_abs"]]))

    def test_gcd_known_eight_second_pause_is_preserved(self):
        source = self.folder / "source"
        source.mkdir()
        path = source / "1Ag.txt"
        with path.open("w", encoding="utf-8") as stream:
            stream.write("Chronopotentiometry\nCathodic Current (A) = 0.001\n"
                         "Time/sec, Potential/V\n")
            t = np.concatenate([np.arange(11), np.arange(11, 21), np.arange(28, 38)])
            v = np.concatenate([np.linspace(1, 0, 11), np.linspace(0.1, 1, 10),
                                np.linspace(0.9, 0, 10)])
            np.savetxt(stream, np.column_stack([t, v]), delimiter=",")
        cfg = {"data_dir": [str(source)], "mass_mg": {"1Ag": 1.0},
               "process": {"cycle": False}}
        with redirect_stdout(io.StringIO()):
            result = eclab.prepare(cfg)
        self.assertEqual(len(result["gcd_tables"]), 1)
        table = result["gcd_tables"][0]
        charge_end = table.loc[table.phase == "charge", "time_s"].iloc[-1]
        discharge_start = table.loc[table.phase == "discharge", "time_s"].iloc[0]
        self.assertEqual(discharge_start - charge_end, 8)

    def test_empty_selection_does_not_process_every_file(self):
        cfg = {**self.cfg, "include_files": []}
        with redirect_stdout(io.StringIO()):
            result = eclab.prepare(cfg)
        self.assertFalse(result["cv"] or result["gcd"] or result["eis"])
        with self.assertRaisesRegex(ValueError, "没有可导出"):
            eclab.export_tables(result, out_dir=self.folder / "empty")
        self.assertFalse((self.folder / "empty").exists())

    def test_external_fit_owns_its_frequency_grid_and_prepare_is_read_only(self):
        source = self.folder / "source"
        source.mkdir()
        raw = source / "impedance.txt"
        raw.write_text("A.C. Impedance\nFreq/Hz, Z'/ohm, Z''/ohm\n"
                       "1000,5,-1\n100,10,-2\n10,20,-3\n", encoding="utf-8")
        fit = source / "impedance-fit.txt"
        fit.write_text("ZView Export\nPt.\tFreq\tZr\tZi\tZrFit\tZiFit\n"
                       "1\t900\t5\t-1\t5.1\t-1.1\n"
                       "2\t20\t20\t-3\t19.9\t-3.2\n", encoding="utf-8")
        original = {p.name: p.read_bytes() for p in source.iterdir()}
        output = self.folder / "result"
        cfg = {"data_dir": [str(source)], "eis": {
            "fit": False, "use_external_fit": True, "export_zview": True},
            "output": {"dir": str(output)}}
        with redirect_stdout(io.StringIO()):
            result = eclab.prepare(cfg)
        self.assertFalse(output.exists())
        np.testing.assert_array_equal(result["eis"][0]["f"], [1000, 100, 10])
        np.testing.assert_array_equal(result["eis"][0]["fit_f"], [900, 20])
        workbook = eclab.export_tables(result)
        measured = pd.read_excel(workbook, sheet_name="EIS")
        fitted = pd.read_excel(workbook, sheet_name="EIS_fit_curve")
        self.assertEqual(measured["Freq_Hz"].tolist(), [1000, 100, 10])
        self.assertEqual(fitted["Freq_Hz"].tolist(), [900, 20])
        self.assertEqual(fitted["Z_re_fit_ohm"].tolist(), [5.1, 19.9])
        self.assertEqual(len(list(output.glob("*.z"))), 1)
        self.assertEqual(original, {p.name: p.read_bytes() for p in source.iterdir()})

    def test_four_column_zview_is_not_silently_claimed_as_fit(self):
        path = self.folder / "invalid-fit.txt"
        path.write_text("ZView Export\n1\t1000\t2\t-3\n", encoding="utf-8")
        self.assertIsNone(eclab.parse_zview_fit(path))

    def test_source_directories_are_protected_before_writing(self):
        root = self.folder / "input"
        root.mkdir()
        for path in (root, root / "nested" / "result"):
            with self.assertRaisesRegex(ValueError, "原始数据"):
                eclab.export_tables(self.data, cfg={"data_dir": [str(root)]}, out_dir=path)
        with self.assertRaisesRegex(ValueError, "原始数据"):
            eclab.export_tables(self.data, cfg={"protected_data_dirs": [str(root)]},
                                out_dir=root / "other")
        self.assertEqual(list(root.iterdir()), [])

    def test_reexport_preserves_previous_workbook(self):
        first = Path(eclab.export_tables(self.data, out_dir=self.folder))
        original = first.read_bytes()
        second = Path(eclab.export_tables(self.data, out_dir=self.folder))
        self.assertNotEqual(first, second)
        self.assertTrue(second.is_file())
        self.assertEqual(first.read_bytes(), original)

    def test_failed_workbook_write_leaves_no_partial_workbook(self):
        with patch.object(pd.DataFrame, "to_excel", side_effect=RuntimeError("disk failure")):
            with self.assertRaises(Exception):
                eclab.export_tables(self.data, out_dir=self.folder)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_engine_figures_are_agg_and_not_pyplot_windows(self):
        with patch.object(eclab.plt, "subplots", side_effect=AssertionError("Qt pyplot window")):
            figure = eclab.plot_cv_overlay(self.data["cv"], eclab.DEFAULT_STYLE)
        self.assertIsInstance(figure.canvas, eclab.FigureCanvasAgg)

    def test_render_exports_and_returns_real_workbook_path(self):
        data = {**self.data, "cv": [], "gcd": [], "cv_tables": [], "gcd_tables": []}
        with redirect_stdout(io.StringIO()):
            output = eclab.render(data, formats=["png"], dpi=72, out_dir=self.folder)
        self.assertTrue(Path(output).is_file())
        self.assertEqual(len(list(self.folder.glob("*.png"))), 1)

    def test_invalid_mass_is_skipped_instead_of_becoming_a_result(self):
        for value in (0, -1, np.nan, np.inf, "bad"):
            with self.subTest(mass=value), redirect_stdout(io.StringIO()):
                self.assertIsNone(eclab.get_mass({"mass_mg": {"sample": value}},
                                               ["sample"], "sample.txt"))

    def test_invalid_area_is_reported_before_cv_calculation(self):
        for value in (0, -1, np.nan, np.inf, "bad"):
            with self.subTest(area=value), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "面积.*有限正数"):
                    eclab.prepare({**self.cfg, "area_cm2": value})

    def test_invalid_scan_rate_is_skipped(self):
        source = Path(make_mock.SAMPLE_DIR) / "CV" / "cv-2mVs.txt"
        meta, voltage, current = eclab.parse_cv(source)
        for value in (0, -1, np.nan, np.inf):
            with self.subTest(scan_rate=value), redirect_stdout(io.StringIO()):
                with patch.object(eclab, "parse_cv", return_value=(
                        {**meta, "scan_rate_Vs": value}, voltage, current)):
                    result = eclab.prepare({**self.cfg, "include_files": [str(source)]})
                self.assertEqual(result["cv"], [])
                self.assertEqual(result["cv_tables"], [])

    def test_invalid_current_and_voltage_window_are_rejected(self):
        times = np.array([0, 1, 2], dtype=float)
        charge = np.array([0, 0.5, 1])
        discharge = np.array([1, 0.5, 0])
        for current in (0, np.nan, np.inf):
            with self.subTest(current=current):
                self.assertIsNone(eclab.gcd_metrics(times, charge, times,
                                                   discharge, current, 0.001))
        for ir_free in (False, True):
            self.assertIsNone(eclab.gcd_metrics(times, charge, times,
                                               np.ones(3), 0.001, 0.001,
                                               use_ir_free=ir_free))
        self.assertIsNone(eclab.gcd_metrics(times, charge, times,
                                           np.array([1, 0.5, 0.8]), 0.001, 0.001,
                                           use_ir_free=True))

    def test_numeric_sample_name_cannot_change_current_density(self):
        source = self.folder / "source"
        source.mkdir()
        content = (Path(make_mock.SAMPLE_DIR) / "GCD" / "gcd-1Ag.txt").read_bytes()
        for name in ("2026-sample.txt", "99Ag.txt"):
            (source / name).write_bytes(content)
        cfg = {"data_dir": [str(source)], "mass_mg": {"2026-sample": 1, "99Ag": 1},
               "process": {"cycle": False}}
        with redirect_stdout(io.StringIO()):
            result = eclab.prepare(cfg)
        self.assertEqual(len(result["gcd"]), 2)
        self.assertTrue(all(r["current_density_A_g"] == 1 for r in result["gcd"]))
        self.assertTrue(any("文件名标注 99 A/g" in note for note in result["anomalies"]))

    @unittest.skipUnless(os.name == "nt", "Windows experimental archive guard")
    def test_entire_experimental_archive_is_read_only_even_for_cli(self):
        with self.assertRaisesRegex(ValueError, "原始数据"):
            ec_export.validate_output_dir("E:/Data/new-results")


if __name__ == "__main__":
    unittest.main(verbosity=2)
