"""Versioned processing presets containing parameters only (stdlib only)."""
import json
import math
from pathlib import Path


SCHEMA = "ec-lab.processing-template"
VERSION = 1
MAX_TEMPLATE_BYTES = 64 * 1024
DEFAULTS = {
    "electrochem": {"mass_mg": 0.0, "time_step": 0.1},
    "cp_cycle": {"time_step": 0.1},
    "cv_cycle": {"split_mode": "peak"},
    "cdi": {"mass_mg": 0.0, "cdi_step": "auto", "cycle_minutes": 60.0,
            "volume_ml": 50.0, "calibration_base": 8.2236,
            "calibration_scale": 1.97252, "conductivity_unit": "uS/cm",
            "cdi_tail": "reference"},
    "contribution": {},
}
RANGES = {"mass_mg": (0, 1e6), "time_step": (0.00001, 3600),
          "cdi_step": (0.001, 3600), "cycle_minutes": (0.001, 10000),
          "volume_ml": (0.0001, 1e6), "calibration_base": (-1e6, 1e6),
          "calibration_scale": (0.000001, 1e6)}
ENUMS = {"split_mode": {"peak", "valley"},
         "conductivity_unit": {"uS/cm", "mS/cm", "S/m"},
         "cdi_tail": {"reference", "include", "complete"}}


def validate_template(document):
    """Reject unknown fields, paths and executable content before applying."""
    if not isinstance(document, dict) or set(document) != {"schema", "version", "mode", "parameters"}:
        raise ValueError("数据处理模板必须包含 schema、version、mode、parameters，且不能包含文件路径或额外字段。")
    if document["schema"] != SCHEMA or type(document["version"]) is not int or document["version"] != VERSION:
        raise ValueError("不支持的数据处理模板格式或版本。")
    mode, parameters = document["mode"], document["parameters"]
    if not isinstance(mode, str) or mode not in DEFAULTS:
        raise ValueError("模板中的处理类型无效。")
    if not isinstance(parameters, dict) or set(parameters) - set(DEFAULTS[mode]):
        raise ValueError("模板含此处理类型不支持的参数；输入文件、输出位置和 Excel 格式模板路径不能保存到参数模板。")
    values = {**DEFAULTS[mode], **parameters}
    for name, value in values.items():
        if name == "cdi_step" and value == "auto":
            continue
        if name in ENUMS:
            if not isinstance(value, str) or value not in ENUMS[name]:
                raise ValueError("模板参数无效：" + name)
        else:
            low, high = RANGES[name]
            if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"模板参数 {name} 必须在 {low:g}–{high:g} 之间。")
            values[name] = float(value)
    if mode == "cdi" and values["cdi_step"] != "auto":
        points = values["cycle_minutes"] * 60 / values["cdi_step"]
        if not math.isclose(points, round(points)) or not 2 <= points <= 100_000:
            raise ValueError("CDI 每圈时长必须能被采样间隔整除，且每圈为 2–10 万个点。")
    return {"schema": SCHEMA, "version": VERSION, "mode": mode, "parameters": values}


def make_template(mode, parameters):
    return validate_template({"schema": SCHEMA, "version": VERSION,
                              "mode": mode, "parameters": parameters})


def load_template(path):
    path = Path(path)
    if path.stat().st_size > MAX_TEMPLATE_BYTES:
        raise ValueError("数据处理模板超过 64 KB，请选择参数 JSON 文件。")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取数据处理模板，请选择有效的 UTF-8 JSON 文件。") from exc
    return validate_template(document)


def save_template(path, mode, parameters):
    """Save only validated parameters; callers own location/overwrite choices."""
    document = make_template(mode, parameters)
    path = Path(path).resolve()
    if path.is_relative_to(Path("E:/Data").resolve()):
        raise ValueError("E:/Data 是只读实验数据目录，请把参数模板保存到项目的 templates 文件夹或其他位置。")
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return document
