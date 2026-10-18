# -*- coding: utf-8 -*-
"""回归测试：最新三处改动（统一错误日志路径 / 取消"最近"按钮 / 预览透明背景）

1) 诉求 1 统一错误日志路径：
   - 模块级常量 ERROR_LOG 存在，且指向 BASE_DIR/错误日志.txt；
   - 两处写日志（_install_excepthook、_check_deps）都引用 ERROR_LOG，
     不再散落 os.path.join(BASE_DIR, "错误日志.txt")；
   - 菜单新增「查看错误日志」入口（_view_error_log）。

2) 诉求 2 取消"最近"按钮：
   - MainWindow 不再有 _menu_recent 方法；
   - _doc_dir 不再被引用（已删除）；
   - _recent_dir 在无历史时返回 ""（交给系统记上次位置，不再强制文档）。

3) 诉求 3 缩小不压缩 + 滚动条 + 一键适应窗口（透明背景已按用户要求回退）：
   - 比例画布框 的 sview 改回灰底 #F2F2F2（透明背景改动已撤销）；
   - widgetResizable 改 False：画布比视口大时出滚动条，不再被迫压缩；
   - resizeEvent 不再调 relayout：缩小窗口只改视口、不动画布尺寸
     （修掉"缩小就卡 + 被压成小方块"的根因）；
   - 新增 fit_window 方法 + 预览工具条「居中 / 适应窗口」按钮，
     手动点一下才按当前绘图区大小重算并居中。

说明：这几项多是白盒不变量（offscreen 下无法机械复现 C++ 渲染），
用源码 + 符号断言锁定，避免改坏。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "QtAgg")

import ec_gui  # noqa: E402

SRC = open(os.path.join(ROOT, "ec_gui.py"), encoding="utf-8").read()


def check(name, cond):
    print(("✅ " if cond else "❌ ") + name)
    if not cond:
        check.failed += 1
check.failed = 0


# ---- 诉求 1：统一错误日志路径 ----
check("ERROR_LOG 常量存在", hasattr(ec_gui, "ERROR_LOG"))
check("ERROR_LOG 指向 BASE_DIR/错误日志.txt",
      ec_gui.ERROR_LOG ==
      os.path.join(ec_gui.BASE_DIR, "错误日志.txt"))
check("写日志不再散落路径（仅定义处保留 os.path.join）",
      SRC.count('os.path.join(BASE_DIR, "错误日志.txt")') == 1
      and SRC.count("ERROR_LOG") >= 4)
check("菜单「查看错误日志」入口存在",
      "查看错误日志" in SRC and "_view_error_log" in SRC)


# ---- 诉求 2：取消"最近"按钮 ----
check("MainWindow 已无 _menu_recent 方法",
      not hasattr(ec_gui.MainWindow, "_menu_recent"))
check("已无 _doc_dir 方法",
      not hasattr(ec_gui.MainWindow, "_doc_dir"))
# _recent_dir 在无历史时应返回 ""（不再强制文档目录）
mw = ec_gui.MainWindow.__new__(ec_gui.MainWindow)  # 不跑完整 __init__
mw._dir_history = []
check("_recent_dir 无历史时返回空串",
      mw._recent_dir() == "")


# ---- 诉求 3：缩小不压缩 + 滚动条 + 一键适应窗口（透明背景已回退）----
check("比例画布框 sview 背景恢复灰底（透明已取消）",
      'self.sview.setStyleSheet("background:#F2F2F2;")' in SRC)
check("holder 不再设透明背景",
      'self.holder.setStyleSheet("background:transparent;")' not in SRC)
check("_figure_at 不再把预览图底板设透明",
      'fig.patch.set_facecolor("none")' not in SRC)
check("滚动区可出滚动条（widgetResizable=False）",
      "self.sview.setWidgetResizable(False)" in SRC)
check("resizeEvent 不再自动 relayout（不再压缩/卡顿）",
      'def resizeEvent(self, ev):\n        super().resizeEvent(ev)\n'
      '        self.relayout()' not in SRC)
check("新增 fit_window 一键适应窗口方法",
      "def fit_window(self):" in SRC)
check("预览工具条有「居中 / 适应窗口」按钮",
      "居中 / 适应窗口" in SRC and "_fit_window" in SRC)


if check.failed:
    print("\n!! 有 %d 项不通过" % check.failed)
    sys.exit(1)
print("\n✅ 全部不变量成立：统一日志路径 / 取消最近按钮 / 缩小不压缩+滚动条+一键适应窗口")
