# -*- coding: utf-8 -*-
"""复现问题5：查看/修改 GCD 比电容图后，切回 CV 等图会报错卡死

模拟真实操作序列：打开预览 → 切到 GCD 比电容 → 点重新绘制
→ 切回 CV 比电容 / CV 叠加。捕获任何异常并打印堆栈。
"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

import eclab
import ec_gui

ROOTDIR = os.path.join(ROOT, "_raw", "电化学数据结构")
cfg0 = {
    "data_dir": [ROOTDIR], "area_cm2": 1.0,
    "pick_segments": [2, 3],
    "mass_mg": {"1A": 1.0, "2A": 1.0, "5A": 1.0, "10A": 1.0, "20A": 1.0,
                "2": 1.0, "5": 1.0, "10": 1.0, "20": 1.0,
                "50": 1.0, "100": 1.0, "200": 1.0},
    "gcd_continuous": False, "dedupe_condition": False,
    "process": {"CV": True, "GCD": True, "EIS": True, "cycle": False},
}

app = QApplication.instance() or QApplication([])


def run():
    data = eclab.prepare(cfg0)
    dlg = ec_gui.PreviewDialog(None, data, cfg0)
    dlg._warm_cache()   # 先把所有图都画好，贴近真实启动
    names = [n for _, n in dlg.items]
    print("预览项：", names)
    # 按真实预览项顺序切：先 GCD 比电容（第3项），改个参数 + 重绘，
    # 再切回 CV 叠加（第0项）/ GCD 充放电（第2项）/ CV 比电容（第1项）
    seq = [3, 1, 3, 0, 2, 1, 4, 0, 3]

    for step, i in enumerate(seq):
        if i >= len(dlg.items):
            print(f"[步{step}] 跳过下标 {i}")
            continue
        k = dlg.items[i][0]
        print(f"\n[步{step}] 切到第 {i} 项 ({k})")
        try:
            dlg.cb_fig.setCurrentIndex(i)   # 触发 _on_pick
            if k == "gcd_cap":
                # 模拟"修改 GCD 比电容"：改一个参数，标记 dirty，再点重新绘制
                print("   修改参数 + 点重新绘制…")
                dlg._on_redraw()
        except Exception as e:
            print(f"   ❌ 第 {step} 步崩了：{type(e).__name__}: {e}")
            traceback.print_exc()
            return step
    print("\n✅ 全程无异常")
    return None


r = run()
sys.exit(1 if r is not None else 0)
