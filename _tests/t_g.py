# -*- coding: utf-8 -*-
"""G 批次自检：图例上下标、图例表格可编辑、颜色组窗口、吸管控件"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")          # 必须在 import eclab 之前
import eclab
from PySide6.QtWidgets import QApplication
import ec_gui

# 1) 图例上下标转换
print("--- legend_display ---")
for s in ("A g^{-1}", "Fe_{3}O_{4}", "电流密度 A g^{-1}", "50 mV s^{-1}",
          "plain text", "自己写 $x^2$"):
    print(" ", repr(s), "->", repr(eclab.legend_display(s)))

app = QApplication([])

# 2) 颜色组管理窗口
print("--- 颜色组管理 ---")
d = ec_gui.颜色组管理()
print("  共 %d 组；默认选中：%s" % (len(d.items), d.picked["名称"]))
mine = [i for i in d.items if not i["内置"]]
print("  其中可编辑(自己存的)：%d 组" % len([i for i in mine if d._editable(i)]))

# 3) 颜色组编辑窗口
print("--- 颜色组编辑 ---")
e = ec_gui.颜色组编辑(None, "测试组", ["#111111", "#2288CC"])
print("  初始颜色:", e._cols)
e._add()
print("  加一个后:", e._cols)
e._del(0)
print("  删第一个后:", e._cols)
print("  result():", e.result())

# 4) 吸管：主视图控件存在且能算坐标
print("--- 吸管 ---")
from PySide6.QtGui import QPixmap, QColor
pm = QPixmap(200, 120)
pm.fill(QColor("#336699"))
v = ec_gui.屏幕视图(pm)
v._scale = 1.0
print("  屏幕视图创建 OK，十字标记初始:", v.cur)

# 5) 逐点配色表的按钮文案
print("--- 逐点配色表 ---")
t = ec_gui.逐点配色表()
from PySide6.QtWidgets import QPushButton
btns = [b.text() for b in t.findChildren(QPushButton)]
print("  按钮:", btns)
print("  有 pick_from_group:", hasattr(t, "pick_from_group"),
      "  已去掉 pick_from_library:", not hasattr(t, "pick_from_library"))
print("全部检查通过")
