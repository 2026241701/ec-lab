# -*- coding: utf-8 -*-
"""循环稳定性算法验证：拿模拟数据（已知理论比电容）对照 eclab 算出来的值"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eclab

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mock", "循环")
MASS_G = 0.0018


def theory(cycle):
    """与 make_mock.py 中 spec_cap 一致的设定值"""
    return 36.0 + 9.0 * np.exp(-(2.0 * cycle) / 600.0)


def check(name, caps, unit="CV"):
    n = len(caps)
    print("\n%s %s：切出 %d 圈" % (unit, name, n))
    if n == 0:
        print("   [失败] 一圈都没切出来")
        return
    rows = []
    for c in (1, 2, 10, 50, 100, 500, 1000, n):
        if c > n:
            continue
        got = caps[c - 1]
        exp = theory(c)
        err = 100.0 * (got - exp) / exp
        rows.append((c, got, exp, err))
        print("   第 %5d 圈：算得 %6.2f F/g   理论 %6.2f F/g   偏差 %+5.1f%%"
              % (c, got, exp, err))
    # 单调性：整体应该缓慢下降
    a = np.array(caps[:min(n, 1000)])
    print("   前 %d 圈范围：%.2f ~ %.2f F/g" % (len(a), a.min(), a.max()))
    return rows


def main():
    t_all = time.time()

    # ---------- CV 理想 ----------
    p = os.path.join(BASE, "CV循环-理想.txt")
    t0 = time.time()
    meta, E, I = eclab.parse_cv(p)
    print("读入 CV循环-理想：%d 点，%.1f s" % (E.size, time.time() - t0))
    t0 = time.time()
    segs = eclab.split_direction(E, I)
    print("分段：%d 段，%.1f s" % (len(segs), time.time() - t0))
    t0 = time.time()
    caps = eclab.cv_all_cycles(E, I, meta["scan_rate_Vs"], MASS_G)
    print("算圈：%.1f s，共 %d 圈" % (time.time() - t0, len(caps)))
    check("CV循环-理想", caps)

    # ---------- CV 真实（含峰 + 噪声） ----------
    p = os.path.join(BASE, "CV循环-真实.txt")
    meta, E, I = eclab.parse_cv(p)
    t0 = time.time()
    caps2 = eclab.cv_all_cycles(E, I, meta["scan_rate_Vs"], MASS_G)
    print("\nCV循环-真实：%d 圈，%.1f s" % (len(caps2), time.time() - t0))
    check("CV循环-真实", caps2)

    # ---------- GCD ----------
    p = os.path.join(BASE, "GCD循环.txt")
    meta, t, V = eclab.parse_gcd(p)
    t0 = time.time()
    allc = eclab.gcd_all_cycles(t, V, meta["current_A"], MASS_G)
    print("\nGCD循环：%d 圈，%.1f s" % (len(allc), time.time() - t0))
    check("GCD循环", [m["capacitance_F_g"] for m in allc], unit="GCD")

    print("\n总耗时 %.1f s" % (time.time() - t_all))


if __name__ == "__main__":
    main()
