# -*- coding: utf-8 -*-
"""调色盘「配色方案」页：紧凑布局 + 整套用上 + 修改/另存/删除 + 单色保护"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QGridLayout
import ec_palette as P
import ec_gui as G

app = QApplication.instance() or QApplication([])

# 用临时配色目录 + 临时记忆文件，别把 t_xxx.json 落到用户真实的「我的配色」里
import tempfile
import shutil
import json
_tmp = tempfile.mkdtemp(prefix="ec_scheme63_")
P.PALETTE_DIR = os.path.join(_tmp, "我的配色")
P.PALETTE_JSON = os.path.join(_tmp, "记忆.json")
os.makedirs(P.PALETTE_DIR, exist_ok=True)
with open(P.PALETTE_JSON, "w", encoding="utf-8") as f:
    json.dump({"recents": [], "groups": [], "counter": 0}, f)
print("临时配色目录 =", P.PALETTE_DIR)


def _cleanup():
    shutil.rmtree(_tmp, ignore_errors=True)


# ---------- 1. 紧凑布局 ----------
d = G.ColorPickerDialog(None, "#1F6E5A")
tab = d.tabs
idx = [tab.tabText(i) for i in range(tab.count())].index("配色方案")
page = tab.widget(idx)

# 内置方案卡片：一套一个 widget，高度固定 24，不再是"一行一套上下拉得很开"
card = d._scheme_card("测试套", ["#111111", "#222222", "#333333"])
assert card.height() == 24 or card.minimumHeight() == 24, \
    (card.height(), card.minimumHeight())
print("方案卡片固定高 24px OK")

# 内置方案：网格两列（STANDARD_SCHEMES 6 套 -> 3 行；
# 末尾多一列是留给 stretch 的空白列，不算）
inner = None
for lay in page.findChildren(QGridLayout):
    if lay.parent() is not page and lay.count() >= len(G.STANDARD_SCHEMES):
        inner = lay
        break
assert inner is not None, "找不到内置方案的网格"
assert inner.rowCount() == (len(G.STANDARD_SCHEMES) + 1) // 2, inner.rowCount()
for i in range(len(G.STANDARD_SCHEMES)):
    w = inner.itemAtPosition(i // 2, i % 2)
    assert w is not None and w.widget() is not None, f"第 {i} 套没放进去"
print(f"内置方案 {len(G.STANDARD_SCHEMES)} 套排成 {inner.rowCount()} 行"
      f"（每行 2 套，末尾一列留白）OK")

# ---------- 2. 单色方案不再被过滤掉 ----------
p1 = P.save_palette("t_单色方案", ["#AABBCC"])
assert p1 and os.path.exists(p1)
d._reload_my_schemes()
found = [it for it in P.scan_palettes() if it.get("名称") == "t_单色方案"]
assert found, "单色方案被 scan_palettes 吞掉了"
d._set_group(["#AABBCC"])
assert d._group_colors == ["#AABBCC"], d._group_colors
assert d.picked == "#AABBCC", d.picked
assert "1 色" in d.lab_group_tip.text(), d.lab_group_tip.text()
print("单色方案：整套用上不丢、提示正确 =", d.lab_group_tip.text())

# 空 / 全非法颜色不崩
d._set_group([])
assert d._group_colors == [], d._group_colors
d._set_group(["", "  ", None])
assert d._group_colors == [], d._group_colors
d._set_group(["#abc", "#112233"])
assert d._group_colors == ["#ABC", "#112233"], d._group_colors
print("空/非法颜色不崩、#abc 短写法归一 OK")

# ---------- 3. 修改 / 删除 按钮存在且接对了底层 ----------
p2 = P.save_palette("t_三色方案", ["#010203", "#040506", "#070809"])
d._reload_my_schemes()
it = [i for i in P.scan_palettes() if i.get("名称") == "t_三色方案"][0]
assert d._can_del(it), "自己存的方案应该可删"
assert not d._can_del({"来源": "记忆"}), "记忆里的不该可删"
assert not d._can_del({"来源": ""}), "内置的不该可删"
card2 = d._scheme_card("t_三色方案", it["颜色"], item=it)
# 色块按钮也是 QPushButton（文字为空），只取有字的那些
btns = [b.text() for b in card2.findChildren(QPushButton) if b.text()]
assert btns == ["整套用上", "另存", "修改", "删除"], btns
print("自存方案四个按钮 =", btns)

card3 = d._scheme_card("内置的", ["#111111"], item=None)
btns3 = [b.text() for b in card3.findChildren(QPushButton) if b.text()]
assert btns3 == ["整套用上", "另存"], btns3
print("内置方案只有两个按钮 =", btns3)

# 不可删的方案 -> 删除按钮置灰
card4 = d._scheme_card("记忆的", ["#111111"],
                       item={"名称": "记忆的", "颜色": ["#111111"],
                             "来源": "记忆"})
b_del4 = [b for b in card4.findChildren(QPushButton)
          if b.text() == "删除"][0]
assert not b_del4.isEnabled(), "非自存的删除按钮应置灰"
print("非自存方案删除按钮置灰 OK")

# 名字太长会被省略（不撑破布局），但完整名在 tooltip
card5 = d._scheme_card("非常非常长的配色方案名字需要被省略掉才对", ["#111111"])
lb5 = [x for x in card5.findChildren(QLabel)][0]
assert lb5.toolTip().startswith("非常非常长"), lb5.toolTip()
print("长名字省略 + tooltip 保留全名 OK ->", lb5.text())

# ---------- 4. update_palette / delete_palette 真删真改 ----------
new_cols = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]
new_path = P.update_palette(it, "t_改过名", new_cols)
assert new_path == it["来源"], (new_path, it["来源"])
back = P._read_palette_json(new_path)
assert back["名称"] == "t_改过名", back
assert back["颜色"] == new_cols, back
print("update_palette 改名 + 改色 OK ->", os.path.basename(new_path))

# 再扫一次确认列表同步（老名字不能再冒出来）
names = [i["名称"] for i in P.scan_palettes()]
assert "t_改过名" in names and "t_三色方案" not in names, names
print("改完列表同步 OK（记忆里的老记录也一起清了）")

assert P.delete_palette({"来源": new_path}) is True
assert not os.path.exists(new_path)
assert not P.delete_palette({"来源": new_path}), "删第二次应失败"
names2 = [i["名称"] for i in P.scan_palettes()]
assert "t_改过名" not in names2, f"删了还从记忆里冒出来: {names2}"
print("delete_palette 删掉 + 记忆副本同步清掉 + 重复删返回 False OK")

# ---------- 5. 我存方案区清空 / 有数据两种形态 ----------
d._reload_my_schemes()
assert d._my_grid is not None and d._my_grid.count() > 0, \
    "还有单色方案 t_单色方案，列表不该是空的"
print("「我存的方案」区项数 =", d._my_grid.count())

# ---------- 6. 旧的 memory 过滤不再吞掉 1~2 色 ----------
for nm, cs in (("t_两色", ["#123456", "#654321"]),):
    P.save_palette(nm, cs)
d._reload_my_schemes()
got = {i["名称"] for i in P.scan_palettes()}
assert "t_单色方案" in got and "t_两色" in got, got
print("1 色 / 2 色方案都能扫到 OK")

_cleanup()
print("\n配色方案页 全部测试通过")

d._reload_my_schemes()
print("\n配色方案页 全部测试通过")