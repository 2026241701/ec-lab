# -*- coding: utf-8 -*-
"""第五批改动回归测试（网格 / Y轴标题丢失 / 空标题 / 线型 / 轴标题编辑器 /
文本框表格 / 图例边框 / 坐标微调）

验证：
1. 网格：GUI _fill/_read 能完整往返（以前控件存在但根本没接线）；
2. Y 轴标题：画布缩到很小也不能被挤出画布（以前会消失）；
3. 空标题 = 真的不画；键不存在才回退默认标题；老配置能迁移；
4. 线型：8 种线型都画得出来，中文名 ↔ matplotlib 写法对得上；
5. 轴标题编辑器：标题文字自动填默认、两个勾选框控制显示、_read 写出开关；
6. 文本框表格：10 列布局读回不炸（以前颜色列 currentText 会 AttributeError，
   导致「重新绘制」静默失效）；坐标微调能用；
7. 图例边框：不勾时整行（含标签）都隐藏。
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import eclab
import richlabel

RES = [{"E": np.linspace(-0.8, 0.45, 60),
        "j": np.sin(np.linspace(-0.8, 0.45, 60) * 6), "label": "a"}]


# ==================================================================
# 1. 网格
# ==================================================================
def test_grid_roundtrip():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["grid"] = {"show": True, "style": ":", "width": 1.0,
                  "alpha": 0.5, "color": "#112233"}
    p.set_styles({"cv_overlay": st}, {"dpi": 600})
    p.set_kind("cv_overlay")
    assert p.ck_grid.isChecked(), "勾选状态没回填"
    assert p.cb_gridsty.currentText() == ":", p.cb_gridsty.currentText()
    assert abs(float(p.c_gridw.currentText()) - 1.0) < 1e-9
    assert abs(float(p.c_gridal.currentText()) - 0.5) < 1e-9
    assert p.ed_gridcol.text() == "#112233"
    out = p._read(eclab.deep_merge(eclab.DEFAULT_STYLE, {}),
                  {"dpi": 600})[0]["grid"]
    assert out == {"show": True, "style": ":", "width": 1.0,
                   "alpha": 0.5, "color": "#112233"}, out
    print("PASS test_grid_roundtrip (网格读写往返)")


def test_grid_engine():
    """引擎侧：show=True 才画网格，参数真的落到 gridline 上"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["grid"] = {"show": True, "style": ":", "width": 1.2,
                  "alpha": 0.5, "color": "#112233"}
    fig = eclab.plot_cv_overlay(RES, st)
    fig.canvas.draw()
    gl = [g for g in fig.axes[0].get_xgridlines() if g.get_visible()]
    assert gl, "勾了网格但一条都没画"
    assert gl[0].get_linestyle() in (":", (0, None, None)), gl[0].get_linestyle()
    assert abs(gl[0].get_linewidth() - 1.2) < 1e-6
    assert abs(gl[0].get_alpha() - 0.5) < 1e-6
    plt.close(fig)

    st2 = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st2["grid"]["show"] = False
    fig2 = eclab.plot_cv_overlay(RES, st2)
    fig2.canvas.draw()
    vis = [g for g in fig2.axes[0].get_xgridlines() if g.get_visible()]
    assert not vis, "没勾网格却画出来了"
    plt.close(fig2)
    print("PASS test_grid_engine (网格引擎生效)")


# ==================================================================
# 2. Y 轴标题不被挤出画布
# ==================================================================
def _y_title_bbox(fig):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ax = fig.axes[0]
    for a in ax.artists:
        if hasattr(a, "which") and a.which == "y":
            return a.box.get_window_extent(r), fig.get_window_extent(r)
    return None, None


def test_y_title_kept_inside():
    """画布缩到很小（预览窗缩小）时，Y 轴富文本标题仍要留在画布内"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["axis"]["titles"] = {"x": "E_{x} (V)",
                            "y": "Current density (A g^{-1})"}
    for w_in, h_in in ((7.09, 5.51), (5.0, 3.9), (3.5, 2.7), (2.4, 1.9)):
        f = eclab.plot_cv_overlay(RES, st)
        f.set_size_inches(w_in, h_in)
        bb, fb = _y_title_bbox(f)
        assert bb is not None, (w_in, "Y 标题富文本框不见了")
        assert bb.x0 >= fb.x0 - 0.5, (w_in, bb, fb)
        assert bb.y0 >= fb.y0 - 0.5, (w_in, bb, fb)
        assert bb.x1 <= fb.x1 + 0.5, (w_in, bb, fb)
        assert bb.y1 <= fb.y1 + 0.5, (w_in, bb, fb)
        plt.close(f)
    print("PASS test_y_title_kept_inside (小画布 Y 标题不丢)")


# ==================================================================
# 3. 空标题 = 空标题 + 老配置迁移
# ==================================================================
def test_empty_title_is_empty():
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["axis"]["titles"] = {"x": "", "y": ""}
    fig = eclab.plot_cv_overlay(RES, st)
    fig.canvas.draw()
    ax = fig.axes[0]
    assert ax.xaxis.label.get_text() == "", ax.xaxis.label.get_text()
    assert ax.yaxis.label.get_text() == "", ax.yaxis.label.get_text()
    rich = [a for a in ax.artists if hasattr(a, "which")]
    assert not rich, "空标题却还画了富文本框"
    plt.close(fig)
    print("PASS test_empty_title_is_empty (留空=不画标题)")


def test_missing_title_key_falls_back():
    """键不存在 → 用这张图的默认标题"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    assert "titles" not in st["axis"], "默认样式里不该有 titles 键"
    fig = eclab.plot_cv_overlay(RES, st)
    fig.canvas.draw()
    assert "Current density" in fig.axes[0].yaxis.label.get_text()
    plt.close(fig)
    print("PASS test_missing_title_key_falls_back (缺键回落默认)")


def test_titles_migration():
    """老配置里空的 titles 键要被删掉（否则新规则下标题全没了）"""
    cfg = {"plot_style": {"axis": {"titles": {"x": "", "y": ""}}},
           "plot_style_by_kind": {
               "cv_cap": {"axis": {"titles": {"x": "", "y": ""}}},
               "EIS": {"axis": {"titles": {"x": "Z' (ohm)", "y": ""}}}}}
    assert eclab._migrate_titles(cfg)
    assert "titles" not in cfg["plot_style"]["axis"]
    assert "titles" not in cfg["plot_style_by_kind"]["cv_cap"]["axis"]
    # EIS 有真标题，必须留着（只清 y 空的会造成误删 → 整键保留）
    assert cfg["plot_style_by_kind"]["EIS"]["axis"]["titles"]["x"] == "Z' (ohm)"
    assert eclab._migrate_titles(cfg) is False, "迁移过不该重复做"
    print("PASS test_titles_migration (老配置迁移)")


def test_title_cfg_switches():
    """font_on / pos_on 关掉时不生效（值保留）"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["axis"]["title_cfg"] = {
        "x": {"font_on": False, "pos_on": False, "color": "#FF0000",
              "weight": "bold", "style": "italic", "pad": 30,
              "shift_x": 12, "shift_y": -8},
        "y": {}}
    cx = eclab._title_cfg(st, "x")
    assert cx["pad"] == 0 and cx["shift_x"] == 0.0 and cx["shift_y"] == 0.0
    assert cx["weight"] == "normal" and cx["style"] == "normal"
    cy = eclab._title_cfg(st, "y")
    assert cy["pad"] == 0 and cy["weight"] == "normal"
    st["axis"]["title_cfg"]["x"] = dict(st["axis"]["title_cfg"]["x"],
                                        font_on=True, pos_on=True)
    cx2 = eclab._title_cfg(st, "x")
    assert cx2["pad"] == 30 and cx2["shift_x"] == 12.0
    assert cx2["weight"] == "bold" and cx2["style"] == "italic"
    print("PASS test_title_cfg_switches (勾选开关生效)")


# ==================================================================
# 4. 线型
# ==================================================================
def test_line_styles_all_draw():
    for name in eclab.LINE_STYLE_NAMES:
        st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
        st["line"]["linestyle"] = name
        code = eclab.line_style(st)
        assert code == dict(eclab.LINE_STYLES)[name], name
        fig = eclab.plot_cv_overlay(RES, st)
        fig.canvas.draw()
        ln = fig.axes[0].get_lines()[0]
        assert ln.get_linestyle() is not None, name
        plt.close(fig)
    assert eclab.line_style({"line": {}}) == "-"
    assert eclab.line_style({"line": {"linestyle": "乱写"}}) == "-"
    print("PASS test_line_styles_all_draw (8 种线型)")


def test_linestyle_gui_roundtrip():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_overlay": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_overlay")
    p.cb_ls.setCurrentText("长点划线")
    out = p._read(eclab.deep_merge(eclab.DEFAULT_STYLE, {}),
                  {"dpi": 600})[0]["line"]["linestyle"]
    assert out == "长点划线", out
    # 老样式没这个键 → 回填成实线，不报错
    p2 = G.StylePanel(None)
    old = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    old["line"].pop("linestyle", None)
    p2.set_styles({"cv_overlay": old}, {"dpi": 600})
    p2.set_kind("cv_overlay")
    assert p2.cb_ls.currentText() == "实线"
    print("PASS test_linestyle_gui_roundtrip (线型读写)")


# ==================================================================
# 5. 轴标题编辑器
# ==================================================================
def test_axis_title_editor():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    ed = G.轴标题编辑(None, "y", "Y")
    # 没有预览白框了
    assert not hasattr(ed, "prev"), "预览框应该删掉"
    ed.set_values("Current density (A g^{-1})", 0, {})
    assert ed.ed_text.text() == "Current density (A g^{-1})"
    v = ed.values()
    assert v["font_on"] is True and v["pos_on"] is True
    ed.ck_font.setChecked(False)
    ed.ck_pos.setChecked(False)
    v2 = ed.values()
    assert v2["font_on"] is False and v2["pos_on"] is False
    assert v2["pad"] == 0 and v2["shift_x"] == 0.0
    assert ed.size_value() == 0, "不勾单独设置时字号应回到 0"
    ed.ck_font.setChecked(True)
    ed.cb_size.setCurrentText("18")
    assert ed.size_value() == 18
    print("PASS test_axis_title_editor (轴标题编辑器)")


def test_axis_title_auto_fill():
    """没写 titles 时，按图的种类自动填默认标题"""
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_cap": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_cap")
    assert p.ed_x.ed_text.text() == eclab.default_titles("cv_cap")[0]
    assert p.ed_y.ed_text.text() == eclab.default_titles("cv_cap")[1]
    print("PASS test_axis_title_auto_fill (标题自动填)")


# ==================================================================
# 6. 文本框表格
# ==================================================================
def test_texts_table_roundtrip():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_overlay": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_overlay")
    p._add_text_row("E_{x} test", 0.5, 0.9, 12, "#112233",
                    "center", "是", True, 45)
    # 这行以前会抛 AttributeError（色块按钮没有 currentText）
    st = p._read(eclab.deep_merge(eclab.DEFAULT_STYLE, {}), {"dpi": 600})[0]
    t = st["texts"]
    assert len(t) == 1, t
    assert t[0]["text"] == "E_{x} test"
    assert abs(t[0]["x"] - 0.5) < 1e-9 and abs(t[0]["y"] - 0.9) < 1e-9
    assert t[0]["color"] == "#112233"
    assert t[0]["frame"] is True and t[0]["rich"] is True
    assert abs(t[0]["rotation"] - 45.0) < 1e-9
    # 回填再读一遍，值必须一模一样
    p._fill(st, {"dpi": 600})
    st2 = p._read(eclab.deep_merge(eclab.DEFAULT_STYLE, {}),
                  {"dpi": 600})[0]
    assert st2["texts"] == t, (st2["texts"], t)
    print("PASS test_texts_table_roundtrip (文本框读写)")


def test_texts_row_number_and_nudge():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_overlay": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_overlay")
    p._add_text_row("a", 0.5, 0.5)
    p._add_text_row("b", 0.5, 0.5)
    p._add_text_row("c", 0.5, 0.5)
    assert p.tb_texts.columnCount() == 10
    assert [p.tb_texts.item(r, 0).text() for r in range(3)] == ["1", "2", "3"]
    p.tb_texts.removeRow(0)
    p._sync_text_rownos()
    assert [p.tb_texts.item(r, 0).text() for r in range(2)] == ["1", "2"]
    w = p.tb_texts.cellWidget(0, 2)
    assert isinstance(w, G.坐标微调)
    assert abs(w.value() - 0.5) < 1e-9
    w.nudge(1)
    assert abs(w.value() - 0.51) < 1e-9
    w.nudge(-100)
    assert abs(w.value() - 0.0) < 1e-9, "越界要夹住"
    w.set_value(5.0)
    assert abs(w.value() - 1.0) < 1e-9, "上界也要夹住"
    print("PASS test_texts_row_number_and_nudge (序号列 + 坐标微调)")


def test_apply_texts_engine():
    """引擎能吃 GUI 写出来的 text 结构（含旋转与富文本）"""
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["texts"] = [{"text": "E_{x}", "x": 0.5, "y": 0.9, "size": 12,
                    "color": "", "ha": "center", "frame": False,
                    "rich": True, "rotation": 90}]
    fig = eclab.plot_cv_overlay(RES, st)
    fig.canvas.draw()
    assert any(isinstance(getattr(a, "offsetbox", None), richlabel._RotLabel)
               for a in fig.axes[0].artists), "文本框没画出来"
    plt.close(fig)
    print("PASS test_apply_texts_engine (文本框引擎渲染)")


# ==================================================================
# 7. 图例边框
# ==================================================================
def test_legend_frame_hides_row():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_overlay": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_overlay")
    p.ck_legframe.setChecked(False)
    p._sync_leg_frame()
    assert p.w_legbw.isHidden(), "没勾边框却还显示边框粗细"
    p.ck_legframe.setChecked(True)
    p._sync_leg_frame()
    assert not p.w_legbw.isHidden()
    p.ck_legframe.setChecked(False)
    assert p.w_legbw.isHidden()
    print("PASS test_legend_frame_hides_row (图例边框整行隐藏)")


# ==================================================================
# 8. 网格设置行的显隐
# ==================================================================
def test_grid_rows_hidden():
    import ec_gui as G
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    p = G.StylePanel(None)
    p.set_styles({"cv_overlay": eclab.deep_merge(eclab.DEFAULT_STYLE, {})},
                 {"dpi": 600})
    p.set_kind("cv_overlay")
    assert p._grid_rows and all(l is not None for l in p._grid_rows)
    p.ck_grid.setChecked(False)
    assert all(l.isHidden() for l in p._grid_rows)
    p.ck_grid.setChecked(True)
    assert not any(l.isHidden() for l in p._grid_rows)
    print("PASS test_grid_rows_hidden (网格设置行显隐)")


if __name__ == "__main__":
    test_grid_roundtrip()
    test_grid_engine()
    test_y_title_kept_inside()
    test_empty_title_is_empty()
    test_missing_title_key_falls_back()
    test_titles_migration()
    test_title_cfg_switches()
    test_line_styles_all_draw()
    test_linestyle_gui_roundtrip()
    test_axis_title_editor()
    test_axis_title_auto_fill()
    test_texts_table_roundtrip()
    test_texts_row_number_and_nudge()
    test_apply_texts_engine()
    test_legend_frame_hides_row()
    test_grid_rows_hidden()
    print("全部通过")