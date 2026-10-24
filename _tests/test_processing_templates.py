"""Processing recipes remain portable parameter data, never file actions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ec_processing_templates import (DEFAULTS, MAX_TEMPLATE_BYTES, load_template,
                                     make_template, save_template, validate_template)


ROOT = Path(__file__).resolve().parents[1]


class ProcessingTemplateTests(unittest.TestCase):
    def test_all_modes_round_trip_with_parameters_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            for mode, parameters in DEFAULTS.items():
                with self.subTest(mode=mode):
                    path = Path(directory) / (mode + ".json")
                    result = save_template(path, mode, parameters)
                    self.assertEqual(load_template(path), result)
                    self.assertEqual(set(json.loads(path.read_text(encoding="utf-8"))),
                                     {"schema", "version", "mode", "parameters"})
                    self.assertEqual(set(result["parameters"]), set(parameters))

    def test_unknown_path_fields_and_bad_versions_are_rejected(self):
        original = make_template("cdi", {})
        for name, value in (("paths", ["E:/Data/source.xlsx"]),
                            ("output_dir", "E:/Data"), ("cdi_template", "E:/Data/example.xlsx"),
                            ("script", "__import__('os')")):
            bad = copy.deepcopy(original)
            bad["parameters"][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_template(bad)
        for field, value in (("version", 2), ("version", True), ("schema", "unknown"),
                             ("mode", "shell"), ("mode", ["cdi"])):
            bad = {**original, field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_template(bad)
        with self.assertRaises(ValueError):
            validate_template({**original, "files": []})

    def test_numeric_enumeration_and_cycle_boundaries(self):
        for name, value in (("mass_mg", -1), ("mass_mg", True), ("volume_ml", 0),
                            ("calibration_base", float("nan")), ("calibration_scale", float("inf")),
                            ("cdi_step", "10"), ("conductivity_unit", "unknown"),
                            ("cdi_tail", ["include"])):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                make_template("cdi", {name: value})
        with self.assertRaisesRegex(ValueError, "整除"):
            make_template("cdi", {"cdi_step": 7})
        self.assertEqual(make_template("cdi", {"cdi_step": 10})["parameters"]["cdi_step"], 10)
        self.assertEqual(make_template("cdi", {"mass_mg": 0})["parameters"]["mass_mg"], 0)

    def test_malformed_large_and_readonly_data_destinations(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON"):
                load_template(path)
            path.write_text("x" * (MAX_TEMPLATE_BYTES + 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "64 KB"):
                load_template(path)
        with patch.object(Path, "write_text") as write:
            with self.assertRaisesRegex(ValueError, "只读"):
                save_template("E:/Data/never-write-template.json", "cdi", {})
            write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
