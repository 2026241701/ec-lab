# -*- coding: utf-8 -*-
"""Portable, plot-independent export contract for ec-lab processed data.

The measurement and fitted EIS grids are deliberately separate.  The workbook
contains actual numeric values and can be plotted without the original files,
local config.json, an Excel installation, or Excel formula recalculation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd


SCHEMA_VERSION = "2"


def validate_output_dir(out_dir, input_dirs=()):
    """Reject output inside any source directory, including junction aliases."""
    destination = os.path.normcase(os.path.realpath(os.path.abspath(out_dir)))
    roots = list(input_dirs)
    if os.name == "nt":
        # The owner's experimental archive is explicitly read-only, including
        # exports launched through CLI rather than the desktop workflow.
        roots.append("E:/Data")
    for source in roots:
        if not source:
            continue
        root = os.path.normcase(os.path.realpath(os.path.abspath(source)))
        try:
            contained = os.path.commonpath([destination, root]) == root
        except ValueError:  # Different Windows drives cannot contain each other.
            contained = False
        if contained:
            raise ValueError("输出目录不能位于原始数据目录内，请选择独立的结果文件夹：" + str(out_dir))
    return os.path.abspath(out_dir)


def input_directories(data, cfg):
    roots = cfg.get("data_dir") or []
    roots = [roots] if isinstance(roots, str) else list(roots)
    protected = cfg.get("protected_data_dirs") or []
    roots += [protected] if isinstance(protected, str) else list(protected)
    roots.extend(os.path.dirname(os.path.abspath(p)) for p in data.get("source_files", []))
    return roots


def unused_path(path):
    """Keep existing results; timestamp repeated exports instead of overwriting."""
    path = Path(path)
    if not path.exists():
        return str(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    number = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{stamp}_{number}{path.suffix}")
        number += 1
    return str(candidate)


def _summary(data):
    rows = []
    for r in data.get("cv", []):
        rows.append({"type": "CV", "file": r["file"],
                     "condition": f"{r['scan_rate_mVs']:g} mV/s",
                     "capacitance_F_g": r["C_F_g"],
                     "scan_rate_mVs": r["scan_rate_mVs"],
                     "mass_mg": r.get("mass_mg")})
    for r in data.get("gcd", []):
        m = r["metrics"]
        rows.append({"type": "GCD", "file": r["file"],
                     "condition": f"{r['current_density_A_g']:g} A/g",
                     "capacitance_F_g": m["capacitance_F_g"],
                     "IR_drop_V": m["IR_drop_V"],
                     "coulombic_eff_%": m.get("coulombic_eff_%"),
                     "energy_Wh_kg": m["energy_Wh_kg"],
                     "power_W_kg": m["power_W_kg"],
                     "current_density_A_g": r["current_density_A_g"],
                     "current_A": r.get("current_A"), "mass_mg": r.get("mass_mg")})
    result = pd.DataFrame(rows)
    if "coulombic_eff_%" in result and result["coulombic_eff_%"].isna().all():
        result = result.drop(columns=["coulombic_eff_%"])
    return result


def _frames(data, cfg):
    # Local import keeps path validation available without importing the engine.
    from eclab import cycle_points

    frames = {}
    for name, key in (("CV", "cv_tables"), ("GCD", "gcd_tables")):
        if data.get(key):
            frames[name] = pd.concat(data[key], ignore_index=True)
    if data.get("eis"):
        frames["EIS"] = pd.concat([
            pd.DataFrame({"file": it["tag"], "Freq_Hz": it["f"],
                          "Z_re_ohm": it["zr"], "Z_im_ohm": it["zi"]})
            for it in data["eis"]], ignore_index=True)
        fits = []
        for it in data["eis"]:
            if it.get("z_fit") is None:
                continue
            z = np.asarray(it["z_fit"], dtype=complex)
            frequency = it.get("fit_f")
            # Legacy external fits do not identify their grid reliably.
            # Preserve the curve, leave frequency blank; never borrow raw f.
            if frequency is None:
                frequency = np.full(len(z), np.nan)
            if len(frequency) != len(z):
                raise ValueError("EIS 拟合频率与拟合曲线点数不一致：" + it["tag"])
            fits.append(pd.DataFrame({
                "file": it["tag"], "Freq_Hz": frequency,
                "Z_re_fit_ohm": z.real, "Z_im_fit_ohm": z.imag,
                "source": it.get("source", ""), "circuit": it.get("circuit", "")}))
        if fits:
            frames["EIS_fit_curve"] = pd.concat(fits, ignore_index=True)
    if data.get("fit_rows"):
        frames["EIS_fit"] = pd.DataFrame(data["fit_rows"])
    frames["summary"] = _summary(data)

    caps, retention = {}, {}
    for name, rec in data.get("cycles", {}).items():
        values = rec["caps"] if isinstance(rec, dict) else rec
        kind = rec.get("kind", "CV") if isinstance(rec, dict) else "CV"
        cycles, selected = cycle_points(values, cfg, kind)
        if not cycles:
            continue
        caps[name] = pd.Series(selected, index=cycles)
        baseline = float(selected[0])
        retention[name] = pd.Series(
            [100.0 * v / baseline if np.isfinite(baseline) and baseline != 0 else np.nan
             for v in selected], index=cycles)
    if caps:
        frames["cycle_capacitance"] = pd.DataFrame(caps).rename_axis("cycle").reset_index()
        frames["cycle_retention"] = pd.DataFrame(retention).rename_axis("cycle").reset_index()

    params = {key: cfg[key] for key in (
        "mass_mg", "area_cm2", "pick_segments", "cv_segments", "gcd_segments",
        "ir_free", "gcd_continuous", "cycle_start", "cycle_step", "cv_cycle_start",
        "cv_cycle_step", "gcd_cycle_start", "gcd_cycle_step", "process", "eis") if key in cfg}
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "software": "ec-lab",
        "GCD_time_s": "Relative to charge start, including measured charge/discharge gap",
        "EIS_sign": "Z_im_ohm is signed imaginary impedance; Nyquist plots use -Z_im_ohm",
        "EIS_fit_grid": "EIS_fit_curve has its own frequency grid; no row alignment with EIS",
        "parameters_json": json.dumps(params, ensure_ascii=False, default=str),
    }
    frames["_ec_lab"] = pd.DataFrame(metadata.items(), columns=["key", "value"])
    if data.get("source_files"):
        frames["sources"] = pd.DataFrame({"source_path": data["source_files"]})
    if data.get("anomalies"):
        frames["warnings"] = pd.DataFrame({"message": data["anomalies"]})
    return frames


def export_tables(data, cfg=None, out_dir=None):
    """Export numeric results without plotting and return the saved xlsx path."""
    from eclab import OUTPUT_DIR, export_zview

    cfg = cfg if cfg is not None else data.get("cfg", {})
    out_dir = out_dir or cfg.get("output", {}).get("dir") or OUTPUT_DIR
    out_dir = validate_output_dir(out_dir, input_directories(data, cfg))
    if not (data.get("cv_tables") or data.get("gcd_tables") or data.get("eis") or data.get("cycles")):
        raise ValueError("没有可导出的处理结果，请先选择文件并处理数据。")
    frames = _frames(data, cfg)
    for name, frame in frames.items():
        if len(frame) > 1_048_575 or len(frame.columns) > 16_384:
            raise ValueError(f"工作表 {name} 超出 Excel 容量，请减少本次处理的数据量。")
    os.makedirs(out_dir, exist_ok=True)
    destination = unused_path(os.path.join(out_dir, "processed_data.xlsx"))
    handle, temporary = tempfile.mkstemp(prefix=".ec_export_", suffix=".xlsx", dir=out_dir)
    os.close(handle)
    try:
        # Own the stream so it is closed even if the Excel writer fails while
        # saving (notably "no visible worksheets" after an earlier exception).
        with open(temporary, "wb") as stream:
            with pd.ExcelWriter(stream, engine="openpyxl") as writer:
                pending = writer.book.create_sheet("_export_pending")
                for name, frame in frames.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
                    worksheet = writer.sheets[name]
                    worksheet.freeze_panes = "A2"
                    if len(frame.columns):
                        worksheet.auto_filter.ref = worksheet.dimensions
                writer.book.remove(pending)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    suffix = Path(destination).stem.removeprefix("processed_data")
    for name in ("cycle_capacitance", "cycle_retention"):
        if name in frames:
            frames[name].to_csv(unused_path(os.path.join(out_dir, name + suffix + ".csv")),
                                index=False, encoding="utf-8-sig")
    if cfg.get("eis", {}).get("export_zview"):
        for it in data.get("eis", []):
            # tag is already unique across input directories; sanitize separators.
            name = re_safe_filename(it["tag"])
            export_zview(name + ".txt", it["f"], it["zr"], it["zi"], out_dir=out_dir)
    print("    [表] " + os.path.basename(destination))
    return destination


def re_safe_filename(value):
    import re
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .") or "EIS"
