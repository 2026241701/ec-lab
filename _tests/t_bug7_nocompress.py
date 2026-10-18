# -*- coding: utf-8 -*-
"""回归测试：缩小不压缩 + 一键适应窗口（运行时打桩验证，不依赖离屏几何）

离屏平台下 QWidget 的 resize 不会改变真实几何，所以用"打桩 relayout 计数"
来锁定真正的修复逻辑：

根因：旧实现 比例画布框.resizeEvent 里调 self.relayout()，
每次窗口缩放都重算画布尺寸并 draw_idle，图一大就卡；且 setWidgetResizable(True)
永不出现滚动条，于是画布被压成小方块。

修复后：
1) 触发 resizeEvent 绝不能调 relayout —— 即窗口缩放不压缩画布、不卡；
2) 点「居中 / 适应窗口」按钮必须调 relayout —— 手动适应才重算尺寸。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

from PySide6.QtCore import QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication
import eclab
import ec_gui

ROOTDIR = os.path.join(ROOT, "_raw", "电化学数据结构")
cfg0 = {
    "data_dir": [ROOTDIR], "area_cm2": 1.0,
    "pick_segments": [2, 3],
    "mass_mg": {"1A": 1.0, "2A": 1.0, "5A": 1.0, "10A": 1.0, "20A": 1.0,
                "2": 1.0, "5": 1.0, "10": 1.0, "20": 1.0,
                "50": 1.0, "100": 1.0, "200": 1.0},
    "gcd_continuous": False, "dedupe_condition": False,
    "process": {"CV": True, "GCD": True, "EIS": True, "cycle": False},
}


def run():
    app = QApplication.instance() or QApplication([])
    dlg = ec_gui.PreviewDialog(None, eclab.prepare(cfg0), cfg0)
    dlg._warm_cache()
    dlg.show()
    app.processEvents()

    cb = dlg.canvas_box

    # 打桩 relayout，统计调用次数
    calls = {"n": 0}
    orig = cb.relayout

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)
    cb.relayout = spy

    # 1) 触发 resizeEvent：绝不能调用 relayout（否则会压缩/卡）
    calls["n"] = 0
    cb.resizeEvent(QResizeEvent(QSize(cb.width(), cb.height()),
                                QSize(cb.width(), cb.height())))
    app.processEvents()
    if calls["n"] != 0:
        print("❌ resizeEvent 仍调了 relayout（%d 次）—— 缩小会压缩/卡"
              % calls["n"])
        return 1
    print("✅ 触发 resizeEvent 不调 relayout（缩小窗口不再压缩/卡顿）")

    # 2) 点「居中 / 适应窗口」按钮：必须调 relayout
    calls["n"] = 0
    dlg._fit_window()
    app.processEvents()
    if calls["n"] < 1:
        print("❌ 「居中 / 适应窗口」按钮没触发 relayout")
        return 1
    print("✅ 「居中 / 适应窗口」按钮触发 relayout（手动适应才重算尺寸）")
    return 0


r = run()
sys.exit(r)
