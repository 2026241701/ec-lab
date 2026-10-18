# -*- coding: utf-8 -*-
"""Bug B 回归：标题串图 / 图上标题与编辑框不一致

要验的四件事：
  ① cv_overlay 写了自己的 titles 之后，其它 kind 拿不到它
  ② GCD 比电容图的 X 标题不是 CV 的 Potential
  ③ 每张图实际画出来的标题符合它自己的数据含义
  ④ 重新绘制前后标题一致（连画两次结果不变）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")

import eclab

FAIL = []


def check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL") + f"  {name}" +
          (f"   {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


def mk_cfg():
    """模拟 GUI _sync_cfg 的产物：plot_style = cv_overlay 那一套"""
    cv = eclab.get_style({}, "cv_overlay")
    cv["axis"]["titles"] = {"x": "Potential (V)",
                            "y": "Current density (A g^{-1})"}
    per = {}
    for k in ("cv_cap", "gcd_overlay", "gcd_cap", "EIS", "cycle"):
        s = eclab.get_style({}, k)
        per[k] = s
    return {"plot_style": cv, "plot_style_by_kind": per}


def titles_of(cfg, kind, results=None):
    """把该 kind 的图真画一遍，读图上真实用的标题

    富文本路径下原生标签存的是去掉 ^{}/_{} 标记的纯文字（那是"占位
    文字"，真字由 richlabel 画），所以比对前统一 strip 一次。
    """
    import matplotlib.pyplot as plt
    import richlabel
    st = eclab.get_style(cfg, kind)
    st["axis"].pop("titles", None)   # 只看引擎自己那张图画的标题
    fig, ax = plt.subplots()
    try:
        eclab.set_axis_titles(ax, st,
                              *eclab.default_titles(kind))
        fig.canvas.draw()
        return (richlabel.strip_markup(ax.xaxis.label.get_text()).strip(),
                richlabel.strip_markup(ax.yaxis.label.get_text()).strip())
    finally:
        plt.close(fig)


def _same(got, want):
    """忽略上下标标记的差异"""
    import richlabel
    return (richlabel.strip_markup(got[0]).strip(),
            richlabel.strip_markup(got[1]).strip()) == (
        richlabel.strip_markup(want[0]).strip(),
        richlabel.strip_markup(want[1]).strip())


print("① 基底污染：cv_overlay 写了 titles，其它 kind 拿不到")
cfg = mk_cfg()
for k in ("cv_cap", "gcd_overlay", "gcd_cap", "EIS", "cycle"):
    t = (eclab.get_style(cfg, k)["axis"] or {}).get("titles")
    check(f"{k} 没继承 cv_overlay 的 titles", t is None, f"实际={t}")

print()
print("② GCD 比电容的 X 标题不能是 Current density / Potential")
cfg2 = mk_cfg()
cfg2["plot_style_by_kind"]["gcd_cap"]["axis"]["titles"] = {
    "x": "Potential (V)", "y": "Current density (A g^{-1})"}
tx, ty = titles_of(cfg2, "gcd_cap")
check("GCD_cap 图上 X 不是 Potential", tx != "Potential (V)", f"实际={tx!r}")

print()
print("③ 每张图默认标题符合自己的数据含义")
for k in ("cv_overlay", "cv_cap", "gcd_overlay", "gcd_cap", "cycle", "EIS"):
    dx, dy = eclab.default_titles(k)
    tx, ty = titles_of(mk_cfg(), k)
    check(f"{k} 图上标题 = 默认标题", _same((tx, ty), (dx, dy)),
          f"图上=({tx!r},{ty!r}) 默认=({dx!r},{dy!r})")

print()
print("④ 重新绘制前后标题一致（连画 3 次不变）")
for k in ("cv_overlay", "gcd_cap", "EIS"):
    seq = [titles_of(mk_cfg(), k) for _ in range(3)]
    check(f"{k} 三次绘制标题一致", len(set(seq)) == 1, f"{seq}")

print()
print("⑤ titles_on_figure 读回带标记的原文（用户能接着改）")
import matplotlib.pyplot as plt
for k in ("cv_overlay", "gcd_cap"):
    st = eclab.get_style(mk_cfg(), k)
    fig, ax = plt.subplots()
    eclab.set_axis_titles(ax, st, *eclab.default_titles(k))
    got = eclab.titles_on_figure(fig, k)
    check(f"{k} 读回 = 默认标题（带 ^{{}}_{{}} 标记）", got == eclab.default_titles(k),
          f"{got}")
    plt.close(fig)

print()
print("⑥ 用户改过的标题要能读回，且不影响别的图")
st = eclab.get_style(mk_cfg(), "gcd_cap")
st["axis"]["titles"] = {"x": "我的横轴", "y": ""}
fig, ax = plt.subplots()
eclab.set_axis_titles(ax, st, *eclab.default_titles("gcd_cap"))
got = eclab.titles_on_figure(fig, "gcd_cap")
check("自定义标题读回正确", got == ("我的横轴", ""), f"{got}")
plt.close(fig)
check("别的图没被影响",
      eclab.get_style(mk_cfg(), "gcd_overlay")["axis"].get("titles") is None)

print()
if FAIL:
    print(f"❌ 失败 {len(FAIL)} 项：" + "、".join(FAIL))
    sys.exit(1)
print("✅ 全部通过")
