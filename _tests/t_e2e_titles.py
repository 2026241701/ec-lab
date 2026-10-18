# -*- coding: utf-8 -*-
"""端到端：真实样本数据 → 各类图 → 标题不串 + 位置正确 + 图上真有标题

给"用户截图那个 bug"收尾的验收脚本。不看内部对象，
只看最终 PNG 和图上真实的标签文字。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import eclab
import richlabel

OUT = os.path.join(HERE, "_e2e")
os.makedirs(OUT, exist_ok=True)

ROOTDIR = os.path.join(ROOT, "_raw", "电化学数据结构")
FAIL = []


def check(name, cond, detail=""):
    print(("  OK  " if cond else "  FAIL") + f"  {name}" +
          (f"   {detail}" if detail else ""))
    if not cond:
        FAIL.append(name)


print("准备真实数据…")
cfg0 = {
    "data_dir": [ROOTDIR], "area_cm2": 1.0,
    "pick_segments": [2, 3],
    # 质量按"样品名"匹配：GCD 是 1A/2A/…，CV 是 2/5/10/…（扫速）
    "mass_mg": {"1A": 1.0, "2A": 1.0, "5A": 1.0, "10A": 1.0, "20A": 1.0,
                "2": 1.0, "5": 1.0, "10": 1.0, "20": 1.0,
                "50": 1.0, "100": 1.0, "200": 1.0},
    "gcd_continuous": False, "dedupe_condition": False,
    "process": {"CV": True, "GCD": True, "EIS": True, "cycle": False},
}
DATA = eclab.prepare(cfg0)
print(f"数据准备完成（CV/GCD/EIS 都有）")


def gui_cfg():
    """模拟 GUI 同步后的配置：plot_style = cv_overlay（含它自己的 titles）"""
    cv = eclab.get_style({}, "cv_overlay")
    cv["axis"]["titles"] = {"x": "Potential (V)",
                            "y": "Current density (A g^{-1})"}
    return {"plot_style": cv,
            "plot_style_by_kind": {k: eclab.get_style({}, k)
                                   for k in ("cv_cap", "gcd_overlay",
                                             "gcd_cap", "EIS", "cycle")}}


def draw(cfg):
    """按 GUI 的入口拿图（draw_figure 返回 (fig, 标题) 或 fig）"""
    res = eclab.draw_figure(DATA, cfg["_key"], cfg)
    fig = res[0] if isinstance(res, tuple) else res
    fig.canvas.draw()
    return fig, fig.canvas.get_renderer()


def audit(fig, r, label):
    """标题：① 不串 ② 原生占位非空 ③ 富文本报/画一致且不被裁"""
    ax = fig.axes[0]
    want = eclab.default_titles(label)
    got = eclab.titles_on_figure(fig, label)
    check(f"{label} 标题没串", got == want, f"图上={got} 应为={want}")

    tx = (ax.xaxis.label.get_text() or "").strip()
    ty = (ax.yaxis.label.get_text() or "").strip()
    check(f"{label} 原生占位标题非空（matplotlib 才留边距）",
          bool(tx and ty), f"x={tx!r} y={ty!r}")

    fb = fig.get_window_extent(r)
    bad = []
    for a in ax.artists:
        if not isinstance(a, richlabel._AxisRichLabel):
            continue
        rep = a.get_window_extent(r)
        real = [t.get_window_extent(r) for t in a.box._texts(r, a.box._anchor)]
        if not real:
            continue
        from matplotlib.transforms import Bbox
        act = Bbox.union(real)
        if max(abs(rep.x0 - act.x0), abs(rep.y0 - act.y0),
               abs(rep.x1 - act.x1), abs(rep.y1 - act.y1)) > 1.0:
            bad.append(f"{a.which} 报/画不一致")
        if rep.x0 < -1 or rep.y0 < -1 or rep.x1 > fb.width + 1 \
                or rep.y1 > fb.height + 1:
            bad.append(f"{a.which} 被裁 "
                       f"({rep.x0:.0f},{rep.y0:.0f})-({rep.x1:.0f},{rep.y1:.0f})")
    check(f"{label} 富文本标题位置自洽且完整", not bad, "；".join(bad))


CASES = [("CV_overlay", "cv_overlay", "cv_overlay"),
         ("GCD_overlay", "gcd_overlay", "gcd_overlay"),
         ("GCD_capacitance", "gcd_cap", "gcd_cap"),
         ("EIS:0", "EIS", "EIS")]

print("\n① 各类图：标题不串、位置正确、图上真有标题")
for key, kind, label in CASES:
    cfg = gui_cfg()
    cfg["_key"] = key
    try:
        fig, r = draw(cfg)
    except Exception as e:
        check(f"{label} 能画出来", False, f"{type(e).__name__}: {e}")
        continue
    audit(fig, r, kind)
    fig.savefig(os.path.join(OUT, f"_e2e_{kind}.png"), dpi=100)
    plt.close(fig)
    print(f"       → _e2e_{kind}.png")

print("\n② 用户改过标题：只影响这一张图，别的图照旧")
cfg = gui_cfg()
cfg["_key"] = "GCD_capacitance"
cfg["plot_style_by_kind"]["gcd_cap"]["axis"]["titles"] = {
    "x": "我的电流密度", "y": ""}
fig, _r = draw(cfg)
got = eclab.titles_on_figure(fig, "gcd_cap")
check("自定义标题生效（Y 留空 = 空标题）", got == ("我的电流密度", ""), f"{got}")
plt.close(fig)
cfg = gui_cfg()
cfg["_key"] = "CV_overlay"
fig, _r = draw(cfg)
got = eclab.titles_on_figure(fig, "cv_overlay")
check("别的图没被影响", got == eclab.default_titles("cv_overlay"), f"{got}")
plt.close(fig)

print("\n③ 连续重画：标题一次都不变（用户反馈的'重画前后不一致'）")
seen = []
for _ in range(4):
    cfg = gui_cfg()
    cfg["_key"] = "GCD_capacitance"
    fig, _r = draw(cfg)
    seen.append(eclab.titles_on_figure(fig, "gcd_cap"))
    plt.close(fig)
check("四次重画标题一致", len(set(seen)) == 1, f"{seen}")

print("\n④ 缩小画布：标题跟着重排，不跑位不裁切")
for scale in (1.0, 0.75, 0.55):
    cfg = gui_cfg()
    cfg["_key"] = "CV_overlay"
    cfg["plot_style"]["canvas"]["width"] = 180.0 * scale
    cfg["plot_style"]["canvas"]["height"] = 140.0 * scale
    fig, r = draw(cfg)
    fb = fig.get_window_extent(r)
    bad = []
    for a in fig.axes[0].artists:
        if not isinstance(a, richlabel._AxisRichLabel):
            continue
        rep = a.get_window_extent(r)
        if rep.x0 < -1 or rep.y0 < -1 or rep.x1 > fb.width + 1 \
                or rep.y1 > fb.height + 1:
            bad.append(f"{a.which}=({rep.x0:.0f},{rep.y0:.0f})-"
                       f"({rep.x1:.0f},{rep.y1:.0f})")
    check(f"缩到 {int(scale * 100)}% 标题完整", not bad, "；".join(bad))
    if abs(scale - 0.55) < 1e-6:
        fig.savefig(os.path.join(OUT, "_e2e_small.png"), dpi=100)
    plt.close(fig)

print()
if FAIL:
    print(f"❌ 失败 {len(FAIL)} 项：" + "、".join(FAIL))
    sys.exit(1)
print("✅ 全部通过")
