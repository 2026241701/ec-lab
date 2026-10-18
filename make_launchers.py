# -*- coding: utf-8 -*-
"""生成启动脚本：纯 ASCII + CRLF 的 bat，以及完全无窗口的 vbs。

为什么要重写：之前的 .bat 是 UTF-8 + 纯 LF 换行且含中文，
cmd 解析时会错行，把 `>nul` 和中文标题当命令执行，于是弹出
"'nul' 不是内部或外部命令" 和中文乱码报错。
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
# 固定 Python：项目自带的虚拟环境（项目根目录下的 .venv，不依赖任何临时环境）。
# 用 Python 3.12+ 创建，例如在项目根目录执行：python -m venv .venv
# 如果整个项目搬到别处，.venv 会失效——在新位置重跑本脚本即可。
SCRIPTS = os.path.join(BASE, ".venv", "Scripts")
PYW = os.path.join(SCRIPTS, "pythonw.exe")     # 无控制台
PYC = os.path.join(SCRIPTS, "python.exe")      # 有控制台（调试用）


def write_crlf(name, lines):
    """写纯 ASCII + CRLF 的批处理，避免 cmd 解析错行"""
    data = ("\r\n".join(lines) + "\r\n").encode("ascii", "replace")
    with open(os.path.join(BASE, name), "wb") as f:
        f.write(data)
    print(f"{name:20s} {len(data):5d} bytes  CRLF={data.count(b'\r\n')}")


write_crlf("启动软件.bat", [
    "@echo off",
    "rem ec-lab launcher - ASCII + CRLF, starts GUI without console",
    'cd /d "%~dp0"',
    f'set "PYW={PYW}"',
    f'set "PYC={PYC}"',
    'if exist "%PYW%" (',
    '    start "" "%PYW%" "%~dp0ec_gui.py"',
    "    exit /b 0",
    ")",
    'if exist "%PYC%" (',
    '    start "" "%PYC%" "%~dp0ec_gui.py"',
    "    exit /b 0",
    ")",
    "where pyw >nul 2>nul",
    "if not errorlevel 1 (",
    '    start "" pyw -3 "%~dp0ec_gui.py"',
    "    exit /b 0",
    ")",
    "echo.",
    "echo [ERROR] Python with PySide6 was not found.",
    "echo Install Python 3, or run this folder with: python ec_gui.py",
    "pause",
])

write_crlf("debug_start.bat", [
    "@echo off",
    "rem Debug launcher - keeps the console so tracebacks stay visible",
    'cd /d "%~dp0"',
    f'"{PYC}" "%~dp0ec_gui.py"',
    "pause",
])

write_crlf("run.bat", [
    "@echo off",
    "rem Command line version: process data without the GUI",
    'cd /d "%~dp0"',
    f'set "PY={PYC}"',
    'if exist "%PY%" (',
    '    "%PY%" eclab.py',
    ") else (",
    "    py -3 eclab.py",
    ")",
    "echo.",
    "echo Done. Results are in the output folder.",
    "pause",
])

# VBS：双击完全不弹任何窗口（wscript 支持 UTF-16LE 带 BOM 的脚本）
vbs_lines = [
    'Set sh = CreateObject("WScript.Shell")',
    'Set fso = CreateObject("Scripting.FileSystemObject")',
    "base = fso.GetParentFolderName(WScript.ScriptFullName)",
    "sh.CurrentDirectory = base",
    f'pyw = "{PYW}"',
    'If Not fso.FileExists(pyw) Then pyw = fso.GetParentFolderName(pyw)'
    ' & "\\python.exe"',
    'If Not fso.FileExists(pyw) Then pyw = ""',
    'If pyw = "" Then',
    '  MsgBox "Python not found. Please install Python 3 first.", 48, '
    '"ec-lab"',
    "Else",
    '  sh.Run """" & pyw & """ """ & base & "\\ec_gui.py""", 0, False',
    "End If",
]
with open(os.path.join(BASE, "启动软件.vbs"), "wb") as f:
    f.write(b"\xff\xfe" + ("\r\n".join(vbs_lines) + "\r\n").encode("utf-16-le"))
print("启动软件.vbs       UTF-16LE（wscript 可正确识别）")

# ------------------------------------------------------------------
# v0.8 新增：体检入口 + 修复入口
# 小白遇到「双击没反应 / 软件打不开」时，第一步就双击这个体检.bat
# ------------------------------------------------------------------
write_crlf("体检.bat", [
    "@echo off",
    "rem ec-lab health check - run this FIRST when something looks wrong",
    'cd /d "%~dp0"',
    f'"{PYC}" "%~dp0doctor.py" --fix',
    "echo.",
    "pause",
])

# 体检完顺手把配置备份一份，小白误删 config.json 也能找回来
write_crlf("修复.bat", [
    "@echo off",
    "rem ec-lab repair - backup config, clean cache, verify files",
    'cd /d "%~dp0"',
    f'"{PYC}" "%~dp0repair.py"',
    "echo.",
    "pause",
])

# 自动备份：每次跑处理前先存一份配置与代码版本
write_crlf("存档.bat", [
    "@echo off",
    "rem ec-lab snapshot - save current code + config into git",
    'cd /d "%~dp0"',
    f'"{PYC}" "%~dp0repair.py" --snapshot',
    "echo.",
    "pause",
])

# 协作看板：Ding 双击就能看谁在改代码、谁该等
# 文件名用英文，因为 cmd 在某些编码下会认不出中文名
write_crlf("collaboration.bat", [
    "@echo off",
    "rem ec-lab collab board - who is editing the code right now",
    'cd /d "%~dp0"',
    f'"{PYC}" "%~dp0ec_board.py"',
    "echo.",
    "pause",
])

board_vbs = [
    'Set sh = CreateObject("WScript.Shell")',
    'Set fso = CreateObject("Scripting.FileSystemObject")',
    "base = fso.GetParentFolderName(WScript.ScriptFullName)",
    "sh.CurrentDirectory = base",
    f'pyw = "{PYW}"',
    'If Not fso.FileExists(pyw) Then pyw = fso.GetParentFolderName(pyw)'
    ' & "\\python.exe"',
    'If Not fso.FileExists(pyw) Then pyw = ""',
    'If pyw = "" Then',
    '  MsgBox "Python not found", 48, "ec-lab"',
    "Else",
    '  sh.Run """" & pyw & """ """ & base & "\\ec_board.py""", 0, False',
    "End If",
]
with open(os.path.join(BASE, "collaboration.vbs"), "wb") as f:
    f.write(b"\xff\xfe" + ("\r\n".join(board_vbs) + "\r\n")
            .encode("utf-16-le"))
print("collaboration.vbs   UTF-16LE（双击不弹黑窗口）")

