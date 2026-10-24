import os
import re
import pandas as pd
import traceback
import numpy as np
from openpyxl.styles import PatternFill
from scipy.signal import find_peaks
from typing import List, Tuple, Dict, Optional

# ====================== 全局可调参数 ======================
FILL_COLOR = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
SMOOTH_WINDOW = 5          # 平滑窗口(奇数)
MIN_DISTANCE_POINTS = 12   # 相邻两个波谷最小间隔点数
MIN_PEAK_TROUGH_AMP = 0.025# 波谷最低落差(V)，圈识别不全就调低至0.018
TIME_STEP = 0.1
# ==========================================================

def moving_smooth(data: np.ndarray, win: int) -> np.ndarray:
    if win % 2 == 0:
        win += 1
    half = win // 2
    smoothed = np.convolve(data, np.ones(win)/win, mode="same")
    return smoothed

def process_raw_txt(file_path: str) -> np.ndarray:
    encodings = ['utf-8', 'utf-16-le', 'gbk']
    lines = []
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                lines = f.readlines()
            print(f"成功读取文件（编码：{encoding}）")
            break
        except Exception:
            continue
    if not lines:
        raise ValueError("文件读取失败，编码不支持")

    start_idx = None
    end_idx = None
    start_pattern = re.compile(r'time/sec.*potential/v', re.IGNORECASE)
    end_pattern = re.compile(r'hold time/sec', re.IGNORECASE)
    for i, line in enumerate(lines):
        s = line.strip()
        if start_pattern.search(s):
            start_idx = i + 1
        if end_pattern.search(s) and start_idx is not None:
            end_idx = i
            break
    if start_idx is None:
        raise ValueError("未找到Time/sec表头行！")
    if end_idx is None:
        end_idx = len(lines)

    voltage_data = []
    for line in lines[start_idx:end_idx]:
        parts = re.split(r'[,\t ]+', line.strip())
        if len(parts) < 2:
            continue
        try:
            voltage_data.append(float(parts[1]))
        except:
            continue
    arr = np.array(voltage_data, dtype=np.float32)
    print(f"成功提取电压数据，总点数：{len(arr)}")
    return arr

def find_all_troughs(raw_v: np.ndarray) -> List[int]:
    """
    专业函数查找波谷，解决部分圈波谷识别丢失
    返回原始序列索引列表
    """
    # 平滑降噪副本，仅用于筛选
    smooth_v = moving_smooth(raw_v, SMOOTH_WINDOW)
    # 反转信号：极小值 → 极大值，使用find_peaks检索波谷
    inverted_v = -smooth_v

    peaks_idx, props = find_peaks(
        inverted_v,
        distance=MIN_DISTANCE_POINTS,
        height=-MIN_PEAK_TROUGH_AMP
    )
    candidate_pos = peaks_idx.tolist()

    # 【核心！消除平滑偏移】候选位置附近原始数据找真实最小值
    real_trough_index = []
    search_radius = SMOOTH_WINDOW
    for pos in candidate_pos:
        left = max(0, pos - search_radius)
        right = min(len(raw_v), pos + search_radius + 1)
        local_slice = raw_v[left:right]
        real_min_offset = np.argmin(local_slice)
        real_idx = left + real_min_offset
        real_trough_index.append(int(real_idx))

    # 去重+从小到大排序
    real_trough_index = sorted(list(set(real_trough_index)))
    print(f"识别得到有效波谷数量：{len(real_trough_index)}")
    if len(real_trough_index) > 0:
        print("前5个波谷电压值校验：")
        for idx in real_trough_index[:5]:
            print(f"索引{idx}  V = {raw_v[idx]:.4f}")
    return real_trough_index

def split_cycles(raw_v: np.ndarray, troughs: List[int]) -> Dict[str, np.ndarray]:
    cycles = {}
    if len(troughs) < 2:
        cycles["1"] = raw_v
        return cycles

    # 前置段
    if troughs[0] > 0:
        cycles["前置数据"] = raw_v[:troughs[0]]
    # 逐圈分割：波谷→下一个波谷 作为一圈
    for i in range(len(troughs)-1):
        c_start = troughs[i]
        c_end = troughs[i+1]
        cycles[str(i+1)] = raw_v[c_start:c_end]
    # 尾部剩余数据
    cycles["后置数据"] = raw_v[troughs[-1]:]
    print(f"成功分割圈数：{len([k for k in cycles.keys() if k.isdigit()])}")
    return cycles

def calc_discharge_time(cycles: Dict[str, np.ndarray], raw_v: np.ndarray, troughs: List[int]) -> Dict[str, float]:
    """峰谷放电时间计算：一圈内第一个最高点 → 波谷"""
    time_result = {}
    global_pos = 0
    trough_set = set(troughs)

    for name, cyc_v in cycles.items():
        if name in ["前置数据", "后置数据"]:
            global_pos += len(cyc_v)
            continue
        # 查找圈内波峰
        inv_cyc = -moving_smooth(cyc_v, SMOOTH_WINDOW)
        peak_loc, _ = find_peaks(inv_cyc, distance=6)
        if len(peak_loc) == 0:
            time_result[name] = np.nan
            global_pos += len(cyc_v)
            continue
        first_peak_local = peak_loc[0]
        peak_global = global_pos + first_peak_local
        # 寻找该峰之后最近的波谷
        later_troughs = [t for t in troughs if t > peak_global]
        if not later_troughs:
            time_result[name] = np.nan
        else:
            trough_global = later_troughs[0]
            delta_t = (trough_global - peak_global) * TIME_STEP
            time_result[name] = round(delta_t, 4)
        global_pos += len(cyc_v)
    return time_result

def build_export_df(cycles: Dict[str, np.ndarray]) -> pd.DataFrame:
    max_length = max(len(arr) for arr in cycles.values())
    time_axis = np.arange(0, max_length * TIME_STEP, TIME_STEP)[:max_length]
    data_dict = {"Time": time_axis}
    for c_name, arr in cycles.items():
        pad_arr = np.full(max_length, np.nan)
        pad_arr[:len(arr)] = arr
        data_dict[c_name] = pad_arr
    df = pd.DataFrame(data_dict, dtype=np.float32)
    return df

def export_xlsx(df: pd.DataFrame, time_data: Dict[str, float], out_path: str):
    stat_df = pd.DataFrame(list(time_data.items()), columns=["圈号", "放电时长(s)"])
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="全量CP数据", index=False)
        stat_df.to_excel(w, sheet_name="放电时间汇总", index=False)
        # 尾数分表
        for tail in range(10):
            valid_cols = ["Time"] + [c for c in df.columns if c.isdigit() and int(c)%10 == tail]
            if len(valid_cols) > 1:
                df[valid_cols].to_excel(w, sheet_name=f"尾数{tail}圈", index=False)
    print(f"\n✅ XLSX文件保存完成：{out_path}")

def export_csv(df: pd.DataFrame, time_data: Dict[str, float], folder: str, base: str):
    df.to_csv(os.path.join(folder, f"{base}_全量数据.csv"), index=False, encoding="utf-8-sig")
    stat_df = pd.DataFrame(list(time_data.items()), columns=["圈号", "放电时长(s)"])
    stat_df.to_csv(os.path.join(folder, f"{base}_时间汇总.csv"), index=False, encoding="utf-8-sig")
    for tail in range(10):
        valid_cols = ["Time"] + [c for c in df.columns if c.isdigit() and int(c)%10 == tail]
        if len(valid_cols) > 1:
            sub_df = df[valid_cols]
            sub_df.to_csv(os.path.join(folder, f"{base}_尾数{tail}.csv"), index=False, encoding="utf-8-sig")
    print(f"\n✅ CSV文件全部导出完成")

def main():
    print("="*70)
    print("CP循环数据处理器【scipy峰谷检索修复版｜解决漏识别波谷】")
    print("="*70)
    work_dir = os.path.dirname(os.path.abspath(__file__))
    txt_list = [f for f in os.listdir(work_dir) if f.lower().endswith(".txt")]
    if len(txt_list) == 0:
        print("目录下未找到TXT测试文件！")
        input("回车退出...")
        return
    for idx, name in enumerate(txt_list, start=1):
        print(f"{idx}. {name}")
    # 文件选择
    while True:
        sel = input("\n输入文件序号：").strip()
        if sel.isdigit():
            num = int(sel)-1
            if 0 <= num < len(txt_list):
                select_file = txt_list[num]
                break
        print("序号无效，请重新输入数字！")
    full_path = os.path.join(work_dir, select_file)
    try:
        voltage_arr = process_raw_txt(full_path)
        trough_index_list = find_all_troughs(voltage_arr)
        cycle_dict = split_cycles(voltage_arr, trough_index_list)
        time_info = calc_discharge_time(cycle_dict, voltage_arr, trough_index_list)
        export_df = build_export_df(cycle_dict)
        # 输出格式选择
        fmt = input("\n输出格式：1=XLSX  2=CSV  >>").strip()
        basename = os.path.splitext(select_file)[0]
        if fmt == "1":
            save_path = os.path.join(work_dir, f"{basename}_处理结果.xlsx")
            export_xlsx(export_df, time_info, save_path)
        else:
            export_csv(export_df, time_info, work_dir, basename)
    except Exception as err:
        print("\n程序异常：")
        traceback.print_exc()
    input("\n按回车键关闭窗口")

if __name__ == "__main__":
    pd.options.mode.chained_assignment = None
    main()
