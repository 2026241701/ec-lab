# -*- coding: utf-8 -*-
"""本轮九项改动的测试"""
import os
import sys
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
import ec_gui as G
import eclab

app = QApplication.instance() or QApplication([])
RES = [{"E": np.linspace(-0.88, 0.45, 60),
        "j": np.sin(np.linspace(-0.88, 0.45, 60) * 6), "label": "a"}]


def fresh(kind="cv_overlay"):
    return eclab.deep_merge(eclab.DEFAULT_STYLE, {})


# ---------- 1. 导出透明背景 ----------
print("=== 1. 导出透明背景 ===")
d = tempfile.mkdtemp()


def export_alpha(trans, fmts=("png",)):
    st = fresh()
    st["canvas"]["transparent"] = trans
    st["canvas"]["width"], st["canvas"]["height"] = 60.0, 45.0
    st["canvas"]["unit"] = "mm"
    fig = eclab.plot_cv_overlay(RES, st)
    p = eclab.save_fig(fig, f"a{trans}", st, list(fmts), 150, d)[0]
    im = Image.open(p).convert("RGBA")
    return im.getpixel((2, 2)), im.getpixel((im.width // 2,
                                              im.height // 2))


c_off, m_off = export_alpha(False)
print("不透明：角 alpha =", c_off[3], "中心 alpha =", m_off[3])
assert c_off[3] == 255 and m_off[3] == 255
c_on, m_on = export_alpha(True)
print("透明  ：角 alpha =", c_on[3], "中心 alpha =", m_on[3])
assert c_on[3] == 0, "画布角应透明"
assert m_on[3] == 0, "绘图区也应透明（不能只透外圈）"
# jpg 不支持透明，要能自动退回而不是报错
export_alpha(True, ("png", "jpg"))
jpgs = [f for f in os.listdir(d) if f.endswith(".jpg")]
assert jpgs and Image.open(os.path.join(d, jpgs[0])).mode == "RGB"
print("jpg 自动退回不透明 OK")
print("  -> 透明背景 OK\n")

# ---------- 2. 边距数字显示不全 ----------
print("=== 2. 边距数字显示 ===")
pnl = G.StylePanel()
pnl.set_styles({"cv_overlay": fresh()}, {})
pnl.resize(560, 900)
pnl.show()
app.processEvents()
for nm in ("c_ml", "c_mr", "c_mt", "c_mb"):
    w = getattr(pnl, nm)
    assert w.width() >= 130, f"{nm} 太窄：{w.width()}"
print("四个边距框宽度 =", [getattr(pnl, n).width()
                      for n in ("c_ml", "c_mr", "c_mt", "c_mb")])
pnl.c_ml.setCurrentText("120")
st, _ = pnl.styles_all()
assert st["cv_overlay"]["canvas"]["margin"]["left"] == 120
print("三位数 120 完整显示且读得对 OK")
# 不该拖一串 .0
st2 = fresh()
st2["canvas"]["margin"] = {"left": 22.0, "right": 4.0,
                          "top": 4.0, "bottom": 16.0}
p2 = G.StylePanel()
p2.set_styles({"cv_overlay": st2}, {})
assert p2.c_ml.currentText() == "22", p2.c_ml.currentText()
print("显示 =", [getattr(p2, n).currentText()
              for n in ("c_ml", "c_mr", "c_mt", "c_mb")], "（无 .0 尾巴）")
print("  -> 边距数字 OK\n")

# ---------- 3. 上下标左右微调（全局，整张图统一）----------
print("=== 3. 上下标左右微调 ===")
sup0 = G.轴标题编辑(None, "x", "X")
sup0.ed_text.setText("Current (A g^{-1})")
sup0.set_mt(sup_dx=0.45, sub_dx=-0.2)
assert sup0._mt["sup_dx"] == 0.45 and sup0._mt["sub_dx"] == -0.2, \
    sup0._mt
print("全局 sup_dx =", sup0._mt["sup_dx"], "sub_dx =", sup0._mt["sub_dx"])
# 引擎要真的接住（sup_dx 走全局 mathtext，不按轴单独设）
st3 = fresh()
st3["axis"]["titles"] = {"x": "Current (A g^{-1})", "y": "Y"}
st3["mathtext"]["sup_dx"] = 0.5
fig = eclab.plot_cv_overlay(RES, st3)
fig.canvas.draw()
kids = [a for a in fig.axes[0].artists
        if hasattr(a, "shift") and a.which == "x"]
assert len(kids) == 1, "X 轴应走富文本"
print("引擎已接受全局 sup_dx，图已重画 OK")
print("  -> 上下标左右微调 OK\n")

# ---------- 4. Y 轴竖排标题显示不全 ----------
print("=== 4. Y 轴竖排标题显示全 ===")
pv = G.标题预览(None, vertical=True)
assert pv.height() >= 200, pv.height()
print("Y 预览默认高 =", pv.height())
pv.set_all(text="Current density (A g^{-1})", size=15)
img = pv.grab().toImage()
w, h = img.width(), img.height()
nonbg = 0
for yy in range(h):
    for xx in range(w):
        if img.pixelColor(xx, yy).name().upper() != "#FBFCFD":
            nonbg += 1
print("有内容的像素数 =", nonbg)
assert nonbg > 200, "预览是空白的"
# 文字要顶到上下边（说明撑满了控件而不是被裁）
rows = [yy for yy in range(h)
        if any(img.pixelColor(xx, yy).name().upper() != "#FBFCFD"
               for xx in range(w))]
print("文字行范围 =", min(rows), "~", max(rows), "控件高 =", h)
assert min(rows) < 8 and max(rows) > h - 8, "文字没占满，可能是被裁了"
print("  -> 竖排标题撑满控件、不裁切 OK\n")

# ---------- 5. 垂直线颜色"空"可选 ----------
print("=== 5. 垂直线颜色空值 ===")
b = G.色块按钮(None, "#D2603A", allow_empty=True, empty_text="跟随线条")
assert b.color() == "#D2603A"
dlg = G.ColorPickerDialog(None, b.color())
dlg.allow_empty = True
dlg.empty_text = "跟随线条"
dlg.btn_empty.setVisible(True)
dlg.btn_empty.setChecked(False)
assert dlg.btn_empty.isCheckable(), "空选项必须能勾选"
dlg._toggle_empty(True)
assert dlg.result_color() == "", "选空应返回空串"
dlg._toggle_empty(False)
dlg._set("#0A6E8A")
assert dlg.result_color() == "#0A6E8A"
dlg._toggle_empty(True)
assert dlg.result_color() == ""
print("空<->具体色  来回切换 OK")
st5 = fresh()
st5["scatter"]["vline_color"] = ""
assert eclab._nth("", 0) == ""
print("空串在引擎里= 跟随曲线色 OK")
print("  -> 垂直线颜色空值可选 OK\n")

# ---------- 6/7. 数据点逐个配色 + 批量 + 循环 ----------
print("=== 6. 数据点逐点配色 ===")
from matplotlib.colors import to_hex


def pts_of(sc_extra, n=5):
    import matplotlib.pyplot as plt
    st = fresh({"scatter": sc_extra} if False else {})
    st["scatter"].update(sc_extra)
    st["colors"] = ["#C1440E", "#0A6E8A", "#3B7A57"]
    w, h = eclab.figsize_inch(st)
    fig, ax = plt.subplots(figsize=(w, h))
    for i in range(n):
        if st["scatter"]["vline"]:
            eclab.draw_vline(ax, i + 1, i * 30 + 10, st, i)
        eclab.draw_point(ax, i + 1, i * 30 + 10, st, i)
    fig.subplots_adjust(left=0.15, right=0.97, top=0.95, bottom=0.17)
    fig.canvas.draw()
    pts, vls = [], []
    for l in ax.lines:
        if l.get_marker() not in ("none", "None", None, " "):
            pts.append(to_hex(l.get_markerfacecolor()).upper())
        else:
            vls.append(to_hex(l.get_color()).upper())
    plt.close(fig)
    return pts, vls


p, v = pts_of({}, 3)
print("只上曲线配色 -> 点 =", p)
assert p == ["#C1440E", "#0A6E8A", "#3B7A57"], p
assert v == ["#C1440E", "#0A6E8A", "#3B7A57"], v
print("  -> 数据点不再是同一色，各跟各的曲线 OK")

p, v = pts_of({"face_colors": ["#111111", "#222222"],
               "vline_colors": ["#333333", "#444444"]}, 3)
print("逐点 2 色 / 3 点 -> 点 =", p, "竖线 =", v)
assert p == ["#111111", "#222222", "#111111"], p
assert v == ["#333333", "#444444", "#333333"], v
print("  -> 逐点配色 + 配色不够自动循环 OK")

p, _ = pts_of({"face_colors": ["#AAAAAA", "#BBBBBB"]}, 5)
assert p == ["#AAAAAA", "#BBBBBB", "#AAAAAA", "#BBBBBB", "#AAAAAA"], p
print("5 点 2 色循环 =", p)

# 界面端到端
print("\n=== 7. 批量应用（界面） ===")
pnl2 = G.StylePanel()
pnl2.set_styles({"cv_cap": fresh()}, {})
pnl2.set_kind("cv_cap")
pnl2.show()
app.processEvents()
pnl2.set_point_labels(["5", "10", "20", "50", "100 mV/s"])
app.processEvents()
assert pnl2.pt_table.tbl.rowCount() == 5
pnl2.pt_table.apply_palette(["#C1440E", "#0A6E8A", "#3B7A57"])
f, vv, e = pnl2.pt_table.values()
print("填入 3 色到 5 个点 =", f)
assert f == ["#C1440E", "#0A6E8A", "#3B7A57", "#C1440E", "#0A6E8A"]
print("提示 =", pnl2.pt_table.lab.text())
s7, _ = pnl2.styles_all()
assert s7["cv_cap"]["scatter"]["face_colors"] == f
print("  -> 批量套用 + 写进样式 OK")
p3 = G.StylePanel()
p3.set_styles(s7, {})
p3.set_kind("cv_cap")
app.processEvents()
assert p3.pt_table.values()[0][:5] == f
print("  -> 样式回填不丢颜色 OK")
pnl2.pt_table.clear_all()
assert pnl2.pt_table.values()[0] == [""] * 5
print("  -> 全部清空 OK\n")

# ---------- 8. EIS 页签按需出现 ----------
print("=== 8. EIS 页签 ===")
pnl4 = G.StylePanel()
pnl4.set_styles({"cv_overlay": fresh()}, {})
pnl4.show()
app.processEvents()


def visible():
    return [pnl4.tabs.tabText(i) for i in range(pnl4.tabs.count())
            if pnl4.tabs.isTabVisible(i)]


print("CV 叠加 ->", visible())
assert "EIS" not in visible()
pnl4.set_kind("EIS")
app.processEvents()
print("切到 EIS ->", visible())
assert "EIS" in visible()
pnl4.set_kind("cv_cap")
app.processEvents()
print("切回 CV ->", visible())
assert "EIS" not in visible()
print("  -> EIS 页签按需出现 OK")

# ---------- 9. 综合：不回归 ----------
print("\n=== 9. 其它功能没被破坏 ===")
pnl5 = G.StylePanel()
pnl5.set_styles({"cv_overlay": fresh()}, {})
pnl5.set_point_labels(["a", "b"])
st9, _ = pnl5.styles_all()
assert st9["cv_overlay"]["axis"]["title_cfg"]["x"]["color"] == "#000000"
assert st9["cv_overlay"]["canvas"]["margin"]["left"] == 22
print("坐标轴锁定/边距/轴标题 默认值都正常")

shutil.rmtree(d, ignore_errors=True)
print("\n本轮九项测试全部通过")