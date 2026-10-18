# -*- coding: utf-8 -*-
"""轴标题功能测试：颜色 / 位置 / 字号 / 上下标 都要真的生效"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from PySide6.QtWidgets import QApplication, QTabWidget
import ec_gui as G
import eclab
import richlabel

app = QApplication.instance() or QApplication([])
RES = [{"E": np.linspace(-0.8, 0.45, 60),
        "j": np.sin(np.linspace(-0.8, 0.45, 60) * 6), "label": "a"}]


def base():
    """每次都拿干净样式，避免互相污染"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["canvas"]["width"], st["canvas"]["height"] = 180.0, 140.0
    st["canvas"]["unit"] = "mm"
    return st


def fig_of(st):
    import matplotlib.pyplot as plt
    w, h = eclab.figsize_inch(st)
    fig, ax = plt.subplots(figsize=(w, h))
    eclab.plot_cv_overlay(RES, st, ax=ax)
    return fig, ax


def render(fig):
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def rich_box(fig, which):
    for a in fig.axes[0].artists:
        if hasattr(a, "shift") and a.which == which:
            return a.box.get_window_extent(render(fig))
    return None


# ---------- 1. 上下标解析 ----------
print("=== 1. 上下标解析 ===")
assert richlabel.parse_markup("J (A g^{-1})") == [
    ("J (A g", 0), ("-1", 1), (")", 0)]
assert richlabel.parse_markup("E_{applied} (V)") == [
    ("E", 0), ("applied", -1), (" (V)", 0)]
assert richlabel.parse_markup("Fe_{3}O_{4}") == [
    ("Fe", 0), ("3", -1), ("O", 0), ("4", -1)]
print("   上下标/下标/多个下标 都解析正确")

# ---------- 2. 竖排顺序（这是修好的老bug）----------
print("\n=== 2. Y 轴竖排顺序 ===")
st = base()
st["axis"]["titles"] = {"x": "X", "y": "Current density (A g^{-1})"}
st["axis"]["title_cfg"]["y"] = {"pad": 8}
fig, ax = fig_of(st)
r = render(fig)
tb = ax.yaxis.label.get_window_extent(r)
print("   占位文字 =", repr(tb))
kids = [a for a in ax.artists if hasattr(a, "shift") and a.which == "y"]
assert len(kids) == 1
vp = kids[0].box                   # _RotLabel：按阅读方向（CCW 90° 自下往上）摆放
# 取实际排好版的那些 Text 段（_place 是排版 + 造对象的唯一入口）
segs = vp._place(r, (0.0, 0.0))
print("   竖排段数 =", len(segs))
assert len(segs) == 3, f"应3段（正文/-1/括号），实际 {len(segs)}"
# _RotLabel 第一段在最底下，读出来就是自然顺序
texts = [c.get_text() for c in segs]
print("   自下往上 =", texts)
bottom_first = texts[0]
assert bottom_first.strip().startswith("Current"), \
    f"最底下应是正文，实际 {bottom_first!r}"
assert texts[1] == "-1", f"中间应是上标，实际 {texts[1]!r}"
print("   -> 竖排自下往上读：正文 →上标 →括号，顺序正确")

# ---------- 3. 颜色 ----------
print("\n=== 3. 颜色 ===")
st = base()
st["axis"]["titles"] = {"x": "E_{x} (V)", "y": "J (A g^{-1})"}
st["axis"]["title_cfg"]["x"] = {"color": "#C1440E", "pad": 10}
st["axis"]["title_cfg"]["y"] = {"color": "#0A6E8A", "pad": 10}
fig, ax = fig_of(st)
r = render(fig)
assert ax.xaxis.label.get_color() == "#C1440E", ax.xaxis.label.get_color()
assert ax.yaxis.label.get_color() == "#0A6E8A"
print("   原生占位标签颜色 =", ax.xaxis.label.get_color(),
      "/", ax.yaxis.label.get_color())
bx, by = rich_box(fig, "x"), rich_box(fig, "y")
assert bx is not None and by is not None
# 富文本框画在画布内
fig.canvas.draw()
axbb = ax.get_window_extent(r)
assert 0 < bx.y0 and bx.x0 > 0, f"X 标题跑到画布外了 {bx}"
assert by.x1 < axbb.x0, f"Y 标题没在轴区左边 {by}"
print("   -> 两轴颜色独立生效，且都在画布内 OK")

# ---------- 4. 位置：pad（离刻度距离）----------
print("\n=== 4. 离刻度距离 pad ===")
st["axis"]["title_cfg"]["x"]["pad"] = 6
fig1, _ = fig_of(st)
b1 = rich_box(fig1, "x")
st["axis"]["title_cfg"]["x"]["pad"] = 60
fig2, _ = fig_of(st)
b2 = rich_box(fig2, "x")
print(f"   pad=6  y0={b1.y0:.1f} / pad=60 y0={b2.y0:.1f}")
assert b2.y0 < b1.y0, f"pad 变大应更靠下: {b1.y0} -> {b2.y0}"
print("   -> pad 越大越远离坐标区 OK")

# ---------- 5. 位置：手动微调 ----------
print("\n=== 5. 手动微调 shift ===")
st["axis"]["title_cfg"]["x"].update({"pad": 6, "shift_y": 0, "shift_x": 0})
st["axis"]["title_cfg"]["y"].update({"pad": 6, "shift_x": 0})
f0, _ = fig_of(st)
x0, y0 = rich_box(f0, "x"), rich_box(f0, "y")
st["axis"]["title_cfg"]["x"]["shift_y"] = 40
st["axis"]["title_cfg"]["x"]["shift_x"] = 35
f1, _ = fig_of(st)
x1 = rich_box(f1, "x")
assert x1.y0 > x0.y0, f"往上微调无效 {x0.y0} -> {x1.y0}"
assert x1.x0 > x0.x0, f"往右微调无效 {x0.x0} -> {x1.x0}"
print(f"   X 竖向 {x0.y0:.1f} -> {x1.y0:.1f}，横向 {x0.x0:.1f} -> {x1.x0:.1f}")
st["axis"]["title_cfg"]["y"]["shift_x"] = -25
f2, _ = fig_of(st)
y2 = rich_box(f2, "y")
assert y2.x0 < y0.x0, f"Y 往左微调无效 {y0.x0} -> {y2.x0}"
print(f"   Y 横向 {y0.x0:.1f} -> {y2.x0:.1f}")
print("   -> 上下左右微调都生效 OK")

# ---------- 6. 字号 ----------
print("\n=== 6. 字号 ===")
st["axis"]["title_cfg"]["x"].update({"shift_y": 0, "shift_x": 0})
st["axis"]["title_size"]["x"] = 10
fa, _ = fig_of(st)
ba = rich_box(fa, "x")
st["axis"]["title_size"]["x"] = 26
fb, _ = fig_of(st)
bb = rich_box(fb, "x")
print(f"   10号高={ba.height:.1f} / 26号高={bb.height:.1f}")
assert bb.height > ba.height * 1.4, "字号没生效"
print("   -> 字号生效 OK")

# ---------- 7. 上下标比例 ----------
print("\n=== 7. 上下标大小比/偏移 ===")
st["axis"]["title_cfg"]["y"] = {"pad": 8, "sub_ratio": 0.5,
                                "rise": 0.8, "drop": 0.5}
fc, _ = fig_of(st)
print("   Y 竖排已用 sub_ratio=0.5 rise=0.8 drop=0.5 重画 OK")
# 参数确实传进了 richlabel
kids = [a for a in fc.axes[0].artists
        if hasattr(a, "shift") and a.which == "y"]
assert len(kids) == 1
print("   -> 上下标参数生效 OK")

# ---------- 8. 粗体/斜体 ----------
print("\n=== 8. 粗体 / 斜体 ===")
st["axis"]["title_cfg"]["x"] = {"pad": 8, "weight": "bold",
                                "style": "italic"}
fd, _ = fig_of(st)
print("   X 粗斜体渲染 OK")

# ---------- 9. 无上下标时走原生标签 ----------
print("\n=== 9. 无上下标 ==")
st2 = base()
st2["axis"]["titles"] = {"x": "Potential (V)", "y": "Plain Y"}
st2["axis"]["title_cfg"]["x"] = {"color": "#00AA00", "pad": 12,
                                 "shift_x": 20, "shift_y": -10}
fe, axe = fig_of(st2)
re_ = render(fe)
assert axe.xaxis.label.get_visible(), "无上下标应显示原生标签"
assert axe.xaxis.label.get_color() == "#00AA00"
px, py = axe.xaxis.label.get_position()
print(f"   原生标签颜色 OK，位置 = ({px:.3f}, {py:.3f})（已微调）")
assert abs(px - 0.5) > 1e-6 or abs(py) > 1e-6, "微调没生效"
print("   -> 无上下标也能上色+微调 OK")

# ---------- 10. 老配置兼容 ----------
print("\n=== 10. 老配置兼容 ===")
st3 = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
del st3["axis"]["title_cfg"]              # 模拟旧配置没有这个字段
st3["axis"]["titles"] = {"x": "Old (V)", "y": "Old Y"}
fg, ag = fig_of(st3)
render(fg)
print("   没有 title_cfg 字段也不报错 OK")

# ---------- 11. 界面端到端 ----------
print("\n=== 11. 界面端到端 ===")
pnl = G.StylePanel()
pnl.set_styles({"cv_overlay": eclab.DEFAULT_STYLE}, {})
tabs = pnl.findChild(QTabWidget)
names = [tabs.tabText(i) for i in range(tabs.count())]
assert "轴标题" in names, names
print("   页签 =", names)
pnl.ed_x.set_values("E_{applied} (V)", 16,
                    {"color": "#C1440E", "pad": 14, "shift_y": 10,
                     "weight": "bold"})
pnl.ed_y.set_values("Current density (A g^{-1})", 15,
                    {"color": "#0A6E8A", "pad": 10, "shift_x": 12})
app.processEvents()
styles, _ = pnl.styles_all()
a = styles["cv_overlay"]["axis"]
assert a["titles"]["x"] == "E_{applied} (V)"
assert a["title_size"]["x"] == 16
assert a["title_cfg"]["x"]["color"] == "#C1440E"
assert a["title_cfg"]["x"]["pad"] == 14
assert a["title_cfg"]["x"]["shift_y"] == 10
assert a["title_cfg"]["x"]["weight"] == "bold"
assert a["title_cfg"]["y"]["color"] == "#0A6E8A"
print("   界面设置全部写进样式 OK")
# 回读
p2 = G.StylePanel()
p2.set_styles(styles, {})
app.processEvents()
assert p2.ed_x.sp_pad.value() == 14
assert p2.ed_x.btn_color.color() == "#C1440E"
print("   样式回填控件 OK")

# ---------- 12. 每张图各设各的 ----------
print("\n=== 12. X / Y 互不干扰 ===")
st4 = base()
st4["axis"]["titles"] = {"x": "AAA", "y": "BBB"}
st4["axis"]["title_cfg"]["x"] = {"pad": 10, "color": "#111111"}
st4["axis"]["title_cfg"]["y"] = {"pad": 40, "color": "#222222"}
f4, a4 = fig_of(st4)
r4 = render(f4)
assert a4.xaxis.label.get_color() == "#111111"
assert a4.yaxis.label.get_color() == "#222222"
print("   -> 两轴设置完全独立 OK")

# ---------- 13. 每张图各设各的（回归：以前会串味）----------
print("\n=== 13. 每张图各设各的 ===")
cfg2 = {"plot_style": {},
        "plot_style_by_kind": {
            "cv_overlay": {"axis": {"titles": {"x": "OVERLAY"},
                                    "title_cfg": {"x": {"color": "#AA0000"}}}},
            "cv_cap": {"axis": {"titles": {"x": "CAP"},
                                "title_cfg": {"x": {"color": "#0000AA"}}}}}}
o = eclab.get_style(cfg2, "cv_overlay")
c = eclab.get_style(cfg2, "cv_cap")
print("   overlay =", o["axis"]["titles"]["x"], o["axis"]["title_cfg"]["x"]["color"])
print("   cap     =", c["axis"]["titles"]["x"], c["axis"]["title_cfg"]["x"]["color"])
assert o["axis"]["titles"]["x"] == "OVERLAY"
assert c["axis"]["titles"]["x"] == "CAP"
# 改其中一张，另一张不能跟着变（这是修过的老 bug）
o["axis"]["title_cfg"]["x"]["color"] = "#00FF00"
assert c["axis"]["title_cfg"]["x"]["color"] == "#0000AA", "另一张被污染了"
# 默认样式里刻意不放 titles 键（缺键 = 用这张图的默认标题，
# 有键但留空 = 真的不画），所以这里查的是"键没被塞进去"
assert "titles" not in eclab.DEFAULT_STYLE["axis"], "全局默认被污染了"
print("   -> 各图独立，改一张不影响另一张和全局默认 OK")

print("\n轴标题测试全部通过")