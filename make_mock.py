# -*- coding: utf-8 -*-
"""生成模拟数据，用来验证算法

两种数据，用途不同：
  1. 2060 圈 CV / GCD 大文件（_mock/循环/）：验证循环稳定性算法。
     生成的比电容是已知的（人为设定衰减曲线），跑完 eclab 后可以拿
     算出来的值跟理论值对照，验证圈切分和积分公式。
  2. 一小套合成样例（examples/sample_data/）：仓库内置的假数据，
     供回归基线「合成档」与新人上手用。比电容真值人为设定且随
     扫速 / 电流密度单调下降（铁律 #4），质量统一登记 1.0 mg。

用法：
    python make_mock.py            # 只生成 2060 圈大文件
    python make_mock.py --sample   # 只生成合成样例
    python make_mock.py --all      # 两种都生成
"""

import os
import sys
import copy
import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mock", "循环")

MASS_G = 0.0018          # 1.8 mg
N_SEG = 2060             # 段数
PTS = 1600               # 每段点数（真实 CHI 在 1.6 V 窗口、0.001 V 间隔下就是这么多）
HI, LO = 0.8, -0.8
WINDOW = HI - LO


def spec_cap(n_seg):
    """第 n 段对应的设定比电容：从 45 F/g 衰减到 36 F/g"""
    return 36.0 + 9.0 * np.exp(-n_seg / 600.0)


def make_cv(name, faraday=True, noise=True):
    """三角波电位 + 电容电流（含法拉第峰与噪声）"""
    # 电位：段 0 从 HI 降到 LO，段 1 升回去，交替
    down = np.linspace(HI, LO, PTS)
    up = np.linspace(LO, HI, PTS)
    E = np.empty(N_SEG * PTS)
    for k in range(N_SEG):
        E[k * PTS:(k + 1) * PTS] = down if k % 2 == 0 else up

    seg_id = np.repeat(np.arange(N_SEG), PTS)
    Cspec = spec_cap(seg_id)                  # F/g
    Icap = Cspec * MASS_G * 0.1               # I = C * v，v = 0.1 V/s
    direction = np.where(seg_id % 2 == 0, -1.0, 1.0)   # 降为负、升为正
    I = Icap * direction

    if faraday:   # 一对氧化还原峰（高斯），让曲线像真实赝电容
        I += direction * 0.004 * np.exp(-((E - 0.25) ** 2) / (2 * 0.12 ** 2))
        I += direction * 0.004 * np.exp(-((E + 0.25) ** 2) / (2 * 0.12 ** 2))
    if noise:
        I += np.random.default_rng(2026).normal(0, 2e-6, E.size)

    path = os.path.join(OUT, name + ".txt")
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("May 24, 2026   16:56:21\n")
        f.write("Cyclic Voltammetry\n")
        f.write("File: %s\n" % name)
        f.write("Data Source:  Experiment\n")
        f.write("Instrument Model:  CHI660F\n")
        f.write("Header: \nNote: \n\n")
        f.write("Init E (V) = 0.8\nHigh E (V) = 0.8\nLow E (V) = -0.8\n")
        f.write("Init P/N = N\nScan Rate (V/s) = 0.1\n")
        f.write("Segment = %d\n" % N_SEG)
        f.write("Sample Interval (V) = 0.001\nQuiet Time (sec) = 2\n")
        f.write("Sensitivity (A/V) = 0.1\n\nResults:\n\n")
        f.write("Potential/V, Current/A\n")
        np.savetxt(f, np.column_stack([E, I]), fmt="%.6e", delimiter=", ")
    print("CV  %-22s %d 行，%.1f MB" % (name, E.size,
                                        os.path.getsize(path) / 1e6))


def make_gcd(name, noise=True):
    """恒流充放电：电位三角波，放电时间由设定比电容反推"""
    I_A = 0.02                      # 20 mA -> 1.8 mg 时约 11 A/g
    t_seg_list, V_list, t0 = [], [], 0.0
    for k in range(N_SEG):
        Cspec = spec_cap(k)                       # F/g
        # C = I*t/(m*dU)  ->  t = C*m*dU/I
        dt = Cspec * MASS_G * WINDOW / I_A
        n = max(20, int(round(dt / 0.1)))         # 采样间隔 0.1 s
        t = t0 + np.arange(n + 1) * (dt / n)
        V = np.linspace(LO, HI, n + 1) if k % 2 == 1 else np.linspace(HI, LO, n + 1)
        t_seg_list.append(t)
        V_list.append(V)
        t0 = t[-1] + 0.1
    t = np.concatenate(t_seg_list)
    V = np.concatenate(V_list)
    if noise:
        V += np.random.default_rng(7).normal(0, 2e-4, V.size)

    path = os.path.join(OUT, name + ".txt")
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("May 24, 2026   18:20:50\n")
        f.write("Chronopotentiometry\n")
        f.write("File: %s\n" % name)
        f.write("Data Source:  Experiment\n")
        f.write("Instrument Model:  CHI660F\n")
        f.write("Header: \nNote: \n\n")
        f.write("Cathodic Current (A) = %.4f\n" % I_A)
        f.write("Anodic Current (A) = %.4f\n" % I_A)
        f.write("Init P/N = N\nData Storage Interval (s) = 0.1\n")
        f.write("High E Limit (V) = 0.8\nHigh E Hold Time (s) = 10\n")
        f.write("Low E Limit (V) = -0.8\nLow E Hold Time (s) = 10\n")
        f.write("Cathodic Time (s) = 10\nAnodic Time (s) = 10\n")
        f.write("Current Switching Polarity = Potential\n")
        f.write("Segment = %d\n\n" % N_SEG)
        f.write("Time/sec, Potential/V\n\n")
        np.savetxt(f, np.column_stack([t, V]), fmt="%.6e", delimiter=", ")
        f.write("\nHold Time/sec, Current/A\n")
    print("GCD %-22s %d 行，%.1f MB" % (name, V.size,
                                        os.path.getsize(path) / 1e6))


# ==================================================================
# 合成样例数据（examples/sample_data/）—— 仓库内置的假数据
# ==================================================================
# 用途：回归基线「合成档」+ README 三步用法演示 + 陌生人 clone 后立刻能跑。
# 边界：数值只用于「公式没被改坏」的回归锁定，不是真实测量，禁止写进论文。
# 质量统一登记 1.0 mg：显式逐个登记，绝不引入 "*" 兜底（铁律 #2）。

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "examples", "sample_data")
SAMPLE_MASS_MG = 1.0

# CV 设定真值：表观比电容 = S_CAP + S_K / sqrt(v)（v 单位 V/s）
#   纯电容部分不随扫速变；法拉第峰幅度按 sqrt(v) 增长，
#   其对积分的贡献按 1/sqrt(v) 衰减 -> 表观比电容随扫速单调下降
S_CAP = 40.0
S_K = 3.0
S_CV_SCAN_RATES = [2, 5, 10, 20]      # mV/s
S_CV_WINDOW = 1.6                     # +0.8 ~ -0.8 V
S_CV_PTS = 161                        # 每段点数（Sample Interval 0.01 V）

# GCD 设定真值：随电流密度单调下降
S_GCD_CURRENTS = [1, 2]               # A/g
S_GCD_CAPS = {1: 95.0, 2: 78.0}       # F/g
S_GCD_WINDOW = 1.54                   # +0.77 ~ -0.77 V
S_GCD_DT = 0.5                        # s，采样间隔

# EIS 设定真值：Z = Rs + Rp / (1 + (j·2πf·τ)^α)，一段压扁的容抗弧
S_EIS = {"Rs": 5.0, "Rp": 30.0, "tau": 0.05, "alpha": 0.85}


def sample_cap_cv(v_Vs):
    """合成 CV 的设定比电容 F/g（随扫速单调下降，铁律 #4）"""
    return S_CAP + S_K / (v_Vs ** 0.5)


def sample_mass_table():
    """合成样例的质量登记表：逐个显式登记，绝不用 "*" 兜底（铁律 #2）"""
    table = {}
    for v in S_CV_SCAN_RATES:
        table["CV_cv-%dmVs" % v] = SAMPLE_MASS_MG
    for cd in S_GCD_CURRENTS:
        table["GCD_gcd-%dAg" % cd] = SAMPLE_MASS_MG
    return table


def sample_cfg(base_cfg=None):
    """基于任意配置生成一份「跑合成样例」的配置（不写回 config.json）

    data_dir 指向 examples/sample_data 并合并质量登记表；
    其余设置（样式等）沿用调用方配置，预览 / 出图与真实数据一致。
    """
    cfg = copy.deepcopy(base_cfg) if isinstance(base_cfg, dict) else {}
    cfg["data_dir"] = [SAMPLE_DIR]
    mass = dict(cfg.get("mass_mg") or {})
    mass.update(sample_mass_table())
    cfg["mass_mg"] = mass
    return cfg


def _gauss_pair(E):
    """一对氧化还原峰（高斯，中心 ±0.25 V，宽 0.15 V）"""
    return (np.exp(-((E - 0.25) ** 2) / (2 * 0.15 ** 2))
            + np.exp(-((E + 0.25) ** 2) / (2 * 0.15 ** 2)))


def _sample_cv_file(path, v_Vs):
    """写一个合成 CV 文件：4 段（1 活化 / 2+3 稳定 / 4 没测完）

    换向点只写一次（与真实 CHI 文件一致）；第 4 段只扫到 0.0 V，
    让 pick_segments 的取段逻辑在样例上真实生效。
    """
    hi, lo = S_CV_WINDOW / 2, -S_CV_WINDOW / 2
    n = S_CV_PTS
    mass_g = SAMPLE_MASS_MG / 1000.0
    c_stable = sample_cap_cv(v_Vs)                # 稳定段设定比电容 F/g
    # 段 1 活化：纯电容部分抬高 25%，模拟首圈不稳（不参与计算）
    c_cap = [S_CAP * 1.25, S_CAP, S_CAP, S_CAP]
    # 折返点序列；最后一段只到 0.0 V（没测完）
    turns = [hi, lo, hi, lo, 0.0]
    # 峰幅度：使峰的积分贡献 = S_K/sqrt(v)
    #   A·G/(sqrt(v)·W·m) = S_K/sqrt(v)  ->  A = S_K·W·m/G
    G = 2 * 0.15 * (2 * np.pi) ** 0.5             # 整个窗口的峰面积
    A = S_K * S_CV_WINDOW * mass_g / G
    E_parts, I_parts = [], []
    for k in range(4):
        seg = np.linspace(turns[k], turns[k + 1], n)
        if k > 0:                     # 换向点已由上一段末尾写出
            seg = seg[1:]
        direction = -1.0 if turns[k + 1] < turns[k] else 1.0
        i_cap = c_cap[k] * v_Vs * mass_g          # I = C·v·m
        I_parts.append(direction
                       * (i_cap + A * (v_Vs ** 0.5) * _gauss_pair(seg)))
        E_parts.append(seg)
    E = np.concatenate(E_parts)
    I = np.concatenate(I_parts)
    rng = np.random.default_rng(20261015 + int(round(v_Vs * 1000)))
    I = I + rng.normal(0.0, 0.002 * float(np.abs(I).max()), I.size)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Oct 15, 2026   10:00:00\n")
        f.write("Cyclic Voltammetry\n")
        f.write("File: %s\n" % os.path.basename(path))
        f.write("Data Source:  Experiment\n")
        f.write("Instrument Model:  CHI660F\n")
        f.write("Header: \nNote: \n\n")
        f.write("Init E (V) = 0.8\nHigh E (V) = 0.8\nLow E (V) = -0.8\n")
        f.write("Init P/N = N\nScan Rate (V/s) = %.4f\n" % v_Vs)
        f.write("Segment = 4\n")
        f.write("Sample Interval (V) = %.4f\n" % (S_CV_WINDOW / (n - 1)))
        f.write("Quiet Time (sec) = 2\nSensitivity (A/V) = 0.001\n\n")
        f.write("Results:\n\nPotential/V, Current/A\n")
        np.savetxt(f, np.column_stack([E, I]), fmt="%.6e", delimiter=", ")
    print("样例 CV  %-14s %5d 点 %6.1f KB | 设定比电容 %.1f F/g"
          % (os.path.basename(path), E.size,
             os.path.getsize(path) / 1024, c_stable))


def _sample_gcd_file(path, I_A, cd_A_g):
    """写一个合成 GCD 文件：4 段（1 放电残段 / 2 充电 / 3 放电 / 4 没充完）

    放电段（第 3 段）首末电位精确等于 ±0.77 V：第 2 段末端越过最高点
    一个采样步、第 4 段起点从最低点退回来一个采样步，换向判定后放电段
    刚好取满窗口，比电容 = I·t/(m·ΔU) 与设定值严格一致。
    """
    mass_g = SAMPLE_MASS_MG / 1000.0
    hi, lo = S_GCD_WINDOW / 2, -S_GCD_WINDOW / 2
    c_target = S_GCD_CAPS[cd_A_g]                  # 设定比电容 F/g
    # C = I·t/(m·ΔU)  ->  t = C·m·ΔU/I
    t_dis = c_target * mass_g * S_GCD_WINDOW / abs(I_A)
    t_chg = t_dis                                  # 充放同时长：效率 100%
    n_dis = max(20, int(round(t_dis / S_GCD_DT)))
    n_chg = max(20, int(round(t_chg / S_GCD_DT)))
    s2 = S_GCD_WINDOW / (n_chg - 1)                # 充电段步长
    s4 = (0.3 - lo) / max(20, int(round(0.5 * t_chg / S_GCD_DT)))
    # 段 2 末端越过 hi 一个步长；段 4 起点从 lo 退回一个步长
    V_parts = [
        np.linspace(0.5, lo, max(20, int(round(0.8 * t_dis / S_GCD_DT)))),
        np.linspace(lo - s2, hi + s2, n_chg),
        np.linspace(hi, lo, n_dis),
        np.linspace(lo + s4, 0.3,
                    max(20, int(round(0.5 * t_chg / S_GCD_DT)))),
    ]
    durations = [0.8 * t_dis, t_chg, t_dis, 0.5 * t_chg]
    t_parts = []
    t0 = 0.0
    for V_seg, dur in zip(V_parts, durations):
        t_seg = t0 + np.linspace(0.0, dur, len(V_seg))   # 时间严格连续
        t_parts.append(t_seg)
        t0 = t_seg[-1]
    # 噪声只加在段内部：各段首末点保持精确，换向判定与 dV_eff 零误差
    rng = np.random.default_rng(20261015 + cd_A_g)
    V_out = []
    for V_seg in V_parts:
        v = V_seg.copy()
        if len(v) > 2:
            v[1:-1] += rng.normal(0.0, 2e-4, len(v) - 2)
        V_out.append(v)
    t = np.concatenate(t_parts)
    V = np.concatenate(V_out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("Oct 15, 2026   10:02:00\n")
        f.write("Chronopotentiometry\n")
        f.write("File: %s\n" % os.path.basename(path))
        f.write("Data Source:  Experiment\n")
        f.write("Instrument Model:  CHI660F\n")
        f.write("Header: \nNote: \n\n")
        f.write("Cathodic Current (A) = %.4f\n" % I_A)
        f.write("Anodic Current (A) = %.4f\n" % I_A)
        f.write("Init P/N = N\nData Storage Interval (s) = %.1f\n"
                % S_GCD_DT)
        f.write("High E Limit (V) = 0.77\nHigh Hold Time (s) = 10\n")
        f.write("Low E Limit (V) = -0.77\nLow Hold Time (s) = 10\n")
        f.write("Cathodic Time (s) = %.1f\nAnodic Time (s) = %.1f\n"
                % (t_chg, t_dis))
        f.write("Current Switching Polarity = Potential\n")
        f.write("Segment = 4\n\n")
        f.write("Time/sec, Potential/V\n\n")
        np.savetxt(f, np.column_stack([t, V]), fmt="%.6e", delimiter=", ")
        f.write("\nHold Time/sec, Current/A\n")
    print("样例 GCD %-14s %5d 点 %6.1f KB | 设定比电容 %.1f F/g"
          % (os.path.basename(path), V.size,
             os.path.getsize(path) / 1024, c_target))


def _sample_eis_file(path):
    """写一条合成 EIS：Z = Rs + Rp/(1+(jωτ)^α)，60 个频点"""
    Rs, Rp = S_EIS["Rs"], S_EIS["Rp"]
    tau, alpha = S_EIS["tau"], S_EIS["alpha"]
    f = np.logspace(5, -2, 60)                      # 1e+5 ~ 1e-2 Hz，从高到低
    u = (2 * np.pi * f * tau) ** alpha
    phi = alpha * np.pi / 2
    den = 1 + 2 * u * np.cos(phi) + u ** 2
    zr = Rs + Rp * (1 + u * np.cos(phi)) / den
    zi = -Rp * u * np.sin(phi) / den                # 虚部为负
    rng = np.random.default_rng(20261015)
    zr = zr + rng.normal(0.0, 0.02, zr.size)
    zi = zi + rng.normal(0.0, 0.02, zi.size)
    z = np.sqrt(zr ** 2 + zi ** 2)
    phase = np.degrees(np.arctan2(zi, zr))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("Oct 15, 2026   10:05:00\n")
        fh.write("A.C. Impedance\n")
        fh.write("File: eis-1\n")
        fh.write("Data Source:  Experiment\n")
        fh.write("Instrument Model:  CHI660F\n\n")
        fh.write("Init E (V) = 0.35\n")
        fh.write("High Frequency (Hz) = 1e+5\n")
        fh.write("Low Frequency (Hz) = 0.01\n")
        fh.write("Imp SF\nAmplitude (V) = 0.005\nQuiet Time (sec) = 2\n\n")
        fh.write("Freq/Hz, Z'/ohm, Z\"/ohm, Z/ohm, Phase/deg\n")
        np.savetxt(fh, np.column_stack([f, zr, zi, z, phase]),
                   fmt="%.4e", delimiter=", ")
    print("样例 EIS %-14s %5d 点 %6.1f KB"
          % (os.path.basename(path), f.size,
             os.path.getsize(path) / 1024))


def make_sample():
    """生成 examples/sample_data/ 全套合成样例

    CV 4 个扫速（2/5/10/20 mV/s）+ GCD 2 个电流（1/2 A/g）+ EIS 1 条，
    比电容真值见 S_CAP/S_K/S_GCD_CAPS，随扫速与电流密度单调下降。
    """
    for v in S_CV_SCAN_RATES:
        _sample_cv_file(os.path.join(SAMPLE_DIR, "CV", "cv-%dmVs.txt" % v),
                        v / 1000.0)
    for cd in S_GCD_CURRENTS:
        _sample_gcd_file(os.path.join(SAMPLE_DIR, "GCD",
                                      "gcd-%dAg.txt" % cd),
                         cd * SAMPLE_MASS_MG / 1000.0, cd)
    _sample_eis_file(os.path.join(SAMPLE_DIR, "EIS", "eis-1.txt"))
    print("合成样例已写入 %s" % SAMPLE_DIR)
    print("质量登记（显式逐个登记，无 * 兜底）：%s" % sample_mass_table())


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--sample" in args or "--all" in args:
        make_sample()
    if "--sample" not in args:
        make_cv("CV循环-理想", faraday=False, noise=False)
        make_cv("CV循环-真实", faraday=True, noise=True)
        make_gcd("GCD循环")

        # 理论值对照表
        with open(os.path.join(OUT, "理论值.csv"), "w", encoding="utf-8-sig") as f:
            f.write("cycle,设定比电容_F_g\n")
            for c in range(1, N_SEG // 2):
                f.write("%d,%.2f\n" % (c, spec_cap(2 * c)))
        print("理论值已写入 理论值.csv")
