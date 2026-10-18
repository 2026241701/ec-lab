# -*- mode: python ; coding: utf-8 -*-
"""
ec-lab PyInstaller 打包配置
用法: python -m PyInstaller ec_lab.spec
输出: dist/ec-lab/ec-lab.exe
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

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
    ('tools/RGB颜色取色器.html', 'tools'),
    ('config.json', '.'),
    ('ec-lab.ico', '.'),            # 窗口图标
    ('palette_icon.png', '.'),      # 调色盘图标
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
a.datas = [d for d in a.datas if not any(k in d[0] for k in _skip_ps)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
