"""Read-only conductivity import and traceable Excel export.

No calibration or adsorption constants are assumed. A bare conductivity value
requires an explicit unit; input rows are never sorted or silently discarded.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from uuid import uuid4

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

MAX_ROWS = 100_000
MAX_COLUMNS = 64
UNIT_FACTORS = {"uS/cm": 1.0, "mS/cm": 1000.0, "S/m": 10000.0}
TIME_FACTORS = {"s": 1.0, "min": 60.0, "h": 3600.0}
STANDARD_COLUMNS = ["file", "elapsed_s", "conductivity_uS_cm", "source_path",
                    "source_sheet", "source_row", "status", "raw_time",
                    "raw_conductivity", "detected_unit"]


@dataclass
class ConductivityResult:
    data: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=STANDARD_COLUMNS))
    issues: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    input_paths: list[str] = field(default_factory=list)

    @property
    def valid_count(self):
        if self.data.empty:
            return 0
        return int((self.data["elapsed_s"].notna()
                    & self.data["conductivity_uS_cm"].notna()).sum())


def project_dir():
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def default_output_dir():
    return project_dir() / "output" / ("conductivity_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                                      + "_" + uuid4().hex[:6])


def _unit(value):
    compact = str(value).replace("μ", "u").replace("µ", "u").replace("／", "/")
    compact = re.sub(r"\s+", "", compact).replace("·", "/")
    return {"us/cm": "uS/cm", "ms/cm": "mS/cm", "s/m": "S/m"}.get(compact.lower())


def _unit_in_header(header):
    header = str(header).replace("μ", "u").replace("µ", "u")
    match = re.search(r"(?<![A-Za-z])(?:uS\s*/\s*cm|mS\s*/\s*cm|S\s*/\s*m)(?![A-Za-z])", header, re.I)
    return _unit(match.group(0)) if match else None


def _header_kind(value):
    value = str(value or "").strip().lower()
    compact = re.sub(r"[\s_()（）\[\]单位]+", "", value)
    if any(term in compact for term in ("测量时间", "测试时间", "采集时间", "时间", "elapsed", "timestamp")) or compact in {"time", "times", "timemin", "timeh", "datetime", "date/time"}:
        return "time"
    if any(term in compact for term in ("检测结果", "电导率", "conductivity")) or compact == "cond":
        return "conductivity"
    return None


def _read_tables(path):
    """Return sheets with physical 1-based row numbers, bounded for desktop use."""
    if path.suffix.lower() == ".xlsx":
        book = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in book:
                if sheet.max_column and sheet.max_column > MAX_COLUMNS:
                    raise ValueError(f"工作表 {sheet.title} 超过 {MAX_COLUMNS} 列，请选取原始测量数据后分批导入。")
                if sheet.max_row and sheet.max_row > MAX_ROWS + 30:
                    raise ValueError(f"工作表 {sheet.title} 超过 {MAX_ROWS:,} 行限制，请分批导入。")
                rows = []
                for i, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    if i > MAX_ROWS + 30:
                        raise ValueError(f"工作表 {sheet.title} 超过导入行数限制。")
                    rows.append((i, list(row)))
                yield sheet.title, rows
        finally:
            book.close()
        return
    if path.suffix.lower() not in {".csv", ".txt", ".tsv"}:
        raise ValueError("支持 .xlsx、.csv、.txt、.tsv；旧版 .xls 请先另存为 .xlsx。")
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("文本文件超过 100 MB，请分批导入。")
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            content = raw.decode(encoding)
            if encoding == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            break
        except UnicodeError:
            continue
    else:
        raise ValueError("无法识别文本编码，请另存为 UTF-8。")
    sample = content[:8000]
    if "\t" in sample:
        delimiter = "\t"
    elif "," in sample:
        delimiter = ","
    elif ";" in sample:
        delimiter = ";"
    else:
        delimiter = None
    rows = []
    if delimiter:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        previous_line = 0
        for row in reader:
            if len(row) > MAX_COLUMNS:
                raise ValueError(f"文件超过 {MAX_COLUMNS} 列，请选取原始测量数据后分批导入。")
            rows.append((previous_line + 1, row))
            previous_line = reader.line_num
            if len(rows) > MAX_ROWS + 30:
                raise ValueError(f"文件超过 {MAX_ROWS:,} 行限制，请分批导入。")
    else:
        for i, line in enumerate(content.splitlines(), 1):
            # Split on the last run of whitespace to preserve a datetime's space.
            row = re.split(r"\s+", line.strip())
            if len(row) == 3 and re.match(r"\d{4}[-/]\d", row[0]):
                row = [row[0] + " " + row[1], row[2]]
            rows.append((i, row))
            if i > MAX_ROWS + 30:
                raise ValueError(f"文件超过 {MAX_ROWS:,} 行限制，请分批导入。")
    yield "text", rows


def _conductivity(value, supplied_unit, header_unit):
    if value is None or str(value).strip() == "":
        raise ValueError("电导率缺失")
    text = str(value).strip().replace("μ", "u").replace("µ", "u")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)", text)
    if not match:
        raise ValueError(f"电导率无法解析：{text[:80]}")
    number = float(match.group(1))
    suffix = match.group(2)
    unit = _unit(suffix) if suffix else header_unit or supplied_unit
    if suffix and not unit:
        raise ValueError(f"不支持的电导率单位：{suffix[:40]}")
    if not unit:
        raise ValueError("裸数值缺少单位，请明确选择 uS/cm、mS/cm 或 S/m")
    converted = number * UNIT_FACTORS[unit]
    if not math.isfinite(converted) or converted < 0:
        raise ValueError("电导率必须是非负有限数值")
    return converted, unit


def _time_value(value, time_unit):
    if value is None or str(value).strip() == "":
        raise ValueError("时间缺失")
    if isinstance(value, datetime):
        return "datetime", value
    if isinstance(value, date):
        return "datetime", datetime.combine(value, time())
    if isinstance(value, time):
        return "clock", value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6
    text = str(value).strip()
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if not math.isfinite(numeric):
            raise ValueError("时间不是有限数值")
        return "numeric", numeric * TIME_FACTORS[time_unit]
    try:
        stamp = datetime.fromisoformat(text.replace("/", "-"))
        return "datetime", stamp
    except ValueError:
        pass
    match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", text)
    if match:
        hours, minutes, seconds = map(float, match.groups())
        if minutes < 60 and seconds < 60:
            return "clock", hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"时间无法解析：{text[:80]}")


def read_conductivity(path, bare_unit=None, numeric_time_unit="s"):
    """Import a file. Invalid rows remain in data with missing numeric values.

    Units embedded in cells take precedence over column units; the selected
    bare_unit is only used for cells without a cell/column unit.
    """
    path = Path(path).resolve()
    if bare_unit is not None and bare_unit not in UNIT_FACTORS:
        raise ValueError("未知的裸数值单位")
    if numeric_time_unit not in TIME_FACTORS:
        raise ValueError("未知的数字时间单位")
    result = ConductivityResult(input_paths=[str(path)])
    records = []

    def issue(sheet, row, severity, message):
        result.issues.append(dict(source_path=str(path), source_sheet=sheet,
                                  source_row=row, severity=severity, message=message))

    for sheet, rows in _read_tables(path):
        if not rows or not any(any(v is not None and str(v).strip() for v in row) for _, row in rows):
            issue(sheet, None, "warning", "空工作表，未包含数据")
            continue
        layout = None
        header_physical_row = None
        for index, (physical_row, row) in enumerate(rows[:30]):
            kinds = [_header_kind(v) for v in row]
            if "time" in kinds and "conductivity" in kinds:
                if kinds.count("time") != 1 or kinds.count("conductivity") != 1:
                    issue(sheet, physical_row, "error", "存在多个时间或电导率列，无法安全自动选择，请提供只含目标两列的副本")
                    layout = "ambiguous"
                else:
                    layout = (index + 1, kinds.index("time"), kinds.index("conductivity"), row)
                    header_physical_row = physical_row
                break
        if layout == "ambiguous":
            continue
        if layout is None:
            # Headerless text is deliberately restricted to exactly two columns.
            nonempty = [(i, row) for i, (_, row) in enumerate(rows)
                        if any(v is not None and str(v).strip() for v in row)]
            if path.suffix.lower() != ".xlsx" and nonempty and all(len(row) == 2 for _, row in nonempty[:20]):
                first_index, first_row = nonempty[0]
                try:
                    _time_value(first_row[0], numeric_time_unit)
                except ValueError:
                    issue(sheet, rows[first_index][0], "error", "未识别到时间和电导率表头；无表头文件第一列必须为时间")
                    continue
                layout = (first_index, 0, 1, ["time", "conductivity"])
                issue(sheet, rows[first_index][0], "warning", "无表头两列文本：按第一列时间、第二列电导率读取")
            else:
                issue(sheet, None, "error", "未找到唯一的时间列和电导率列，工作表未导入")
                continue
        start, time_col, value_col, headers = layout
        if header_physical_row is not None and start > 1:
            issue(sheet, 1, "info", f"表头前 {start - 1} 行为说明，未作为测量行")
        header_unit = _unit_in_header(headers[value_col])
        time_header = str(headers[time_col]).lower()
        detected_time_unit = numeric_time_unit
        if "elapsed_s" in time_header or re.search(r"\b(?:s|sec|seconds)\b|秒", time_header):
            detected_time_unit = "s"
        elif re.search(r"\b(?:min|minutes)\b|分钟", time_header):
            detected_time_unit = "min"
        elif re.search(r"\b(?:h|hours)\b|小时", time_header):
            detected_time_unit = "h"
        first_time = None
        time_kind = None
        previous_time = None
        sheet_start = len(records)
        for physical_row, row in rows[start:]:
            if len(records) >= MAX_ROWS:
                raise ValueError(f"单文件超过 {MAX_ROWS:,} 测量行限制，请分批导入。")
            raw_time = row[time_col] if time_col < len(row) else None
            raw_value = row[value_col] if value_col < len(row) else None
            messages = []
            elapsed, conductivity, unit = None, None, None
            try:
                conductivity, unit = _conductivity(raw_value, bare_unit, header_unit)
            except ValueError as exc:
                messages.append(str(exc))
            try:
                kind, stamp = _time_value(raw_time, detected_time_unit)
                if first_time is None:
                    first_time, time_kind = stamp, kind
                if kind != time_kind:
                    raise ValueError("同一工作表混用了日期时间和数字时间")
                elapsed = (stamp - first_time).total_seconds() if kind == "datetime" else stamp - first_time
                if previous_time is not None and elapsed <= previous_time:
                    issue(sheet, physical_row, "warning", "时间重复或倒退；保留原始行顺序，请检查数据或跨午夜时间")
                previous_time = elapsed
            except (ValueError, TypeError) as exc:
                elapsed = None
                messages.append(str(exc))
            for message in messages:
                issue(sheet, physical_row, "error", message)
            record = dict(file=f"{path.name} [{sheet}]", elapsed_s=elapsed,
                          conductivity_uS_cm=conductivity, source_path=str(path),
                          source_sheet=sheet, source_row=physical_row,
                          status="; ".join(messages) if messages else "ok",
                          raw_time=raw_time, raw_conductivity=raw_value, detected_unit=unit)
            for column, value in enumerate(row):
                title = str(headers[column]) if column < len(headers) and headers[column] is not None else f"column_{column + 1}"
                record[f"raw_{column + 1}_{title}"] = value
            records.append(record)
        count = len(records) - sheet_start
        result.sources.append(dict(source_path=str(path), source_sheet=sheet,
                                   rows=count, header_row=header_physical_row if header_physical_row is not None else "无表头",
                                   bare_unit=bare_unit or "未指定", column_unit=header_unit or "无",
                                   numeric_time_unit=detected_time_unit,
                                   time_origin=str(first_time) if first_time is not None else "无"))
    if records:
        result.data = pd.DataFrame.from_records(records)
    return result


def process_files(paths, bare_unit=None, numeric_time_unit="s", progress=None):
    """Process sequentially in one worker; one bad file does not hide others."""
    result = ConductivityResult()
    frames = []
    total_rows = 0
    unique_paths = list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
    for i, path in enumerate(unique_paths):
        if progress:
            progress(f"正在读取 {i + 1}/{len(unique_paths)}：{Path(path).name}")
        result.input_paths.append(path)
        try:
            item = read_conductivity(path, bare_unit, numeric_time_unit)
            if not item.data.empty:
                if total_rows + len(item.data) > MAX_ROWS:
                    raise ValueError(f"加入该文件会超过本批次 {MAX_ROWS:,} 测量行限制，请另开一批处理该文件。")
                frames.append(item.data)
                total_rows += len(item.data)
            result.issues.extend(item.issues)
            result.sources.extend(item.sources)
        except Exception as exc:
            result.issues.append(dict(source_path=path, source_sheet="", source_row=None,
                                      severity="error", message=f"文件未导入：{exc}"))
    if frames:
        result.data = pd.concat(frames, ignore_index=True)
        # Include full path only for duplicate display labels from different folders.
        names = result.data.groupby("file")["source_path"].nunique()
        duplicate = set(names[names > 1].index)
        if duplicate:
            mask = result.data["file"].isin(duplicate)
            result.data.loc[mask, "file"] = (result.data.loc[mask, "source_path"]
                                                 + " [" + result.data.loc[mask, "source_sheet"] + "]")
    return result


def validate_destination(path, input_paths):
    target = Path(path).resolve()
    roots = [Path(p).resolve().parent for p in input_paths]
    if os.name == "nt":
        roots.append(Path("E:/Data").resolve())
    if any(target == root or root in target.parents for root in roots):
        raise ValueError("输出不能位于原始数据文件夹或 E:\\Data 内。请选择项目 output 文件夹。")
    if target.suffix.lower() != ".xlsx":
        raise ValueError("输出文件必须使用 .xlsx 扩展名。")
    if target.exists():
        raise ValueError("输出文件已存在。请选择新文件名，避免覆盖已有结果。")
    return target


def _excel_value(value):
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def export_conductivity(result, path):
    """Export a new workbook, with a separate issue log and source records."""
    if result.data.empty:
        raise ValueError("没有可导出的测量行，请先检查输入格式和错误清单。")
    target = validate_destination(path, result.input_paths)
    if len(result.data) > 1_048_575:
        raise ValueError("数据超过 Excel 单工作表行数限制，请分批导出。")
    target.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    book.remove(book.active)

    def add_sheet(name, columns, rows):
        sheet = book.create_sheet(name)
        sheet.append(list(columns))
        for row_index, row in enumerate(rows, 2):
            sheet.append([_excel_value(v) for v in row])
            # Raw cells are data, including any leading '=' from a source file.
            for column_index in range(1, len(columns) + 1):
                cell = sheet.cell(row_index, column_index)
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="235D75")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for i, header in enumerate(columns, 1):
            sheet.column_dimensions[sheet.cell(1, i).column_letter].width = min(48, max(18, len(str(header)) + 4))
        return sheet

    try:
        add_sheet("conductivity", result.data.columns, result.data.itertuples(index=False, name=None))
        issue_columns = ["source_path", "source_sheet", "source_row", "severity", "message"]
        add_sheet("issues", issue_columns, ([item.get(k) for k in issue_columns] for item in result.issues))
        source_columns = ["source_path", "source_sheet", "rows", "header_row", "bare_unit", "column_unit", "numeric_time_unit", "time_origin"]
        add_sheet("sources", source_columns, ([item.get(k) for k in source_columns] for item in result.sources))
        add_sheet("说明", ["项目", "说明"], [
            ("生成时间", datetime.now().isoformat(timespec="seconds")),
            ("处理方式", "逐文件逐工作表处理；保留原始行顺序和所有测量行，不插值、不平滑、不去重、不自动排序。"),
            ("横坐标 elapsed_s", "每个来源工作表以首个可解析时间为零点；单位为秒。原始时间和时间单位另行保存。"),
            ("纵坐标 conductivity_uS_cm", "统一为 μS/cm：1 mS/cm = 1000 μS/cm；1 S/m = 10000 μS/cm。"),
            ("单位优先级", "单元格明确单位 > 列标题单位 > 用户选择的裸数值单位。未指定单位的裸数值保留为空并报错。"),
            ("异常行", "缺失或非法数值仍保留；对应标准字段留空。issues 记录错误和时间重复/倒退。绘图前检查错误清单。"),
            ("原始信息", "source_path/source_sheet/source_row 指向来源；raw_* 为原始单元格读值；公式取源文件已有缓存结果。"),
            ("有效点数", result.valid_count),
            ("总测量行数", len(result.data)),
            ("浓度与吸盐量", "未计算。不假设标定关系、溶液体积、活性物质质量或温度补偿。"),
            ("原始数据保护", "导入只读；导出禁止位于源文件夹或 E:\\Data，已有文件不覆盖。"),
        ])
        # Exclusive creation also prevents accidental overwrite during a race.
        with target.open("xb") as handle:
            book.save(handle)
    finally:
        book.close()
    return target
