import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import matplotlib
matplotlib.use("QtAgg")
import ec_gui
import eclab
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
# 主窗口能起来吗（含列宽/文件夹历史/输出参数外移的改动）
w = ec_gui.MainWindow()
print("主窗口 OK, _dir_history =", w._dir_history, " startup=", w._startup)

root = os.path.abspath(os.path.join("_raw", "电化学数据结构", "GCD"))
mass = {"1A": 1.0, "2A": 1.0, "5A": 1.0, "10A": 1.0, "20A": 1.0}
cfg = {
    "data_dir": [root], "area_cm2": 1.0, "pick_segments": [2, 3],
    "mass_mg": mass, "gcd_continuous": False, "dedupe_condition": False,
    "process": {"CV": False, "GCD": True, "EIS": False, "cycle": False},
}
data = eclab.prepare(cfg)
dlg = ec_gui.PreviewDialog(w, data, cfg)
print("预览窗 OK，图数量 =", len(dlg.items))
# 首张已显示
assert dlg.fig is not None, "首张没显示"
n0 = len(dlg._cache)
# 切换到后面几张（预热前的现画也算缓存）
for i in range(len(dlg.items)):
    dlg._on_pick(i)
    assert dlg.fig is not None
print("逐张切换 OK，缓存数 =", len(dlg._cache))
# 记录切换耗时（应全部走缓存，毫秒级）
import time
t0 = time.perf_counter()
for _ in range(3):
    for i in range(len(dlg.items)):
        dlg._on_pick(i)
dt = (time.perf_counter() - t0) / 3 / max(len(dlg.items), 1) * 1000
print("平均每次切图耗时 %.1f ms" % dt)
# 改参数 → dirty 提示；重画 → dirty 清除
dlg._mark_dirty()
assert dlg._dirty and "重新绘制" in dlg.b_draw.text()
dlg._redraw()
assert not dlg._dirty
print("dirty/重画流程 OK")
# 没有日志区残留
assert not hasattr(dlg, "log_view"), "log_view 还在"
dlg.close()
print("全部通过")
