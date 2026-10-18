# -*- coding: utf-8 -*-
"""回归测试：Bug 5 切图崩溃（白盒不变量校验）

现象（错误日志.txt）：查看/修改 GCD 比电容图后切回 CV 等图，报
  "RuntimeError: FigureCanvasQTAgg already deleted" 卡死。

根因：PreviewDialog._cache 缓存的是 (fig, canvas) 对象，而
比例画布框.set_canvas 在挂新画布前对"上一个挂着的 canvas"调 deleteLater。
那个 canvas 往往是另一张图的缓存项；在真实窗口里事件循环一泵，C++ 对象
就被销毁，而缓存还指着它，下次切回复用 → 崩。

注意：offscreen 平台下 deleteLater 不会真正销毁 C++ 对象，对已销毁 canvas
调方法也不抛异常，所以「机械复现崩溃」在测试环境做不到（旧测试因此误报通过）。
这里改为校验根因不变量：

    【不变量】任何时刻，_cache 里仍然缓存的 canvas，绝不曾被 deleteLater 过。

旧代码会在 set_canvas 里 deleteLater 一个仍在缓存中的 canvas → 违反不变量
→ 测试失败。修复后 set_canvas 只摘布局、不销毁缓存 canvas，_redraw 替换缓存
项时才显式 deleteLater 旧 canvas（且 cache[idx] 已指向新 canvas）→ 不变量成立。
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
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

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


def install_tracker():
    """记录所有被 deleteLater 的 FigureCanvas（真实平台下它会被销毁）"""
    deleted = set()
    import PySide6.QtWidgets as QW
    orig = QW.QWidget.deleteLater

    def tracked(self):
        if isinstance(self, FigureCanvasQTAgg):
            deleted.add(id(self))
        orig(self)

    QW.QWidget.deleteLater = tracked
    return deleted


def indices(dlg):
    out = {}
    for i, (k, _n) in enumerate(dlg.items):
        out.setdefault(eclab.kind_of_key(k), i)
    return out


def run():
    deleted = install_tracker()
    app = QApplication.instance() or QApplication([])
    data = eclab.prepare(cfg0)
    dlg = ec_gui.PreviewDialog(None, data, cfg0)
    dlg._warm_cache()
    idx = indices(dlg)
    i_gcd = idx.get("gcd_cap")
    i_cv = idx.get("cv_cap")
    i_gcd_cd = idx.get("gcd_overlay")
    assert i_gcd is not None, "找不到 gcd_cap 预览项"

    plan = [i_gcd, "redraw", i_cv, i_gcd, i_cv, i_gcd]
    if i_gcd_cd is not None:
        plan += [i_gcd_cd, i_cv, i_gcd]

    for step, act in enumerate(plan):
        if act == "redraw":
            dlg._redraw()
        else:
            dlg.cb_fig.setCurrentIndex(act)
        app.processEvents()
        app.processEvents()

    # 【核心断言】缓存里仍活着的 canvas，绝不能是被 deleteLater 过的
    violations = []
    for i, (fig, canvas) in dlg._cache.items():
        if id(canvas) in deleted:
            violations.append((i, dlg.items[i][0]))

    # 反向校验：所有缓存 canvas 当前都还能 setSizePolicy（真实平台下僵尸会崩）
    bad = []
    for i, (fig, canvas) in dlg._cache.items():
        try:
            from PySide6.QtWidgets import QSizePolicy
            canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        except RuntimeError as e:
            bad.append((i, dlg.items[i][0], str(e)))

    if violations:
        print("❌ 不变量被破坏：以下缓存项的 canvas 曾被 deleteLater 过：")
        for i, k in violations:
            print(f"   idx={i} {k}")
        return 1
    if bad:
        print("❌ 以下缓存 canvas 已是僵尸（真实平台会崩）：")
        for i, k, e in bad:
            print(f"   idx={i} {k}: {e}")
        return 1
    print("✅ Bug5 不变量成立：_cache 中所有 canvas 均未被提前 deleteLater，"
          "切图不会复用僵尸 canvas")
    return 0


r = run()
sys.exit(r)
