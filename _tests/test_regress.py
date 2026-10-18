# -*- coding: utf-8 -*-
"""回归测试：确认坐标轴锁定那批修复没被配色改动破坏"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from PySide6.QtWidgets import QApplication, QPushButton
import ec_gui as G
import eclab

app = QApplication.instance() or QApplication([])

E = np.linspace(-0.88, 0.4, 300)
data = {
    "cv": [{"label": "样品%d" % (i + 1), "E": E,
            "j": np.sin(E * 6) * (5 - i),
            "scan_rate_mVs": [5, 10, 20][i],
            "C_F_g": [120.0, 210.0, 300.0][i]} for i in range(3)],
    "gcd": [], "eis": [], "cycles": {},
}
cfg = {"plot_style": {}, "dedupe_condition": True,
       "output": {"formats": ["png"], "dpi": 600, "dir": eclab.OUTPUT_DIR}}

dlg = G.PreviewDialog(None, data, cfg)
dlg.show()
app.processEvents()
print("工具条 =", [b.text() for b in dlg.bar.findChildren(QPushButton)])
assert dlg.bar.nav is not None, "工具条还没挂上画布"
# 官方工具条只当"发动机"，按钮必须全清空（那个齿轮就是 μ 界面）
assert len(dlg.bar.nav.actions()) == 0, "官方齿轮按钮不该出现"
assert dlg.bar.nav.isVisible() is False, "官方工具条不该露出来"
print("官方齿轮按钮数 = 0 且不可见 OK")


def rng():
    ax = dlg.bar.canvas.figure.axes[0]
    return (round(float(ax.get_xlim()[0]), 3), round(float(ax.get_xlim()[1]), 3),
            round(float(ax.get_ylim()[0]), 3), round(float(ax.get_ylim()[1]), 3))


def redraw():
    """样式改动是"延迟重画"的（省内存、不卡），所以要主动点重新绘制"""
    dlg._redraw()
    app.processEvents()


dlg._take_limits(-0.5, 0.1, -8, 8)
redraw()
base = rng()
assert base[0] == -0.5 and base[1] == 0.1, base
print("填范围 =", base)

# 改配色（这次走新配色库路径）
dlg.panel.ed_colors.setText("#FF0000, #0000FF, #00AA00")
redraw()
assert rng() == base, f"改配色后范围被弹回: {rng()}"
print("改配色后 =", rng(), " <- 没被弹回 OK")

# 换色块按钮的颜色也一样不动范围
dlg.panel.cb_facecol.set_color("#A63E76")
redraw()
assert rng() == base
print("改色块按钮颜色后 =", rng(), " <- 没被弹回 OK")

dlg.panel.c_f_label.setCurrentText("20")
redraw()
assert rng() == base
print("改字号后 =", rng(), " <- 没被弹回 OK")

dlg._step(1)
app.processEvents()
dlg._step(-1)
app.processEvents()
assert rng() == base, "切回来范围变了"
print("切图往返后 =", rng(), " <- 保持 OK")

dlg.bar._zoom_out()
app.processEvents()
assert rng()[1] > base[1], "缩小无效"
print("缩小一半 OK")
dlg.bar._reset_view()
app.processEvents()
assert rng() == base, "还原无效"
print("还原 OK")

# 配色真能落到图上
st = eclab.get_style(dlg.final_cfg(), "cv_overlay")
fig = eclab.plot_cv_overlay(data["cv"], st)
line_cols = [ln.get_color() for ln in fig.axes[0].lines]
print("图上曲线颜色 =", line_cols)
assert line_cols[:3] == ["#FF0000", "#0000FF", "#00AA00"], line_cols
ax = fig.axes[0]
print("导出范围 =", (round(float(ax.get_xlim()[0]), 3),
                    round(float(ax.get_xlim()[1]), 3),
                    round(float(ax.get_ylim()[0]), 3),
                    round(float(ax.get_ylim()[1]), 3)))
assert (float(ax.get_xlim()[0]), float(ax.get_xlim()[1])) == (-0.5, 0.1)
print("配色与范围一起进最终图 OK")

print("\n回归测试通过")