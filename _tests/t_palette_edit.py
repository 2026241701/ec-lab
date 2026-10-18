# -*- coding: utf-8 -*-
"""回归测试：调色盘「编辑重名方案」的命名 bug

背景 bug：GUI 的 _edit_my_scheme 把 item.get("名称")（显示名，重名时
带「 (2)」后缀）传给 颜色组编辑 当初始组名，用户不改名就直接
update_palette 写回，于是「 (2)」被烤进存储名。后果：两个「方案A」
变体的显示去重被破坏——一个显示「方案A」、另一个永久显示「方案A (2)」，
不再属于同一个重名家族。

修复：_edit_my_scheme 改用 item.get("原名", ...)（无后缀）初始化对话框。

本测试：
1) 行为：保存两个同名不同色方案，编辑第二个（用原名）后，
   scan 出来的条目 原名 仍应是干净的名字、显示名被重新去重成「… (2)」；
   同时验证「用显示名（带后缀）去改」会把后缀烤进存储名（即 bug 复现）。
2) 白盒：源码 _edit_my_scheme 用 原名 初始化对话框。
"""
import os
import sys
import json
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ec_palette as P              # noqa: E402
import ec_gui                          # noqa: E402

SRC = open(os.path.join(ROOT, "ec_gui.py"), encoding="utf-8").read()


def check(name, cond):
    print(("✅ " if cond else "❌ ") + name)
    if not cond:
        check.failed += 1
check.failed = 0


# 用临时配色目录 + 临时记忆文件，不污染用户真实的「我的配色」
_TMP = tempfile.mkdtemp(prefix="ecp_edit_")
P.PALETTE_DIR = os.path.join(_TMP, "我的配色")
P.PALETTE_JSON = os.path.join(_TMP, "记忆.json")
os.makedirs(P.PALETTE_DIR, exist_ok=True)
json.dump({"recents": [], "groups": [], "counter": 0},
          open(P.PALETTE_JSON, "w", encoding="utf-8"))


# 1) 存两个同名不同色方案
P.save_palette("方案A", ["#111111"])
P.save_palette("方案A", ["#222222"])

items = P.scan_palettes()
second = [x for x in items if x["名称"] == "方案A (2)"][0]
check("重名第二个方案显示名为「方案A (2)」", second["名称"] == "方案A (2)")
check("重名第二个方案原名为「方案A」（无后缀）",
      second.get("原名") == "方案A")


# 2) 修复行为：用原名编辑，原名应保留、显示名重新去重
P.update_palette(second, second["原名"], ["#333333"])   # 用原名「方案A」
items2 = P.scan_palettes()
edited = [x for x in items2 if x.get("颜色") == ["#333333"]][0]
check("用原名编辑后：原名仍是干净名「方案A」", edited.get("原名") == "方案A")
check("用原名编辑后：显示名被重新去重（仍以「 (2)」区分）",
      edited["名称"] == "方案A (2)")


# 3) bug 复现：用带后缀的显示名去改，会把「 (2)」烤进存储名
P.update_palette(second, second["名称"], ["#444444"])  # 用显示名「方案A (2)」
# 直接读回 json，看内部 名称 字段
import glob
jf = [f for f in glob.glob(os.path.join(P.PALETTE_DIR, "*.json"))]
stored = {}
for f in jf:
    stored.update({json.load(open(f, encoding="utf-8")).get("名称"): f})
check("bug 复现：用显示名改会把「 (2)」烤进存储名",
      "方案A (2)" in stored)


# 4) 白盒：_edit_my_scheme 现在用 原名 初始化对话框
seg = SRC.split("_edit_my_scheme(self, item):", 1)[1]
check("源码 _edit_my_scheme 用 原名 初始化对话框",
      'item.get("原名", item.get("名称"' in seg
      and '颜色组编辑(self,' in seg[:600])


shutil.rmtree(_TMP, ignore_errors=True)

if check.failed:
    print("\n!! 有 %d 项不通过" % check.failed)
    sys.exit(1)
print("\n✅ 调色盘编辑重名方案：原名保留 + 显示去重正确 + 源码已修")
