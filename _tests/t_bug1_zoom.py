# -*- coding: utf-8 -*-
"""回归测试：Bug 1 预览缩放/改窗口大小不应改变真实画布尺寸

现象：出图预览里调整框大小（缩放档位 / 适应窗口 / 拖窗口），
用户期望"只是显示压缩"，图形本身的真实英寸尺寸不变；
但旧实现会在 relayout 里调 figure.set_size_inches，且 matplotlib 的
FigureCanvasQT.resizeEvent 在 canvas 控件尺寸变化时也会自动改 figure 尺寸，
导致预览缩放把导出图的真实大小带偏。

修复：比例画布框 用 固定画布 子类覆盖 resizeEvent（只让 Qt 缩放、不回写
figure 尺寸）；relayout 只定 canvas 显示大小，绝不调 set_size_inches。

本测试断言：无论怎么切换缩放档位 / 拉伸 preview 框，
每张图缓存里的 figure 的 get_figwidth/get_figheight 始终恒定。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

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
    data = eclab.prepare(cfg0)
    dlg = ec_gui.PreviewDialog(None, data, cfg0)
    dlg._warm_cache()

    # 记录每张图初始真实尺寸（英寸）
    base = {}
    for i, (fig, _c) in dlg._cache.items():
        base[i] = (fig.get_figwidth(), fig.get_figheight())

    cb = dlg.canvas_box

    # 1) 遍历所有缩放档位
    for mode in range(4):
        cb.set_mode(mode)
        app.processEvents()

    # 2) 模拟拉伸 preview 框（触发 resizeEvent → 旧实现会改 figure）
    for w, h in [(1200, 700), (500, 300), (900, 560), (1500, 950)]:
        cb.resize(w, h)
        app.processEvents()

    # 3) 切几张图再回来，确认尺寸仍恒定
    for i in list(dlg._cache.keys()):
        try:
            dlg.cb_fig.setCurrentIndex(i)
        except Exception:
            pass
        app.processEvents()

    # 断言：所有 figure 真实尺寸未变
    bad = []
    for i, (fig, _c) in dlg._cache.items():
        cur = (fig.get_figwidth(), fig.get_figheight())
        if abs(cur[0] - base[i][0]) > 1e-6 or abs(cur[1] - base[i][1]) > 1e-6:
            bad.append((i, dlg.items[i][0], base[i], cur))

    if bad:
        print("❌ 检测到 figure 真实尺寸被预览缩放改变：")
        for i, k, b, c in bad:
            print(f"   idx={i} {k}: 初始 {b} -> 变成 {c}")
        return 1
    print("✅ Bug1 不变量成立：所有 figure 真实尺寸在缩放/拉伸预览框后保持恒定")
    return 0


r = run()
sys.exit(r)
