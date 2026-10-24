# -*- coding: utf-8 -*-
"""
ec-lab  -  CHI660 电化学工作站数据批处理引擎  v0.4
==================================================
负责：识别 -> 取数 -> 计算 -> 作图 -> 导出
所有绘图外观（画布/字号/线宽/颜色/刻度/图例/坐标范围/输出格式）
全部由传入的 plot_style 决定，界面或模板改了这里就跟着变。

坐标轴范围（axis.x_min/x_max/y_min/y_max）留空 = 自动，
填了数值 = 固定，改配色/字号/线宽都不会被弹回去。

CLI：python eclab.py
GUI：python ec_gui.py
"""

import os
import re
import sys
import time
import copy
import json
import glob
import math
import numpy as np
import pandas as pd

import matplotlib
# Respect the GUI's chosen backend; newly created engine figures use their own
# Agg canvas below and therefore do not require a Qt window in worker threads.
if "matplotlib.pyplot" not in sys.modules:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import MultipleLocator, AutoMinorLocator

import richlabel

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 打包成 exe 后，__file__ 指向临时解压目录，所有读写都要落在 exe 同级目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


# ==================================================================
# 一、绘图样式：全部可配置，默认值在此更改
# ==================================================================

DEFAULT_STYLE = {
    "canvas": {
        "width": 180.0, "height": 140.0, "dpi": 600,
        "unit": "mm",                  # inch / cm / mm / px
        "transparent": False,          # 图片背景透明
        # 绘图区到画布四边的距离（单位跟画布一致），
        # 留 0 = 用 matplotlib 默认；填数字 = 精确指定
        "margin": {"left": 22.0, "right": 4.0, "top": 4.0, "bottom": 16.0},
    },
    "font": {
        "family": "Arial",             # 西文字体
        "cjk": "SimSun",               # 中文兜底（宋体）
        "base": 14,                    # 全局基准字号
        "label": 14,                   # 坐标轴标题
        "tick": 14,                    # 刻度数字
        "legend": 14,                  # 图例
        "title": 14,
    },
    "line": {"width": 1.8, "marker": 5, "cap_size": 8,
             # 线型：写中文名（LINE_STYLES 里的那些），引擎自动翻译
             "linestyle": "实线"},
    # 上下标：字号等比缩放 + 基线偏移（不用 mathtext，字形与正文一致）
    "mathtext": {
        "fontset": "custom",           # 仅保留兼容旧配置
        "rm": "", "it": "", "bf": "",
        "sub_ratio": 0.68,             # 上下标字号 / 正文字号
        "rise": 0.40,                  # 上标抬高几个字号
        "drop": 0.18,                  # 下标下压几个字号
        "sup_dx": 0.0,                 # 上标左右微调（单位：正文字号）
        "sub_dx": 0.0,                 # 下标左右微调
    },
    "colors": ["#1F6E5A", "#38699E", "#A63E76", "#D2603A",
               "#7A5AA8", "#4E9BC8", "#8C8C8C"],
    "axis": {
        "linewidth": 1.2,              # 轴线粗细
        "tick_dir": "in",              # in / out
        "tick_len": 5,                 # 主刻度线长度
        "tick_width": 1.0,             # 刻度线粗细
        "minor": True,                 # 总开关：是否画副刻度
        "minor_per_major": 2,
        "x_major": 0,                  # 0 = 自动；>0 为该步长
        "y_major": 0,
        # 坐标轴范围：留空 = 让 matplotlib 自动算（跟以前一样）；
        # 填了数值 = 固定住，改配色/改线宽/换图都不会被改回去。
        "x_min": "", "x_max": "",
        "y_min": "", "y_max": "",
        "show_top_right": True,        # 四边都有刻度
        # 四条边各自的主刻度 / 副刻度 / 刻度文字
        # 默认只有下轴、左轴显示刻度（Origin 风格），上/右轴可随时勾上
        "sides": {
            "bottom": {"major": True, "minor": True, "labels": True},
            "top": {"major": False, "minor": False, "labels": False},
            "left": {"major": True, "minor": True, "labels": True},
            "right": {"major": False, "minor": False, "labels": False},
        },
        # 轴标题文字：故意不写默认值 —— 键不存在 = 用这张图的默认标题，
        # 键存在但留空 = 真的不画标题（GUI 会把默认标题自动填进输入框）
        "title_size": {"x": 0, "y": 0},  # 0 = 跟随全局 label 字号
        # 轴标题逐项控制：X / Y 各一套，互不影响
        # color留空 = 黑色；pad 是离刻度文字的距离（点）；
        # shift_x / shift_y 是手动微调（点），往正方向推；
        # weight粗体、style 斜体
        # 上下标的大小/偏移不在这里 —— 整张图统一走 mathtext 全局设置
        # rich：富文本开关，关掉后 ^{} / _{} 原样显示（不缩放、不偏移）
        "title_cfg": {
            "x": {"color": "", "pad": 0, "shift_x": 0.0, "shift_y": 0.0,
                  "weight": "", "style": "", "rich": True},
            "y": {"color": "", "pad": 0, "shift_x": 0.0, "shift_y": 0.0,
                  "weight": "", "style": "", "rich": True},
        },
        "tick_label_size": 0,          # 0 = 跟随全局 tick 字号
        # 类别轴：2/5/10/20/50 这种不均匀刻度可选均匀分布，只当文本用
        "categorical": {"x": False, "y": False},
        "cat_labels": {"x": "", "y": ""},   # 逗号分隔，留空用原数值
    },
    "legend": {
        "show": True,
        "loc": "best",                 # best/upper left/upper right/...
        "ncol": 1,                     # 图例列数
        "frameon": False,              # 是否画边框
        "alpha": 1.0,
        "border_width": 0.8,           # 边框粗细
        "items": [],                   # 自定义图例文字（可写上下标）
        "rich": True,                  # 富文本开关：关掉后 ^{}/_{} 原样显示
        "handle_length": 2.0,          # 示意图宽度
        "handle_height": 0.7,          # 示意图大小（高度）
        "handle_textpad": 0.8,         # 示意图与文字的间距
        "label_spacing": 0.5,          # 条目之间的间距
        "column_spacing": 2.0,         # 列间距
    },
    "grid": {"show": False, "style": "--", "width": 0.6, "alpha": 0.4,
             "color": "#999999"},
    # 比电容图的数据点样式（散点）
    "scatter": {
        "marker": "o",                 # o 圆 s 方 ^ 三角 v 倒三角 D 菱 p 五边形
        "fill": "实心",                # 实心 / 空心 / 立体
        "face_color": "",              # 填充色，空 = 跟线条颜色
        "edge_color": "",              # 边线色，空 = 跟线条颜色
        "edge_width": 1.2,
        "size": 8,                     # 点的大小
        "vline": True,                 # 是否画从零到数据点的垂直线
        "vline_color": "",             # 空 = 跟线条颜色
        "vline_width": 1.8,
        "vline_style": "-",
        "vline_alpha": 1.0,
        # 逐个数据点单独配色：列表里第 i 项对应第 i 个数据点，
        # 空字符串 = 跟着上面的统一设置走。列表不够长时，后面的点循环
        # 套用配色（数据点比配色多时也能用）。
        "face_colors": [],             # 例：["#C1440E", "", "#0A6E8A"]
        "edge_colors": [],
        "vline_colors": [],
    },
    "eis": {
        "equal_scale": True,           # 横纵等比（看半圆圆不圆）
        "x_max": 0,                    # 0 = 自动；>0 手动上限
        "y_max": 0,
        "inset": False,                # 是否叠加高频区放大插图
        "inset_x_max": 0,              # 插图范围，0 = 自动
    },
    # 用户自己加的文本框（可以有多个），坐标是 0~1 的相对位置
    "texts": [],
}

UNIT_TO_INCH = {"inch": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4}


def deep_merge(base, override):
    """递归合并字典：override 里没写的项保留 base

    注意：base 会被真正深拷贝一份再改。原来这里只浅拷贝了顶层，
    结果嵌套字典（axis/canvas/font…）全都跟 DEFAULT_STYLE 共用同一个对象，
    任何一次"改这张图的样式"都会顺手改掉全局默认值、以及别的图 ——
    改 CV 的 X 标题，CV 比电容图也跟着变。
    """
    out = copy.deepcopy(base) if base else {}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# 图类型 -> 样式细分键。每张图都能单独调（轴标题天然不同，不会串）
KIND_ALIAS = {          # 新键: (旧的大类键, 自己的键)
    "cv_overlay": ("CV", "cv_overlay"),
    "cv_cap": ("CV", "cv_cap"),
    "gcd_overlay": ("GCD", "gcd_overlay"),
    "gcd_cap": ("GCD", "gcd_cap"),
}


def get_style(cfg, kind=None):
    """从配置取绘图样式，缺项用默认值补齐

    kind = cv_overlay / cv_cap / gcd_overlay / gcd_cap / EIS / cycle：
    每张图可以单独存一套样式。先取通用样式 plot_style 作基底，
    再叠加旧的大类样式（CV/GCD，兼容旧模板），最后叠加这张图自己的。

    ⚠ 基底里的 axis.titles 必须剥掉，不能渗进别的图。
    GUI 把 cfg["plot_style"] 直接写成 cv_overlay 那一套（见 ec_gui
    的 _sync_cfg），而"这张图画什么轴标题"是每张图自己的语义 ——
    以前不剥的结果就是：GCD 比电容图的 X 标题串成 CV 的
    "Potential (V)"，用户看到的"X 标题怎么变成 Current density"
    就是这么来的。字号、颜色这些通用属性照常继承，只有 titles 不行。
    """
    raw = cfg.get("plot_style") or {}
    if kind:
        # 浅拷贝，把 titles 摘掉 —— 不动原始配置，也不怕键不存在
        base = {k: v for k, v in raw.items() if k != "axis"}
        axis = {k: v for k, v in (raw.get("axis") or {}).items()
                if k != "titles"}
        if axis:
            base["axis"] = axis
    else:
        base = raw
    st = deep_merge(DEFAULT_STYLE, base)
    if kind:
        per = cfg.get("plot_style_by_kind") or {}
        old, own = KIND_ALIAS.get(kind, (None, kind))
        if old and per.get(old):
            st = deep_merge(st, per[old])
        if per.get(own):
            st = deep_merge(st, per[own])
    # 带上 kind：set_axis_titles 要用它把"实际用的标题"记下来
    st = dict(st)
    st["axis"] = dict(st["axis"])
    st["axis"]["_kind"] = kind
    return st


def kind_of_key(key):
    """预览项的 key -> 图类型（决定用哪一套样式）"""
    if key.startswith("cycle:"):
        return "cycle"
    if key.startswith("EIS:"):
        return "EIS"
    if key == "CV_overlay":
        return "cv_overlay"
    if key == "CV_capacitance":
        return "cv_cap"
    if key == "GCD_overlay":
        return "gcd_overlay"
    if key == "GCD_capacitance":
        return "gcd_cap"
    return "cv_overlay"


# 每种图的默认轴标题（GUI 靠它把文字自动填进输入框；引擎在没有
# 用户设定时也用它兜底）。EIS 用 ^{} 写法，跟新的富文本体系一致。
DEFAULT_TITLES = {
    "cv_overlay":  ("Potential (V)", "Current density (A g^{-1})"),
    "cv_cap":      ("Scan rate (mV s^{-1})",
                    "Specific capacitance (F g^{-1})"),
    "gcd_overlay": ("Time (s)", "Potential (V)"),
    "gcd_cap":     ("Current density (A g^{-1})",
                    "Specific capacitance (F g^{-1})"),
    "cycle":       ("Cycle number",
                    "Specific capacitance (F g^{-1})"),
    "EIS":         ("Z' (ohm)", "-Z'' (ohm)"),
}


# 曲线线型：名字 → matplotlib 写法
# 虚线的 dash 序列按"点数"给，跟线宽无关，改粗细时疏密比例不会乱。
LINE_STYLES = [
    ("实线", "-"),
    ("虚线", "--"),
    ("点线", ":"),
    ("点划线", "-."),
    ("长虚线", (0, (9, 3))),
    ("短虚线", (0, (3, 2))),
    ("长点划线", (0, (7, 3, 1.5, 3))),
    ("短点划线", (0, (5, 2, 1, 2))),
]
LINE_STYLE_NAMES = [n for n, _ in LINE_STYLES]


def line_style(st):
    """取样式里的线型（中文名 → matplotlib 写法），认不出来就当实线"""
    v = (st.get("line") or {}).get("linestyle", "实线")
    for name, code in LINE_STYLES:
        if v == name:
            return code
    # 老配置里直接存过 matplotlib 写法的话照用，
    # 其它一律当实线（避免把乱字符串塞给 matplotlib 画图时报错）
    return v if isinstance(v, tuple) or v in ("-", "--", "-.", ":") else "-"


def default_titles(kind):
    """某种图的默认轴标题；没有登记的返回两个空串"""
    return DEFAULT_TITLES.get(kind, ("", ""))


# 每画一张图，把"图上真实用的轴标题"记在 figure 上（属性 _ec_titles），
# GUI 的标题编辑框从那里回填 —— 显示的就是图上真在画的字，
# 而不是另查一张固定表（两处一旦不同步，就会出现"框里写着 A、
# 图上画着 B"，用户看到的串图就是这么来的）。
def _record_titles(ax, kind, tx, ty):
    """把"这张图实际用的 X / Y 标题"挂到 figure 上"""
    try:
        ax.figure._ec_titles = (tx, ty)
        ax.figure._ec_kind = kind or ""
    except Exception:
        pass


def titles_on_figure(fig, kind=None):
    """读一张已画好的图上真实的轴标题（带 ^{}/_{} 标记的原文）

    set_axis_titles 画的时候把原文挂在 figure 上了（_ec_titles），
    这里直接读它 —— 比原生标签准（原生标签在富文本路径下存的是去掉
    标记的占位文字，用户没法接着改），也不会串到别的图上
    （拿的是这一张图自己的，不是全局缓存）。
    拿不到再依次退回原生标签、这张图的默认表。
    """
    if fig is not None:
        try:
            v = getattr(fig, "_ec_titles", None)
            if v:
                return tuple(v)
        except Exception:
            pass
    if fig is not None:
        try:
            axs = [a for a in fig.axes if a.get_visible()]
            if axs:
                ax = axs[0]
                tx = (ax.xaxis.label.get_text() or "").strip()
                ty = (ax.yaxis.label.get_text() or "").strip()
                if tx or ty:
                    return tx, ty
        except Exception:
            pass
    return default_titles(kind)


def apply_style(st):
    """把样式写进 matplotlib 全局参数"""
    f = st["font"]
    # 字体列表必须直接放 font.family 才会逐字回退，
    # 写成 family=serif + font.serif 时中文会变方块
    mt = st.get("mathtext", {})
    fontset = (mt.get("fontset") or "custom").lower()
    plt.rcParams.update({
        "font.family": [f["family"], f["cjk"], "DejaVu Serif"],
        "mathtext.fontset": fontset,
        "mathtext.default": "it",
        "font.size": f["base"],
        "axes.labelsize": f["label"],
        "axes.titlesize": f["title"],
        "legend.fontsize": f["legend"],
        "legend.frameon": st["legend"]["frameon"],
        "xtick.labelsize": f["tick"],
        "ytick.labelsize": f["tick"],
        "xtick.direction": st["axis"]["tick_dir"],
        "ytick.direction": st["axis"]["tick_dir"],
        "xtick.top": st["axis"]["show_top_right"],
        "ytick.right": st["axis"]["show_top_right"],
        "xtick.major.size": st["axis"]["tick_len"],
        "ytick.major.size": st["axis"]["tick_len"],
        "xtick.minor.size": st["axis"].get("tick_len_minor",
                                           st["axis"]["tick_len"] * 0.5),
        "ytick.minor.size": st["axis"].get("tick_len_minor",
                                           st["axis"]["tick_len"] * 0.5),
        "xtick.minor.visible": st["axis"]["minor"],
        "ytick.minor.visible": st["axis"]["minor"],
        # tick_width 为 0 或没填时跟轴线粗细一致
        "xtick.major.width": st["axis"].get("tick_width", 0)
            or st["axis"]["linewidth"],
        "ytick.major.width": st["axis"].get("tick_width", 0)
            or st["axis"]["linewidth"],
        "xtick.minor.width": (st["axis"].get("tick_width", 0)
            or st["axis"]["linewidth"]) * 0.8,
        "ytick.minor.width": (st["axis"].get("tick_width", 0)
            or st["axis"]["linewidth"]) * 0.8,
        "axes.linewidth": st["axis"]["linewidth"],
        "lines.linewidth": st["line"]["width"],
        "lines.markersize": st["line"]["marker"],
    })
    if fontset == "custom":       # 上下标用与正文同一套字体
        fam = f["family"]
        plt.rcParams.update({
            "mathtext.rm": (mt.get("rm") or fam),
            "mathtext.it": (mt.get("it") or fam + ":italic"),
            "mathtext.bf": (mt.get("bf") or fam + ":bold"),
        })


def figsize_inch(st):
    """画布尺寸换算成英寸（支持 inch / cm / mm / px 四种单位）"""
    c = st["canvas"]
    unit = (c.get("unit") or "inch").lower()
    w, h = float(c.get("width", 6)), float(c.get("height", 4.6))
    if unit == "px":
        dpi = float(c.get("dpi") or 600) or 600
        return max(w / dpi, 0.2), max(h / dpi, 0.2)
    k = UNIT_TO_INCH.get(unit, 1.0)
    return max(w * k, 0.2), max(h * k, 0.2)


def apply_canvas_margin(fig, st):
    """按「绘图区到画布四边的距离」压紧/留白边距

    数值单位跟画布一致（mm 就填 mm）。全为 0 = 用 matplotlib 默认边距，
    这样出来的图最紧凑；填了数字就按填的来。
    """
    m = (st.get("canvas", {}) or {}).get("margin") or {}
    vals = {k: float(m.get(k, 0) or 0) for k in
            ("left", "right", "top", "bottom")}
    if not any(vals.values()):
        return False
    w_in, h_in = figsize_inch(st)
    unit = (st["canvas"].get("unit") or "inch").lower()
    k_in = UNIT_TO_INCH.get(unit, 1.0) if unit != "px" else \
        1.0 / (float(st["canvas"].get("dpi") or 600) or 600)
    fw, fh = fig.get_figwidth(), fig.get_figheight()   # 本身就是英寸
    left = min(max(vals["left"] * k_in, 0.0), fw * 0.45) / fw
    right = min(max(vals["right"] * k_in, 0.0), fw * 0.45) / fw
    bottom = min(max(vals["bottom"] * k_in, 0.0), fh * 0.45) / fh
    top = min(max(vals["top"] * k_in, 0.0), fh * 0.45) / fh
    fig.subplots_adjust(left=left, right=1.0 - right,
                        bottom=bottom, top=1.0 - top)
    return True


def apply_axes(ax, st):
    """四条边的刻度显隐 + 轴线粗细 + 刻度线长度/粗细"""
    a = st["axis"]
    for side in ("top", "bottom", "left", "right"):
        try:
            ax.spines[side].set_linewidth(a["linewidth"])
        except KeyError:
            pass
    sides = a.get("sides") or {}
    for side, cfg in sides.items():
        if side not in ("top", "bottom", "left", "right"):
            continue
        which = "x" if side in ("top", "bottom") else "y"
        major = bool(cfg.get("major", True))
        minor = bool(cfg.get("minor", True)) and bool(a.get("minor", True))
        labels = bool(cfg.get("labels", False)) and major
        kw = {side: major, "label" + side: labels}
        try:
            ax.tick_params(axis=which, which="major", **kw)
            ax.tick_params(axis=which, which="minor", **{side: minor})
        except ValueError:
            pass
    ax.tick_params(which="major", length=a.get("tick_len", 5),
                   width=a.get("tick_width", 1.0),
                   direction=a.get("tick_dir", "in"))
    ax.tick_params(which="minor", length=a.get("tick_len", 5) * 0.55,
                   width=a.get("tick_width", 1.0) * 0.8,
                   direction=a.get("tick_dir", "in"))
    if a.get("tick_label_size"):
        ax.tick_params(labelsize=a["tick_label_size"])


def _title_cfg(st, which):
    """取某一个轴标题的样式配置，缺项用默认（老配置也不会报错）

    两个总开关（GUI 里的勾选框）：
      font_on —— 关：字号/颜色/字型全部跟随全局，不看下面的值
      pos_on  —— 关：距离/上下左右微调一律用默认（pad=4、不微调）
    关掉时保留用户填过的数值，下次勾上还能接着用。
    """
    d = ((st.get("axis", {}).get("title_cfg") or {}).get(which) or {})
    font_on = d.get("font_on", True) is not False
    pos_on = d.get("pos_on", True) is not False
    out = {"color": (d.get("color") or "").strip() or "#000000",
           "pad": (d.get("pad", 0) or 0) if pos_on else 0,
           "shift_x": (d.get("shift_x", 0.0) or 0.0) if pos_on else 0.0,
           "shift_y": (d.get("shift_y", 0.0) or 0.0) if pos_on else 0.0,
           "weight": (d.get("weight") or "normal") if font_on else "normal",
           "style": (d.get("style") or "normal") if font_on else "normal",
           # 富文本开关：关掉后 ^{} / _{} 当普通字符原样显示
           "rich": d.get("rich", True) is not False}
    # 上下标比例/偏移：整张图统一，只认「画布/字体」页的全局设置。
    # 以前每个轴标题能各存一套，结果同一个图里两套比例对不上，
    # 全局栏也管不到轴标题 —— 现在一律走全局（老配置里的局部值忽略）。
    mt = st.get("mathtext", {}) or {}
    out["sub_ratio"] = mt.get("sub_ratio", 0.68)
    out["rise"] = mt.get("rise", 0.40)
    out["drop"] = mt.get("drop", 0.18)
    out["sup_dx"] = mt.get("sup_dx", 0.0)
    out["sub_dx"] = mt.get("sub_dx", 0.0)
    return out


def set_axis_titles(ax, st, xlabel="", ylabel=""):
    """轴标题：文字、字号、颜色、位置、粗斜体、上下标全都可单独调

    写了 ^{} / _{} 的改用 richlabel 渲染（字号等比缩放 + 基线偏移，
    字形与正文完全一致）；没写的仍走 matplotlib 原生标签。

    pad 是"离刻度文字的距离"，靠 matplotlib 的 labelpad 实现 ——
    这样刻度数量变了、字号变了，距离会自动跟着重算，不会跑位。

    标题文字：键存在就是用户写的（留空 = 空标题，真不画）；
    键不存在才退回这张图的默认标题。
    """
    a = st["axis"]
    tt = a.get("titles")
    if isinstance(tt, dict):
        tx = (tt.get("x") if "x" in tt else xlabel) or ""
        ty = (tt.get("y") if "y" in tt else ylabel) or ""
    else:
        tx, ty = xlabel or "", ylabel or ""
    tx, ty = tx.strip(), ty.strip()
    # 记下"这张图实际用的标题"，供 GUI 标题框回填
    _record_titles(ax, a.get("_kind"), tx, ty)
    ts = a.get("title_size", {})
    fs = st["font"]
    # 原生标签默认离刻度 4 点；用户填的值是"额外的距离"
    base_pad = 4.0

    for txt, which in ((tx, "x"), (ty, "y")):
        size = int(ts.get(which) or fs["label"])
        cfg = _title_cfg(st, which)
        common = dict(west=fs["family"], cjk=fs["cjk"],
                      sub_ratio=cfg["sub_ratio"], rise=cfg["rise"],
                      drop=cfg["drop"], weight=cfg["weight"],
                      style=cfg["style"], sup_dx=cfg["sup_dx"],
                      sub_dx=cfg["sub_dx"])
        pad = base_pad + (cfg["pad"] or 0)
        setter = ax.set_xlabel if which == "x" else ax.set_ylabel
        if not txt:                       # 空标题 = 真的不画
            setter("")
            continue
        # 富文本找不到原生标签时会退回这个兜底距离
        gap = 7 + (cfg["pad"] or 0)
        kw = dict(fontsize=size, color=cfg["color"], labelpad=pad)
        if cfg.get("rich", True) and richlabel.has_markup(txt):
            # 塞一份去掉上下标符号的占位文字，matplotlib 才会把边距算对
            setter(richlabel.strip_markup(txt), **kw)
            richlabel.add_axis_label(
                ax, txt, which, size=size, gap=gap,
                color=cfg["color"],
                shift=(cfg["shift_x"], cfg["shift_y"]), **common)
        else:
            setter(txt, **kw)
            # 没上下标时也支持手动微调位置
            sx, sy = cfg["shift_x"], cfg["shift_y"]
            if sx or sy:
                native = ax.xaxis.label if which == "x" else ax.yaxis.label
                px, py = native.get_position()
                native.set_position((px + sx, py + sy))


def cat_positions(values, enable, labels=""):
    """类别轴：把不均匀的数值（2/5/10/20/50…）当文本，均匀排布

    返回 (绘图用坐标, 刻度文字)；enable=False 时原样返回数值坐标。
    这是可选项，不会取代原本按数字大小排列的方式。
    """
    vals = list(values)
    if not enable:
        return np.asarray(vals, dtype=float), None
    pos = np.arange(len(vals), dtype=float)
    labs = [t.strip() for t in str(labels or "").replace("，", ",").split(",")
            if t.strip()]
    if len(labs) < len(vals):
        labs += [f"{v:g}" for v in vals[len(labs):]]
    return pos, labs[:len(vals)]


def apply_cat_ticks(ax, which, pos, labels):
    """把类别轴的刻度放到均匀位置并写上文本"""
    if not labels:
        return
    (ax.set_xticks if which == "x" else ax.set_yticks)(pos)
    (ax.set_xticklabels if which == "x" else ax.set_yticklabels)(labels)


def apply_texts(ax, st):
    """画用户自己加的文本框（可多个，坐标是 0~1 的相对位置）"""
    fs = st["font"]
    mt = st.get("mathtext", {}) or {}
    for t in st.get("texts", []) or []:
        txt = (t.get("text") or "").strip()
        if not txt:
            continue
        size = t.get("size") or fs["base"]
        color = (t.get("color") or "").strip() or "#000000"
        weight = "bold" if t.get("bold") else "normal"
        style = "italic" if t.get("italic") else "normal"
        x = float(t.get("x", 0.5))
        y = float(t.get("y", 0.95))
        # 富文本开关：关掉就当普通文字，^{} / _{} 原样显示
        rot = float(t.get("rotation", 0) or 0)
        if t.get("rich", True) is not False and richlabel.has_markup(txt):
            richlabel.add_label(
                ax, txt, (x, y), size=size, color=color, west=fs["family"],
                cjk=fs["cjk"], ha=t.get("ha", "center"),
                va=t.get("va", "top"), weight=weight, style=style,
                rotation=rot,
                sub_ratio=mt.get("sub_ratio", 0.68),
                rise=mt.get("rise", 0.40), drop=mt.get("drop", 0.18))
            continue
        kw = {"transform": ax.transAxes, "fontsize": size, "color": color,
              "ha": t.get("ha", "center"), "va": t.get("va", "top"),
              "weight": weight, "style": style}
        if rot:
            kw["rotation"] = rot
        if t.get("frame"):
            kw["bbox"] = dict(boxstyle="round,pad=0.3", fc="white",
                              ec=color, lw=0.8)
        try:
            ax.text(x, y, txt, **kw)
        except Exception:
            pass


def nice_ceiling(x):
    """向上取整到好看的刻度上限"""
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    base = 10 ** exp
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if x <= m * base:
            return m * base
    return 10 * base


def color_of(st, i):
    """按序号取调色板颜色（超出后循环）"""
    cs = st["colors"] or DEFAULT_STYLE["colors"]
    return cs[i % len(cs)]


# ==================================================================
# 二、文件读取与自动识别
# ==================================================================

def read_text(path):
    """CHI660F 文件可能是 UTF-8 或 GBK，逐个尝试"""
    with open(path, "rb") as source:
        raw = source.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_kind(text):
    """判断数据类型：CV / GCD / EIS / FIT / None

      - CV / GCD：文件头有技术名称
      - EIS：原始数据一定带 "Freq/Hz" 表头；不带表头的跳过
      - FIT：ZView 导出的拟合结果（用作外部拟合曲线，不单独当原始数据处理）
    """
    head = text[:400]
    if "ZView Export" in head:
        return "FIT"
    if "Cyclic Voltammetry" in head:
        return "CV"
    if "Chronopotentiometry" in head:
        return "GCD"
    if "A.C. Impedance" in head or "Freq/Hz" in text[:2000]:
        return "EIS"
    return None


def parse_meta(text):
    """从文件头提取实验参数"""
    meta = {}
    patterns = {
        "scan_rate_Vs": r"Scan Rate \(V/s\) = ([\d.eE+-]+)",
        # CHI 大圈数写成科学计数法（Segment = 2.06e+3），必须按浮点读
        "segments": r"Segment = ([\d.eE+-]+)",
        "current_A": r"Cathodic Current \(A\) = ([\d.eE+-]+)",
        "high_E": r"High E \(V\) = ([\d.eE+-]+)",
        "low_E": r"Low E \(V\) = ([\d.eE+-]+)",
        "init_E": r"Init E \(V\) = ([\d.eE+-]+)",
        "sensitivity": r"Sensitivity \(A/V\) = ([\d.eE+-]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            v = m.group(1)
            if key == "segments":
                meta[key] = int(round(float(v)))
            else:
                meta[key] = float(v)
    return meta


def load_numeric(lines, sep=None):
    """把数值行读成二维数组（逗号或空白/Tab 分隔都支持），跳过坏行"""
    rows = []
    for line in lines:
        if sep == "tab":
            parts = [p.strip().strip('"') for p in re.split(r"[\t]+", line)]
        else:
            parts = [p.strip().strip('"') for p in line.split(",")]
        parts = [p for p in parts if p != ""]
        if len(parts) < 2:
            continue
        try:
            rows.append([float(p) for p in parts])
        except ValueError:
            continue
    return np.array(rows)


def parse_cv(path):
    """解析 CV 文件：返回 meta, E(V), I(A)"""
    text = read_text(path)
    meta = parse_meta(text)
    lines = text.splitlines()
    idx = next(i for i, l in enumerate(lines)
               if "Potential/V" in l and "Current/A" in l)
    data = load_numeric(lines[idx + 1:])
    return meta, data[:, 0], data[:, 1]


def parse_gcd(path):
    """解析 GCD 文件：数据块位于 Time/sec 表头之后、Hold Time/sec 之前"""
    text = read_text(path)
    meta = parse_meta(text)
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("Time/sec"))
    end = next((i for i, l in enumerate(lines) if "Hold Time/sec" in l), len(lines))
    data = load_numeric(lines[start + 1:end])
    return meta, data[:, 0], data[:, 1]


def parse_eis(path):
    """解析 EIS 文件：返回 meta, f(Hz), Z'(ohm), Z''(ohm)"""
    text = read_text(path)
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines)
                if l.strip().startswith("Freq/Hz")), None)
    data = load_numeric(lines[idx + 1:] if idx is not None else lines)
    if data.size == 0 or data.shape[1] < 3:
        raise ValueError("有效数据列不足 3 列，不是 EIS 数据")
    return parse_meta(text), data[:, 0], data[:, 1], data[:, 2]


def parse_zview_fit(path):
    """解析 ZView 导出的拟合文件（Tab 分隔）

    列含义：Pt. | Freq | Z'(实测) | Z''(实测) | Z'(拟合) | Z''(拟合)
    返回 (f, zr_data, zi_data, zr_fit, zi_fit)；列不足返回 None
    """
    text = read_text(path)
    lines = text.splitlines()
    data = load_numeric(lines, sep="tab")
    if data.size == 0 or data.shape[1] < 6:
        return None
    f = data[:, 1]
    zr_d, zi_d = data[:, 2], data[:, 3]
    zr_f = data[:, 4]
    zi_f = data[:, 5]
    return f, zr_d, zi_d, zr_f, zi_f


def find_fit_file(path):
    """找与原始数据同名的 ZView 拟合文件（xxx.txt -> xxx-fit.txt 等变体）"""
    stem, ext = os.path.splitext(path)
    for cand in (stem + "-fit" + ext, stem + " -fit" + ext,
                 stem + "-Fit" + ext, stem + "_fit" + ext):
        if os.path.exists(cand):
            return cand
    return None


def export_zview(path, f, zr, zi, out_dir=None):
    """导出 ZView 可读的 .z 文件（Tab 分隔三列：Freq  Z'  Z''）"""
    out_dir = out_dir or OUTPUT_DIR
    from ec_export import validate_output_dir, unused_path
    source_dirs = [os.path.dirname(os.path.abspath(path))] if os.path.isfile(path) else []
    out_dir = validate_output_dir(out_dir, source_dirs)
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0] + ".z"
    dst = unused_path(os.path.join(out_dir, name))
    with open(dst, "w", encoding="utf-8") as fo:
        fo.write('"Made by ec-lab"\n')
        fo.write('"Frequency" "Z\'" "Z\'\'"\n')
        for a, b, c in zip(f, zr, zi):
            fo.write("%.6e\t%.6e\t%.6e\n" % (a, b, c))
    return dst


# ==================================================================
# 三、CV / GCD 计算
# ==================================================================

def split_direction(x, y, min_span_ratio=0.3, min_pts=5):
    """把曲线按 x 的变化方向切分成 segment（一个 segment = 单向变化一支）"""
    x = np.asarray(x)
    y = np.asarray(y)
    window = x.max() - x.min()
    if window <= 0 or len(x) < 10:
        return []

    # 全向量化：2060 圈 × 1600 点 ≈ 330 万点也能秒级完成
    sign = np.sign(np.diff(x))
    nz = np.where(sign != 0)[0]
    if len(nz) < 2:
        return [(x, y)]
    s = sign[nz]
    chg = np.where(s[1:] != s[:-1])[0] + 1
    bounds = [0] + (nz[chg] + 1).tolist() + [len(x)]

    segs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < min_pts:
            continue
        segs.append((x[a:b], y[a:b]))

    # 换向点抖动会把一支切成两段，把相邻的同向段合回去
    merged = []
    for seg in segs:
        if merged:
            pdir = np.sign(merged[-1][0][-1] - merged[-1][0][0])
            cdir = np.sign(seg[0][-1] - seg[0][0])
            if pdir != 0 and pdir == cdir:
                merged[-1] = (np.concatenate([merged[-1][0], seg[0]]),
                              np.concatenate([merged[-1][1], seg[1]]))
                continue
        merged.append(seg)

    return [s for s in merged
            if (s[0].max() - s[0].min()) >= min_span_ratio * window]


def pick_segments(segs, want):
    """按 segment 编号取段（1-based），返回 (选中的段, 编号, 说明)"""
    n = len(segs)
    valid = [i for i in want if 1 <= i <= n]
    if not valid:
        valid = [i for i in (2, 3) if i <= n] or ([n] if n >= 1 else [])
        note = (f"[注意] 只有 {n} 段，要求的第 {want} 段不存在 "
                f"-> 自动取第 {valid} 段")
    elif valid == list(want):
        note = f"共 {n} 段，按要求取第 {valid} 段"
    else:
        miss = sorted(set(want) - set(valid))
        note = f"共 {n} 段，实际取第 {valid} 段（第 {miss} 段不存在，已跳过）"
    return [segs[i - 1] for i in valid], valid, note


def cv_capacitance(E, I, scan_rate_Vs, mass_g, window=None):
    """CV 积分比电容 C (F/g)：C = 环路 |I|dV 积分 / (2 * v * dV * m)"""
    if window is None:
        window = E.max() - E.min()
    if not all(np.isfinite(v) and v > 0 for v in (window, scan_rate_Vs, mass_g)):
        return np.nan
    dE = np.diff(E)
    sign = np.sign(dE)
    sign = sign[sign != 0]
    if len(sign) == 0:
        return np.nan
    turns = np.where(np.diff(sign) != 0)[0] + 1
    bounds = [0] + turns.tolist() + [len(E)]
    total = 0.0
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < 5:
            continue
        total += abs(np.trapezoid(np.abs(I[a:b]), E[a:b]))
    return total / (2.0 * scan_rate_Vs * window * mass_g)


def gcd_metrics(chg_t, chg_V, dis_t, dis_V, current_A, mass_g,
                use_ir_free=False, continuous=False, dt_est=None):
    """从充电段、放电段分别计算放电时间、比电容、能量/功率密度、IR drop

    chg_* 为充电段（电位低->高），dis_* 为放电段（电位高->低）。
    ΔU 取放电段自己的首末电位差：充电截止后若有静置弛豫，
    放电起始电位会低于充电截止电位，不能拿充电末端点当放电起点，
    否则 ΔU 偏大、比电容被低估。

    dt_est：采样间隔。CHI 时间戳只有 4 位有效数字，超过 1000 s 后
      分辨率掉到 1 s，同一秒内的点时间戳相同，直接用 t[-1]-t[0] 会得到 0
      而把整圈丢掉；此时用 (点数-1) × dt_est 兜底。
    """
    chg_V = np.asarray(chg_V, float)
    chg_t = np.asarray(chg_t, float)
    dis_V = np.asarray(dis_V, float)
    dis_t = np.asarray(dis_t, float)
    if len(dis_t) < 3 or len(chg_t) < 3:
        return None
    if not (np.isfinite(mass_g) and mass_g > 0
            and np.isfinite(current_A) and abs(current_A) > 0):
        return None
    if not all(np.isfinite(values).all() for values in (chg_t, chg_V, dis_t, dis_V)):
        return None

    t_dis = dis_t[-1] - dis_t[0]
    t_chg = chg_t[-1] - chg_t[0]
    if dt_est and dt_est > 0:
        if t_dis <= 0 and len(dis_t) > 1:
            t_dis = (len(dis_t) - 1) * dt_est
        if t_chg <= 0 and len(chg_t) > 1:
            t_chg = (len(chg_t) - 1) * dt_est
    if not (np.isfinite(t_dis) and np.isfinite(t_chg)) or t_dis <= 0 or t_chg <= 0:
        return None

    ir_drop = max(0.0, dis_V[0] - dis_V[1]) if len(dis_V) > 1 else 0.0
    dV_eff = abs(dis_V[0] - dis_V[-1])
    if not np.isfinite(dV_eff) or dV_eff <= 0:
        return None
    if use_ir_free:
        ir_free_window = dV_eff - ir_drop
        if not np.isfinite(ir_free_window) or ir_free_window <= 0:
            return None
        dV_eff = max(ir_free_window, 1e-6)

    I = abs(current_A)
    C = I * t_dis / (mass_g * dV_eff)          # F/g
    ce = (100.0 * t_dis / t_chg) if continuous else None
    E = 0.5 * C * (dV_eff ** 2) / 3.6          # Wh/kg
    P = E * 3600.0 / t_dis                     # W/kg
    if not all(np.isfinite(value) for value in (C, E, P)) or C <= 0:
        return None

    return {
        "t_discharge_s": t_dis, "t_charge_s": t_chg,
        "IR_drop_V": ir_drop, "dV_eff_V": dV_eff,
        "capacitance_F_g": C, "coulombic_eff_%": ce,
        "energy_Wh_kg": E, "power_W_kg": P,
        "discharge_t": dis_t - dis_t[0], "discharge_V": dis_V,
        "charge_t": chg_t - chg_t[0], "charge_V": chg_V,
        # 原始时间轴：作图时把充放电连成一条连续的线
        "charge_t_abs": chg_t, "discharge_t_abs": dis_t,
    }


def gcd_pick_cd(picked):
    """从 pick_segments 的结果里辨认充电段/放电段（GCD 用）

    充电 = 电位低->高；若首段电位整体下降说明 picked 顺序反了，交换。
    返回 (charge_seg, discharge_seg)，每个元素是 (V, t)。
    """
    a, b = picked[0], picked[1]
    if a[0][-1] < a[0][0]:                     # 首段电位下降 -> a 是放电
        a, b = b, a
    return a, b


def cv_all_cycles(E, I, scan_rate_Vs, mass_g):
    """CV 每一圈的比电容：第 k 圈 = segment 2k + (2k+1)，segment 1 丢弃"""
    segs = split_direction(E, I)
    caps = []
    for i in range(1, len(segs) - 1, 2):
        Ec = np.concatenate([segs[i][0], segs[i + 1][0]])
        Ic = np.concatenate([segs[i][1], segs[i + 1][1]])
        caps.append(cv_capacitance(Ec, Ic, scan_rate_Vs, mass_g))
    return caps


def gcd_all_cycles(t, V, current_A, mass_g, use_ir_free=False):
    """GCD 每一圈：充电段 + 紧随的放电段 = 一圈（比电容只取放电段）"""
    segs = split_direction(V, t, min_span_ratio=0.1, min_pts=2)
    d = np.diff(np.asarray(t))
    d = d[d > 0]
    dt_est = float(np.median(d)) if len(d) else 0.1
    out = []
    for i in range(1, len(segs) - 1, 2):
        chg, dis = gcd_pick_cd([segs[i], segs[i + 1]])
        m = gcd_metrics(chg[1], chg[0], dis[1], dis[0],
                        current_A, mass_g, use_ir_free, dt_est=dt_est)
        if m is not None:
            out.append(m)
    return out


# ==================================================================
# 四、EIS 等效电路拟合
# ==================================================================
# 按等效电路图： Rs —[ (Rp + W) ∥ CPE ]—
#   Z_CPE = 1/(Y0*(jw)^n)
#   W  平面 Warburg：      Z = sigma*(1-j)/sqrt(w)
#   Wo 有限层（短路）：     Z = R*tanh((jwT)^P)/(jwT)^P
#   Ws 有限层（阻塞）：     Z = R*coth((jwT)^P)/(jwT)^P
# Wo/Ws 的指数 P 可调，低频不是标准 45°/90° 而是 60~80° 斜线时也能贴住。

def z_model(p, w, wtype="W"):
    """返回复阻抗 Z(ω)

    wtype="W"       -> p = [Rs, Rp, Y0, n, sigma]
    wtype="Wo"/"Ws" -> p = [Rs, Rp, Y0, n, R_w, T_w, P]
    """
    Rs, Rp, Y0, n = p[:4]
    jw = 1j * w
    z_cpe = 1.0 / (Y0 * jw ** n)
    if wtype in ("Wo", "Ws"):
        R_w, T_w, P = p[4], p[5], p[6]
        x = (jw * T_w) ** P
        xs = np.where(np.abs(x) < 1e-10, (1e-10 + 0j), x)
        if wtype == "Wo":
            with np.errstate(over="ignore", invalid="ignore"):
                ratio = np.where(np.abs(xs) > 20, 1.0 / xs,
                                 np.tanh(xs) / xs)
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                ratio = np.where(np.abs(xs) > 20, 1.0 / xs,
                                 1.0 / (np.tanh(xs) * xs))
        z_w = R_w * ratio
    else:
        sigma = p[4]
        z_w = sigma * (1.0 - 1j) / np.sqrt(w)
    z_branch = Rp + z_w
    z_p = 1.0 / (1.0 / z_cpe + 1.0 / z_branch)
    return Rs + z_p


def _eis_initial_guess(f, zr, zi, wtype="W"):
    """从数据形态给初值（初值不合理是 EIS 拟合失败的头号原因）"""
    w = 2 * np.pi * f
    Rs = float(zr[0])
    Rp = max(float(zr.max()) - Rs, 0.1 * Rs)
    Y0 = 1.0 / max(abs(zr[-1] + 1j * zi[-1]), 1e-9)
    n = 0.85
    if wtype in ("Wo", "Ws"):
        R_w = max(float(zr[-1]) - Rs, Rp)
        T_w = 1.0 / max(w[len(f) // 2], 1e-3)
        return [Rs, Rp, max(Y0, 1e-6), n, R_w, max(T_w, 1e-6), 0.6]
    k = max(3, len(f) // 5)
    sigma = float(np.median(-zi[-k:] * np.sqrt(w[-k:])))
    return [Rs, Rp, max(Y0, 1e-6), n, max(sigma, 0.0)]


def fit_eis(f, zr, zi, circuit="auto"):
    """拟合 Rs-[(Rp+W)∥CPE]

    circuit: "auto" = W/Wo/Ws 三种都拟取 R² 最高；
             也可指定 "W" / "Wo" / "Ws" 强行用某一种。
    返回 (参数 dict, 拟合曲线 z_fit, 报告 str)
    """
    from scipy.optimize import least_squares

    # 防御：未知电路代码直接给明确报错，不要被 least_squares 的
    # bounds/初值长度不匹配吞成“无法收敛”（GUI 下拉框可手输自定义串）
    if circuit not in ("auto", "W", "Wo", "Ws"):
        return (None, None,
                "不支持的等效电路 '%s'（仅支持 auto / W / Wo / Ws）。"
                "如需自定义电路请用 ZView 拟合，把结果命名为 xx-fit.txt "
                "放进数据文件夹并勾选「优先用 ZView 拟合结果」" % circuit)

    f = np.asarray(f, float)
    w = 2 * np.pi * f
    z_exp = np.asarray(zr, float) + 1j * np.asarray(zi, float)
    scale = np.abs(z_exp) + 1e-9
    ss_tot = float(np.sum(((z_exp.real - z_exp.real.mean()) / scale) ** 2
                          + ((z_exp.imag - z_exp.imag.mean()) / scale) ** 2))

    tried = ("W", "Wo", "Ws") if circuit == "auto" else (circuit,)
    best = None
    for wt in tried:
        p0 = _eis_initial_guess(f, np.asarray(zr, float),
                                np.asarray(zi, float), wt)
        lb = ([0.0, 0.0, 1e-8, 0.5, 0.0, 1e-7, 0.30] if wt != "W"
              else [0.0, 0.0, 1e-8, 0.5, 0.0])
        ub = ([np.inf, np.inf, 1e3, 1.2, np.inf, np.inf, 0.90]
              if wt != "W" else [np.inf, np.inf, 1e3, 1.2, np.inf])

        def resid(p):
            z_cal = z_model(p, w, wt)
            return np.concatenate([(z_cal - z_exp).real / scale,
                                   (z_cal - z_exp).imag / scale])

        try:
            r = least_squares(resid, p0, bounds=(lb, ub), max_nfev=6000)
            r2 = 1.0 - float(np.sum(r.fun ** 2)) / max(ss_tot, 1e-12)
        except Exception:
            continue
        if best is None or r2 > best["r2"]:
            best = {"wtype": wt, "p": r.x, "r2": r2,
                    "chi2": float(np.mean(r.fun ** 2))}

    if best is None:
        return None, None, ("拟合失败：该电路无法收敛，可在 ZView 里拟合后 "
                            "把 -fit.txt 放在同一目录，软件会读它作图")

    p = best["p"]
    z_fit = z_model(p, w, best["wtype"])
    d = {"Rs": float(p[0]), "Rp": float(p[1]), "Y0": float(p[2]),
         "n": float(p[3]), "R2": best["r2"], "chi2": best["chi2"],
         "source": "ec-lab 拟合"}
    if best["wtype"] == "W":
        d["sigma"] = float(p[4])
        d["circuit"] = "Rs-[(Rp+W)||CPE]"
        report = ("Rs {Rs:.3f}  Rp {Rp:.3f} ohm | Y0 {Y0:.3e} S*s^n  "
                  "n {n:.3f} | sigma {sigma:.3f} | R² {R2:.4f}".format(**d))
    else:
        d["R_w"] = float(p[4])
        d["T_w"] = float(p[5])
        d["P_w"] = float(p[6])
        d["circuit"] = ("Rs-[(Rp+Wo)||CPE]" if best["wtype"] == "Wo"
                        else "Rs-[(Rp+Ws)||CPE]")
        report = ("Rs {Rs:.3f}  Rp {Rp:.3f}  R_w {R_w:.3f} ohm | "
                  "Y0 {Y0:.3e} S*s^n  n {n:.3f} | T_w {T_w:.3g} s  "
                  "P {P_w:.3f} | R² {R2:.4f}".format(**d))
    return d, z_fit, report


# ==================================================================
# 五、作图
# ==================================================================

def _tick_step(st, key, lo, hi, count=6):
    """主刻度步长：手动优先，否则按范围自动取整数值"""
    manual = st["axis"].get(key, 0) or 0
    if manual and manual > 0:
        return manual
    span = hi - lo
    if span <= 0:
        return 1
    raw = span / count
    mag = 10 ** math.floor(math.log10(raw))
    return min(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)


def _limit(v):
    """用户填的坐标轴范围：空 = 自动（返回 None），有值 = 固定"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def apply_limits(ax, st):
    """坐标轴范围：只固定用户明确填了数值的那些边，没填的一律交给自动

    这是「改了配色就弹回原始范围」的解药 —— 范围一旦写进样式，
    就跟着样式走，任何一次重画都不会再被自动覆盖。
    """
    a = st["axis"]
    x0, x1 = _limit(a.get("x_min")), _limit(a.get("x_max"))
    y0, y1 = _limit(a.get("y_min")), _limit(a.get("y_max"))
    if x0 is not None or x1 is not None:
        cur = ax.get_xlim()
        ax.set_xlim(x0 if x0 is not None else cur[0],
                    x1 if x1 is not None else cur[1])
    if y0 is not None or y1 is not None:
        cur = ax.get_ylim()
        ax.set_ylim(y0 if y0 is not None else cur[0],
                    y1 if y1 is not None else cur[1])
    # 固定了范围就取消自动留白，否则边缘会莫名空出一截
    if (x0 is not None or x1 is not None) or (y0 is not None or y1 is not None):
        ax.margins(x=0, y=0)


def finish_axes(ax, xlabel, ylabel, st, auto_minor=True):
    """套用轴标题、四边刻度、网格与用户文本框"""
    set_axis_titles(ax, st, xlabel, ylabel)
    a = st["axis"]
    if auto_minor and a["minor"]:
        ax.xaxis.set_minor_locator(AutoMinorLocator(a["minor_per_major"]))
        ax.yaxis.set_minor_locator(AutoMinorLocator(a["minor_per_major"]))
    # 用户手动填的主刻度步长：>0 时优先于自动刻度（之前只有 EIS 生效）
    for axis_name, key in (("x", "x_major"), ("y", "y_major")):
        manual = a.get(key, 0) or 0
        if manual > 0:
            ax_obj = ax.xaxis if axis_name == "x" else ax.yaxis
            ax_obj.set_major_locator(MultipleLocator(manual))
    apply_axes(ax, st)
    g = st["grid"]
    if g["show"]:
        ax.grid(True, linestyle=g["style"], linewidth=g["width"],
                alpha=g["alpha"], color=g.get("color", "#999999"))
        ax.set_axisbelow(True)
    apply_limits(ax, st)
    apply_texts(ax, st)


def legend_display(txt):
    """把图例文字里的上下标（^{-1} / _{x}）转成 matplotlib 能画出来的写法

    只把上下标那几段单独包进 $...$，正文（含中文）留在数学模式外面 ——
    这样中文不会变成方块，字形也跟正文一致。
    用户自己写了 $ 的按 mathtext 原样处理，不再二次转换。
    """
    if not txt or "$" in txt or not richlabel.has_markup(txt):
        return txt
    out = []
    for seg, role in richlabel.parse_markup(txt):
        if role == 1:
            out.append("$^{%s}$" % seg)
        elif role == -1:
            out.append("$_{%s}$" % seg)
        else:
            out.append(seg)
    return "".join(out)


def apply_legend(ax, st, loc=None):
    """统一图例样式：文字可自定义（支持上下标）、示意图大小/间距可调

    上下标不再走 mathtext（那是图例斜体的根源）：
    带上下标的行交给 richlabel.LegendRichText 画成富文本，
    字形跟正文完全一致，缩放比/偏移就是「画布/字体」页上下标栏那几个数。
    自定义锚点：legend.anchor.on = True 时，把图例的 leg_corner 角
    对齐到画布坐标 (x, y)（0~1，可超 1 或为负把图例放到画布外）。
    """
    if not st["legend"]["show"]:
        return None
    lg = st["legend"]
    handles, labels = ax.get_legend_handles_labels()
    if not handles:
        return None
    items = lg.get("items") or []
    for i, txt in enumerate(items):
        if i < len(labels) and (txt or "").strip():
            labels[i] = txt
    # 带上下标标记的行：原生图例文字换成"去标记的纯文字"占位，
    # 富文本盖在上面画（布局不变、字形一致）。
    # 图例的「富文本」开关关掉时，一行都不转，^{} / _{} 原样显示。
    rich = []
    for i, txt in enumerate(labels):
        if (lg.get("rich", True) is not False and txt
                and "$" not in txt and richlabel.has_markup(txt)):
            rich.append((i, txt))
            labels[i] = richlabel.strip_markup(txt)
    use_loc = loc or lg["loc"]
    bbox = None
    anc = lg.get("anchor") or {}
    if anc.get("on"):
        corner = anc.get("leg_corner", "upper right")
        if corner in ("upper right", "upper left", "lower right",
                      "lower left", "center"):
            use_loc = corner          # loc 换成图例自己的对齐角
            try:
                bbox = (float(anc.get("x", 1.0)), float(anc.get("y", 1.0)))
            except (TypeError, ValueError):
                bbox = None
    leg = ax.legend(
        handles, labels, loc=use_loc,
        bbox_to_anchor=bbox, ncol=lg["ncol"],
        frameon=lg["frameon"], fontsize=st["font"]["legend"],
        framealpha=lg.get("alpha", 1.0),
        handlelength=lg.get("handle_length", 2.0),
        handleheight=lg.get("handle_height", 0.7),
        handletextpad=lg.get("handle_textpad", 0.8),
        labelspacing=lg.get("label_spacing", 0.5),
        columnspacing=lg.get("column_spacing", 2.0))
    if leg is not None and lg["frameon"]:
        leg.get_frame().set_linewidth(lg.get("border_width", 0.8))
    if leg is not None and rich:
        mt = st.get("mathtext", {}) or {}
        fs = st.get("font", {}) or {}
        try:
            overlay = richlabel.LegendRichText(
                leg, rich,
                sub_ratio=mt.get("sub_ratio", 0.68),
                rise=mt.get("rise", 0.40),
                drop=mt.get("drop", 0.18),
                sup_dx=mt.get("sup_dx", 0.0),
                sub_dx=mt.get("sub_dx", 0.0),
                west=fs.get("family") or "Arial",
                cjk=fs.get("cjk") or fs.get("family") or "SimSun")
            ax.add_artist(overlay)
        except Exception:
            pass                     # 富文本盖不上就退回纯文字，图不能挂
    return leg


def save_fig(fig, name, st=None, formats=None, dpi=None, out_dir=None):
    """按指定格式输出 PNG/PDF/SVG 等

    防覆盖：目标文件已存在时自动加时间戳改存（如 CV_overlay_143522.png），
    并在日志提醒——"直接输出"不会悄悄覆盖上一次的图。
    透明背景有个坑：只要给 savefig 传了 facecolor，transparent=True 就会被
    忽略（matplotlib 里 facecolor 优先）。所以要透明时必须传
    facecolor="none"，同时把坐标区底色也设成透明，否则绘图区还是一块白。
    """
    st = st or DEFAULT_STYLE
    formats = formats or ["png", "pdf"]
    dpi = int(dpi or st["canvas"]["dpi"] or 600)
    out_dir = out_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    want_trans = bool(st.get("canvas", {}).get("transparent", False))
    # jpg/jpeg 根本不支持透明，硬给会报错，这类格式自动退回不透明
    if want_trans and any(f.lower().lstrip(".") in ("jpg", "jpeg")
                          for f in formats):
        want_trans = False
    made = []
    for fmt in formats:
        fmt = fmt.lower().lstrip(".")
        from ec_export import unused_path
        dst = unused_path(os.path.join(out_dir, name + "." + fmt))
        if want_trans:
            # 坐标区底色也得一起透明，不然只有画布外圈透明
            for ax in fig.axes:
                try:
                    ax.patch.set_alpha(0.0)
                except Exception:
                    pass
            fig.savefig(dst, dpi=dpi if fmt in ("png", "tif", "tiff")
                        else None, transparent=True, facecolor="none")
        else:
            fig.savefig(dst, dpi=dpi if fmt in ("png", "jpg", "jpeg", "tif", "tiff")
                        else None, transparent=False,
                        facecolor=fig.get_facecolor())
        made.append(dst)
    return made


def _prep_ax(st, ax=None):
    """给定 ax 就在它上面画（预览用），否则按画布尺寸新建；返回 (fig, ax)"""
    if ax is not None:
        return ax.figure, ax
    w, h = figsize_inch(st)
    fig = Figure(figsize=(w, h))
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    apply_canvas_margin(fig, st)
    return fig, ax


def _emit(fig, name, st, formats, dpi, out_dir=None):
    """有 formats 就保存并关闭，否则原样返回 fig 供界面预览"""
    if formats:
        save_fig(fig, name, st, formats, dpi, out_dir)
        plt.close(fig)
        return None
    return fig


MARKER_NAMES = {
    "圆": "o", "正方形": "s", "三角形": "^", "倒三角": "v", "菱形": "D",
    "五边形": "p", "五角星": "*", "六边形": "h", "八边形": "8", "横线": "_",
}


def _nth(list_, i):
    """取列表第 i 项；越界就循环取（数据点比配色多时自动循环配色）"""
    if not list_:
        return ""
    try:
        k = int(i)
    except (TypeError, ValueError):
        return ""
    return list_[k % len(list_)] or ""


def draw_point(ax, x, y, st, i, label=None, zorder=3):
    """画一个数据点（比电容图用）：形状/填充方式/填充色/边线色都可改

    优先级：单个点单独指定的颜色 > 统一设置 > 该曲线本身的颜色。
    """
    sc = st.get("scatter", {})
    col = color_of(st, i)
    m = sc.get("marker", "o") or "o"
    fill = sc.get("fill", "实心")
    size = sc.get("size", 8) or 8
    one_face = _nth(sc.get("face_colors"), i)
    one_edge = _nth(sc.get("edge_colors"), i)
    fc = one_face or (sc.get("face_color") or "").strip() or col
    ec = one_edge or (sc.get("edge_color") or "").strip() or col
    ew = sc.get("edge_width", 1.2)
    if fill == "空心":
        fc = "none"
    if fill == "立体":                       # 先来一层偏移阴影，再叠实体点
        ax.plot([x * 1.0 + size * 0.02], [y * 1.0 + size * 0.0], marker=m,
                ms=size, color="#888888", alpha=0.45, mec="none",
                linestyle="none", zorder=zorder - 1)
        ax.plot([x], [y], marker=m, ms=size, mfc=fc, mec="white", mew=ew,
                linestyle="none", label=label, zorder=zorder)
        return
    ax.plot([x], [y], marker=m, ms=size,
            mfc=fc if fill != "空心" else "none",
            mec=ec, mew=ew, linestyle="none", label=label, zorder=zorder)


def draw_vline(ax, x, y, st, i):
    """从 0 到数据点的垂直线（颜色可跟数据点一致，也可单独改）"""
    sc = st.get("scatter", {})
    if not sc.get("vline", True):
        return
    one = _nth(sc.get("vline_colors"), i)
    col = one or (sc.get("vline_color") or "").strip() or color_of(st, i)
    ax.plot([x, x], [0, y], color=col, lw=sc.get("vline_width", 1.8),
            ls=sc.get("vline_style", "-") or "-",
            alpha=sc.get("vline_alpha", 1.0), zorder=2)


def _zero_bottom(ax, st):
    """下边界归零：只在用户没手动指定 Y 下限时生效"""
    if _limit(st["axis"].get("y_min")) is None:
        ax.set_ylim(bottom=0)


def plot_cv_overlay(results, st, formats=None, dpi=None, ax=None,
                   out_dir=None):
    fig, ax = _prep_ax(st, ax)
    ls = line_style(st)
    for i, r in enumerate(results):
        ax.plot(r["E"], r["j"], color=color_of(st, i), ls=ls,
                lw=st["line"]["width"], label=r["label"])
    finish_axes(ax, "Potential (V)", "Current density (A g^{-1})", st)
    apply_legend(ax, st)
    return _emit(fig, "CV_overlay", st, formats, dpi, out_dir)


def plot_cv_capacitance(results, st, formats=None, dpi=None, ax=None,
                       out_dir=None):
    """比电容-扫速图：每根棒一个文件，图例写明条件与数值

    X 轴可切成类别轴（扫速 2/5/10/20/50… 不均匀时均匀排布，只当文本看）。
    """
    fig, ax = _prep_ax(st, ax)
    xs = [r["scan_rate_mVs"] for r in results]
    xp, xlab = cat_positions(xs, bool(st["axis"]["categorical"].get("x")),
                             st["axis"].get("cat_labels", {}).get("x", ""))
    for i, r in enumerate(results):
        draw_vline(ax, xp[i], r["C_F_g"], st, i)
        draw_point(ax, xp[i], r["C_F_g"], st, i,
                   label=r["label"])
    finish_axes(ax, "Scan rate (mV s^{-1})",
                "Specific capacitance (F g^{-1})", st)
    if xlab:
        apply_cat_ticks(ax, "x", xp, xlab)
    _zero_bottom(ax, st)
    apply_legend(ax, st)
    return _emit(fig, "CV_capacitance", st, formats, dpi, out_dir)


def plot_gcd_overlay(results, st, formats=None, dpi=None, ax=None,
                    out_dir=None):
    """充放电曲线：一个文件（1A / 2A / …）画成一条线，几条线叠加在一起

    横坐标必须用"每个文件自己的相对时间"（都从 0 开始）：
    CHI 录进文件的是绝对时间戳，一个下午连着测的几个文件各不相同，
    直接用绝对时间会把几条曲线沿 x 轴前后排开，看着像一串而不是叠加图。
    充电段 + 放电段首尾相接（保留中间真实的弛豫间隔），同 CV 一样叠加。
    """
    fig, ax = _prep_ax(st, ax)
    for i, r in enumerate(results):
        col = color_of(st, i)
        m = r["metrics"]
        cv_ = np.asarray(m["charge_V"], float)
        dv = np.asarray(m["discharge_V"], float)
        ct_raw = m.get("charge_t")
        dt_raw = m.get("discharge_t")
        ct = np.asarray(m["charge_t_abs"] if ct_raw is None else ct_raw, float)
        dt = np.asarray(m["discharge_t_abs"] if dt_raw is None else dt_raw,
                        float)
        if ct_raw is None:                # 老数据兜底：自己减成相对时间
            ct = ct - ct[0]
        if dt_raw is None:
            dt = dt - dt[0]
        # 充放电之间真实的松弛间隔（没有就用 0）
        gap = 0.0
        if m.get("charge_t_abs") is not None and m.get("discharge_t_abs") is not None:
            gap = max(0.0, float(np.asarray(m["discharge_t_abs"])[0]
                                 - np.asarray(m["charge_t_abs"])[-1]))
        t = np.concatenate([ct, dt + ct[-1] + gap])
        ax.plot(t, np.concatenate([cv_, dv]), ls=line_style(st),
                color=col, lw=st["line"]["width"], label=r["label"])
    finish_axes(ax, "Time (s)", "Potential (V)", st)
    apply_legend(ax, st)
    return _emit(fig, "GCD_overlay", st, formats, dpi, out_dir)


def plot_gcd_capacitance(results, st, formats=None, dpi=None, ax=None,
                        out_dir=None):
    """GCD 比电容-电流密度图（X 轴同样可切成类别轴）"""
    fig, ax = _prep_ax(st, ax)
    xs = [r["current_density_A_g"] for r in results]
    xp, xlab = cat_positions(xs, bool(st["axis"]["categorical"].get("x")),
                             st["axis"].get("cat_labels", {}).get("x", ""))
    for i, r in enumerate(results):
        y = r["metrics"]["capacitance_F_g"]
        draw_vline(ax, xp[i], y, st, i)
        draw_point(ax, xp[i], y, st, i,
                   label=r["label"])
    finish_axes(ax, "Current density (A g^{-1})",
                "Specific capacitance (F g^{-1})", st)
    if xlab:
        apply_cat_ticks(ax, "x", xp, xlab)
    _zero_bottom(ax, st)
    apply_legend(ax, st)
    return _emit(fig, "GCD_capacitance", st, formats, dpi, out_dir)


def plot_cycle_stability(cycles, caps, name, st, formats=None, dpi=None,
                         ax=None, out_dir=None):
    """循环稳定性：左轴比电容衰减 + 右轴容量保持率"""
    fig, ax = _prep_ax(st, ax)
    n = np.asarray(cycles)
    base = caps[0] if caps[0] else np.nan
    ret = 100.0 * np.asarray(caps) / base

    ax.plot(n, caps, ls=line_style(st), marker="o",
            ms=st["line"]["marker"] * 0.9,
            lw=st["line"]["width"] * 0.9, color=color_of(st, 0),
            mec="white", mew=0.8, label="Capacitance")
    finish_axes(ax, "Cycle number", "Specific capacitance (F g^{-1})", st)
    _zero_bottom(ax, st)
    span = max(cycles) - min(cycles)
    step = _tick_step(st, "x_major", min(cycles), max(cycles))
    if span / max(step, 1e-9) > 30:      # 防止刻度过密糊成一片
        step = max(1, int(round(span / 8)))
        mag = 10 ** math.floor(math.log10(step))
        step = min(m * mag for m in (1, 2, 5, 10) if m * mag >= step)
    ax.xaxis.set_major_locator(MultipleLocator(step))

    ax2 = ax.twinx()
    ax2.plot(n, ret, "s--", ms=st["line"]["marker"] * 0.8,
             lw=st["line"]["width"] * 0.7, color=color_of(st, 2), alpha=0.85,
             label="Retention")
    ax2.set_ylabel("Retention (%)")
    ax2.set_ylim(0, 110)
    ax2.tick_params(axis="y", direction=st["axis"]["tick_dir"])
    # 两条曲线共用一张图例（文字也可自定义）
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    if st["legend"]["show"]:
        lg = st["legend"]
        labels = l1 + l2
        for i, txt in enumerate(lg.get("items") or []):
            if i < len(labels) and (txt or "").strip():
                labels[i] = txt
        ax.legend(h1 + h2, labels, loc=lg["loc"], ncol=lg["ncol"],
                  frameon=lg["frameon"], fontsize=st["font"]["legend"],
                  framealpha=lg.get("alpha", 1.0),
                  handlelength=lg.get("handle_length", 2.0),
                  handleheight=lg.get("handle_height", 0.7),
                  handletextpad=lg.get("handle_textpad", 0.8),
                  labelspacing=lg.get("label_spacing", 0.5),
                  columnspacing=lg.get("column_spacing", 2.0))
    return _emit(fig, "stability_" + name, st, formats, dpi, out_dir)


def _axis_limits(st, zr, neg_zi):
    """EIS 坐标范围：手动优先，否则自动（等比时两轴取同一上限）

    EIS 面板自己的 x_max/y_max 优先于通用坐标范围，通用范围次之，
    两处都没填才自动算 —— 这样图例里改的范围同样能锁住。
    """
    e = st["eis"]
    a = st["axis"]
    hi_data = float(max(zr.max(), neg_zi.max()))
    lo_data = float(min(zr.min(), neg_zi.min()))
    xhi = float(e["x_max"]) if e.get("x_max") else (
        _limit(a.get("x_max")) or nice_ceiling(hi_data * 1.05))
    yhi = float(e["y_max"]) if e.get("y_max") else (
        _limit(a.get("y_max")) or
        (xhi if e.get("equal_scale") else nice_ceiling(neg_zi.max() * 1.05)))
    lo = _limit(a.get("x_min"))
    if lo is None:
        lo = _limit(a.get("y_min"))
    if lo is None:
        lo = min(0.0, lo_data)
    if e.get("equal_scale"):
        xhi = yhi = max(xhi, yhi)
    return lo, xhi, yhi


def plot_eis_nyquist(items, name, st, formats=None, dpi=None, ax=None,
                     out_dir=None):
    """Nyquist 图；items = [(label, f, zr, zi), ...]"""
    fig, ax = _prep_ax(st, ax)
    all_zr, all_zi = None, None
    for i, it in enumerate(items):
        label, f, zr, zi = it[:4]
        style = it[4] if len(it) > 4 else "o"
        lw = it[5] if len(it) > 5 else st["line"]["width"]
        nzi = -np.asarray(zi)
        ax.plot(zr, nzi, style, ms=st["line"]["marker"], lw=lw,
                color=color_of(st, i), mec="white", mew=0.6, label=label)
        all_zr, all_zi = zr, nzi

    lo, xhi, yhi = _axis_limits(st, all_zr, all_zi)
    ax.set_xlim(lo, xhi)
    ax.set_ylim(lo, yhi)
    step = _tick_step(st, "x_major", lo, xhi)
    if st["eis"].get("equal_scale"):
        ax.set_aspect("equal", adjustable="box")
        ax.yaxis.set_major_locator(MultipleLocator(step))
    ax.xaxis.set_major_locator(MultipleLocator(step))
    finish_axes(ax, "Z' (ohm)", "-Z'' (ohm)", st)
    apply_legend(ax, st)
    return _emit(fig, "EIS_nyquist_" + name, st, formats, dpi, out_dir)


def plot_eis_fit(f, zr, zi, z_fit, name, st, formats=None, dpi=None,
                 circuit="", ax=None, out_dir=None):
    """原始点 + 拟合线"""
    fig, ax = _prep_ax(st, ax)
    nzi = -np.asarray(zi)
    ax.plot(zr, nzi, "o", ms=st["line"]["marker"], mfc="none",
            mec=color_of(st, 1), mew=0.9, label="Experimental")
    if z_fit is not None:
        ax.plot(z_fit.real, -z_fit.imag, ls=line_style(st),
                lw=st["line"]["width"],
                color=color_of(st, 2),
                label=("Fit: " + circuit) if circuit else "Fit")

    lo, xhi, yhi = _axis_limits(st, np.asarray(zr), nzi)
    ax.set_xlim(lo, xhi)
    ax.set_ylim(lo, yhi)
    step = _tick_step(st, "x_major", lo, xhi)
    if st["eis"].get("equal_scale"):
        ax.set_aspect("equal", adjustable="box")
        ax.yaxis.set_major_locator(MultipleLocator(step))
    ax.xaxis.set_major_locator(MultipleLocator(step))
    finish_axes(ax, "Z' (ohm)", "-Z'' (ohm)", st)
    apply_legend(ax, st)
    if st["eis"].get("inset"):
        try:
            ix = st["eis"].get("inset_x_max") or max(xhi * 0.12, zr[0] * 2)
            axi = ax.inset_axes([0.55, 0.55, 0.4, 0.4])
            axi.plot(zr, nzi, "o", ms=3, mfc="none",
                     mec=color_of(st, 1), mew=0.7)
            if z_fit is not None:
                axi.plot(z_fit.real, -z_fit.imag, "-", lw=1.2,
                         color=color_of(st, 2))
            axi.set_xlim(min(0, zr.min()), ix)
            axi.set_ylim(0, ix)
            axi.set_aspect("equal", adjustable="box")
            axi.tick_params(labelsize=max(6, st["font"]["tick"] - 3),
                            direction=st["axis"]["tick_dir"])
        except Exception:
            pass
    return _emit(fig, "EIS_fit_" + name, st, formats, dpi, out_dir)


# ==================================================================
# 六、质量登记
# ==================================================================

def mass_from_name(names):
    """从文件名/相对路径提取质量：...-1.6mg-CV循环 或 1.6mg_cv_2000圈

    文件名没写质量时（如 循环-100mV-2030.txt），常写在目录名里，
    所以对相对路径（含目录）一并搜索。
    """
    for n in names:
        m = re.search(r"(\d+(?:\.\d+)?)\s*mg", n, re.I)
        if m:
            return float(m.group(1))
    return None


def get_mass(cfg, names, path):
    """获取样品质量（g）：config 登记优先，其次 '*' 兜底，再次文件名/目录名提取"""
    table = cfg.get("mass_mg", {})
    mg = None
    for n in names:
        if n in table and table[n] is not None:
            mg = table[n]
            break
    if mg is not None:
        src = "config 登记"
    elif isinstance(table.get("*"), (int, float)):
        mg = float(table["*"])
        src = "config 兜底(*)"
    else:
        mg = mass_from_name(list(names) + [path])
        src = "文件名自动提取"
    if mg is None:
        print(f"    [跳过] {os.path.basename(path)}：未登记质量"
              f"（样品名 = {names[0]}），请在表格里填写")
        return None
    try:
        mg = float(mg)
    except (TypeError, ValueError):
        mg = np.nan
    if not np.isfinite(mg) or mg <= 0:
        print(f"    [跳过] {os.path.basename(path)}：质量必须是有限正数（mg），请核对登记值")
        return None
    if not (0.05 <= mg <= 20):
        print(f"    [警告] {os.path.basename(path)} 质量 {mg} mg "
              f"超出常识范围，请确认")
    if src == "文件名自动提取":
        print(f"      质量 {mg:g} mg（从文件名提取）")
    mass_g = mg / 1000.0
    if not np.isfinite(mass_g) or mass_g <= 0:
        print(f"    [跳过] {os.path.basename(path)}：质量换算为 g 后超出可计算范围")
        return None
    return mass_g


# ==================================================================
# 七、扫描与主流程
# ==================================================================

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"([0-9]+)", s)]


def dirs_of(cfg):
    d = cfg.get("data_dir", [])
    return [d] if isinstance(d, str) else list(d)


def scan_files(cfg):
    """递归扫描数据目录；返回 ({"CV":[],"GCD":[],"EIS":[]}, skipped列表)

    注意：文件名排除规则（skip_keywords_cv / exclude_filename）在这里就生效，
    否则界面上勾了"跳过含活化的 CV"、文件列表里却照样出现，看着像程序坏了。
    """
    dirs = dirs_of(cfg)
    excl = cfg.get("exclude_filename", ["-fit", "副本"])
    skip_cv = cfg.get("skip_keywords_cv", ["活化"])
    skip_gcd = cfg.get("skip_keywords_gcd", [])
    found = {"CV": [], "GCD": [], "EIS": []}
    skipped = []
    paths = []
    for data_dir in dirs:
        paths += glob.glob(os.path.join(data_dir, "**", "*.txt"),
                           recursive=True)
    for path in paths:
        name = os.path.basename(path)
        if name.startswith("~$"):
            continue
        stem = os.path.splitext(name)[0]
        if any(e in name for e in excl):
            skipped.append(name)
            continue
        try:
            text = read_text(path)
        except Exception:
            continue
        kind = detect_kind(text)
        if kind in ("SKIP", "FIT"):       # ZView 拟合结果单独用，不算原始数据
            continue
        if kind == "CV" and any(k in stem for k in skip_cv):
            skipped.append(name)          # 活化数据不参与计算与作图
            continue
        if kind == "GCD" and any(k in stem for k in skip_gcd):
            skipped.append(name)
            continue
        if kind:
            found[kind].append(path)
    # 去重：data_dir 同时含父目录与子目录时，递归 glob 会把同一批文件扫到多次；
    # 路径分隔符不一致（如 "2mg\GCD\1A.txt" 与 "2mg/GCD\1A.txt"）会让朴素去重失效，
    # 故统一用 normpath(abspath) 归一并按原始路径去重。
    for k in found:
        seen, uniq = set(), []
        for p in found[k]:
            key = os.path.normpath(os.path.abspath(p))
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        found[k] = uniq
        found[k].sort(key=lambda p: natural_key(os.path.basename(p)))
    return found, skipped


def unique_tag(path, roots):
    """用相对路径生成不重复的文件名（不同文件夹下常有同名文件）"""
    if isinstance(roots, str):
        roots = [roots]
    rel = None
    for r in roots:
        try:
            candidate = os.path.relpath(path, r)
        except ValueError:
            continue
        if rel is None or len(candidate) < len(rel):
            rel = candidate
    if rel is None:
        rel = os.path.basename(path)
    tag = rel.replace(os.sep, "_")
    if tag.lower().endswith(".txt"):
        tag = tag[:-4]
    for ch in ' ()（）[]【】+':
        tag = tag.replace(ch, "-")
    return tag


def short_label(tag, maxlen=28):
    """图例短名：过长时截断，避免图例占满画面"""
    return tag if len(tag) <= maxlen else "..." + tag[-(maxlen - 3):]


def _migrate_titles(cfg):
    """老配置的 axis.titles = {"x":"","y":""} 表示"用默认标题"

    现在的规则是"留空 = 真的不画"，所以老配置得把这种空标题整个键删掉，
    删掉之后引擎才会回退到这张图的默认标题。已经迁移过的靠标记位跳过。
    """
    if not isinstance(cfg, dict) or cfg.get("_titles_migrated"):
        return False
    hit = False

    def clean(axis):
        nonlocal hit
        ti = axis.get("titles")
        if isinstance(ti, dict) and not any(
                str(v or "").strip() for v in ti.values()):
            axis.pop("titles", None)
            hit = True

    clean((cfg.get("plot_style") or {}).get("axis") or {})
    for v in (cfg.get("plot_style_by_kind") or {}).values():
        clean((v or {}).get("axis") or {})
    cfg["_titles_migrated"] = True
    return hit


def load_config():
    """读配置。损坏时自动从备份恢复（见 cfg_guard）。

    额外返回第二个值（提示信息，CLI 下打印、GUI 下弹窗）；
    旧代码只取第一个值也不受影响。
    """
    from cfg_guard import load_config as _load
    cfg, note = _load()
    if isinstance(cfg, dict):
        try:
            _migrate_titles(cfg)
        except Exception:
            pass
    if note:
        print("[配置] " + note.replace("\n", " "))
    return cfg


def _dedupe_results(results, keyfunc, kind, verbose=True):
    """同条件只保留第一个文件参与叠加图/比电容图，其余视为撞数据"""
    seen, out, dropped = set(), [], []
    for r in results:
        k = keyfunc(r)
        if k in seen:
            dropped.append(r["file"])
        else:
            seen.add(k)
            out.append(r)
    if dropped and verbose:
        print(f"  [去重] {kind} 每个条件只取一个文件作图，"
              f"忽略撞数据 {len(dropped)} 个："
              f"{', '.join(short_label(d, 22) for d in dropped[:6])}"
              f"{'...' if len(dropped) > 6 else ''}")
    return out


def prepare(cfg):
    """第一步：识别 -> 取数 -> 计算 -> EIS 拟合（不画图、不导出）

    返回 data 字典。界面拿到它之后可以先预览、改绘图样式，
    满意了再调 render() 真正输出图片和表格。
    """
    eis_cfg = cfg.get("eis", {})
    files, skipped = scan_files(cfg)
    if "include_files" in cfg:         # 空列表表示未勾选，不应意外处理全部
        keep = set(os.path.abspath(p) for p in (cfg["include_files"] or []))
        for k in files:
            skipped += [os.path.basename(p) for p in files[k]
                        if os.path.abspath(p) not in keep]
            files[k] = [p for p in files[k] if os.path.abspath(p) in keep]

    print("=" * 70)
    for d in dirs_of(cfg):
        print("扫描目录：" + d)
    for k in ("CV", "GCD", "EIS"):
        print(f"  参与处理 {k:3s} 文件 {len(files[k])} 个")
    if skipped:
        print(f"  另有 {len(skipped)} 个文件未参与"
              f"（活化 / 副本 / ZView 拟合结果 / 界面未勾选）")
    print("=" * 70)

    want_cv = segs_of(cfg, "CV")
    want_gcd = segs_of(cfg, "GCD")
    area = cfg.get("area_cm2", 1.0)
    skip_cv = cfg.get("skip_keywords_cv", ["活化"])
    cycle_caps = {}
    anomalies = []          # 物理上不合理的计算结果，收集起来最后统一提醒

    # 处理类型开关：界面上勾了哪些就处理哪些
    proc = cfg.get("process") or {}
    do_cv = bool(proc.get("CV", True))
    do_gcd = bool(proc.get("GCD", True))
    do_eis = bool(proc.get("EIS", True))
    do_cyc = bool(proc.get("cycle", True))
    if (do_cv or do_cyc) and files["CV"]:
        try:
            area = float(area)
        except (TypeError, ValueError):
            area = np.nan
        if not np.isfinite(area) or area <= 0:
            raise ValueError("电极面积 area_cm2 必须是有限正数（cm²），请修改参数后重试。")
    on_list = [n for n, v in (("CV", do_cv), ("GCD", do_gcd),
                              ("EIS", do_eis), ("循环稳定性", do_cyc)) if v]
    print("  本次处理：" + ("、".join(on_list) if on_list else "（未选任何类型）"))
    if not on_list:
        print("  没有勾选任何处理类型，请返回勾选后再开始。")

    # ---------- CV ----------
    cv_results, cv_tables = [], []
    if not do_cv and not do_cyc:
        print("  CV 与循环都没勾，跳过 CV 文件")
        files["CV"] = []
    for path in files["CV"]:
        key = os.path.splitext(os.path.basename(path))[0]
        tag = unique_tag(path, dirs_of(cfg))
        if any(k in key for k in skip_cv):
            print(f"    [跳过] {tag}：CV 活化数据不参与计算")
            continue
        mass_g = get_mass(cfg, [tag, key], path)
        if mass_g is None:
            continue
        try:
            meta, E, I = parse_cv(path)
        except Exception as exc:
            print(f"    [跳过] {key}：解析失败（{exc}）")
            continue
        sr = meta.get("scan_rate_Vs", 0)
        if not np.isfinite(sr) or sr <= 0:
            print(f"    [跳过] {key}：扫速缺失或不是有限正数（V/s）")
            continue
        if not (np.isfinite(E).all() and np.isfinite(I).all()):
            print(f"    [跳过] {key}：电位或电流包含 NaN/Inf")
            continue
        segs = split_direction(E, I)
        picked, idxs, note = pick_segments(segs, want_cv)
        if not picked:
            print(f"    [跳过] {key}：无法切出有效 segment")
            continue
        sr = meta.get("scan_rate_Vs", 0)
        print(f"  CV  {short_label(tag, 34):34s} 扫速 {sr*1000:6.1f} mV/s | {note}")
        Ec = np.concatenate([s[0] for s in picked])
        Ic = np.concatenate([s[1] for s in picked])
        j = Ic / mass_g
        C = cv_capacitance(Ec, Ic, sr, mass_g)
        if not np.isfinite(C) or C <= 0:
            print(f"    [跳过] {key}：电压窗或积分结果无效，无法计算有限正比电容")
            continue
        area_density = Ic * 1000 / area
        if not (np.isfinite(j).all() and np.isfinite(area_density).all()):
            print(f"    [跳过] {key}：电流密度超出可计算范围，请核对质量和面积单位")
            continue
        cv_tables.append(pd.DataFrame({
            "file": tag, "segment": "+".join(str(i) for i in idxs),
            "Potential_V": Ec, "Current_A": Ic,
            "CurrentDensity_A_g": j,
            "CurrentDensity_mA_cm2": area_density,
            "scan_rate_mVs": sr * 1000, "mass_mg": mass_g * 1000,
        }))
        cv_results.append({
            "label": f"{sr*1000:.0f} mV/s",
            "scan_rate_mVs": sr * 1000, "E": Ec, "j": j, "C_F_g": C,
            "file": tag, "mass_mg": mass_g * 1000,
            "source_path": os.path.abspath(path)})
        print(f"      比电容 = {C:.1f} F/g")

        if do_cyc and len(segs) >= 6:
            caps = cv_all_cycles(E, I, sr, mass_g)
            if len(caps) >= 3:
                cycle_caps[tag] = {"kind": "CV", "caps": caps}
                print(f"      循环数据：共 {len(caps)} 圈")

    # ---------- GCD ----------
    gcd_results, gcd_tables = [], []
    if not do_gcd and not do_cyc:
        print("  GCD 与循环都没勾，跳过 GCD 文件")
        files["GCD"] = []
    for path in files["GCD"]:
        key = os.path.splitext(os.path.basename(path))[0]
        tag = unique_tag(path, dirs_of(cfg))
        mass_g = get_mass(cfg, [tag, key], path)
        if mass_g is None:
            continue
        try:
            meta, t, V = parse_gcd(path)
        except Exception as exc:
            print(f"    [跳过] {key}：解析失败（{exc}）")
            continue
        I_A = meta.get("current_A", None)
        if I_A is None or not np.isfinite(I_A) or abs(I_A) <= 0:
            print(f"    [跳过] {key}：电流缺失、为零或不是有限数（A）")
            continue
        if not (np.isfinite(t).all() and np.isfinite(V).all()):
            print(f"    [跳过] {key}：时间或电位包含 NaN/Inf")
            continue
        segs = split_direction(V, t, min_span_ratio=0.1, min_pts=2)
        picked, idxs, note = pick_segments(segs, want_gcd)
        if len(picked) < 2:
            print(f"    [跳过] {key}：至少需要一段充电和一段放电")
            continue
        # 电流密度由实验电流和实际质量确定，样品编号/文件名不得改变数值。
        cd = abs(I_A) / mass_g
        if not np.isfinite(cd) or cd <= 0:
            print(f"    [跳过] {key}：电流密度超出可计算范围，请核对电流和质量单位")
            continue
        mnum = re.match(r"^(\d+(?:\.\d+)?)\s*(?:A/g|Ag|A[-_]g|A)(?:$|[._\-\s（(])", key, re.I)
        if mnum:
            named_cd = float(mnum.group(1))
            if not np.isclose(named_cd, cd, rtol=0.02, atol=0.01):
                note_cd = (f"{tag}：文件名标注 {named_cd:g} A/g，按电流和质量计算为 "
                           f"{cd:g} A/g；本次采用计算值，请核对文件名与实验参数。")
                print("    [注意] " + note_cd)
                anomalies.append(note_cd)
        print(f"  GCD {short_label(tag, 34):34s} 电流 {abs(I_A)*1000:6.2f} mA | "
              f"{cd:.2f} A/g | {note}")
        Vc = np.concatenate([s[0] for s in picked])
        tc = np.concatenate([s[1] for s in picked])
        dd = np.diff(t)
        dd = dd[dd > 0]
        dt_est = float(np.median(dd)) if len(dd) else 0.1
        chg, dis = gcd_pick_cd(picked)
        m = gcd_metrics(chg[1], chg[0], dis[1], dis[0], I_A, mass_g,
                        use_ir_free=cfg.get("ir_free", False),
                        continuous=cfg.get("gcd_continuous", False),
                        dt_est=dt_est)
        if m is None:
            print(f"    [跳过] {key}：充放电时间、质量、电流或有效电压窗无效")
            continue
        gap = max(0.0, float(m["discharge_t_abs"][0] - m["charge_t_abs"][-1]))
        gcd_tables.append(pd.DataFrame({
            "file": tag, "segment": "+".join(str(i) for i in idxs),
            "time_s": np.concatenate([m["charge_t"],
                                      m["discharge_t"] + m["charge_t"][-1] + gap]),
            "Potential_V": np.concatenate([m["charge_V"], m["discharge_V"]]),
            "time_abs_s": np.concatenate([m["charge_t_abs"], m["discharge_t_abs"]]),
            "time_phase_s": np.concatenate([m["charge_t"], m["discharge_t"]]),
            "phase": ["charge"] * len(m["charge_t"]) + ["discharge"] * len(m["discharge_t"]),
            "current_A": abs(I_A), "current_density_A_g": cd,
            "mass_mg": mass_g * 1000,
        }))
        gcd_results.append({"label": f"{cd:g} A/g",
                            "current_density_A_g": cd, "metrics": m,
                            "file": tag, "mass_mg": mass_g * 1000,
                            "current_A": abs(I_A), "source_path": os.path.abspath(path)})
        ce = m["coulombic_eff_%"]
        ce_txt = (f" | 库伦效率 {ce:.1f}%" if ce is not None
                  else " | 库伦效率 不适用（独立充放电测试）")
        print(f"      放电 {m['t_discharge_s']:.1f} s | IR drop "
              f"{m['IR_drop_V']*1000:.1f} mV | 比电容 "
              f"{m['capacitance_F_g']:.1f} F/g{ce_txt}")
        # 库伦效率 >105% 物理上不可能：多半是起始就有剩余电量（测试没跑满
        # 稳态循环）或取到了跨段数据。必须显式提醒，否则小白会直接抄进论文。
        if ce is not None and ce > 105:
            anomalies.append(
                f"{short_label(tag, 30)}：库伦效率 {ce:.0f}%（>100% 不合物理）"
                f"—— 放电时间 {m['t_discharge_s']:.0f} s 比充电 "
                f"{m['t_charge_s']:.0f} s 还长，说明起始电极没放空，"
                f"或这段测试还没进入稳态。建议换后面的 segment 取数，"
                f"或直接在论文里不报这个数。")
        if ce is not None and ce < 50 and cfg.get("gcd_continuous", False):
            anomalies.append(
                f"{short_label(tag, 30)}：库伦效率只有 {ce:.0f}%，"
                f"可能有副反应或漏电流，建议核对电流设置与测试时长。")

        allc = (gcd_all_cycles(t, V, I_A, mass_g, cfg.get("ir_free", False))
                if do_cyc else [])
        if len(allc) >= 3:
            cycle_caps[tag] = {"kind": "GCD",
                               "caps": [x["capacitance_F_g"] for x in allc]}
            print(f"      循环数据：共 {len(allc)} 圈")

    # ---------- EIS ----------
    eis_items, fit_rows = [], []
    do_fit = eis_cfg.get("fit", True)
    circuit = eis_cfg.get("circuit", "auto")
    use_ext = eis_cfg.get("use_external_fit", True)
    if not do_eis:
        print("  EIS 没勾，跳过阻抗数据")
        files["EIS"] = []
    for path in files["EIS"]:
        key = os.path.splitext(os.path.basename(path))[0]
        try:
            meta, f, zr, zi = parse_eis(path)
        except Exception as exc:
            print(f"    [跳过] {key}：解析失败（{exc}）")
            continue
        tag = unique_tag(path, dirs_of(cfg))
        print(f"  EIS {short_label(tag, 34):34s} 频点 {len(f):3d} | "
              f"Rs ≈ {zr[0]:.2f} ohm")
        item = {"tag": tag, "key": key, "f": f, "zr": zr, "zi": zi,
                "z_fit": None, "fit_f": None, "circuit": "", "source": "未拟合",
                "source_path": os.path.abspath(path)}

        if use_ext:                      # 优先用同目录的 ZView 拟合结果
            fit_path = find_fit_file(path)
            if fit_path:
                par = parse_zview_fit(fit_path)
                if par is not None:
                    fit_f, _, _, zrf, zif = par
                    item.update({"fit_f": fit_f, "z_fit": zrf + 1j * zif,
                                 "circuit": "ZView " + os.path.basename(
                                     fit_path),
                                 "source": "ZView 外部拟合"})
                    fit_rows.append({"file": tag, "source": "ZView 外部拟合",
                                     "circuit": "由 ZView 给出",
                                     "fit_file": os.path.basename(fit_path)})
                    print(f"      [拟合] 使用外部拟合结果 "
                          f"{os.path.basename(fit_path)}")

        if do_fit and item["z_fit"] is None:
            d_fit, z_fit, rep = fit_eis(f, zr, zi, circuit)
            print(f"      [拟合] {rep}")
            if d_fit:
                item.update({"z_fit": z_fit, "fit_f": f.copy(), "circuit": d_fit["circuit"],
                             "source": "本程序拟合"})
                fit_rows.append({"file": tag, **d_fit})

        eis_items.append(item)

    # ---------- 数据合理性提醒 ----------
    if anomalies:
        print("-" * 66)
        print(f"  [注意] 有 {len(anomalies)} 处结果物理上不合理，"
              f"抄进论文前务必核对：")
        for i, a in enumerate(anomalies, 1):
            print(f"    {i}. {a}")
        print("-" * 66)

    return {
        "cfg": cfg, "cv": cv_results, "gcd": gcd_results,
        "cv_tables": cv_tables, "gcd_tables": gcd_tables,
        "eis": eis_items, "cycles": cycle_caps, "fit_rows": fit_rows,
        "skipped": skipped, "anomalies": anomalies,
        "source_files": [p for group in files.values() for p in group],
    }


# ==================================================================
# 八、第二步：出图 + 导出（界面可先预览再决定）
# ==================================================================

def _plot_targets(data, cfg=None, verbose=True):
    """按去重规则挑出真正参与作图的文件（撞数据只留一个）"""
    cfg = cfg or data["cfg"]
    cv, gcd = list(data["cv"]), list(data["gcd"])
    if cfg.get("dedupe_condition", True):
        cv = _dedupe_results(cv, lambda r: round(r["scan_rate_mVs"], 3),
                             "CV", verbose=verbose)
        gcd = _dedupe_results(gcd,
                              lambda r: round(r["current_density_A_g"], 3),
                              "GCD", verbose=verbose)
    cv.sort(key=lambda r: r["scan_rate_mVs"])
    gcd.sort(key=lambda r: r["current_density_A_g"])
    return cv, gcd


def cycle_points(caps, cfg, kind="CV"):
    """循环数据 -> (圈号列表, 比电容列表)，按起始圈与步长取样

    CV 与 GCD 用各自的循环参数（cv_cycle_start / gcd_cycle_start 等），
    老配置只有 cycle_start / cycle_step 时两边共用。
    """
    kind = str(kind or "CV").upper()
    pre = "gcd" if kind == "GCD" else "cv"
    start = max(1, int(cfg.get(f"{pre}_cycle_start",
                              cfg.get("cycle_start", 10))))
    step = max(1, int(cfg.get(f"{pre}_cycle_step",
                             cfg.get("cycle_step", 10))))
    idx = list(range(start - 1, len(caps), step))
    if not idx:
        return [], []
    return [i + 1 for i in idx], [caps[i] for i in idx]


def segs_of(cfg, kind):
    """取某类（CV / GCD）要用的 segment；没单独设就用通用 pick_segments"""
    pre = "gcd" if str(kind).upper() == "GCD" else "cv"
    v = cfg.get(f"{pre}_segments")
    if isinstance(v, (list, tuple)) and len(v):
        return [int(x) for x in v]
    return [int(x) for x in cfg.get("pick_segments", [2, 3])]


def export_tables(data, cfg=None, out_dir=None):
    """只导出处理结果 Excel/CSV/ZView，不生成图片，返回工作簿路径。"""
    from ec_export import export_tables as write_tables
    return write_tables(data, cfg=cfg, out_dir=out_dir)


def render(data, cfg=None, formats=None, dpi=None, out_dir=None):
    """第二步：按当前样式出图 + 导出表格（data 来自 prepare）"""
    cfg = cfg or data["cfg"]
    st = get_style(cfg)                 # 保留一个通用样式给导出用
    out_cfg = cfg.get("output", {})
    formats = formats or out_cfg.get("formats", ["png", "pdf"])
    dpi = dpi or out_cfg.get("dpi", st["canvas"]["dpi"])
    out_dir = out_dir or out_cfg.get("dir") or OUTPUT_DIR
    from ec_export import validate_output_dir, input_directories
    out_dir = validate_output_dir(out_dir, input_directories(data, cfg))
    os.makedirs(out_dir, exist_ok=True)

    print("-" * 66)
    cv_plot, gcd_plot = _plot_targets(data, cfg)
    if cv_plot:                          # CV 两张图各用各的样式
        st_a = get_style(cfg, "cv_overlay")
        apply_style(st_a)
        plot_cv_overlay(cv_plot, st_a, formats, dpi, out_dir=out_dir)
        st_b = get_style(cfg, "cv_cap")
        apply_style(st_b)
        plot_cv_capacitance(cv_plot, st_b, formats, dpi, out_dir=out_dir)
        print("    [图] CV_overlay / CV_capacitance")
    if gcd_plot:                         # GCD 两张图各用各的样式
        st_a = get_style(cfg, "gcd_overlay")
        apply_style(st_a)
        plot_gcd_overlay(gcd_plot, st_a, formats, dpi, out_dir=out_dir)
        st_b = get_style(cfg, "gcd_cap")
        apply_style(st_b)
        plot_gcd_capacitance(gcd_plot, st_b, formats, dpi, out_dir=out_dir)
        print("    [图] GCD_overlay / GCD_capacitance")

    n_eis = 0
    st_eis = get_style(cfg, "EIS")
    apply_style(st_eis)
    for it in data["eis"]:
        if it["z_fit"] is not None:
            plot_eis_fit(it["f"], it["zr"], it["zi"], it["z_fit"],
                         it["tag"], st_eis, formats, dpi,
                         circuit=it["circuit"], out_dir=out_dir)
        else:
            plot_eis_nyquist([(it["key"], it["f"], it["zr"], it["zi"])],
                             it["tag"], st_eis, formats, dpi,
                             out_dir=out_dir)
        n_eis += 1
    if n_eis:
        print(f"    [图] EIS {n_eis} 张")

    # 循环绘图与表格导出分开，使“仅处理数据”入口无需创建任何画布。
    st_cyc = get_style(cfg, "cycle")
    for name, rec in data.get("cycles", {}).items():
        caps = rec["caps"] if isinstance(rec, dict) else rec
        kind = rec.get("kind", "CV") if isinstance(rec, dict) else "CV"
        cyc, vals = cycle_points(caps, cfg, kind)
        if cyc:
            apply_style(st_cyc)
            plot_cycle_stability(cyc, vals, name, st_cyc, formats, dpi, out_dir=out_dir)
    xlsx = export_tables(data, cfg, out_dir=out_dir)
    print("=" * 66)
    print("全部完成，结果在：" + out_dir)
    return xlsx


def process_all(cfg):
    """命令行主流程：prepare + render 一步到位"""
    return render(prepare(cfg), cfg)


# ==================================================================
# 九、预览：界面在输出前先看效果
# ==================================================================

def preview_list(data, cfg=None):
    """列出可预览的图：[(key, 显示名)]"""
    cfg = cfg or data["cfg"]
    cv, gcd = _plot_targets(data, cfg, verbose=False)
    items = []
    if cv:
        items.append(("CV_overlay", "CV 叠加图"))
        items.append(("CV_capacitance", "CV 比电容图"))
    if gcd:
        items.append(("GCD_overlay", "GCD 充放电曲线"))
        items.append(("GCD_capacitance", "GCD 比电容图"))
    for i, it in enumerate(data["eis"]):
        items.append((f"EIS:{i}", "EIS " + short_label(it["tag"], 26)
                      + ("（含拟合）" if it["z_fit"] is not None
                         else "（仅原始点）")))
    for name, rec in data["cycles"].items():
        kind = rec.get("kind", "CV") if isinstance(rec, dict) else "CV"
        items.append((f"cycle:{name}", f"循环稳定性·{kind} "
                      + short_label(name, 22)))
    return items


def draw_figure(data, key, cfg=None):
    """画一张预览图，返回 (fig, 标题)；不保存文件"""
    cfg = cfg or data["cfg"]
    st = get_style(cfg, kind_of_key(key))
    apply_style(st)
    cv, gcd = _plot_targets(data, cfg, verbose=False)

    if key == "CV_overlay":
        return plot_cv_overlay(cv, st, ax=None), "CV 叠加图"
    if key == "CV_capacitance":
        return plot_cv_capacitance(cv, st, ax=None), "CV 比电容 - 扫速"
    if key == "GCD_overlay":
        return plot_gcd_overlay(gcd, st, ax=None), "GCD 充放电曲线"
    if key == "GCD_capacitance":
        return plot_gcd_capacitance(gcd, st, ax=None), "GCD 比电容 - 电流密度"
    if key.startswith("EIS:"):
        it = data["eis"][int(key[4:])]
        if it["z_fit"] is not None:
            return (plot_eis_fit(it["f"], it["zr"], it["zi"], it["z_fit"],
                                 it["tag"], st, ax=None,
                                 circuit=it["circuit"]),
                    "EIS " + short_label(it["tag"], 30))
        return (plot_eis_nyquist([(it["key"], it["f"], it["zr"], it["zi"])],
                                 it["tag"], st, ax=None),
                "EIS " + short_label(it["tag"], 30) + "（未拟合）")
    if key.startswith("cycle:"):
        name = key[6:]
        rec = data["cycles"].get(name, [])
        caps = rec["caps"] if isinstance(rec, dict) else rec
        kind = rec.get("kind", "CV") if isinstance(rec, dict) else "CV"
        cyc, vals = cycle_points(caps, cfg, kind)
        return (plot_cycle_stability(cyc, vals, name, st, ax=None),
                f"循环稳定性·{kind} " + short_label(name, 26))
    return None, ""


def main():
    cfg = load_config()
    process_all(cfg)


if __name__ == "__main__":
    main()
