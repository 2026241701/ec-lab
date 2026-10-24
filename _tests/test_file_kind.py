"""Classification of processing-workspace files into CV / GCD / EIS / CDI."""
import os
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from ec_file_kind import KINDS, KIND_PRIORITY, classify, classify_paths


class FileKindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_txt_kinds_are_detected(self):
        cv = self.write("cv.txt", "Cyclic Voltammetry\nSegment = 4\nPotential/V, Current/A\n-0.8, 0.001\n")
        gcd = self.write("gcd.txt", "Chronopotentiometry\nTime/sec, Potential/V\n0, 0.1\n")
        eis = self.write("eis.txt", "A.C. Impedance\nFreq/Hz, Z'\n1, 2\n")
        self.assertEqual(classify(cv), "CV")
        self.assertEqual(classify(gcd), "GCD")
        self.assertEqual(classify(eis), "EIS")

    def test_cdi_csv_tsv_and_xlsx_are_detected(self):
        csv = self.write("c.csv", "time_s,conductivity_uS_cm\n0,100\n5,99\n")
        tsv = self.write("c.tsv", "测量时间\t检测结果\n00:00:00\t100\n")
        self.assertEqual(classify(csv), "CDI")
        self.assertEqual(classify(tsv), "CDI")

        from openpyxl import Workbook
        xlsx = self.root / "c.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.append(["测量时间", "检测结果"])
        sheet.append(["2026-01-01 00:00:00", 100])
        book.save(xlsx)
        book.close()
        self.assertEqual(classify(xlsx), "CDI")

    def test_unrecognised_and_priority(self):
        self.assertIsNone(classify(self.write("note.txt", "只是说明，不是数据\n")))
        self.assertEqual(list(KINDS), ["CV", "GCD", "EIS", "CDI"])
        self.assertEqual(KIND_PRIORITY, {"CV": 0, "GCD": 1, "EIS": 2, "CDI": 3})
        self.assertEqual(classify_paths([]), [])


if __name__ == "__main__":
    unittest.main()
