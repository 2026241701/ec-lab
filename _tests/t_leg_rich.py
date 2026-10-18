# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import eclab

root = os.path.abspath(os.path.join("_raw", "电化学数据结构", "CV"))
cfg = {
    "data_dir": [root], "area_cm2": 1.0, "pick_segments": [2, 3],
    "mass_mg": {"2": 1.0, "5": 1.0, "10": 1.0},
    "process": {"CV": True, "GCD": False, "EIS": False, "cycle": False},
}
data = eclab.prepare(cfg)
st = eclab.get_style(cfg, "cv_overlay")
st["legend"]["show"] = True
st["legend"]["loc"] = "upper left"
st["legend"]["frameon"] = True
st["legend"]["items"] = ["Fe_{3}O_{4} 2 mV s^{-1}", "", "TO@C1 10 mV s^{-1}"]
res = eclab.draw_figure(data, "CV_overlay", cfg) if False else None
from eclab import plot_cv_overlay
fig, ax = eclab._prep_ax(st)
# 直接用 prepare 的 CV 结果画
plot_cv_overlay(data["cv"][:3], st, ax=ax)
leg = ax.get_legend()
print("图例行数 =", len(leg.texts))
for i, t in enumerate(leg.texts):
    print("  行%d 文字=%r alpha=%.2f" % (i, t.get_text(), t.get_alpha() if t.get_alpha() is not None else 1.0))
overlays = [a for a in ax.artists if type(a).__name__ == "LegendRichText"]
print("富文本覆盖层数 =", len(overlays))
assert overlays, "没有生成富文本覆盖层"
fig.canvas.draw()   # 触发 draw，验证不抛异常
fig.savefig("_tests/_leg_rich.png", dpi=110)
print("渲染 OK，已存 _tests/_leg_rich.png")
