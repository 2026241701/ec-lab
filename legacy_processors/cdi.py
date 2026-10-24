# -*- coding: utf-8 -*-
"""
CDI 数据处理脚本

功能：
1. 在当前目录中列出可处理的源 Excel 文件（排除 *-处理.xlsx 和临时文件）。
2. 让用户输入编号选择一个源文件。
3. 读取源文件中“测量时间”和“检测结果”两列，生成 7 个工作表：
   - 原始数据
   - 电导率
   - 浓度
   - 浓度差
   - 吸附容量
   - 吸附速率
   - 吸附最大值
4. 输出文件名：源文件名-处理.xlsx

依赖：
pip install openpyxl
"""

from __future__ import annotations

import copy
import math
import os
import re
from datetime import datetime
from typing import List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.workbook.properties import CalcProperties
from openpyxl.utils import get_column_letter


# ===== 核心可配置参数（用户按需修改）=====
TEMPLATE_NAME = "TNO@C2-处理.xlsx"  # 优先使用该模板；找不到则自动新建
TIME_STEP_SECONDS = 5  # 每个数据点的时间间隔（秒/点）
CYCLE_TOTAL_MINUTES = 60  # 每圈总时长（分钟）：吸附+脱附
CYCLE_ADSORPTION_MINUTES = 30  # 每圈吸附时长（分钟）
CYCLE_DESORPTION_MINUTES = 30  # 每圈脱附时长（分钟）
# 自动计算每圈总行数 = 总时长(分钟)*60秒 / 时间步长(秒)
ROWS_PER_CYCLE = int(CYCLE_TOTAL_MINUTES * 60 / TIME_STEP_SECONDS)

# 浓度/吸附计算常数（无需修改）
CONDUCTIVITY_TO_CONCENTRATION_BASE = 8.2236
CONDUCTIVITY_TO_CONCENTRATION_SCALE = 1.97252
SOLUTION_VOLUME_ML = 0.05
DEFAULT_MASS_MG = 24  # 模板里若已有质量值，可作为默认值；None 表示不给默认
# =================================


def safe_float(value) -> Optional[float]:
    """从字符串/数值中提取第一个浮点数。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else None


def parse_datetime(value) -> Optional[datetime]:
    """尽量把单元格值解析成 datetime。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None

    # 常见格式：2026-05-23 22:20:32
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass

    return None


def get_script_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def list_source_files(folder: str) -> List[str]:
    files = []
    for name in os.listdir(folder):
        lower = name.lower()
        if not lower.endswith(".xlsx"):
            continue
        if name.startswith("~$"):
            continue
        # 排除模板和已处理文件
        if name.endswith("-处理.xlsx"):
            continue
        files.append(name)
    files.sort()
    return files


def choose_source_file(folder: str) -> str:
    files = list_source_files(folder)
    if not files:
        raise FileNotFoundError("当前目录下没有可处理的 .xlsx 源文件。")

    print("\n可处理文件列表：")
    for idx, name in enumerate(files, start=1):
        print(f"{idx}. {name}")

    while True:
        choice = input(f"请输入要处理的文件编号（1-{len(files)}）：").strip()
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(files):
                return os.path.join(folder, files[n - 1])
        print("输入无效，请重新输入。")


def load_template(folder: str) -> Workbook:
    template_path = os.path.join(folder, TEMPLATE_NAME)
    if os.path.exists(template_path):
        return load_workbook(template_path)

    # 找不到模板时自动新建
    wb = Workbook()
    default_sheet = wb.active
    default_sheet.title = "原始数据"
    for title in ["电导率", "浓度", "浓度差", "吸附容量", "吸附速率", "吸附最大值"]:
        wb.create_sheet(title)
    return wb


def ensure_sheet_order(wb: Workbook) -> None:
    desired = ["原始数据", "电导率", "浓度", "浓度差", "吸附容量", "吸附速率", "吸附最大值"]
    existing = set(wb.sheetnames)
    for title in desired:
        if title not in existing:
            wb.create_sheet(title)
    wb._sheets = [wb[title] for title in desired]


def clear_sheet_values(ws) -> None:
    """只清空单元格内容，保留格式。"""
    if ws.max_row == 0 or ws.max_column == 0:
        return
    for row in ws.iter_rows():
        for cell in row:
            cell.value = None


def find_header_col(ws, candidates: List[str], fallback: int) -> int:
    """按标题名找列，找不到返回 fallback（1-based）。"""
    header_map = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is None:
            continue
        header_map[str(v).strip()] = c

    for cand in candidates:
        if cand in header_map:
            return header_map[cand]

    # 再做一次包含匹配
    for c in range(1, ws.max_column + 1):
        v = ws.cell(1, c).value
        if v is None:
            continue
        s = str(v).strip()
        for cand in candidates:
            if cand in s:
                return c

    return fallback


def read_source_data(source_path: str) -> Tuple[List[float], List[float], float]:
    wb = load_workbook(source_path, data_only=False)
    ws = wb[wb.sheetnames[0]]

    time_col = find_header_col(ws, ["测量时间", "时间"], fallback=3)
    value_col = find_header_col(ws, ["检测结果", "电导率", "结果"], fallback=7)

    times = []
    values = []

    # 读取 D1 默认质量值：如果源文件中已有，就优先取；否则返回 None
    default_mass = None

    for r in range(2, ws.max_row + 1):
        t_raw = ws.cell(r, time_col).value
        v_raw = ws.cell(r, value_col).value

        dt = parse_datetime(t_raw)
        times.append(dt if dt is not None else t_raw)
        values.append(safe_float(v_raw))

    # 计算相对秒数：优先用时间戳；若无法解析，则按 10s 等差生成
    elapsed_seconds: List[float] = []
    first_dt = times[0] if times else None
    if isinstance(first_dt, datetime):
        for t in times:
            if isinstance(t, datetime):
                elapsed_seconds.append((t - first_dt).total_seconds())
            else:
                elapsed_seconds.append(len(elapsed_seconds) * TIME_STEP_SECONDS)
    else:
        elapsed_seconds = [i * TIME_STEP_SECONDS for i in range(len(times))]

    # 将秒数四舍五入到整数，尽量得到 0,10,20...
    elapsed_seconds = [int(round(x)) for x in elapsed_seconds]

    return elapsed_seconds, values, default_mass


def write_raw_sheet(ws, elapsed_seconds: List[int], conductivity: List[float], mass_mg) -> None:
    ws["A1"] = "Time"
    ws["B1"] = "电导率"
    ws["C1"] = "材料质量（mg）："
    ws["D1"] = mass_mg

    for i, (t, c) in enumerate(zip(elapsed_seconds, conductivity), start=2):
        ws.cell(i, 1, t)
        ws.cell(i, 2, c)


def write_conductivity_sheet(ws, raw_data_count: int) -> int:
    """
    根据原始数据条数生成分圈后的电导率表。
    只保留完整圈数（每圈 ROWS_PER_CYCLE 条）。
    返回圈数。
    """
    circles = math.ceil(raw_data_count / ROWS_PER_CYCLE) if raw_data_count else 0
    remainder = raw_data_count % ROWS_PER_CYCLE if raw_data_count else 0
    if remainder:
        print(f"注意：原始数据共有 {raw_data_count} 条，每圈需 {ROWS_PER_CYCLE} 条（{CYCLE_TOTAL_MINUTES}分钟/{TIME_STEP_SECONDS}秒），最后1圈为不完整数据（剩余 {remainder} 条），已自动补空白单元格。")
    ws["A1"] = "Time"
    for circle in range(1, circles + 1):
        col = circle + 1  # B=2
        ws.cell(1, col, circle)
        start_raw_row = 2 + (circle - 1) * ROWS_PER_CYCLE
        for idx in range(ROWS_PER_CYCLE):
            src_row = start_raw_row + idx
            dst_row = 2 + idx
            if src_row <= raw_data_count + 1:
                ws.cell(dst_row, col, f"=原始数据!B{src_row}")
            else:
                ws.cell(dst_row, col, None)

    # A列引用原始数据 A2:A{ROWS_PER_CYCLE+1}
    for r in range(2, 2 + ROWS_PER_CYCLE):
        ws.cell(r, 1, f"=原始数据!A{r}")

    return circles


def write_concentration_sheet(ws, circles: int) -> None:
    ws["A1"] = "Time"
    for circle in range(1, circles + 1):
        col = circle + 1
        ws.cell(1, col, circle)
        src_col_letter = get_column_letter(col)
        for r in range(2, 2 + ROWS_PER_CYCLE):
            ws.cell(r, col, f"=(电导率!{src_col_letter}{r}-{CONDUCTIVITY_TO_CONCENTRATION_BASE})/{CONDUCTIVITY_TO_CONCENTRATION_SCALE}")

    for r in range(2, 2 + ROWS_PER_CYCLE):
        ws.cell(r, 1, f"=电导率!A{r}")


def write_difference_sheet(ws, circles: int) -> None:
    ws["A1"] = "Time"
    for circle in range(1, circles + 1):
        col = circle + 1
        col_letter = get_column_letter(col)
        ws.cell(1, col, circle)
        for r in range(2, 2 + ROWS_PER_CYCLE):
            ws.cell(r, col, f"=浓度!${col_letter}$2-浓度!{col_letter}{r}")

    for r in range(2, 2 + ROWS_PER_CYCLE):
        ws.cell(r, 1, f"=浓度!A{r}")


def write_capacity_sheet(ws, circles: int) -> None:
    ws["A1"] = "Time"
    for circle in range(1, circles + 1):
        col = circle + 1
        col_letter = get_column_letter(col)
        ws.cell(1, col, circle)
        for r in range(2, 2 + ROWS_PER_CYCLE):
            ws.cell(r, col, f"=浓度差!{col_letter}{r}*{SOLUTION_VOLUME_ML}/(原始数据!$D$1)*1000")

    for r in range(2, 2 + ROWS_PER_CYCLE):
        ws.cell(r, 1, f"=浓度差!A{r}")


def write_rate_sheet(ws, circles: int) -> None:
    ws["A1"] = "Time"
    for circle in range(1, circles + 1):
        col = circle + 1
        col_letter = get_column_letter(col)
        ws.cell(1, col, circle)
        for r in range(2, 2 + ROWS_PER_CYCLE):
            ws.cell(r, col, f"=吸附容量!{col_letter}{r}/吸附速率!A{r}")

    for r in range(2, 2 + ROWS_PER_CYCLE):
        ws.cell(r, 1, f"=吸附容量!A{r}")


def write_max_sheet(ws, circles: int) -> None:
    for circle in range(1, circles + 1):
        col = circle
        col_letter = get_column_letter(col + 1)
        ws.cell(1, col, circle)
        ws.cell(2, col, f"=MAX(吸附容量!{col_letter}2:{col_letter}{1 + ROWS_PER_CYCLE})")


def main() -> None:
    # 打印当前配置（方便用户核对）
    print("===== 当前运行配置 =====")
    print(f"时间步长：{TIME_STEP_SECONDS} 秒/点")
    print(f"每圈总时长：{CYCLE_TOTAL_MINUTES} 分钟（吸附{CYCLE_ADSORPTION_MINUTES}min + 脱附{CYCLE_DESORPTION_MINUTES}min）")
    print(f"每圈数据行数：{ROWS_PER_CYCLE} 行")
    print("=======================\n")

    folder = get_script_dir()
    source_path = choose_source_file(folder)
    source_name = os.path.splitext(os.path.basename(source_path))[0]
    output_path = os.path.join(folder, f"{source_name}-处理.xlsx")

    # 读取源数据
    elapsed_seconds, conductivity, default_mass = read_source_data(source_path)

    # 模板 / 新建工作簿
    wb = load_template(folder)
    ensure_sheet_order(wb)

    # 需要按模板长度先清空内容
    for sheet_name in wb.sheetnames:
        clear_sheet_values(wb[sheet_name])

    # 质量默认值：优先模板已有值，其次代码默认值，最后让用户输入
    existing_mass = DEFAULT_MASS_MG
    if "原始数据" in wb.sheetnames:
        # 清空后模板值已失去，这里改从代码默认值控制即可
        existing_mass = DEFAULT_MASS_MG

    prompt_default = existing_mass if existing_mass is not None else ""
    user_mass = input(f"请输入材料质量(mg)（直接回车则使用默认值 {prompt_default}）：").strip()
    if user_mass:
        mass_mg = safe_float(user_mass)
        if mass_mg is None:
            raise ValueError("材料质量输入无效，请输入数字。")
    else:
        if prompt_default == "":
            # 若没有默认值，再尝试给一个空值，后续公式仍然可手动填写
            mass_mg = None
        else:
            mass_mg = prompt_default

    # 写入数据
    ws_raw = wb["原始数据"]
    write_raw_sheet(ws_raw, elapsed_seconds, conductivity, mass_mg)

    ws_cond = wb["电导率"]
    circles = write_conductivity_sheet(ws_cond, raw_data_count=len(conductivity))

    ws_conc = wb["浓度"]
    write_concentration_sheet(ws_conc, circles)

    ws_diff = wb["浓度差"]
    write_difference_sheet(ws_diff, circles)

    ws_cap = wb["吸附容量"]
    write_capacity_sheet(ws_cap, circles)

    ws_rate = wb["吸附速率"]
    write_rate_sheet(ws_rate, circles)

    ws_max = wb["吸附最大值"]
    write_max_sheet(ws_max, circles)

    # 让 Excel 打开时自动重算公式
    wb.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True)

    wb.save(output_path)
    print(f"\n处理完成：{output_path}")


if __name__ == "__main__":
    main()
