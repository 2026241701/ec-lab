# -*- coding: utf-8 -*-
"""Appearance, legacy recipe compatibility and export identity on synthetic data."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image
import ec_plotting as plot

TEST_ROOT = ROOT / "output" / "_test_tmp"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class PlotStyleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "cycling.csv"
        self.source.write_text("x,y,z\n3,1,4\n1,-2,5\n,,\n2,3,6\n", encoding="utf-8")
        self.book = plot.load_table_book(str(self.source))
        self.spec = plot.generic_plot("cycling", "x", ["y", "z"], xlabel="Potential", ylabel="Current")

    def test_validation_is_sparse_pure_and_rejects_non_style_or_unsafe_values(self):
        original = {"xlim": [-1, 4], "series_labels": ["first", ""],
                    "series_colors": ["red", ""], "palette": ["#112233"]}
        snapshot = copy.deepcopy(original)
        clean = plot.validate_plot_style(original)
        self.assertEqual(set(clean), set(original))
        self.assertEqual(clean["series_colors"], ["#ff0000", ""])
        clean["xlim"][0] = -99
        clean["series_labels"][0] = "different"
        self.assertEqual(original, snapshot)
        invalid = [None, [], {"source": "measurement.xlsx"}, {"x": "Potential"},
                   {"xlim": [2, 1]}, {"ylim": [1, 1]}, {"xlim": [0, float("inf")]},
                   {"ylim": [False, 4]}, {"ylim": [0]}, {"dpi": 99.5}, {"dpi": "300"},
                   {"width_cm": 0}, {"linewidth": float("nan")}, {"axis_font_size": True},
                   {"tick_font_size": complex(1, 2)}, {"xlim": [0, 10**400]}, {"legend_visible": "false"},
                   {"legend_location": "outside"}, {"font_family": ""},
                   {"series_labels": ["bad\nlabel"]}, {"series_colors": ["not-a-color"]},
                   {"palette": []}, {"palette": ["C0"]},
                   {"width_cm": 60, "height_cm": 60, "dpi": 1200}]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plot.validate_plot_style(value)

    def test_preset_defaults_and_styles_are_independent(self):
        self.assertEqual(self.spec.style, {})
        other = plot.PlotSpec("other", [])
        self.spec.style["dpi"] = 300
        self.assertEqual(other.style, {})
        style = plot.resolve_plot_style({}, "paper")
        self.assertEqual(style["dpi"], 600)
        self.assertEqual(style["axis_font_size"], 11)
        self.assertIsNone(style["legend_visible"])
        np.testing.assert_allclose([style["width_cm"] / 2.54, style["height_cm"] / 2.54], [6.4, 4.5])
        self.assertEqual(plot.resolve_plot_style({}, "mono")["palette"], ["#222222"])
        self.assertEqual(plot.resolve_plot_style({}, "talk")["axis_font_size"], 14)
        style["palette"][0] = "#ffffff"
        self.assertEqual(plot.resolve_plot_style({})["palette"][0], plot.COLORS[0].lower())

    def test_style_template_roundtrip_unknown_versions_and_source_rejection(self):
        path = self.root / "style.json"
        style = plot.resolve_plot_style({"palette": ["navy", "orange"], "dpi": 300})
        self.assertEqual(plot.save_style_template(path, style), str(path.resolve()))
        self.assertEqual(plot.load_style_template(path), style)
        saved = path.read_bytes()
        with patch.object(plot.os, "replace", side_effect=OSError("cannot replace")):
            with self.assertRaisesRegex(OSError, "cannot replace"):
                plot.save_style_template(path, {"dpi": 200})
        self.assertEqual(path.read_bytes(), saved)
        self.assertEqual(list(self.root.glob(".plot-style-*.tmp")), [])
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"schema", "version", "style"})
        self.assertNotIn(str(self.source), path.read_text(encoding="utf-8"))
        payload["version"] = 999
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "版本"):
            plot.load_style_template(path)
        payload["version"] = 1
        payload["style"]["source_path"] = str(self.source)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不能保存数据路径"):
            plot.load_style_template(path)
        with self.assertRaisesRegex(ValueError, "json"):
            plot.save_style_template(self.root / "input.xlsx", {})
        self.assertFalse((self.root / "input.xlsx").exists())
        blocked = self.root / "blocked" / "style.json"
        with patch("ec_export.validate_output_dir", side_effect=ValueError("read only")):
            with self.assertRaisesRegex(ValueError, "read only"):
                plot.save_style_template(blocked, {})
        self.assertFalse(blocked.parent.exists())

    def test_draw_applies_ranges_fonts_labels_colors_without_changing_samples(self):
        before = self.book.tables["cycling"].copy(deep=True)
        self.spec.style = {"xlim": [0, 5], "ylim": [-4, 8], "legend_visible": True,
                           "legend_location": "upper left", "series_labels": ["_sample", ""],
                           "series_colors": ["", "#ff0000"], "palette": ["#00aa44"],
                           "font_family": "DejaVu Sans", "axis_font_size": 15,
                           "tick_font_size": 12, "legend_font_size": 9,
                           "width_cm": 10.16, "height_cm": 7.62, "linewidth": 2.5, "dpi": 300}
        figure = plot.draw_plot(self.book, self.spec, dpi=100)
        self.addCleanup(figure.clear)
        axes = figure.axes[0]
        np.testing.assert_allclose(figure.get_size_inches(), [4, 3])
        self.assertEqual(figure.dpi, 100)
        np.testing.assert_allclose(axes.get_xlim(), [0, 5])
        np.testing.assert_allclose(axes.get_ylim(), [-4, 8])
        np.testing.assert_array_equal(axes.lines[0].get_xdata(), [3, 1, np.nan, 2])
        np.testing.assert_array_equal(axes.lines[0].get_ydata(), [1, -2, np.nan, 3])
        self.assertEqual([line.get_color() for line in axes.lines], ["#00aa44", "#ff0000"])
        self.assertEqual(axes.lines[0].get_linewidth(), 2.5)
        self.assertEqual([text.get_text() for text in axes.get_legend().get_texts()], ["_sample", "z"])
        self.assertEqual(axes.xaxis.label.get_fontsize(), 15)
        self.assertEqual(axes.get_xticklabels()[0].get_fontsize(), 12)
        self.assertEqual(axes.get_legend().get_texts()[0].get_fontsize(), 9)
        self.assertEqual(axes.xaxis.label.get_fontfamily()[0], "DejaVu Sans")
        self.assertTrue(before.equals(self.book.tables["cycling"]))

    def test_explicit_legend_overrides_automatic_and_keeps_mixed_artist_order(self):
        many = plot.PlotSpec("many", [plot.ColumnSeries("cycling", "x", "y", label=str(i)) for i in range(21)])
        auto = plot.draw_plot(self.book, many)
        self.assertIsNone(auto.axes[0].get_legend())
        auto.clear()
        many.style = {"legend_visible": True}
        visible = plot.draw_plot(self.book, many)
        self.assertEqual(len(visible.axes[0].get_legend().get_texts()), 21)
        visible.clear()
        self.spec.series[0].mode = "scatter"
        self.spec.style = {"legend_visible": False}
        hidden = plot.draw_plot(self.book, self.spec)
        self.assertIsNone(hidden.axes[0].get_legend())
        hidden.clear()
        self.spec.style = {"series_labels": ["scatter", "line"]}
        mixed = plot.draw_plot(self.book, self.spec)
        self.assertEqual([t.get_text() for t in mixed.axes[0].get_legend().get_texts()], ["scatter", "line"])
        mixed.clear()

    def test_export_custom_dpi_final_style_and_recipe_reproduce_the_same_image(self):
        original_hash = plot._hash(self.source)
        self.spec.style = {"width_cm": 10.16, "height_cm": 7.62, "dpi": 100,
                           "series_labels": ["A", "B"], "series_colors": ["red", "blue"],
                           "xlim": [0, 5], "legend_location": "lower right", "axis_font_size": 10}
        initial_style = copy.deepcopy(self.spec.style)
        with patch.object(plot, "BASE_DIR", self.root):
            output = Path(plot.export_plots(self.book, [self.spec], formats=("png", "svg")))
            book, specs, preset = plot.load_recipe(output / "绘图配方.json")
            replay = Path(plot.export_plots(book, specs, preset, formats=("png",)))
        with Image.open(next(output.glob("*.png"))) as first, Image.open(next(replay.glob("*.png"))) as second:
            self.assertEqual(first.size, (400, 300))
            np.testing.assert_array_equal(np.asarray(first), np.asarray(second))
        self.assertEqual(specs[0].style, plot.resolve_plot_style(initial_style))
        self.assertEqual(self.spec.style, initial_style)
        self.assertEqual(plot._hash(self.source), original_hash)
        payload = json.loads((output / "绘图配方.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["dpi"], 100)
        self.assertEqual(payload["plots"][0]["spec"]["style"]["dpi"], 100)

    def test_old_v1_recipe_without_style_retains_preset(self):
        from dataclasses import asdict
        values = asdict(self.spec)
        del values["style"]
        payload = {"schema": "ec-lab-plot-recipe", "version": 1,
                   "source": {"path": str(self.source), "sha256": self.book.sha256},
                   "preset": "mono", "preset_values": plot.PRESETS["mono"],
                   "plots": [{"spec": values, "files": []}]}
        path = self.root / "legacy-recipe.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        book, specs, preset = plot.load_recipe(path)
        self.assertEqual(specs[0].style, {})
        figure = plot.draw_plot(book, specs[0], preset)
        self.addCleanup(figure.clear)
        self.assertEqual(figure.axes[0].lines[0].get_color(), "#222222")
        self.assertEqual(figure.axes[0].lines[1].get_linestyle(), "--")
        payload["plots"][0]["spec"]["style"] = {"ylim": [2, 1]}
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "最小值"):
            plot.load_recipe(path)

    def test_invalid_styles_reject_before_output_is_created(self):
        self.spec.style = {"xlim": [2, 1]}
        with patch.object(plot, "BASE_DIR", self.root):
            with self.assertRaisesRegex(ValueError, "最小值"):
                plot.export_plots(self.book, [self.spec], formats=("png",))
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
