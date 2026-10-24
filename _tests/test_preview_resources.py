# -*- coding: utf-8 -*-
"""Real offscreen PreviewDialog lifecycle test, isolated from user settings."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
from matplotlib.image import imread
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, qInstallMessageHandler
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import isValid

import ec_gui
import eclab
import make_mock


class PreviewResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.cfg = make_mock.sample_cfg({
            "eis": {"fit": False, "use_external_fit": False},
            "process": {"CV": True, "GCD": True, "EIS": True, "cycle": False},
            "output": {"formats": ["png"], "dpi": 72},
        })
        with redirect_stdout(io.StringIO()):
            cls.data = eclab.prepare(cls.cfg)

    def pump(self):
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def assert_current_canvas(self, dialog):
        self.assertIn(dialog.idx, dialog._cache, dialog.lab_hint.text())
        figure, canvas = dialog._cache[dialog.idx]
        self.assertIs(dialog.fig, figure)
        self.assertIs(dialog.canvas_box.canvas, canvas)
        self.assertTrue(isValid(canvas))
        self.assertLessEqual(len(dialog._cache), 3)
        canvas.draw()
        self.assertTrue(canvas.isVisible(), "cached canvas must be shown again")
        self.assertGreaterEqual(dialog.canvas_box.holder.width(), canvas.width())
        self.assertGreaterEqual(dialog.canvas_box.holder.height(), canvas.height())

    def test_scaled_canvas_is_visible_without_changing_export_size(self):
        dialog = ec_gui.PreviewDialog(None, self.data, self.cfg)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        self.pump()
        figure, canvas = dialog._cache[dialog.idx]
        inches = figure.get_size_inches().copy()
        for size in ((400, 311), (1100, 855)):
            canvas.setFixedSize(*size)
            dialog.canvas_box.holder.setFixedSize(*size)
            self.pump()
            snapshot = canvas.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
            pixels = np.frombuffer(snapshot.bits(), dtype=np.uint8).reshape(
                snapshot.height(), snapshot.bytesPerLine() // 4, 4)
            rgb = pixels[:, :snapshot.width(), :3]
            # Both halves must contain the plotted axes/curves. An unscaled
            # QtAgg blit left the bottom/right of a large preview empty.
            h, w = rgb.shape[:2]
            self.assertGreater(float(rgb[h//2:, w//2:].std()), 10)
            np.testing.assert_allclose(figure.get_size_inches(), inches)
            np.testing.assert_allclose(
                canvas.mouseEventCoords(QPointF(canvas.width()/2, canvas.height()/2)),
                [figure.bbox.width/2, figure.bbox.height/2])
        self.assertGreater(dialog.canvas_box.holder.width(), 0)
        dialog.close()
        self.pump()

    def test_preview_switch_redraw_export_and_close(self):
        errors, qt_messages = [], []
        previous_handler = qInstallMessageHandler(lambda _kind, _context, text: qt_messages.append(text))
        self.addCleanup(lambda: qInstallMessageHandler(previous_handler))
        temporary = tempfile.TemporaryDirectory(prefix="_preview_test_", dir=ROOT)
        self.addCleanup(temporary.cleanup)
        cfg = {**self.cfg, "output": {"formats": ["png"], "dpi": 72, "dir": temporary.name}}

        with patch.object(ec_gui.cfg_guard, "save_config", side_effect=AssertionError("user config must not be written")), \
                patch.object(sys, "excepthook", side_effect=lambda *args: errors.append("".join(traceback.format_exception(*args)))):
            dialog = ec_gui.PreviewDialog(None, self.data, cfg)
            self.addCleanup(lambda: dialog.deleteLater() if isValid(dialog) else None)
            dialog.show()
            self.pump()
            self.assertGreater(len(dialog.items), 3)
            self.assert_current_canvas(dialog)

            # Force deferred deletion during forward/backward navigation so a
            # stale C++ canvas reference cannot pass merely by staying alive.
            for index in list(range(len(dialog.items))) + list(reversed(range(len(dialog.items)))):
                dialog.cb_fig.setCurrentIndex(index)
                self.pump()
                self.assert_current_canvas(dialog)
            dialog._step(1)
            self.pump()
            self.assert_current_canvas(dialog)
            dialog._step(-1)
            self.pump()
            self.assert_current_canvas(dialog)

            cv_index = next(i for i, (key, _) in enumerate(dialog.items) if key == "CV_overlay")
            dialog.cb_fig.setCurrentIndex(cv_index)
            self.pump()
            old_canvas = dialog.canvas_box.canvas
            dialog.panel.c_lw.setCurrentText("2.7")
            QTest.qWait(130)
            self.assertTrue(dialog._dirty)
            dialog._redraw()
            self.pump()
            self.assertFalse(dialog._dirty, dialog.lab_hint.text())
            self.assertNotIn(cv_index, dialog._stale)
            self.assert_current_canvas(dialog)
            self.assertFalse(isValid(old_canvas), "redraw should release the replaced canvas")
            self.assertAlmostEqual(dialog.fig.axes[0].lines[0].get_linewidth(), 2.7)
            np.testing.assert_allclose(dialog.fig.axes[0].lines[0].get_xdata(), self.data["cv"][0]["E"])

            # Saving a dirty preview must redraw it first, not save old styling.
            dialog.panel.c_lw.setCurrentText("3.1")
            with patch.object(QMessageBox, "information", return_value=QMessageBox.Ok), \
                    patch.object(QMessageBox, "warning", side_effect=AssertionError("unexpected save warning")):
                dialog._save_current()
            self.pump()
            self.assert_current_canvas(dialog)
            exported_linewidth = dialog.fig.axes[0].lines[0].get_linewidth()
            pngs = list(Path(temporary.name).glob("CV_overlay*.png"))
            self.assertEqual(len(pngs), 1)
            pixels = imread(pngs[0])
            self.assertGreater(pixels.shape[0], 200)
            self.assertGreater(pixels.shape[1], 200)
            self.assertGreater(float(np.std(pixels[..., :3])), 0.02)

            self.assertTrue(dialog.close())
            self.pump()
            self.assertEqual(dialog._cache, {})
            self.assertIsNone(dialog.fig)
            dialog.deleteLater()
            self.pump()

        self.assertEqual(errors, [], "\n".join(errors))
        bad_messages = [message for message in qt_messages
                        if any(word in message.lower() for word in (
                            "already deleted", "destroyed while", "qpainter::", "qobject::"))]
        self.assertEqual(bad_messages, [], "\n".join(bad_messages))
        self.assertAlmostEqual(exported_linewidth, 3.1,
                               msg="rapid save exported the previous line style")


if __name__ == "__main__":
    unittest.main(verbosity=2)
