# -*- coding: utf-8 -*-
"""ec-lab 配置保险箱  cfg_guard.py

解决的问题：
  小白最容易干的蠢事之一是手改 config.json，改坏了��下次双击就开不了。
  这个模块负责：
    1. save_config()  写回前自动备份，保留最近 10 份
    2. load_config()  读配置；坏了自动从备份恢复并记录，不再静默丢数据
    3. 写入用「临时文件 + 原子替换」，断电/崩溃不会写出半个文件

用法（在 ec_gui.py 里把原来的 open(...)+json.dump(...) 换成）：
    from cfg_guard import load_config, save_config
    cfg = load_config()                    # 永远拿到可用的配置
    save_config(cfg)                       # 永远安全地写回
"""

import os
import re
import sys
import json
import glob
import time
import shutil

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
# 公开仓库里提交的是模板（不含任何个人路径与样品质量）；config.json 本身
# 不入库，首次运行时由 seed_config_from_example() 复制模板生成。
EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")
BACKUP_DIR = os.path.join(BASE_DIR, "_cfg_backup")
KEEP_N = 10          # 保留最近几份备份

# 最小可用配置：config.json 全丢了也能凭这个起步
FALLBACK = {
    "_说明": [
        "data_dir: 数据文件夹路径（可多个，递归扫描）",
        "mass_mg: 每个样品的活性物质质量 mg。星号键(*)是兜底值；删掉它则强制逐个填写（推荐）",
        "本文件由 ec-lab 自动维护，每次写回前会自动备份到 _cfg_backup 文件夹",
    ],
    "data_dir": [],
    "area_cm2": 1.0,
    "pick_segments": [2, 3],
    "cv_segments": [],
    "gcd_segments": [],
    "cycle_start": 30,
    "cycle_step": 10,
    "skip_keywords_cv": ["活化"],
    "ir_free": False,
    "gcd_continuous": False,
    "dedupe_condition": True,
    "exclude_filename": ["-fit", "副本"],
    "mass_mg": {},
    "eis": {"fit": True, "circuit": "auto",
            "use_external_fit": True, "export_zview": False},
    "output": {"formats": ["png"], "dpi": 600, "dir": None},
    "plot_style": {},
    "plot_style_by_kind": {},
}


# ==================================================================
# 备份
# ==================================================================

def _ts():
    return time.strftime("%Y%m%d-%H%M%S")


def backup_config(cfg=None):
    """把当前 config.json 复制一份到 _cfg_backup，返回备份路径

    没有 config.json 时不报错（首次运行属正常）。
    """
    if not os.path.isfile(CONFIG_PATH):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = _ts()
        dst = os.path.join(BACKUP_DIR, "config_%s.json" % stamp)
        n = 1
        while os.path.exists(dst):        # 同一秒内多次保存不覆盖
            dst = os.path.join(BACKUP_DIR, "config_%s-%d.json"
                               % (stamp, n))
            n += 1
        if cfg is not None:
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        else:
            shutil.copy2(CONFIG_PATH, dst)
        _prune()
        return dst
    except Exception:
        return None


def _prune():
    """只留最近 KEEP_N 份，避免备份文件夹无限膨胀"""
    try:
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, "config_*.json")))
        for old in files[:-KEEP_N]:
            os.remove(old)
    except Exception:
        pass


def list_backups():
    """所有可用备份，新到旧"""
    try:
        return sorted(glob.glob(os.path.join(BACKUP_DIR, "config_*.json")),
                      reverse=True)
    except Exception:
        return []


# ==================================================================
# 读写
# ==================================================================

def save_config(cfg):
    """安全写回 config.json

    返回 (是否成功, 说明)。成功时自动先备份旧文件。
    """
    try:
        if os.path.isfile(CONFIG_PATH):
            backup_config()
        os.makedirs(BASE_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())          # 确保真的落盘
        os.replace(tmp, CONFIG_PATH)      # 原子替换，不会留半个文件
        return True, "已保存"
    except Exception as exc:
        # 磁盘满 / 文件被占用 —— 保住旧文件，把原始错误交回去
        return False, str(exc)


def _sanity(cfg):
    """配置必须满足的最低条件，不满足就补默认值"""
    if not isinstance(cfg, dict):
        raise ValueError("配置不是字典格式")
    for k, v in FALLBACK.items():
        if k.startswith("_"):
            continue
        cfg.setdefault(k, json.loads(json.dumps(v)))
    if not isinstance(cfg.get("data_dir"), (list, str)):
        cfg["data_dir"] = []
    if not isinstance(cfg.get("mass_mg"), dict):
        cfg["mass_mg"] = {}
    if not isinstance(cfg.get("eis"), dict):
        cfg["eis"] = json.loads(json.dumps(FALLBACK["eis"]))
    if not isinstance(cfg.get("output"), dict):
        cfg["output"] = json.loads(json.dumps(FALLBACK["output"]))
    return cfg


def seed_config_from_example():
    """config.json 不存在时，用仓库自带的模板 config.example.json 生成一份

    开源分发场景：仓库里只提交模板（不含个人数据路径、不含样品质量登记），
    陌生人 clone 后第一次启动就自动得到一份干净的可写配置，不需要手动复制。
    走 save_config() 的原子写，绝不会留下半个文件。

    返回 True 表示刚生成了新配置；已有配置 / 没模板 / 写不进去都返回 False
    （写不进去时 load_config 后面还有备份恢复与 FALLBACK 两道兜底）。
    """
    if os.path.isfile(CONFIG_PATH):
        return False
    if not os.path.isfile(EXAMPLE_PATH):
        return False
    try:
        with open(EXAMPLE_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return False
        ok, _msg = save_config(cfg)
        return ok
    except Exception:
        return False


def load_config():
    """读配置。坏了自动恢复，实在不行给一份能用的空配置。

    返回 (cfg, 提示信息 或 None)。提示信息是需要弹窗告诉用户的。
    """
    note = None
    cfg = None

    # 首次运行：config.json 不在时，先用仓库自带的模板生成一份。
    # 开源分发只提交 config.example.json；Ding 自己的 config.json 不入库，
    # 所以陌生人 clone 后第一次启动就能拿到一份干净配置。
    try:
        seed_config_from_example()
    except Exception:
        pass      # 模板写不进去也不要紧，下面还有备份与 FALLBACK 两道兜底

    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:
            note = ("config.json 读不出来（%s）\n"
                    "已自动从备份恢复，你的设置不会丢。" % exc)
            bad = CONFIG_PATH + ".坏了_" + _ts()
            try:
                shutil.copy2(CONFIG_PATH, bad)     # 坏文件留档，不删
            except Exception:
                pass
            cfg = None

    if cfg is None:
        for b in list_backups():
            try:
                with open(b, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if not note:
                    note = ("config.json 缺失或损坏，\n"
                            "已自动恢复最近备份：\n%s" % os.path.basename(b))
                try:
                    save_config(cfg)
                except Exception:
                    pass
                break
            except Exception:
                continue

    if cfg is None:
        cfg = json.loads(json.dumps(FALLBACK))
        if not note:
            note = ("找不到可用的 config.json，\n"
                    "已生成一份默认配置，请在软件里重新填数据文件夹。")
        try:
            save_config(cfg)
        except Exception:
            pass

    try:
        cfg = _sanity(cfg)
    except Exception as exc:
        cfg = json.loads(json.dumps(FALLBACK))
        note = (note or "") + "\n配置格式异常（%s），已重置为默认。" % exc

    return cfg, note


def backup_problem_files(path):
    """把 CHI 原始数据里的重复/副本文件列出来，帮小白清理数据目录

    只读，不动任何文件 —— 返回 [(重复文件名, 出现次数)]。
    """
    from collections import Counter
    cnt = Counter()
    try:
        for p in glob.glob(os.path.join(path, "**", "*.txt"),
                           recursive=True):
            cnt[os.path.basename(p)] += 1
    except Exception:
        return []
    return sorted([(n, c) for n, c in cnt.items() if c > 1],
                  key=lambda x: -x[1])
