# -*- coding: utf-8 -*-
"""GUI 离屏冒烟测试：不开真窗口，验证界面能起来、配置保险箱能用。"""
import os
import sys
import json
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MPLBACKEND"] = "QtAgg"
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

fails = []


def ok(cond, msg):
    print(("  OK   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


print("=== 1. 配置保险箱 ===")
import cfg_guard
import make_mock
cfg, note = cfg_guard.load_config()
ok(isinstance(cfg, dict) and len(cfg) > 10, "load_config 返回可用配置")
# data_dir 为空是合法状态（干净机器 / CI）：自动改用仓库内置合成样例
use_sample = not (cfg.get("data_dir") or [])
if use_sample:
    print("  data_dir 为空 -> 自动使用合成样例 examples/sample_data")
ok(isinstance(cfg.get("data_dir"), list),
   "data_dir 字段正常：%s" % (cfg.get("data_dir") or "为空，改用合成样例",))
ok("mass_mg" in cfg, "mass_mg 字段存在")
# 本次冒烟实际使用的配置：有真实数据用真实，没有用合成样例
work = make_mock.sample_cfg(cfg) if use_sample else cfg

probe = dict(cfg)
probe["_体检测试标记"] = "abc"
ok_made, msg = cfg_guard.save_config(probe)
ok(ok_made, "save_config 成功：%s" % msg)
baks = cfg_guard.list_backups()
ok(len(baks) > 0, "自动生成了备份，共 %d 份" % len(baks))
cfg2, _ = cfg_guard.load_config()
ok(cfg2.get("_体检测试标记") == "abc", "写入内容能读回来")

print("=== 2. 损坏自愈 ===")
with open(cfg_guard.CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write("{这不是合法的 JSON")
cfg3, note3 = cfg_guard.load_config()
ok(isinstance(cfg3, dict) and "data_dir" in cfg3, "坏文件被自动恢复")
ok(note3 and ("恢复" in note3 or "损坏" in note3), "给出了提示：%s" % note3)
# 还原
cfg_guard.save_config(cfg)
cfg4, _ = cfg_guard.load_config()
ok("_体检测试标记" not in cfg4, "测试标记已清除，配置还原")

print("=== 3. 引擎数据流 ===")
import eclab
data = eclab.prepare(work)
ok(len(data["cv"]) > 0, "CV 结果 %d 个" % len(data["cv"]))
ok(len(data["gcd"]) > 0, "GCD 结果 %d 个" % len(data["gcd"]))
ok("anomalies" in data, "含 anomalies 字段：%d 条" % len(data["anomalies"]))
caps = [r["C_F_g"] for r in data["cv"]]
ok(all(c > 0 for c in caps), "所有比电容为正：%s" % [round(c, 1) for c in caps])
ok(caps == sorted(caps, reverse=True), "比电容随扫速单调下降（物理正确）")

print("=== 4. 界面能起来 ===")
import matplotlib
matplotlib.use("QtAgg")
import ec_gui
from PySide6.QtWidgets import QApplication
app = QApplication([])
ec_gui.apply_theme(app, "classic")
w = ec_gui.MainWindow()
ok(w is not None, "主窗口创建成功")
ok(w.log is not None, "日志区控件正常")

print("=== 5. 预览与出图 ===")
items = eclab.preview_list(data)
ok(len(items) > 0, "可预览图 %d 张" % len(items))
fig, title = eclab.draw_figure(data, items[0][0], work)
ok(fig is not None, "第一张图画出来了：%s" % title)
ok(len(ec_gui.THEMES) >= 2, "主题数 %d" % len(ec_gui.THEMES))

print("=== 6. 体检工具 ===")
import doctor
r = doctor.Report()
doctor.check_python(r)
doctor.check_packages(r)
doctor.check_files(r)
doctor.run_math_check(r)
ok(len(r.bad) == 0, "体检无致命项（坏了 %d 项）" % len(r.bad))

print()
print("=" * 56)
if fails:
    print("失败 %d 项：" % len(fails))
    for f in fails:
        print("  x " + f)
else:
    print("全部通过")
print("=" * 56)
sys.exit(1 if fails else 0)
