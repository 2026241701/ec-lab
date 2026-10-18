# -*- coding: utf-8 -*-
"""回归基线检查：改动后这些数字必须一模一样。

这是还锁前的最后一道关。跑法：
    python regress_check.py

只有输出「基线一致」才可以还锁给别人。

双档设计（2026-10-15 O1「T6 基线澄清与测试数据分离」落地）：
  - 合成档（主档，任何机器可跑）：data_dir 为空时自动用仓库内置合成
    样例 examples/sample_data（质量统一登记 1.0 mg），数字锁定。
    陌生机器 / CI 上没有真实数据，靠这一档守护计算公式。
  - 真实档（可选增强）：仅当 data_dir 指向已登记数据集时锁数字，
    基线与「数据集 + 质量登记」绑定（见 REAL_TRACKS）。
  - data_dir 指向未登记数据集：只跑结构断言、不锁数字并明确提示。

背景（T6 结论）：138.8/101.4 是 _raw 数据集（1.8 mg）的基线；后来
data_dir 换成 FTO@C1（2.0 mg），12 个点全部 0.9 倍偏低，根因是
数据集 + 质量切换，计算公式自 v0.7 未变（复跑实验已证实）。
"""
import os
import sys
import io
import contextlib

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TOL = 0.15          # 允许的四舍五入误差

# ---------- 合成档基线（examples/sample_data，质量统一 1.0 mg） ----------
# 设定真值见 make_mock.py：CV = 40 + 3/sqrt(v) F/g，GCD 1A/g 95、2A/g 78。
# 下列是引擎对固定文件的实测锁定值（取数段首点差一个采样步长、梯形
# 积分对峰形的离散误差，使实测比设定值低约 0.3%，与真实数据同性质）；
# 重新生成样例（make_mock.py --sample）后必须重跑本脚本核对。
SYNTH_CV_BASE = [106.8, 82.2, 69.7, 61.0]
SYNTH_GCD_BASE = [95.0, 78.0]

# ---------- 真实档基线：与「数据集 + 质量登记」绑定 ----------
# 换数据集或改质量登记，都必须重算对应档位并更新这里的数字。
REAL_TRACKS = [
    {
        "name": "_raw/电化学数据结构",
        "match": "_raw",
        "mass_mg": 1.8,
        "cv": [138.8, 83.7, 69.1, 59.6, 49.6, 40.4, 31.3],
        "gcd": [101.4, 73.2, 50.1, 39.1, 24.6],
        "note": "v0.7 起锁定的原始基线（数据集 _raw，质量登记 1.8 mg）",
    },
    {
        "name": "FTO@C1",
        "match": "FTO@C1",
        "mass_mg": 2.0,
        "cv": [124.9, 75.3, 62.2, 53.6, 44.6, 36.4, 28.1],
        "gcd": [91.3, 65.8, 45.1, 35.2, 22.1],
        "note": ("2026-10-15 O1 重算：data_dir 从 _raw 换成 FTO@C1 后按 "
                 "2.0 mg 登记重锁（T6：0.9 倍偏差全部来自数据集+质量"
                 "切换）。若确认真实质量不是 2.0 mg，改 config.json 的 "
                 "mass_mg 后必须重算本档"),
    },
]

fails = []


def ok(c, m):
    print(("  OK   " if c else "  FAIL ") + m)
    if not c:
        fails.append(m)


def series_of(data):
    """从 prepare 结果取出 (CV 比电容, GCD 比电容)，各保留 1 位"""
    cv = [round(float(r["C_F_g"]), 1) for r in data["cv"]]
    gcd = [round(float(r["metrics"]["capacitance_F_g"]), 1)
           for r in data["gcd"]]
    return cv, gcd


def run_prepare(cfg, tag):
    """跑一遍 prepare；引擎日志进缓冲区，失败记 fails 并返回 None"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return eclab.prepare(cfg)
    except Exception as exc:
        print("  FAIL %s：引擎跑不起来：%s" % (tag, exc))
        print(buf.getvalue()[-1500:])
        fails.append("%s 引擎跑不起来：%s" % (tag, exc))
        return None


def check_series(tag, got, base):
    """逐点比对基线 + 单调下降断言（铁律 #4）"""
    print("%s 实测 %s" % (tag, got))
    print("%s 基线 %s" % (tag, base))
    ok(len(got) == len(base), "%s 条数一致（%d vs %d）"
       % (tag, len(got), len(base)))
    if len(got) == len(base):
        diffs = [abs(a - b) for a, b in zip(got, base)]
        ok(all(d <= TOL for d in diffs), "%s 每个数都在基线上（最大偏差 %.2f）"
           % (tag, max(diffs)))
    ok(got == sorted(got, reverse=True), "%s 单调下降（物理正确）" % tag)


def match_track(dirs):
    """data_dir 指向哪个已登记数据集；没有则返回 None"""
    for tr in REAL_TRACKS:
        for d in dirs:
            if tr["match"] in str(d).replace("\\", "/"):
                return tr
    return None


print("=== 回归基线检查（双档）===")

import eclab
import make_mock
from cfg_guard import load_config

cfg, _ = load_config()

# ---------- 合成档：任何机器都能跑，数字锁定（主档） ----------
scfg = make_mock.sample_cfg(cfg)
sdata = run_prepare(scfg, "合成档")
if sdata is not None:
    scv, sgcd = series_of(sdata)
    check_series("合成 CV", scv, SYNTH_CV_BASE)
    check_series("合成 GCD", sgcd, SYNTH_GCD_BASE)
    print("    （样例目录 %s，质量统一登记 %.1f mg）"
          % (os.path.relpath(make_mock.SAMPLE_DIR, BASE),
             make_mock.SAMPLE_MASS_MG))
    print()

# ---------- 真实档：仅当 data_dir 指向已登记数据集才锁数字 ----------
data = None
dirs = eclab.dirs_of(cfg)
tr = match_track(dirs)
if not dirs:
    print("--- 真实档：data_dir 为空，跳过（公式回归由合成档负责）---")
    print()
elif tr is None:
    print("--- 真实档：data_dir 指向未登记的数据集，不锁数字 ---")
    for d in dirs:
        print("    %s" % d)
    print("    结构断言照跑；要锁数字请先在 REAL_TRACKS 登记"
          "「数据集 + 质量」新档")
    print()
else:
    print("--- 真实档：%s（质量登记 %.1f mg）---" % (tr["name"], tr["mass_mg"]))
    print("    %s" % tr["note"])
    data = run_prepare(cfg, "真实档")
    if data is not None:
        # 质量登记核对：基线绑定「数据集 + 质量登记」组合，
        # 登记值变了说明样品质量被改过，基线不再适用
        reg = {cfg.get("mass_mg", {}).get(r["file"]) for r in data["cv"]}
        if reg and reg != {tr["mass_mg"]}:
            ok(False, "数据集 %s 的质量登记是 %s mg，基线按 %.1f mg 锁定"
               "——请确认样品质量或重算该档"
               % (tr["name"], sorted(reg, key=str), tr["mass_mg"]))
        else:
            rcv, rgcd = series_of(data)
            check_series("真实 CV", rcv, tr["cv"])
            check_series("真实 GCD", rgcd, tr["gcd"])
        print()

# 后续结构断言用哪份数据：真实档优先，没有就复用合成档
if data is None:
    data = sdata
if data is None:
    print("  FAIL 合成档与真实档都没跑起来，无法继续")
    sys.exit(1)
ok("anomalies" in data, "anomalies 字段还在（异常拦截没被删）")
print("  异常 %d 条：%s" % (len(data.get("anomalies") or []),
                           "有（正常，见日志）" if data.get("anomalies")
                           else "无"))

# 关键模块还在不在
for name in ("finish_axes", "apply_limits", "split_direction",
             "gcd_metrics", "fit_eis"):
    ok(hasattr(eclab, name), "引擎函数 %s 还在" % name)

# GUI 关键组件
try:
    import matplotlib
    matplotlib.use("QtAgg")
    import ec_gui
    for cls in ("比例画布框", "PreviewDialog", "StylePanel",
                "图内工具条", "MainWindow"):
        ok(hasattr(ec_gui, cls), "界面类 %s 还在" % cls)
    st = eclab.get_style(cfg, "cv_cap")
    for k in ("x_min", "x_max", "y_min", "y_max"):
        ok(k in st.get("axis", {}), "样式键 axis.%s 还在（坐标轴锁定）" % k)
except Exception as exc:
    ok(False, "界面导入失败：%s" % exc)

print()
print("=" * 56)
if fails:
    print("基线不一致，%d 项失败 —— 不要还锁，先查清楚：" % len(fails))
    for f in fails:
        print("  x " + f)
    print("=" * 56)
    sys.exit(1)
print("基线一致，可以还锁。")
print("=" * 56)
sys.exit(0)
