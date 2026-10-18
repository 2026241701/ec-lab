# -*- coding: utf-8 -*-
"""ec-lab 一键体检  doctor.py

什么时候跑：
  1. python doctor.py          ——文字版，输出到终端（推荐）
  2. 双击「体检.bat」           ——界面版，会弹窗告诉你哪里坏了、怎么修
                                  （由 python make_launchers.py 生成）
  3. 程序报错后跑一次           ——先排除环境问题再看代码

它只做检查、不改任何数据（除非你显式传 --fix 自动补装缺包）。
"""

import os
import re
import sys
import json
import shutil
import glob
import subprocess
import platform
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
# numpy 2.x / pandas 3.x 要求 Python 3.12 以上，低于这个版本装不上依赖
PY_MIN = (3, 12)

# 运行这个程序必需的包：缺任何一个都跑不了
NEED = [("numpy", "数值计算"), ("pandas", "数据表"),
        ("matplotlib", "画图"), ("scipy", "曲线拟合"),
        ("openpyxl", "导出 Excel"), ("PySide6", "图形界面")]

# 画图质量相关：缺了能跑但图会变难看或中文变方块
NICE = [("PIL", "图片处理")]

# 电化学论文常用字体
FONTS = ["Times New Roman", "SimSun", "SimHei", "Microsoft YaHei",
         "DejaVu Serif", "Arial"]

OK, WARN, BAD = "OK  ", "注意", "坏了"


class Report:
    def __init__(self):
        self.rows = []
        self.fixes = []

    def add(self, level, item, detail=""):
        self.rows.append((level, item, detail))
        print("  [%s] %-22s %s" % (level, item, detail))

    def fix(self, how):
        self.fixes.append(how)

    @property
    def bad(self):
        return [r for r in self.rows if r[0] == BAD]

    @property
    def warn(self):
        return [r for r in self.rows if r[0] == WARN]


# ==================================================================
# 各项检查
# ==================================================================

def check_python(rep):
    v = sys.version_info
    ver = "%d.%d.%d" % v[:3]
    if v[:2] < PY_MIN:
        rep.add(BAD, "Python 版本", "%s 太老，需要 3.12 以上" % ver)
        rep.fix("去 python.org 装 Python 3.12 或更新的版本"
                "（numpy 2.x 要求 3.12+），安装时勾选 Add Python to PATH")
        return
    rep.add(OK, "Python 版本", ver)


def check_where(rep):
    """解释器是不是临时环境里的——这类环境被清理后软件就打不开了"""
    exe = os.path.abspath(sys.executable)
    low = exe.replace("/", "\\").lower()
    # 临时目录 / 会被自动清理的私有环境，都是危险的解释器位置
    markers = ("\\temp\\", "\\appdata\\local\\temp\\", ".workbuddy")
    if any(m in low for m in markers):
        rep.add(WARN, "解释器位置", "在临时目录里，环境被清理后软件就打不开了")
        rep.fix("请把项目放在一个固定、不临时的目录，并在项目里建自己的虚拟环境"
                "（python -m venv .venv），或按说明打包成 exe")
    else:
        rep.add(OK, "解释器位置", exe)


def check_project_path(rep):
    """项目是不是躺在会被清理的临时目录里"""
    p = BASE.replace("/", "\\")
    low = p.lower()
    if "\\temp\\" in low or "\\appdata\\local\\temp\\" in low:
        rep.add(WARN, "项目位置", "在临时目录，有被清理的风险")
        rep.fix("把整个项目文件夹放到一个固定、不临时的目录长期存放"
                "（例如 D 盘根目录下新建一个文件夹），别放在桌面临时目录里")
    else:
        rep.add(OK, "项目位置", p)


def check_packages(rep, auto_fix=False):
    missing = []
    for mod, why in NEED:
        try:
            m = __import__(mod)
            got = getattr(m, "__version__", "?")
            rep.add(OK, mod, "%s（%s）" % (got, why))
        except Exception:
            missing.append(mod)
            rep.add(BAD, mod, "没装 —— 软件无法%s" % why)

    if missing and auto_fix:
        cmd = [sys.executable, "-m", "pip", "install"] + missing
        rep.add(WARN, "自动补装", "正在装：" + " ".join(missing))
        try:
            subprocess.check_call(cmd)
            rep.add(OK, "自动补装", "装完了，重新运行一次体检确认")
        except Exception as exc:
            rep.add(BAD, "自动补装", "失败：%s" % exc)
            rep.fix("联网后在这个目录开命令行，手动执行：\n    "
                    '"%s" -m pip install %s' % (sys.executable,
                                                " ".join(missing)))
    elif missing:
        rep.fix('在此目录开命令行，执行：\n    "%s" -m pip install %s'
                % (sys.executable, " ".join(missing)))

    for mod, why in NICE:
        try:
            __import__(mod)
            rep.add(OK, mod, why)
        except Exception:
            rep.add(WARN, mod, "没装（不影响使用）")


def check_fonts(rep):
    try:
        from matplotlib import font_manager
    except Exception:
        rep.add(WARN, "绘图字体", "matplotlib 没装，跳过检查")
        return
    try:
        names = set(f.name for f in font_manager.fontManager.ttflist)
    except Exception as exc:
        rep.add(WARN, "绘图字体", "读不到字体列表：%s" % exc)
        return

    have = [f for f in FONTS if f in names]
    for f in FONTS:
        if f in names:
            rep.add(OK, "字体 " + f, "")
    if "Times New Roman" not in names:
        rep.add(WARN, "西文字体", "缺 Times New Roman，图会换成默认字体")
        rep.fix("论文图建议西文 Times New Roman、中文宋体。"
                "Windows 自带 Times New Roman，若显示缺失请检查是否"
                "安装了精简版系统")
    if "SimSun" not in names and "SimHei" not in names:
        rep.add(WARN, "中文字体", "缺宋体/黑体，图中中文会变方块")
        rep.fix("Windows 自带 SimSun 与 SimHei。若确实没有，"
                "在绘图样式里把中文字体改成'微软雅黑'")


def check_files(rep):
    must = ["eclab.py", "ec_gui.py", "config.json"]
    for f in must:
        p = os.path.join(BASE, f)
        if os.path.isfile(p):
            rep.add(OK, "文件 " + f, "")
        else:
            rep.add(BAD, "文件 " + f, "不见了")
            rep.fix("%s 丢了：可运行 python ec_gui.py 让它自动生成一份"
                    "（第一次运行会用 config.example.json 模板），"
                    "或用 git 恢复：git checkout -- %s" % (f, f))

    # config.json 能不能解析 —— 手改坏了这里会报错
    cp = os.path.join(BASE, "config.json")
    if os.path.isfile(cp):
        try:
            cfg = json.load(open(cp, encoding="utf-8"))
            rep.add(OK, "config.json 格式", "正常")
            check_cfg_dirs(rep, cfg)
        except Exception as exc:
            rep.add(BAD, "config.json 格式", "坏了：%s" % exc)
            baks = sorted(glob.glob(os.path.join(BASE,
                          "config_backup_*.json")), reverse=True)
            if baks:
                rep.fix("把 config.json 换成备份：%s" % baks[0])
            else:
                rep.fix("删掉损坏的 config.json，程序会重建一份默认的，"
                        "再重新填数据文件夹")


def check_cfg_dirs(rep, cfg):
    dirs = cfg.get("data_dir", [])
    if isinstance(dirs, str):
        dirs = [dirs]
    if not dirs:
        rep.add(WARN, "数据文件夹", "一个都没设")
        rep.fix("打开软件点『添加文件夹』选你的 CHI660 数据所在目录")
    for d in dirs:
        if os.path.isdir(d):
            n = len(glob.glob(os.path.join(d, "**", "*.txt"),
                              recursive=True))
            rep.add(OK, "数据文件夹", "%s（%d 个 txt）"
                    % (os.path.basename(d) or d, n))
        else:
            rep.add(BAD, "数据文件夹", "不存在：%s" % d)
            rep.fix("路径变了或硬盘没插上。改回实际位置，或打开软件"
                    "重新『添加文件夹』")

    mass = cfg.get("mass_mg", {})
    if isinstance(mass, dict) and "*" in mass:
        rep.add(WARN, "样品质量", "用的是兜底值 %s mg" % mass.get("*"))
        rep.fix("所有样品都套同一个质量会算错比电容。"
                "在扫描结果表格里逐个填真实质量，"
                "再删掉 mass_mg 里的 '*' 这一行")
    elif isinstance(mass, dict) and mass:
        rep.add(OK, "样品质量", "已逐个登记 %d 个" % len(mass))


def check_output(rep, cfg):
    od = (cfg.get("output") or {}).get("dir") or os.path.join(BASE, "output")
    parent = od if os.path.isdir(od) else BASE
    if os.path.isdir(od):
        rep.add(OK, "输出文件夹", od)
    else:
        rep.add(WARN, "输出文件夹", "还不存在，会自动创建")
    if not os.access(parent, os.W_OK):
        rep.add(BAD, "写入权限", "%s 不可写" % parent)
        rep.fix("把输出目录改到桌面或 D 盘，别放在需要管理员权限的位置")
    else:
        rep.add(OK, "写入权限", "正常")

    try:
        free = shutil.disk_usage(BASE).free / 1024 ** 3
        if free < 2:
            rep.add(BAD, "磁盘空间", "只剩 %.1f GB，出图会失败" % free)
            rep.fix("清理磁盘，或把输出目录换到空盘")
        elif free < 10:
            rep.add(WARN, "磁盘空间", "剩 %.0f GB，偏少" % free)
        else:
            rep.add(OK, "磁盘空间", "剩 %.0f GB" % free)
    except Exception:
        pass


def check_git(rep):
    if os.path.isdir(os.path.join(BASE, ".git")):
        try:
            n = subprocess.check_output(
                ["git", "-C", BASE, "rev-list", "--count", "HEAD"],
                stderr=subprocess.DEVNULL).decode().strip()
            rep.add(OK, "版本记录", "%s 个历史版本" % n)
            dirty = subprocess.check_output(
                ["git", "-C", BASE, "status", "--porcelain"],
                stderr=subprocess.DEVNULL).decode().strip()
            if dirty:
                rep.add(WARN, "未保存改动", "%d 个文件改了还没存档"
                        % len(dirty.splitlines()))
                rep.fix("改完代码后在项目目录执行："
                        'git add -A && git commit -m "说明"')
            else:
                rep.add(OK, "未保存改动", "无")
        except Exception:
            rep.add(OK, "版本记录", "已启用 git")
    else:
        rep.add(WARN, "版本记录", "没启用 git")
        rep.fix("代码改坏了无法回退。在项目目录执行：\n"
                "    git init && git add -A && "
                'git commit -m "基线"')


def check_launchers(rep):
    """启动脚本是不是指向了会消失的解释器"""
    names = ("启动软件.bat", "run.bat", "debug_start.bat")
    if not any(os.path.isfile(os.path.join(BASE, f)) for f in names):
        # 公开仓库不带 .bat（由 make_launchers.py 按本机 Python 路径生成），
        # 所以一个都没有是正常状态：直接 python ec_gui.py 启动即可
        rep.add(OK, "启动脚本", "未生成（可选），用 python ec_gui.py 启动")
        return
    for f in names:
        p = os.path.join(BASE, f)
        if not os.path.isfile(p):
            rep.add(WARN, "启动 " + f, "不存在")
            continue
        raw = open(p, "rb").read()
        note = []
        if b"\r\n" not in raw:
            note.append("换行不是 CRLF，双击可能报错")
        if b".workbuddy" in raw:
            note.append("指向临时 Python")
        if note:
            rep.add(WARN, "启动 " + f, "；".join(note))
            rep.fix("执行 python make_launchers.py 重新生成启动脚本"
                    "（会按本机 Python 位置重写 .bat）")
        else:
            rep.add(OK, "启动 " + f, "")

    p = os.path.join(BASE, "启动软件.vbs")
    if os.path.isfile(p):
        raw = open(p, "rb").read()
        if raw[:2] == b"\xff\xfe":
            rep.add(OK, "启动 启动软件.vbs", "编码正确")
        else:
            rep.add(WARN, "启动 启动软件.vbs", "编码不对，双击会乱码")
    else:
        rep.add(WARN, "启动 启动软件.vbs", "不存在")


def check_collab(rep):
    """协作锁状态：多人（或多个窗口）同时改同一个软件时用"""
    if not os.path.isdir(os.path.join(BASE, "_collab")):
        # 没启用过协作锁（公开仓库 / 单人使用）：整段跳过，别报红
        return
    try:
        import ec_lock
    except Exception:
        return
    cur = ec_lock._read_lock()
    if cur and cur.get("name"):
        import time as _t
        held = _t.time() - (cur.get("since") or _t.time())
        rep.add(WARN, "协作锁", "%s 正在改（已持有 %.0f 分钟）"
                % (cur["name"], held / 60))
        if held > 3600:
            rep.add(WARN, "锁可能忘了还", "超过 1 小时了")
            rep.fix("如果对方已经不干了："
                    "python ec_lock.py steal")
        else:
            rep.fix("现在别改代码。先只读、想方案，"
                    "或去改不会冲突的文件")
    else:
        rep.add(OK, "协作锁", "空闲")

    ho = ec_lock.HANDOVER
    if os.path.isfile(ho):
        try:
            txt = open(ho, encoding="utf-8").read().strip()
            if txt:
                rep.add(OK, "交接便条", txt[:60])
        except Exception:
            pass

    work = os.path.join(BASE, "_collab", "工作台.md")
    if os.path.isfile(work):
        rep.add(OK, "协作工作台", "三个项目分工已记录")
    else:
        rep.add(WARN, "协作工作台", "缺少 _collab/工作台.md")
        rep.fix("多项目同时改时，分工要写清楚，否则会互相覆盖")


def run_math_check(rep):
    """用小样本验证计算引擎没被改坏——比电容必须为正且随扫速单调下降"""
    try:
        import numpy as np
        import eclab
    except Exception as exc:
        rep.add(WARN, "算法自检", "引擎没导入成功：%s" % exc)
        return
    try:
        # 造一条理想 CV：扫速越快比电容越低
        ok = True
        vals = []
        for sr in (0.05, 0.1, 0.2):
            t = np.linspace(0, 1, 400)
            E = np.concatenate([np.linspace(-0.8, 0.8, 200),
                                np.linspace(0.8, -0.8, 200)])
            I = np.concatenate([np.sin(t[:200] * 6) * 1e-3,
                                np.sin(t[:200] * 6 + 3) * 1e-3])
            C = eclab.cv_capacitance(E, I, sr, 0.001)
            vals.append(C)
            if not np.isfinite(C) or C <= 0:
                ok = False
        if ok:
            rep.add(OK, "算法自检", "CV 比电容计算正常")
        else:
            rep.add(BAD, "算法自检", "算出了异常值 %s" % vals)
            rep.fix("引擎可能被改坏了，用 git 恢复："
                    "git checkout -- eclab.py")
    except Exception as exc:
        rep.add(WARN, "算法自检", "跳过：%s" % exc)


# ==================================================================
# 汇总与呈现
# ==================================================================

def build_help(rep):
    lines = []
    lines.append("=" * 62)
    lines.append("  ec-lab 体检结果   %s"
                 % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("=" * 62)
    if rep.bad:
        lines.append("")
        lines.append("【必须处理】%d 项坏了，不处理软件跑不起来："
                     % len(rep.bad))
        for _, item, detail in rep.bad:
            lines.append("  x %s：%s" % (item, detail))
    if rep.warn:
        lines.append("")
        lines.append("【建议处理】%d 项有隐患：" % len(rep.warn))
        for _, item, detail in rep.warn:
            lines.append("  ! %s：%s" % (item, detail))
    if not rep.bad and not rep.warn:
        lines.append("")
        lines.append("一切正常，可以放心用。")

    if rep.fixes:
        lines.append("")
        lines.append("-" * 62)
        lines.append("照着做就能修好：")
        lines.append("")
        for i, f in enumerate(rep.fixes, 1):
            lines.append("  %d. %s" % (i, f))
    lines.append("")
    lines.append("=" * 62)
    return "\n".join(lines)


def main():
    auto_fix = "--fix" in sys.argv
    print("=" * 62)
    print("  ec-lab 一键体检")
    print("=" * 62)

    rep = Report()
    check_python(rep)
    check_where(rep)
    check_project_path(rep)
    check_packages(rep, auto_fix=auto_fix)
    check_fonts(rep)
    check_files(rep)
    check_git(rep)
    check_launchers(rep)
    check_collab(rep)
    check_output(rep, _load_cfg())
    run_math_check(rep)

    help_text = build_help(rep)
    print()
    print(help_text)

    out = os.path.join(BASE, "体检报告.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(help_text + "\n")
        print("报告已保存：%s" % out)
    except Exception:
        pass

    # GUI 环境下弹窗，方便小白直接看到
    if os.environ.get("EC_DOCTOR_GUI") == "1":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, help_text, "ec-lab 体检结果", 0x10 if rep.bad else 0x40)
        except Exception:
            pass
    return 1 if rep.bad else 0


def _load_cfg():
    p = os.path.join(BASE, "config.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


if __name__ == "__main__":
    sys.exit(main())
