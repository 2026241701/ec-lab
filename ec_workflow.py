"""Small, UI-independent guards for reproducible processing jobs."""
import hashlib
import json
import os
from pathlib import Path


def calculation_signature(cfg):
    """Invalidate cached numbers when parameters or source files change.

    Styling and output changes never trigger a recalculation. File metadata is
    collected in the worker, including external EIS fit files and new files.
    """
    numeric = {k: v for k, v in cfg.items()
               if k not in {"output", "plot_style", "plot_style_by_kind"}
               and not k.startswith("_")}
    roots = cfg.get("data_dir") or []
    if isinstance(roots, str):
        roots = [roots]
    records = {}
    for root in roots:
        for directory, _, files in os.walk(root):
            for name in files:
                if not name.lower().endswith(".txt"):
                    continue
                path = Path(directory, name)
                key = os.path.normcase(str(path.resolve()))
                try:
                    stat = path.stat()
                    records[key] = (stat.st_size, stat.st_mtime_ns)
                except OSError:
                    records[key] = None
    payload = json.dumps([numeric, sorted(records.items())], sort_keys=True,
                         ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_output(cfg, default):
    """Reject writing under source folders, including this user's data archive."""
    target = Path(cfg.get("output", {}).get("dir") or default).resolve()
    roots = cfg.get("data_dir") or []
    if isinstance(roots, str):
        roots = [roots]
    protected = [Path(root).resolve() for root in roots]
    if os.name == "nt":
        protected.append(Path("E:/Data").resolve())
    if any(target == root or root in target.parents for root in protected):
        raise ValueError("输出文件夹不能位于原始实验数据目录内。请选择项目下的 output 文件夹。")
    return str(target)
