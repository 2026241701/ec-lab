# -*- coding: utf-8 -*-
"""富文本开关 + 上下标缩放比整张图生效 回归测试

覆盖三处文字：轴标题（X/Y）、图例、文本框。
1) rich=True 时三处都走 richlabel（有覆盖层 / 有占位透明文字）
2) rich=False 时三处都原样显示，不生成富文本覆盖层
3) 只改全局 sub_ratio，三处一起变
"""
import os
import sys
import matplotlib
matplotlib.use("Agg")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
OUT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)

import matplotlib.pyplot as plt          # noqa: E402
import eclab                             # noqa: E402
import richlabel                         # noqa: E402

TITLE_X = "Scan rate (mV s^{-1})"
TITLE_Y = "Current density (A g^{-1})"
LEG = "FTO/TO@C_{2} 50 mV s^{-1}"
TXT = "Fe_{3}O_{4} @ 20 A g^{-1}"


def make(style, name):
    fig = plt.figure(figsize=(6, 4.5), dpi=150)
    ax = fig.add_subplot(111)
    ax.plot([0, 1, 2], [0, 1, 0.5], label=LEG)
    ax.plot([0, 1, 2], [0.2, 0.8, 0.4], label="plain line")
    eclab.set_axis_titles(ax, style, xlabel=TITLE_X, ylabel=TITLE_Y)
    eclab.apply_legend(ax, style)
    eclab.apply_texts(ax, style)
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=150)
    return fig, ax, path


def count_overlay(ax):
    """数图上有几个富文本覆盖层（轴标题 / 图例）"""
    n_leg = sum(1 for a in ax.get_children()
                if isinstance(a, richlabel.LegendRichText))
    # 轴标题覆盖层类名带下划线，按类名认
    n_ax = sum(1 for a in ax.get_children()
               if type(a).__name__ == "_AxisRichLabel")
    return n_ax, n_leg


def placeholder_alpha(ax):
    """轴标题占位文字应该是透明的（0.0 = 富文本接管）"""
    return (ax.xaxis.label.get_alpha(), ax.yaxis.label.get_alpha())


def base_style(rich=True, ratio=0.68):
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["axis"]["titles"] = {"x": TITLE_X, "y": TITLE_Y}
    st["axis"]["title_cfg"]["x"]["rich"] = rich
    st["axis"]["title_cfg"]["y"]["rich"] = rich
    st["legend"]["rich"] = rich
    st["legend"]["show"] = True
    st["legend"]["items"] = [LEG, "plain line"]
    st["texts"] = [{"text": TXT, "x": 0.5, "y": 0.9, "size": 13,
                    "color": "#000000", "ha": "center",
                    "frame": False, "rich": rich}]
    st["mathtext"]["sub_ratio"] = ratio
    return st


print("=" * 60)
print("1) 富文本开启：三处都应走 richlabel")
print("=" * 60)
st = base_style(rich=True)
fig, ax, p1 = make(st, "_rich_on.png")
n_ax, n_leg = count_overlay(ax)
print("  轴标题覆盖层 =", n_ax, "（应为 2）")
print("  图例覆盖层   =", n_leg, "（应为 1）")
print("  轴标题占位透明度 =", placeholder_alpha(ax), "（应为 0.0）")
assert n_ax == 2, "轴标题富文本没生效"
assert n_leg == 1, "图例富文本没生效"
assert placeholder_alpha(ax) == (0.0, 0.0), "轴标题占位没透明"
plt.close(fig)

print()
print("=" * 60)
print("2) 富文本关闭：三处都应原样显示（无覆盖层、占位不透明）")
print("=" * 60)
st = base_style(rich=False)
fig, ax, p2 = make(st, "_rich_off.png")
n_ax, n_leg = count_overlay(ax)
print("  轴标题覆盖层 =", n_ax, "（应为 0）")
print("  图例覆盖层   =", n_leg, "（应为 0）")
print("  轴标题占位透明度 =", placeholder_alpha(ax), "（应为 1.0）")
print("  X 轴标题实际文字 =", repr(ax.xaxis.get_label_text()))
assert n_ax == 0 and n_leg == 0, "关了开关还在生成富文本"
assert ax.xaxis.get_label_text() == TITLE_X, "关了开关文字被改了"
plt.close(fig)

print()
print("=" * 60)
print("3) 全局缩放比改一次，三处一起变")
print("=" * 60)
for ratio in (0.45, 0.68, 0.9):
    st = base_style(rich=True, ratio=ratio)
    fig, ax, _ = make(st, "_rich_r%s.png" % str(ratio).replace(".", ""))
    # 图例覆盖层记录的缩放比 = 全局值
    leg = [a for a in ax.get_children()
           if isinstance(a, richlabel.LegendRichText)][0]
    axl = [a for a in ax.get_children()
           if type(a).__name__ == "_AxisRichLabel"]
    ratios = [round(a.kw["sub_ratio"], 3) for a in axl]
    print("  ratio=%-5s 图例=%.3f  轴标题=%s" % (ratio, leg.sub_ratio, ratios))
    assert abs(leg.sub_ratio - ratio) < 1e-6, "图例缩放比没跟全局"
    assert all(abs(r - ratio) < 1e-6 for r in ratios), "轴标题缩放比没跟全局"
    plt.close(fig)

print()
print("产物：", p1, p2)
print("\n富文本开关 + 全局缩放比 测试全部通过")
