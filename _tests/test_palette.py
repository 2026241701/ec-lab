# -*- coding: utf-8 -*-
"""配色存储 + 调色盘 全部测试（缩略图/配色库浏览器已按需求移除）"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import matplotlib
matplotlib.use("QtAgg")
import json
import zipfile
import shutil
import tempfile
from PySide6.QtWidgets import QApplication
import ec_palette as P
import ec_gui as G

app = QApplication.instance() or QApplication([])
# 用临时配色目录 + 临时记忆文件，别把测试配色写进用户真实的「我的配色」
import tempfile
_TMP = tempfile.mkdtemp(prefix="ec_palette_")
P.PALETTE_DIR = os.path.join(_TMP, "我的配色")
P.PALETTE_JSON = os.path.join(_TMP, "记忆.json")
os.makedirs(P.PALETTE_DIR, exist_ok=True)
json.dump({"recents": [], "groups": [], "counter": 0},
          open(P.PALETTE_JSON, "w", encoding="utf-8"))
print("配色目录 =", P.PALETTE_DIR)

# ---------- 配色存储 ----------
p1 = P.save_palette("我的深色系", ["#1F6E5A", "#38699E", "#A63E76"])
p2 = P.save_palette("我的深色系", ["#D2603A", "#7A5AA8"])
p3 = P.save_palette("", ["#111111", "#222222"])
print("保存 =", os.path.basename(p1), "|", os.path.basename(p2), "|",
      os.path.basename(p3))
assert p1 != p2, "同名不该覆盖"
assert "未命名" not in os.path.basename(p3), "自动命名不该叫未命名"
assert os.path.dirname(p1) == P.PALETTE_DIR, "该固定目录，不该弹路径"
print("固定目录保存 + 同名不覆盖 + 自动命名 OK")

for c in ("#FF0000", "#00FF00", "#FF0000"):
    P.remember_color(c)
rec = P.load_memory()["recents"]
assert rec[0] == "#FF0000" and rec.count("#FF0000") == 1
print("最近用色（去重+按使用顺序）=", rec[:4])

P.remember_group("投稿灰阶", ["#000000", "#555555", "#999999", "#CCCCCC"])
P.remember_group("投稿灰阶", ["#000000", "#555555", "#999999", "#CCCCCC"])
g = P.load_memory()["groups"]
assert len([x for x in g if x["name"] == "投稿灰阶"]) == 1
print("颜色组记忆（重复不重存）OK")

items = P.scan_palettes()
assert len(items) >= 4
assert all("缩略图" not in i for i in items), "缩略图字段应已移除"
print("扫描配色 =", len(items), "套")

# 外部文件夹（含子目录）+ zip
ext = tempfile.mkdtemp(prefix="ecp_")
os.makedirs(os.path.join(ext, "sub"), exist_ok=True)
for n, c in [("A组", ["#111111", "#EEEEEE", "#888888"]),
             ("B组", ["#AA0000", "#00AA00", "#0000AA"])]:
    json.dump({"colors": c}, open(os.path.join(ext, "sub", n + ".json"), "w",
                                  encoding="utf-8"), ensure_ascii=False)
zp = os.path.join(ext, "配色包.zip")
with zipfile.ZipFile(zp, "w") as z:
    z.writestr("p1.json", json.dumps(
        {"名称": "Nature系", "colors": ["#0A6E8A", "#C1440E", "#F2A900"]},
        ensure_ascii=False))
    z.writestr("p2.json", json.dumps(
        {"名称": "冷色系", "colors": ["#264653", "#2A9D8F", "#E9C46A"]},
        ensure_ascii=False))
    z.writestr("readme.txt", "不该被读")

it2 = P.scan_palettes(ext)
allnames = [i["名称"] for i in it2] + [a for i in it2
                                      for a in i.get("别名", [])]
for want in ("A组", "B组", "Nature系", "冷色系"):
    assert want in allnames, f"缺少 {want}: {allnames}"
print("文件夹+子目录+zip 批量加载 =", len(it2), "套 OK")

# 坏文件不崩
open(os.path.join(ext, "坏.json"), "w").write("{不是 json")
bad = os.path.join(ext, "坏.zip")
open(bad, "w").write("not a zip")
P.scan_palettes(ext, bad)
print("坏 json / 坏 zip 都能跳过 OK")

# ---------- 调色盘 ----------
d = G.ColorPickerDialog(None, "#1F6E5A")
titles = [d.tabs.tabText(i) for i in range(d.tabs.count())]
print("页签 =", titles)
for want in ("标准色", "RGB", "滑块", "配色方案"):
    assert want in titles, want
# 「我用过」后来改成常驻底部（哪个页签都能点），不再是独立页签
from PySide6.QtWidgets import QGroupBox as _QGB  # noqa: E402
recs = d.findChildren(_QGB)
assert any("我用过" in g.title() for g in recs), "缺「我用过」常驻区"
print("三种选色方式 + 配色方案页 + 我用过常驻区 齐全")

d.sp_r.setValue(255)
d.sp_g.setValue(0)
d.sp_b.setValue(0)
assert d.picked == "#FF0000", d.picked
d.ed_hex.setText("#00FF00")
d._on_hex()
app.processEvents()
assert (d.sp_r.value(), d.sp_g.value(), d.sp_b.value()) == (0, 255, 0)
print("RGB 三格 ↔ HEX 双向联动 OK")

sl = dict(d._slider_rows)
sl["色相"].setValue(240)
sl["饱和"].setValue(255)
sl["明度"].setValue(255)
app.processEvents()
assert d.picked == "#0000FF", d.picked
print("HSV 三滑块联动 OK")

d.band.resize(360, 30)
h = d.band.hueAt(180)
d._on_band(h)
print("色调带取色 hue =", h, "->", d.picked)

# 明度条真画出来了（HTML 空 span 是画不出来的，必须自绘）
img = d.bar_shades.grab().toImage()
kinds = {img.pixelColor(x, y).name().upper()
         for x in range(img.width()) for y in range(img.height())}
assert len(kinds) > 6, kinds
print("明度参照条画出", len(kinds), "种深浅 OK")

b = G.色块按钮(None, "#38699E")
assert b.color() == "#38699E" and b.text() == "#38699E"
b.set_color("")
assert b.color() == ""
be = G.色块按钮(None, "", allow_empty=True)
assert "跟随" in be.text()
print("色块按钮（正常/留空/可留空）OK")

grp = ["#0A6E8A", "#C1440E", "#F2A900", "#3B7A57"]
d._set_group(grp)
assert d._group_colors == grp and d.picked == grp[0]
print("整套配色套用 + 记住整套 OK")

shutil.rmtree(ext, ignore_errors=True)
shutil.rmtree(_TMP, ignore_errors=True)
print("\n配色存储 + 调色盘 测试通过")