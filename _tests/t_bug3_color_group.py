# -*- coding: utf-8 -*-
"""回归测试：Bug 3 颜色组编辑支持删除 + 上下排序

修复前：颜色组编辑只能「加一个颜色」，没明显的删除入口，也不能调整顺序。
修复后：每行都有「删除 / ↑上移 / ↓下移」按钮，可删可排序。

这里直接驱动 颜色组编辑 的数据操作（_del / _move）并校验结果，
等价于点了那些按钮。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

from PySide6.QtWidgets import QApplication

import ec_gui

COLS = ["#111111", "#222222", "#333333", "#444444", "#555555"]


def run():
    app = QApplication.instance() or QApplication([])
    d = ec_gui.颜色组编辑(None, "测试组", list(COLS), item=None,
                          is_copy=True)

    # 初始 5 色
    assert d._cols == COLS, d._cols

    # 删除下标 2（#333333）
    d._del(2)
    assert d._cols == ["#111111", "#222222", "#444444", "#555555"], d._cols

    # 把 #555555（现在在下标 3）上移一格 -> 下标 2
    d._move(3, -1)
    assert d._cols == ["#111111", "#222222", "#555555", "#444444"], d._cols

    # 把 #111111（下标 0）下移一格 -> 下标 1
    d._move(0, 1)
    assert d._cols == ["#222222", "#111111", "#555555", "#444444"], d._cols

    # 边界：下标 0 不能上移、末尾不能下移（_move 应安全忽略）
    before = list(d._cols)
    d._move(0, -1)
    d._move(len(d._cols) - 1, 1)
    assert d._cols == before, d._cols

    # 删除到空也安全
    while d._cols:
        d._del(0)
    assert d._cols == []
    assert d.result()[1] == []   # result() 过滤掉空串

    print("✅ Bug3：颜色组删除 + 上下排序 行为正确")
    return 0


r = run()
sys.exit(r)
