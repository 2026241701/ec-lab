# -*- coding: utf-8 -*-
"""轴标题效果对比图"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import ec_gui as G
import eclab

OUT = os.path.dirname(os.path.abspath(__file__))
x = np.linspace(-0.88, 0.45, 400)
res = [{"E": x, "j": np.sin(x * 7) * 6, "label": "1.6 mg-5 mV/s"},
       {"E": x, "j": np.sin(x * 7) * 3.2, "label": "1.6 mg-10 mV/s"}]

def base():
    st = eclab.deep_merge(eclab.DEFAULT_STYLE, {})
    st["canvas"]["width"], st["canvas"]["height"] = 180.0, 140.0
    st["canvas"]["unit"] = "mm"
    st["font"]["family"] = "Times New Roman"
    return st

def render(st, path):
    w, h = eclab.figsize_inch(st)
    fig, ax = plt.subplots(figsize=(w, h))
    eclab.plot_cv_overlay(res, st, ax=ax)
    fig.subplots_adjust(left=0.21, right=0.97, top=0.95, bottom=0.165)
    fig.savefig(path, dpi=120, facecolor="white")
    plt.close(fig)
    print("->", os.path.basename(path))

# 默认标题
st = base()
render(st, os.path.join(OUT, "shot_标题_默认.png"))

# 全套自定义
st = base()
st["axis"]["titles"] = {"x": "E_{applied} (V)",
                        "y": "Current density (A g^{-1})"}
st["axis"]["title_size"] = {"x": 17, "y": 15}
st["axis"]["title_cfg"]["x"] = {"color": "#C1440E", "pad": 14,
                                "weight": "bold"}
st["axis"]["title_cfg"]["y"] = {"color": "#0A6E8A", "pad": 12,
                                "style": "italic"}
render(st, os.path.join(OUT, "shot_标题_全套.png"))

# 手动微调 + 上下标参数
st = base()
st["axis"]["titles"] = {"x": "E_{applied} (V)",
                        "y": "Current density (A g^{-1})"}
st["axis"]["title_size"] = {"x": 16, "y": 14}
st["axis"]["title_cfg"]["x"] = {"color": "#B2182B", "pad": 22,
                                "shift_x": 45, "shift_y": 8,
                                "weight": "bold"}
st["axis"]["title_cfg"]["y"] = {"color": "#2166AC", "pad": 16,
                                "sub_ratio": 0.58, "rise": 0.52,
                                "drop": 0.26}
render(st, os.path.join(OUT, "shot_标题_微调.png"))

# 轴标题页签截图（离屏中文会是方块，看布局）
os.environ["QT_QPA_PLATFORM"] = "offscreen"
matplotlib.use("QtAgg")
from PySide6.QtWidgets import QApplication, QTabWidget
app = QApplication.instance() or QApplication([])
pnl = G.StylePanel()
pnl.set_styles({"cv_overlay": eclab.DEFAULT_STYLE}, {})
pnl.resize(600, 940)
pnl.show()
app.processEvents()
tabs = pnl.findChild(QTabWidget)
for i in range(tabs.count()):
    if tabs.tabText(i) == "轴标题":
        tabs.setCurrentIndex(i)
pnl.ed_x.set_values("E_{applied} (V)", 16,
                    {"color": "#C1440E", "pad": 14, "weight": "bold"})
pnl.ed_y.set_values("Current density (A g^{-1})", 15,
                    {"color": "#0A6E8A", "pad": 12, "sub_ratio": 0.6})
app.processEvents()
pnl.grab().save(os.path.join(OUT, "shot_轴标题页.png"))
print("-> shot_轴标题页.png")
