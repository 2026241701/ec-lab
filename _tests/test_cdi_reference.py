"""CDI sample contracts: measured sampling, mass suggestions and cycle edges."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
from openpyxl import load_workbook

from ec_legacy import cdi_workbook, run_legacy, suggest_cdi_mass


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "cdi_reference_20261024"
REFERENCE_PAIRS = [
    (Path("E:/Data/CDI/电导率/FTO/FTO@C2/24mg/FTO@C2-前5圈.xlsx"), 24),
    (Path("E:/Data/CDI/电导率/FTO/FTO@C1/25mg-200mg/FTO@C1(25mg)-200mg.xlsx"), 25),
]


class CDIReferenceTests(unittest.TestCase):
    def setUp(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=OUTPUT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.outputs = self.root / "outputs"
        self.inputs.mkdir(); self.outputs.mkdir()

    def csv(self, times):
        source = self.inputs / "conductivity.csv"
        source.write_text("time_s,conductivity_uS_cm\n" + "\n".join(
            f"{t},{100-i}" for i, t in enumerate(times)), encoding="utf-8")
        return source

    def workbook(self, source, **options):
        result = cdi_workbook(source, self.outputs, options, progress=lambda _: None)
        wb = load_workbook(result, data_only=True)
        self.addCleanup(wb.close)
        return wb

    def test_auto_detects_measured_five_and_ten_second_sampling(self):
        for step in (5, 10):
            with self.subTest(step=step):
                wb = self.workbook(self.csv(range(0, 120, step)), ads_minutes=0.5, des_minutes=0.5)
                self.assertEqual(wb["电导率"].max_row, 60 // step + 1)
                self.assertEqual(wb["电导率"].max_column, 3)
                self.assertEqual(wb["原始数据"]["A3"].value, step)
                self.assertEqual(wb["电导率"]["A1"].font.name, "宋体")

    def test_endpoint_stays_raw_and_partial_cycle_is_not_discarded(self):
        source = self.csv(range(0, 125, 5))
        wb = self.workbook(source, ads_minutes=0.5, des_minutes=0.5)
        self.assertEqual(wb["原始数据"].max_row, 26)
        self.assertEqual(wb["原始数据"]["A26"].value, 120)
        self.assertEqual(wb["电导率"].max_column, 3)
        self.assertEqual(wb["吸附最大值"].max_column, 2)
        all_points = self.workbook(source, ads_minutes=0.5, des_minutes=0.5, cdi_tail="include")
        self.assertEqual(all_points["电导率"].max_column, 4)
        partial = self.workbook(self.csv(range(0, 130, 5)), ads_minutes=0.5, des_minutes=0.5)
        self.assertEqual(partial["电导率"].max_column, 4)
        self.assertEqual(partial["电导率"]["D3"].value, 75)
        self.assertIn(partial["吸附容量"]["D4"].value, (None, ""))
        complete = self.workbook(self.inputs / "conductivity.csv", ads_minutes=0.5, des_minutes=0.5, cdi_tail="complete")
        self.assertEqual(complete["电导率"].max_column, 3)
        self.assertEqual(complete["原始数据"].max_row, 27)

    def test_unequal_adsorption_and_desorption_durations_sum_to_total(self):
        # 吸附 40 min + 脱附 20 min = 总 60 min；5 s 步长 -> 每圈 12 点。
        # 计算只用总时长对称切圈；吸附容量仍对整圈所有点写公式（不改吸附段切分）。
        source = self.csv(range(0, 65, 5))  # 13 点，末点为整圈结束点
        wb = self.workbook(source, mass_mg=24, ads_minutes=2 / 3, des_minutes=1 / 3)
        self.assertEqual(wb["电导率"].max_row, 12 + 1)
        self.assertEqual(wb["电导率"].max_column, 2)
        self.assertIsNotNone(wb["吸附容量"]["B13"].value)   # 整圈最后一行仍计算吸附容量
        self.assertEqual(wb["原始数据"]["A2"].value, 0)
        self.assertEqual(wb["原始数据"]["A14"].value, 60)

    def test_missing_or_irregular_time_requires_explicit_resolution(self):
        with self.assertRaisesRegex(ValueError, "手动填写"):
            self.workbook(self.csv(["", "", ""]), ads_minutes=0.5, des_minutes=0.5)
        manual = self.workbook(self.inputs / "conductivity.csv", ads_minutes=0.5, des_minutes=0.5, cdi_step=10)
        self.assertEqual(manual["原始数据"]["A4"].value, 20)
        with self.assertRaisesRegex(ValueError, "时间间隔与设定不一致"):
            self.workbook(self.csv([0, 5, 10, 25, 30]), ads_minutes=0.5, des_minutes=0.5)
        with self.assertRaisesRegex(ValueError, "时间间隔与设定不一致"):
            self.workbook(self.csv([0, 5, 10, 15]), ads_minutes=0.5, des_minutes=0.5, cdi_step=10)

    def test_mass_is_only_an_explicit_unambiguous_suggestion(self):
        self.assertEqual(suggest_cdi_mass(REFERENCE_PAIRS[0][0])["mass_mg"], 24)
        self.assertEqual(suggest_cdi_mass(REFERENCE_PAIRS[1][0])["mass_mg"], 25)
        self.assertIsNone(suggest_cdi_mass("E:/experiment/25mg-200mg/sample.xlsx"))
        self.assertIsNone(suggest_cdi_mass("E:/experiment/24mg/sample-25mg-200mg.xlsx"))
        self.assertIsNone(suggest_cdi_mass("E:/experiment/sample(25mg)(26mg).xlsx"))
        source = self.csv(range(0, 60, 5))
        named = source.with_name("sample(25mg)-200mg.csv")
        source.rename(named)
        wb = self.workbook(named, mass_mg=23, ads_minutes=0.5, des_minutes=0.5)
        self.assertEqual(wb["原始数据"]["D1"].value, 23)

    def test_resolved_parameters_and_sources_are_recorded(self):
        source = self.csv(range(0, 125, 5))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        result = run_legacy("cdi", [source], self.outputs, {"ads_minutes": 0.5, "des_minutes": 0.5}, lambda _: None)
        manifest = json.loads((Path(result["folder"]) / "处理说明.json").read_text(encoding="utf-8"))
        actual = manifest["resolved_parameters"][0]
        self.assertEqual(actual["sampling_seconds"], 5)
        self.assertEqual(actual["cycles"], 2)
        self.assertEqual(actual["trailing_points_only_in_raw"], 1)
        self.assertEqual(manifest["sources"][0]["sha256"], digest)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

    @unittest.skipUnless(all(p.exists() and p.with_name(p.stem + "-处理.xlsx").exists()
                            for p, _ in REFERENCE_PAIRS), "Local user reference files unavailable")
    def test_two_real_references_match_every_measurement_and_formula(self):
        for source, mass in REFERENCE_PAIRS:
            with self.subTest(source=source.name):
                reference = source.with_name(source.stem + "-处理.xlsx")
                before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, reference)}
                result = cdi_workbook(source, self.outputs, {"mass_mg": mass}, lambda _: None)
                actual_formula = load_workbook(result)
                actual_value = load_workbook(result, data_only=True)
                reference_formula = load_workbook(reference)
                reference_value = load_workbook(reference, data_only=True)
                try:
                    self.assertEqual(actual_formula.sheetnames, reference_formula.sheetnames)
                    for sheet in reference_formula:
                        other = actual_formula[sheet.title]
                        self.assertEqual(sheet.max_row, other.max_row)
                        if sheet.title != "原始数据":
                            self.assertEqual(sheet.max_column, other.max_column)
                        for row in sheet.iter_rows(max_col=4 if sheet.title == "原始数据" else sheet.max_column):
                            for cell in row:
                                expected, actual = cell.value, other[cell.coordinate].value
                                # The only changed scientific formula is the known zero-time guard.
                                if sheet.title == "吸附速率" and cell.column > 1 and cell.row > 1:
                                    self.assertEqual(actual, f'=IF(A{cell.row}=0,"",{expected[1:]})')
                                else:
                                    self.assertEqual(actual, expected, sheet.title + "!" + cell.coordinate)
                                ev = reference_value[sheet.title][cell.coordinate].value
                                av = actual_value[sheet.title][cell.coordinate].value
                                if sheet.title == "吸附速率" and cell.row == 2 and cell.column > 1:
                                    self.assertEqual(ev, "#DIV/0!")
                                    self.assertIn(av, (None, ""))
                                elif isinstance(ev, (int, float)):
                                    self.assertTrue(math.isclose(ev, av, rel_tol=1e-12, abs_tol=1e-10),
                                                    f"{sheet.title}!{cell.coordinate}: {ev} != {av}")
                                else:
                                    self.assertEqual(av, ev)
                    self.assertFalse(any(c.data_type == "e" for ws in actual_value for row in ws for c in row))
                finally:
                    for book in (actual_formula, actual_value, reference_formula, reference_value):
                        book.close()
                self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})


if __name__ == "__main__":
    unittest.main()
