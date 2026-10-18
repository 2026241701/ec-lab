# -*- coding: utf-8 -*-
"""端到端：图例文字带上标/下标后真能画出来（不报错、图例文字被正确转换）"""
import copy
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import eclab

st = copy.deepcopy(eclab.DEFAULT_STYLE)
st["legend"]["show"] = True
st["legend"]["items"] = ["A g^{-1}", "Fe_{3}O_{4}", "电流密度 A g^{-1}"]
print("默认字体：", st["font"]["family"], "/", st["font"]["cjk"])
eclab.apply_style(st)          # 真实出图走这一步：字体列表含中文字体
fig, ax = plt.subplots(figsize=(4, 3))
for i in range(3):
    ax.plot([0, 1], [i * 0.3, i * 0.3 + 0.5], label="s%d" % i)
leg = eclab.apply_legend(ax, st)
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "out_leg.png"), dpi=100)
print("画出来了，图例文字：")
for t in leg.get_texts():
    print("  ->", repr(t.get_text()))
plt.close(fig)
print("OK：图例上下标端到端渲染没报错")
