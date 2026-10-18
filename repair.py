# -*- coding: utf-8 -*-
"""ec-lab 修复与存档  repair.py

用法（一般不用手动跑，双击对应的 bat 即可）：
    python repair.py             修一遍：备份配置、清缓存、清理垃圾
    python repair.py --snapshot  顺便把当前代码存进 git

它做的事都不会破坏你的数据：
  - 配置备份到 _cfg_backup（本来就只增不减）
  - 删 __pycache__（Python 自动生成的缓存，删了会自己重建）
  - 把改坏的 config 留档成 config.json.坏了_时间戳（不删原件）
"""

import os
import sys
import glob
import time
import shutil
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# 绝不能删的东西
KEEP = {"eclab.py", "ec_gui.py", "cfg_guard.py", "doctor.py",
        "repair.py", "config.json", "repair.bat", "doctor.bat"}


def backup_cfg():
    import cfg_guard
    cfg, note = cfg_guard.load_config()
    dst = cfg_guard.backup_config(cfg)
    if dst:
        print("  [备份] 配置已存到 %s" % os.path.basename(dst))
    if note:
        print("  [提示] %s" % note.replace("\n", " "))
    return cfg


def clean_cache():
    n = 0
    for d in glob.glob(os.path.join(BASE, "__pycache__")):
        try:
            shutil.rmtree(d)
            n += 1
        except Exception:
            pass
    print("  [清理] 缓存目录 %d 个" % n)


def archive_broken():
    """损坏的配置留档，不删——小白常常需要看它错在哪"""
    p = os.path.join(BASE, "config.json")
    if not os.path.isfile(p):
        return
    try:
        import json
        json.load(open(p, encoding="utf-8"))
    except Exception:
        dst = p + ".坏了_" + time.strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(p, dst)
            print("  [留档] 损坏的配置已复制为 %s（原文件保留）"
                  % os.path.basename(dst))
        except Exception:
            pass


def quarantine_junk():
    """把明显的临时/测试文件挪进 _junk 目录，不删"""
    junk_dir = os.path.join(BASE, "_junk")
    moved = 0
    for p in glob.glob(os.path.join(BASE, "*.py")):
        name = os.path.basename(p)
        if name in KEEP:
            continue
        if name.startswith("_t_") or name.startswith("tmp"):
            try:
                os.makedirs(junk_dir, exist_ok=True)
                shutil.move(p, os.path.join(junk_dir, name))
                moved += 1
            except Exception:
                pass
    if moved:
        print("  [归整] %d 个临时脚本挪到 _junk（没删）" % moved)


def snapshot():
    """把当前代码存进 git，改坏了能回去"""
    if not os.path.isdir(os.path.join(BASE, ".git")):
        print("  [存档] 还没启用 git，跳过（执行 git init 可启用）")
        return
    try:
        r = subprocess.run(["git", "-C", BASE, "add", "-A"],
                           capture_output=True, timeout=60)
        r = subprocess.run(["git", "-C", BASE, "diff", "--cached",
                            "--quiet"], capture_output=True, timeout=60)
        if r.returncode == 0:
            print("  [存档] 代码没有变化，无需提交")
            return
        msg = "存档 %s" % time.strftime("%Y-%m-%d %H:%M")
        c = subprocess.run(
            ["git", "-C", BASE, "-c", "user.name=Ding",
             "-c", "user.email=ding@local", "commit", "-q", "-m", msg],
            capture_output=True, timeout=60)
        if c.returncode == 0:
            n = subprocess.check_output(
                ["git", "-C", BASE, "rev-list", "--count", "HEAD"],
                stderr=subprocess.DEVNULL).decode().strip()
            print("  [存档] 已提交，现在共 %s 个历史版本" % n)
        else:
            print("  [存档] 提交没成功：%s"
                  % c.stderr.decode(errors="replace")[:120])
    except FileNotFoundError:
        print("  [存档] 没装 git，跳过")
    except Exception as exc:
        print("  [存档] 出错：%s" % exc)


def verify():
    """确认核心文件都还在、代码能导入"""
    missing = [f for f in ("eclab.py", "ec_gui.py", "config.json")
               if not os.path.isfile(os.path.join(BASE, f))]
    if missing:
        print("  [检查] 缺少：%s —— 用 git 恢复：git checkout -- <文件>"
              % " ".join(missing))
        return
    print("  [检查] 核心文件齐全")
    try:
        import eclab
        import cfg_guard
        print("  [检查] 引擎与保险箱可以正常导入")
    except Exception as exc:
        print("  [检查] 导入失败：%s" % exc)


def main():
    snapshot_mode = "--snapshot" in sys.argv
    print("=" * 56)
    print("  ec-lab 修复工具")
    print("=" * 56)
    archive_broken()
    backup_cfg()
    clean_cache()
    quarantine_junk()
    if snapshot_mode:
        snapshot()
    verify()
    print()
    print("完成。以后遇到问题，先双击「体检.bat」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
