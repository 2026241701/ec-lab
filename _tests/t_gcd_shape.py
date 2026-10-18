import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import eclab

root = os.path.join("_raw", "电化学数据结构", "GCD")
mass = {"1A": 1.0, "2A": 1.0, "5A": 1.0, "10A": 1.0, "20A": 1.0}
cfg = {
    "data_dir": [os.path.abspath(root)], "area_cm2": 1.0,
    "pick_segments": [2, 3], "mass_mg": mass, "gcd_continuous": False,
    "dedupe_condition": False,
    "process": {"CV": False, "GCD": True, "EIS": False, "cycle": False},
}
data = eclab.prepare(cfg)
res = eclab.draw_figure(data, "GCD_overlay", cfg)
fig = res[0] if isinstance(res, tuple) else res
ax = fig.axes[0]
print("线条数 =", len(ax.get_lines()))
for ln in ax.get_lines():
    xd, yd = ln.get_xdata(), ln.get_ydata()
    print("   %-8s %5d点  x %.2f~%.2f   y %.2f~%.2f"
          % (ln.get_label(), len(xd), xd[0], xd[-1], yd.min(), yd.max()))
print("xlim", ax.get_xlim())
fig.savefig("_tests/_gcd_check.png", dpi=80)
print("已存预览图 _tests/_gcd_check.png")
