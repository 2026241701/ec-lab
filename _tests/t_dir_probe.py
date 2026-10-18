# -*- coding: utf-8 -*-
"""方向诊断：Y 轴标题富文本当前到底朝哪边（渲染出图目检）"""
import os
import sys
import matplotlib
matplotlib.use("Agg")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
OUT = os.path.dirname(os.path.abspath(__file__))

import matplotlib.pyplot as plt  # noqa: E402
import eclab                     # noqa: E402

TXT = "Current density (A g^{-1})"

fig = plt.figure(figsize=(5, 4), dpi=150)
ax = fig.add_subplot(111)
ax.plot([0, 1], [0, 1])
st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
st["axis"]["titles"] = {"x": "Scan rate (mV s^{-1})", "y": TXT}
eclab.set_axis_titles(ax, st, xlabel=st["axis"]["titles"]["x"],
                      ylabel=TXT)
p = os.path.join(OUT, "_dir_engine.png")
fig.savefig(p, dpi=150)
print("engine ->", p)
plt.close(fig)

# GUI 预览（竖排）
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
import ec_gui as G           # noqa: E402
prev = G.标题预览(vertical=True)
prev.set_all(text=TXT, size=14)
prev.resize(140, 260)
prev.show()
app.processEvents()
p2 = os.path.join(OUT, "_dir_preview.png")
prev.grab().save(p2)
print("preview ->", p2)
