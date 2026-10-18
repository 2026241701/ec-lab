# -*- coding: utf-8 -*-
"""截「配色方案」页的图，肉眼确认紧凑度 + 按钮布局"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")
from PySide6.QtWidgets import QApplication
import ec_palette as P
import ec_gui as G

app = QApplication.instance() or QApplication([])
HERE = os.path.dirname(os.path.abspath(__file__))

# 用临时配色目录：截图要几套示例配色，但绝不能写进用户真实的「我的配色」
import tempfile
import json
import shutil
_TMP = tempfile.mkdtemp(prefix="ec_shot63_")
P.PALETTE_DIR = os.path.join(_TMP, "我的配色")
P.PALETTE_JSON = os.path.join(_TMP, "记忆.json")
os.makedirs(P.PALETTE_DIR, exist_ok=True)
json.dump({"recents": [], "groups": [], "counter": 0},
          open(P.PALETTE_JSON, "w", encoding="utf-8"))

# 塞几套进去，看看一屏能显示多少套
for nm, cs in (("我的深蓝", ["#0A6E8A", "#0072B2", "#38699E", "#56B4E9"]),
               ("橙红渐变", ["#C1440E", "#D2603A", "#E69F00", "#F2A900"]),
               ("单色方案", ["#1F6E5A"]),
               ("灰度投稿", ["#000000", "#404040", "#737373", "#A6A6A6",
                          "#D9D9D9"]),
               ("冷暖对比", ["#38699E", "#A63E76", "#1F6E5A", "#D2603A",
                          "#7A5AA8"])):
    P.save_palette(nm, cs)

d = G.ColorPickerDialog(None, "#1F6E5A")
d.resize(700, 620)
tab = d.tabs
i = [tab.tabText(k) for k in range(tab.count())].index("配色方案")
tab.setCurrentIndex(i)
d.show()
app.processEvents()
page = tab.widget(i)
out = os.path.join(HERE, "_scheme63.png")
d.grab().save(out)
print("已存", out)

# 量一下紧凑度：整页高度能塞几行
h = page.sizeHint().height()
print(f"配色方案页内容总高 = {h}px / 每套 24px  -> 一屏约可显示 "
      f"{int(620 // 26)} 套（旧版一行一套 + 大间距，一屏只有 9 套左右）")

shutil.rmtree(_TMP, ignore_errors=True)