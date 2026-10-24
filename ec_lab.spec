# -*- mode: python ; coding: utf-8 -*-
"""
ec-lab PyInstaller 打包配置（适配 PyInstaller 6.x / Python 3.13 / PySide6 6.11）
用法：.venv\\Scripts\\python.exe tools\\build_portable.py --noconfirm（隔离 PATH 并核对依赖来源）
输出：dist/ec-lab/ec-lab.exe

2026-10 打包移植版改动（相对 2026-10-08 旧版）：
  1. 不再打包真实 config.json，改打包 config.example.json（模板）。
     真实配置含 Ding 的个人数据路径与 85 条样品质量登记，绝不能随包分发。
     首次运行由 cfg_guard.seed_config_from_example() 复制模板生成空白 config.json。
  2. 打包 examples/ 合成样例数据，让别人没真实数据也能先试跑（禁止用于论文）。
  3. 适配 PyInstaller 6.x：去掉已删除的 block_cipher / cipher 参数、
     已废弃的 win_no_prefer_redirects / win_private_assemblies，以及
     PYZ 里不再需要的 a.zipped_data。
  4. COLLECT 指定 contents_directory='.'，保持「exe 旁边就是全部文件」的平铺布局。
     PyInstaller 6.x 默认把依赖塞进 _internal/ 子目录，而 cfg_guard 只认
     exe 同级的 config.example.json —— 平铺布局才能让模板机制正常工作。
  5. 保留 PySide6 裁剪（_skip_ps / _skip_bin），约省 200MB。
  6. 「绘图模板/」是用户自己的绘图样式存档，属于用户数据，不打包。
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# --- 收集 matplotlib 数据文件（字体、样式等）---
datas = []
datas += collect_data_files('matplotlib')

# PySide6：只收集必要的，跳过 QML/Quick/WebEngine/3D/多媒体等大模块
_pyside_datas = collect_data_files('PySide6')
_skip_ps = ('qml', 'quick', 'webengine', 'Qt3D', 'multimedia',
            'charts', 'datavisual', 'translations', 'examples',
            'WebSockets', 'Bluetooth', 'Nfc', 'Positioning',
            'Location', 'Sensors', 'SerialPort', 'SerialBus',
            'RemoteObjects', 'Scxml', 'StateMachine', 'UiTools',
            'Designer', 'Help', 'Pdf', 'Test', 'Sql',
            'Concurrent', 'PrintSupport', 'OpenGL', 'SvgWidgets',
            'HttpServer', 'QtQuick', 'QtQml')
datas += [(src, dst) for src, dst in _pyside_datas
          if not any(k in src for k in _skip_ps)]

# 本地资源
BASE = os.path.abspath('.')
datas += [
    ('tools/RGB颜色取色器.html', 'tools'),   # ec_gui.py COLOR_PICKER_HTML 用到
    ('config.example.json', '.'),            # 模板：首启复制成空白 config.json
    ('ec-lab.ico', '.'),                     # 窗口图标
    ('palette_icon.png', '.'),               # 调色盘图标
]

# 合成样例数据：没有真实 CHI 数据的人可以先拿它试跑（假数据，禁止用于论文）
datas += [
    ('examples/sample_data', 'examples/sample_data'),
    ('examples/README.md', 'examples'),
    ('examples/conductivity_demo.csv', 'examples'),
    ('docs/data-and-plot-guide.md', 'docs'),
    ('docs/plotting-sources.md', 'docs'),
    ('templates/电容贡献率模板.xlsx', 'templates'),
    ('docs/original-excel-guide.md', 'docs'),
    ('docs/cdi-reference-audit-20261024.md', 'docs'),
    ('docs/ui-design-20261024.md', 'docs'),
    ('docs/科研绘图项目设计学习报告-20261024.md', 'docs'),
]

# --- 隐藏导入 ---
hiddenimports = [
    'scipy.special',
    'scipy.optimize',
    'scipy.interpolate',
    'scipy.integrate',
]
hiddenimports += collect_submodules('matplotlib.backends')

a = Analysis(
    ['ec_gui.py'],
    pathex=[BASE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',          # 用 PySide6，不需要
        'PyQt5', 'PyQt6',   # 避免冲突
        'IPython', 'jupyter',
        'pytest', 'docutils',
        # --- PySide6 不用的模块（省 ~200MB）---
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
        'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.Qt3DLogic',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtWebSockets', 'PySide6.QtBluetooth',
        'PySide6.QtNfc', 'PySide6.QtPositioning',
        'PySide6.QtLocation', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtSerialBus',
        'PySide6.QtRemoteObjects', 'PySide6.QtScxml',
        'PySide6.QtStateMachine', 'PySide6.QtUiTools',
        'PySide6.QtDesigner', 'PySide6.QtHelp',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtTest', 'PySide6.QtSql',
        'PySide6.QtConcurrent', 'PySide6.QtPrintSupport',
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
        'PySide6.QtSvgWidgets', 'PySide6.QtHttpServer',
        # --- matplotlib 不用的后端 ---
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_gtk3agg',
        'matplotlib.backends.backend_gtk4agg',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends.backend_wx',
        'matplotlib.backends.backend_qt5agg',
        # --- 其他不用的 ---
        'PIL.ImageQt',  # 不需要 PIL-Qt 桥接
    ],
    noarchive=False,
)

# --- 过滤掉不需要的 PySide6 二进制（DLL/EXE）---
_skip_bin = ('Qt6Qml', 'Qt6Quick', 'Qt6Quick3D', 'Qt6WebEngine',
             'Qt6WebEngineCore', 'Qt6WebChannel', 'Qt63D', 'Qt6Multimedia',
             'Qt6Charts', 'Qt6DataVisualization', 'Qt6WebSockets',
             'Qt6Bluetooth', 'Qt6Nfc', 'Qt6Positioning', 'Qt6Location',
             'Qt6Sensors', 'Qt6SerialPort', 'Qt6SerialBus',
             'Qt6RemoteObjects', 'Qt6Scxml', 'Qt6StateMachine',
             'Qt6UiTools', 'Qt6Designer', 'Qt6Help', 'Qt6Pdf',
             'Qt6Test', 'Qt6Sql', 'Qt6Concurrent', 'Qt6PrintSupport',
             'Qt6OpenGL', 'Qt6SvgWidgets', 'Qt6HttpServer',
             'opengl32sw', 'Qt6QuickControls2', 'Qt6QuickTemplates2',
             'Qt6QuickDialogs2', 'Qt6QuickLayouts', 'Qt6QuickEffects',
             'Qt6QmlWorkerScript', 'Qt6QuickParticles', 'Qt6QuickShapes',
             'Qt6Quick3DUtils', 'Qt6Quick3DAssetImport', 'Qt6Quick3DRuntimeRender')
a.binaries = [b for b in a.binaries if not any(k in b[0] for k in _skip_bin)]
# 只过滤 PySide6 的数据文件：_skip_ps 里有 'examples' 这类通用词，
# 若无条件过滤会把 examples/sample_data 合成样例也一起删掉。
a.datas = [d for d in a.datas
           if not ('PySide6' in d[0] and any(k in d[0] for k in _skip_ps))]

# PyInstaller 6.x：PYZ 只需要 a.pure（a.zipped_data 与 cipher 均已移除）
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ec-lab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ec-lab.ico',
    # PyInstaller 6.x：onedir 的布局开关在 EXE 上（COLLECT 会继承它）。
    # '.' = 旧式平铺布局，exe 与全部依赖同目录。必须这样：
    # cfg_guard.EXAMPLE_PATH 只认 exe 同级的 config.example.json，
    # 塞进 _internal/ 模板机制就失效了；图标、工具页、output/ 同理。
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ec-lab',
)
