import os
import glob
import csv
from typing import List, Tuple

# ===================== 配置参数 =====================
WINDOW_SIZE = 3
MIN_PEAK_VALLEY_DIFF = 1e-6

# ===================== 自动识别文件编码 =====================
def detect_file_encoding(file_path: str) -> str:
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16-le', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(1024)
            return enc
        except:
            continue
    return 'utf-8'

# ===================== 读取清洗TXT =====================
def read_and_clean_txt(file_path: str) -> Tuple[List[float], List[float]]:
    encoding = detect_file_encoding(file_path)
    print(f"✅ 编码识别：{encoding}")

    voltage, current = [], []
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            lines = f.readlines()
    except:
        print("❌ 文件读取失败")
        return [], []

    first_idx = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s and (s[0].isdigit() or s[0] == '-'):
            first_idx = i
            break
    if first_idx is None:
        print("❌ 无有效数据")
        return [], []

    for line in lines[first_idx:]:
        line = line.replace(',', ' ').strip()
        if not line: continue
        parts = list(filter(None, line.split()))
        if len(parts) < 2: continue
        try:
            v = float(parts[0])
            c = float(parts[1])
            voltage.append(v)
            current.append(c)
        except:
            continue

    if len(voltage) < WINDOW_SIZE:
        print("❌ 数据长度不足")
        return [], []
    print(f"✅ 有效数据 {len(voltage)} 行")
    return voltage, current

# ===================== 波峰/波谷检测 =====================
def detect_points(data: List[float], mode: str) -> List[int]:
    if len(data) < WINDOW_SIZE: return []
    half = WINDOW_SIZE // 2
    points = []
    for i in range(half, len(data) - half):
        cur = data[i]
        ok = True
        for j in range(i - half, i + half + 1):
            if j == i: continue
            if mode == "peak":
                if cur <= data[j] + MIN_PEAK_VALLEY_DIFF:
                    ok = False
                    break
            else:
                if cur >= data[j] - MIN_PEAK_VALLEY_DIFF:
                    ok = False
                    break
        if ok: points.append(i)
    print(f"✅ 检测到 {len(points)} 个{mode}")
    return points

# ===================== 分圈 =====================
def split_cycles(voltage, current, points):
    if len(points) < 2: return []
    cycles = []
    for i in range(len(points)-1):
        s, e = points[i], points[i+1]
        cycles.append((voltage[s:e], current[s:e]))
    print(f"✅ 分圈完成：{len(cycles)} 圈")
    return cycles

# ===================== 构建处理后大表 =====================
def build_processed_table(cycles):
    if not cycles: return []
    max_row = max(len(v) for v, _ in cycles)
    cols = len(cycles)
    table = []

    # 表头：电压,1,2,3,4...
    header = ["电压"] + [str(i+1) for i in range(cols)]
    table.append(header)

    # 逐行填充（短列补空白）
    for r in range(max_row):
        row = []
        v1, _ = cycles[0]
        row.append(v1[r] if r < len(v1) else "")

        for _, cur in cycles:
            row.append(cur[r] if r < len(cur) else "")
        table.append(row)
    return table

# ===================== 尾号筛选 =====================
def filter_by_last_digit(table):
    if len(table) < 2: return {}
    result = {"原始处理数据": table}
    header = table[0]

    for digit in range(10):
        keep_idx = [0]
        for idx, col_name in enumerate(header[1:], 1):
            try:
                num = int(col_name)
                if num % 10 == digit:
                    keep_idx.append(idx)
            except:
                continue

        new_table = [ [header[i] for i in keep_idx] ]
        for row in table[1:]:
            new_table.append( [row[i] for i in keep_idx] )
        result[f"尾号{digit}"] = new_table
    return result

# ===================== 自动重命名 =====================
def get_safe_name(base, suffix, ext):
    name = f"{base}{suffix}{ext}"
    cnt = 1
    while os.path.exists(name):
        name = f"{base}{suffix}_{cnt}{ext}"
        cnt +=1
    return name

# ===================== 输出：11个CSV =====================
def save_csv_all(tables, base):
    for name, table in tables.items():
        if len(table) <= 1:
            print(f"📝 {name} 无数据")
            continue
        fname = get_safe_name(base, f"_{name}", ".csv")
        with open(fname, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerows(table)
        print(f"✅ 已保存：{os.path.basename(fname)}")

# ===================== 输出：1个XLSX =====================
def save_xlsx_all(tables, base):
    try:
        from openpyxl import Workbook
    except:
        print("❌ 请安装：pip install openpyxl")
        return

    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, table in tables.items():
        if len(table) <=1: continue
        ws = wb.create_sheet(title=sheet_name)
        for row in table:
            ws.append(row)
    fname = get_safe_name(base, "", ".xlsx")
    wb.save(fname)
    print(f"✅ 已保存：{os.path.basename(fname)}")

# ===================== 主程序 =====================
def main():
    print("="*70)
    print("📊 CV循环最终版（可选择单个文件）")
    print("流程：分圈 → 构建表格 → 尾号筛选 → 输出")
    print("="*70)

    # -------------------------- 列出文件，让用户选择 --------------------------
    txt_files = sorted(glob.glob("*.txt"))
    if not txt_files:
        print("\n❌ 未找到txt文件")
        input("回车退出")
        return

    print("\n📂 当前目录找到以下 TXT 文件：")
    for i, file in enumerate(txt_files, 1):
        print(f" {i}. {file}")

    while True:
        try:
            choice = int(input("\n请输入要处理的文件序号：").strip())
            if 1 <= choice <= len(txt_files):
                selected_file = txt_files[choice-1]
                break
            else:
                print(f"❌ 请输入 1~{len(txt_files)} 之间的数字")
        except:
            print("❌ 请输入有效数字")

    print(f"\n✅ 已选择：{selected_file}")

    # 1. 分圈选择
    print("\n1. 分圈依据：")
    print(" 1 波峰 ｜ 2 波谷")
    while True:
        i = input("输入1/2（默认1）：").strip()
        if i in ("","1"):
            mode, mcn = "peak","波峰"
            break
        if i=="2":
            mode, mcn = "valley","波谷"
            break
        print("❌ 只能输1/2")

    # 2. 输出模式
    print("\n2. 输出模式：")
    print(" 1 11个CSV ｜ 2 1个XLSX")
    while True:
        o = input("输入1/2：").strip()
        if o in ("1","2"): break
        print("❌ 只能输1/2")

    print(f"\n✅ 开始处理：{selected_file}")
    base = os.path.splitext(selected_file)[0]

    # -------------------------- 处理选中的单个文件 --------------------------
    v,c = read_and_clean_txt(selected_file)
    if not v:
        input("\n数据错误，回车退出")
        return

    pts = detect_points(v, mode)
    if not pts:
        input("\n未检测到特征点，回车退出")
        return

    cycles = split_cycles(v,c,pts)
    if not cycles:
        input("\n分圈失败，回车退出")
        return

    table = build_processed_table(cycles)
    if not table:
        input("\n表格生成失败，回车退出")
        return

    tables = filter_by_last_digit(table)

    # 输出
    if o=="1":
        save_csv_all(tables, base)
    else:
        save_xlsx_all(tables, base)

    print("\n" + "="*70)
    print("🎉 文件处理完成！")
    input("回车退出")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        input("回车退出")