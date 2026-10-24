# -*- coding: utf-8 -*-
"""
CHI电化学一键绘图 - 桌面版
==========================================
四步：① 添加文件夹 → ② 扫描并勾选文件 → ③ 开始处理（先算数）
      ④ 出图预览：调样式/看效果 → 确认输出

界面：菜单栏 + 工具栏 + 工作区，可切换经典/黑暗两套配色。
绘图样式按「每张图一套」分开：CV 叠加 / CV 比电容 / GCD 曲线 /
GCD 比电容 / EIS / 循环稳定性。

依赖：pip install -r requirements.txt（numpy pandas matplotlib scipy openpyxl PySide6）
运行：python ec_gui.py（Windows 上可先跑 python make_launchers.py 生成
      「启动软件.bat」，以后双击它启动、不弹黑窗口）
"""

import os
import sys
import json
import math
import queue
import threading
import time
import traceback
import tempfile

# Keep numerical libraries from occupying every CPU core on a remote desktop.
for _thread_var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_thread_var, "1")

import matplotlib
matplotlib.use("QtAgg")      # 预览图要嵌进 Qt 窗口，必须在导入 pyplot 前设置

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal, QStandardPaths
from PySide6.QtGui import (QFont, QFontMetrics, QColor, QPixmap, QIcon, QPainter, QImage,
                           QPen, QPolygon, QGuiApplication, QCursor)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QGroupBox, QVBoxLayout,
    QHBoxLayout, QListWidget, QPushButton, QTableWidget, QTableWidgetItem,
    QCheckBox, QDoubleSpinBox, QSpinBox, QLineEdit, QLabel, QTextEdit,
    QFileDialog, QMessageBox, QHeaderView, QAbstractItemView, QDialog,
    QFormLayout, QComboBox, QTabWidget, QDialogButtonBox, QSizePolicy,
    QPlainTextEdit, QGridLayout, QColorDialog, QToolBar, QSlider, QStatusBar,
    QScrollArea, QInputDialog, QFrame, QRadioButton, QButtonGroup,
    QToolButton,
)
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT)

# 打包成 exe 后 __file__ 指向临时解压目录：配置、日志、输出都放在 exe 同级目录
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    _MEI = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _MEI = BASE_DIR
# 统一错误日志路径：报错与查看报错都指向这里（附在软件目录，自动生成）
ERROR_LOG = os.path.join(BASE_DIR, "错误日志.txt")
sys.path.insert(0, BASE_DIR)
import eclab   # noqa: E402  处理引擎（命令行与界面共用同一套代码）
import ec_palette as ecpal   # noqa: E402  配色存储：存配色、记用色
import cfg_guard  # noqa: E402  配置保险箱（自动备份 + 损坏自愈）
from ec_workflow import calculation_signature, validate_output

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MARKER_NAMES = eclab.MARKER_NAMES
# 调色盘网页：优先用 exe 同级的（用户可自行替换），否则用打包进内部的
COLOR_PICKER_HTML = os.path.join(BASE_DIR, "tools", "RGB颜色取色器.html")
if not os.path.exists(COLOR_PICKER_HTML):
    COLOR_PICKER_HTML = os.path.join(_MEI, "tools", "RGB颜色取色器.html")

# ------------------------------------------------------------------
# 主题配色：经典（浅）/ 黑暗（深）
# ------------------------------------------------------------------
THEMES = {
    "classic": {
        "bg": "#f5f6f7", "panel": "#ffffff", "fg": "#1f2328",
        "muted": "#5b6570", "line": "#c3c9ce", "accent": "#1f6feb",
        "accent_fg": "#ffffff", "sel": "#d8e6ff", "log_bg": "#11161c",
        "log_fg": "#d6e0e8", "group": "#eef1f4",
    },
    "dark": {
        "bg": "#1b1f24", "panel": "#23282e", "fg": "#e6e9ec",
        "muted": "#9aa4ae", "line": "#3d444c", "accent": "#4c8dff",
        "accent_fg": "#0f1216", "sel": "#31435e", "log_bg": "#0d1117",
        "log_fg": "#c9d1d9", "group": "#2a3037",
    },
}

THEME_QSS = """
QWidget {{ background: {bg}; color: {fg}; }}
QMainWindow, QDialog, QMenu {{ background: {panel}; color: {fg}; }}
QMenuBar {{ background: {panel}; color: {fg}; border-bottom:1px solid {line}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {sel}; }}
QMenu::item {{ padding: 6px 22px; }}
QToolBar {{ background: {panel}; border:0; border-bottom:1px solid {line};
            padding:4px; spacing:6px; }}
QPushButton, QToolButton {{
    background: {panel}; border: 1px solid {line}; border-radius: 4px;
    padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: {sel}; }}
QPushButton:pressed {{ background: {group}; }}
QPushButton:disabled {{ color: {muted}; background: {group}; }}
QPushButton#primary {{ background: {accent}; color: {accent_fg};
                       border: 1px solid {accent}; font-weight: bold; }}
/* 颜色按钮有自己的颜色，不被主题覆盖 */
QPushButton[colorBtn="true"] {{
    padding: 6px 12px; border-radius: 4px; }}
QGroupBox {{ border: 1px solid {line}; border-radius: 5px; margin-top: 12px;
             font-weight: bold; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
QTableWidget, QListWidget {{
    background: {panel}; border: 1px solid {line}; gridline-color: {line};
    selection-background-color: {accent}; selection-color: {accent_fg}; }}
QTableWidget::item {{ padding: 4px 6px; }}
QTableWidget::item:selected {{ background: {accent}; color: {accent_fg};
    border-top: 1px solid {accent_fg}; border-bottom: 1px solid {accent_fg}; }}
QTableWidget::item:hover:!selected {{ background: {sel}; }}
QHeaderView {{ background: {group}; }}
QHeaderView::section {{ background: {group}; border: 0;
                        border-right:1px solid {line}; padding: 5px;
                        font-weight: bold; }}
/* 复选框加大加描边，勾选后填充主色——表格里的“处理”列一眼能看清 */
QCheckBox, QGroupBox {{ spacing: 7px; }}
QGroupBox::indicator {{
    width: 15px; height: 15px;
    border: 2px solid {fg}; border-radius: 4px;
    background: {panel}; }}
QGroupBox::indicator:hover {{ border-color: {accent}; }}
QGroupBox::indicator:checked {{
    border: 2px solid {accent}; border-radius: 4px;
    background: {accent}; image: url({chk}); }}
QCheckBox::indicator, QTableView::indicator {{
    width: 16px; height: 16px;
    border: 2px solid {fg}; border-radius: 4px;
    background: {panel}; }}
QCheckBox::indicator:hover, QTableView::indicator:hover {{
    border-color: {accent}; background: {sel}; }}
QCheckBox::indicator:unchecked:hover, QTableView::indicator:unchecked:hover {{
    border-color: {accent}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked {{
    border: 2px solid {accent}; border-radius: 4px;
    background: {accent};
    image: url({chk}); }}
QCheckBox:disabled::indicator {{ border-color: {line}; background: {group}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {panel}; border: 1px solid {line}; border-radius: 4px;
    padding: 3px 5px; selection-background-color: {sel}; }}
QTabWidget::pane {{ border: 1px solid {line}; }}
QTabBar::tab {{ background: {group}; border: 1px solid {line};
                padding: 6px 12px; }}
QTabBar::tab:selected {{ background: {accent}; color: {accent_fg}; }}
QStatusBar {{ background: {panel}; border-top:1px solid {line}; }}
QSlider::groove:horizontal {{ height: 6px; background: {group};
                               border:1px solid {line}; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0;
                              background:{accent}; }}
QSlider::sub-page:horizontal {{ background: {accent}; }}
QLabel#hint {{ color: {muted}; }}
QTextEdit#log {{ background: {log_bg}; color: {log_fg};
                 border: 1px solid {line}; }}
/* 所有按钮统一用手型光标。QSS 一旦给了 background，
   Qt 有时就不再套用按钮的默认光标，鼠标移上去会变"插入文字"，
   看着像按钮其实点不动，这里统一钉死。 */
QPushButton, QToolButton, QCheckBox, QRadioButton {{
    cursor: pointinghand; }}
/* SpinBox 微调按钮：给独立的区域和光标，避免事件穿透到文本框 */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {group}; border: 1px solid {line};
    width: 18px; border-radius: 2px;
    cursor: pointinghand; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {sel}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 8px; height: 8px; image: url({arrow_up}); }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 8px; height: 8px; image: url({arrow_down}); }}
"""

FONT_WEST = ["Arial", "Times New Roman", "Helvetica", "Calibri",
             "Georgia", "DejaVu Serif", "Tahoma", "Verdana"]
FONT_CJK = ["SimSun", "SimHei", "Microsoft YaHei", "KaiTi", "FangSong",
            "DengXian", "STZhongsong"]
UNIT_NAMES = [("毫米", "mm"), ("厘米", "cm"), ("英寸", "inch"), ("像素", "px")]
SIZE_PRESETS = [8, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28]
LW_PRESETS = [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0]
DPI_PRESETS = [72, 96, 150, 300, 400, 600, 900, 1200]
CANVAS_PRESETS = {
    "mm": [80, 100, 120, 150, 160, 170, 180, 200, 250, 300],
    "cm": [8, 10, 12, 15, 16, 17, 18, 20, 25, 30],
    "inch": [3, 3.5, 4, 5, 6, 7, 8, 10, 12],
    "px": [400, 600, 800, 1000, 1200, 1600, 2000],
}
MARGIN_PRESETS = [0, 2, 4, 6, 8, 10, 12, 15, 18, 20, 22, 25, 30]
# 换画布单位时用：数值 × 该系数 = 毫米
CANVAS_SCALE = {"mm": 1.0, "cm": 10.0, "inch": 25.4, "px": 25.4 / 600}
# 每张图一套独立样式
KINDS = [("CV 叠加图", "cv_overlay"),
         ("CV 比电容图", "cv_cap"),
         ("GCD 充放电曲线", "gcd_overlay"),
         ("GCD 比电容图", "gcd_cap"),
         ("EIS 图（Nyquist）", "EIS"),
         ("循环稳定性图", "cycle")]
KIND_CODES = [c for _, c in KINDS]
LEGEND_LOCS = [
    ("最佳位置", "best"), ("右上", "upper right"), ("左上", "upper left"),
    ("左下", "lower left"), ("右下", "lower right"), ("中左", "center left"),
    ("中右", "center right"), ("下中", "lower center"),
    ("上中", "upper center"), ("正中", "center"),
]
PALETTES = {
    "经典（默认）": None,
    "Origin 风": ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD",
                  "#8C564B", "#E377C2"],
    "材料渐变（蓝→橙红）": ["#2166AC", "#4393C3", "#92C5DE", "#FDDBC7",
                            "#F4A582", "#D6604D", "#B2182B"],
    "冷暖对比": ["#38699E", "#A63E76", "#1F6E5A", "#D2603A", "#7A5AA8",
                 "#4E9BC8", "#8C8C8C"],
    "黑白灰（投稿）": ["#000000", "#555555", "#999999", "#CCCCCC", "#333333",
                       "#777777", "#BBBBBB"],
}
COLOR_CHOICES = [
    "#000000", "#404040", "#808080", "#BFBFBF", "#FFFFFF", "#1F6E5A",
    "#2E8B57", "#38699E", "#4C8DFF", "#7A5AA8", "#A63E76", "#D2603A",
    "#F4A582", "#FFD700", "#8C8C8C", "#1a9e8f",
]

# ------------------------------------------------------------------
# 标准色库：按用途分组，闭着眼也能点到想要的颜色
# ------------------------------------------------------------------
STANDARD_COLORS = [
    ("黑白灰（正文/投稿）", [
        "#000000", "#1A1A1A", "#333333", "#4D4D4D", "#666666",
        "#808080", "#999999", "#B3B3B3", "#CCCCCC", "#E6E6E6", "#F2F2F2",
        "#FFFFFF"]),
    ("红（强调/危险）", [
        "#FF0000", "#E02020", "#C00000", "#990000", "#FF6B6B",
        "#FF9999", "#7F0000", "#A52A2A", "#D2691E", "#B22222"]),
    ("橙黄（暖/警示）", [
        "#FF8C00", "#FFA500", "#FFB347", "#FFC800", "#FFD700",
        "#E8A33D", "#C77B22", "#8B5A00", "#FF9500", "#F4B400"]),
    ("绿（通过/安全）", [
        "#008000", "#00A000", "#1F6E5A", "#2E8B57", "#00B050",
        "#4CAF50", "#8BC34A", "#CDDC39", "#0F9D58", "#1DB954",
        "#00C853", "#76FF03"]),
    ("青蓝（冷/科技）", [
        "#008080", "#0097A7", "#00ACC1", "#00B8D4", "#1E90FF",
        "#2196F3", "#38699E", "#4C8DFF", "#0066CC", "#003366",
        "#4169E1", "#4682B4"]),
    ("蓝紫（沉稳）", [
        "#000080", "#0000CD", "#191970", "#483D8B", "#6A5ACD",
        "#7A5AA8", "#8B008B", "#800080", "#4B0082", "#9370DB",
        "#663399", "#301934"]),
    ("粉（柔和/标注）", [
        "#FFC0CB", "#FFB6C1", "#FF69B4", "#FF1493", "#DB7093",
        "#C71585", "#FFD700", "#FFE4E1", "#F8BBD0", "#E75480"]),
    ("棕/土（材料）", [
        "#8B4513", "#A0522D", "#CD853F", "#D2691E", "#BC8F8F",
        "#DEB887", "#F5DEB3", "#8B7355", "#6B4423", "#3E2723"]),
    ("莫兰迪（低饱和高级灰）", [
        "#A8B5A2", "#C4A69D", "#98A8B8", "#B8A9C9", "#D4C4B5",
        "#9DB4C0", "#C2B2B4", "#A5A58D", "#B7B7A4", "#CB997E"]),
    ("马卡龙（浅色系）", [
        "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
        "#E3BAFF", "#FFC6E0", "#C6FFDD", "#FFF5BA", "#D4F0F0"]),
    ("宝石色（高饱和）", [
        "#E0115F", "#0F52BA", "#50C878", "#9966CC", "#FFBF00",
        "#00BFFF", "#FF2400", "#7CFC00", "#FF69B4", "#40E0D0"]),
    ("大地色（自然沉稳）", [
        "#704214", "#96694C", "#C19A6B", "#E6CCB2", "#5F6B54",
        "#8A9A5B", "#A67B5B", "#6F4E37", "#826644", "#EDC9AF"]),
    ("荧光色（标注醒目）", [
        "#39FF14", "#FF073A", "#FF6EC7", "#CCFF00", "#FF9933",
        "#08E8DE", "#FE59C2", "#BFFF00", "#FF5F1F", "#00FFFF"]),
    ("海军蓝系（商务稳重）", [
        "#001F3F", "#003366", "#004080", "#0059B3", "#0074D9",
        "#1E4E79", "#2E5E8C", "#3D6E9E", "#003153", "#0A2351"]),
    ("玫瑰红系（女性化）", [
        "#B03060", "#C21E56", "#DE3163", "#E52B50", "#F88379",
        "#FC6C85", "#FF7F8F", "#FFA6B5", "#D70040", "#E0115F"]),
    ("森林绿系（环保自然）", [
        "#0B3D0B", "#145214", "#1E6B1E", "#2F8F2F", "#4FA64F",
        "#228B22", "#32CD32", "#6B8E23", "#556B2F", "#9ACD32"]),
    ("日落橙系（温暖活力）", [
        "#CC3300", "#E64A19", "#FF5722", "#FF7043", "#FF8A65",
        "#F4511E", "#D84315", "#BF360C", "#FF6F00", "#FFA000"]),
    ("紫罗兰系（神秘优雅）", [
        "#4B0082", "#5D3FD3", "#7B68EE", "#9370DB", "#B57EDC",
        "#8A2BE2", "#9932CC", "#BA55D3", "#DA70D6", "#EE82EE"]),
]
# 常用论文配色，一键可选
STANDARD_SCHEMES = [
    ("Nature 系", ["#0A6E8A", "#C1440E", "#F2A900", "#3B7A57", "#8C5E58"]),
    ("Science 系", ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9"]),
    ("灰度投稿", ["#000000", "#404040", "#737373", "#A6A6A6", "#D9D9D9"]),
    ("冷暖对比", ["#38699E", "#A63E76", "#1F6E5A", "#D2603A", "#7A5AA8"]),
    ("蓝橙互补", ["#2166AC", "#67A9CF", "#D1E5F0", "#FDDBC7", "#B2182B"]),
    ("材料渐变", ["#2166AC", "#4393C3", "#92C5DE", "#FDDBC7", "#D6604D",
                  "#B2182B"]),
]


def combo_edit(presets, default=None):
    """可编辑下拉框：预设常用值，也允许自己输入"""
    c = QComboBox()
    c.setEditable(True)
    for p in presets:
        c.addItem(str(p))
    if default is not None:
        c.setCurrentText(str(default))
    return c


def _lim_str(v):
    """坐标轴范围存成字符串：空 = 自动。显示时别拖一串 0 尾巴出来"""
    return _num_str(v)


def _num_str(v):
    """数字转字符串，整数就不带小数点尾巴（22.0 -> 22，读着清楚）"""
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return f"{f:g}"


def num_val(c, cast=float, default=0.0):
    try:
        return cast(str(c.currentText()).strip())
    except ValueError:
        return default


def color_icon(hexcolor, size=14):
    pix = QPixmap(size, size)
    col = QColor(hexcolor)
    pix.fill(col if col.isValid() else QColor("#FFFFFF"))
    return QIcon(pix)


def make_check_icon(fg, size=16):
    """画一个对勾图标存成临时 png，供 QSS 的 ::indicator:checked 用"""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(fg))
    pen.setWidth(2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size / 16.0
    p.drawLine(QPointF(3.5 * s, 8.4 * s), QPointF(6.7 * s, 11.6 * s))
    p.drawLine(QPointF(6.7 * s, 11.6 * s), QPointF(12.6 * s, 4.6 * s))
    p.end()
    path_out = os.path.join(tempfile.gettempdir(),
                            f"ec_check_{fg.lstrip('#')}_{size}.png")
    px.save(path_out, "PNG")
    return path_out.replace("\\", "/")


def _make_arrow_pngs():
    """动态生成 SpinBox 上下箭头的小三角图片（QSS 的 image: url 需要）。

    CSS border 画三角在 QSS 的 arrow 子控件里渲染不可靠（会出黑块），
    必须用真实图片。生成到临时目录，主题深浅各一套。
    返回 (up_path, down_path)。
    """
    import tempfile
    from PySide6.QtGui import QPainter, QPolygonF
    from PySide6.QtCore import QPointF

    d = os.path.join(tempfile.gettempdir(), "_ec_lab_arrows")
    os.makedirs(d, exist_ok=True)
    paths = []
    for name, dark in (("up", True), ("down", True)):
        p = os.path.join(d, f"arrow_{name}.png")
        pm = QPixmap(16, 16)
        pm.fill(Qt.transparent)
        pa = QPainter(pm)
        pa.setRenderHint(QPainter.Antialiasing)
        col = QColor("#333333")
        pa.setBrush(col)
        pa.setPen(Qt.NoPen)
        tri = QPolygonF()
        if name == "up":
            tri << QPointF(3, 11) << QPointF(13, 11) << QPointF(8, 4)
        else:
            tri << QPointF(3, 5) << QPointF(13, 5) << QPointF(8, 12)
        pa.drawPolygon(tri)
        pa.end()
        pm.save(p, "PNG")
        paths.append(p)
    return paths[0], paths[1]


_ARROW_PATHS = None


def apply_theme(app, name="classic"):
    global _ARROW_PATHS
    t = THEMES.get(name, THEMES["classic"])
    t = dict(t)
    t["chk"] = make_check_icon(t["accent_fg"])
    if _ARROW_PATHS is None:
        _ARROW_PATHS = _make_arrow_pngs()
    # QSS 的 url() 里反斜杠会被当成转义符，必须换成正斜杠
    t["arrow_up"] = _ARROW_PATHS[0].replace("\\", "/")
    t["arrow_down"] = _ARROW_PATHS[1].replace("\\", "/")
    # 切换主题时先暂停重绘，一次性套完再刷新，避免肉眼可见的闪烁卡顿
    for w in app.allWidgets():
        w.setUpdatesEnabled(False)
    app.setStyleSheet(THEME_QSS.format(**t))
    for w in app.allWidgets():
        w.setUpdatesEnabled(True)
    app.processEvents()
    return t


def app_icon():
    """应用图标：开发时用源码旁的 ec-lab.ico，打包后从 _MEIPASS 找"""
    for base in (BASE_DIR, getattr(sys, "_MEIPASS", BASE_DIR)):
        p = os.path.join(base, "ec-lab.ico")
        if os.path.isfile(p):
            return QIcon(p)
    return QIcon()


class QueueWriter:
    """把 print 输出导进线程安全队列，供日志区实时显示"""

    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


# ==================================================================
# 屏幕吸管 + 软件内置调色盘
# ==================================================================
class 屏幕视图(QWidget):
    """截屏显示 + 跟随鼠标的十字线：一眼看出鼠标落在哪个像素

    原来只有右下角一个放大镜，主图上完全看不出鼠标在哪（还把光标藏了），
    这里改成主图上直接画贯穿的十字线 + 高亮小方框，光标也换成十字。
    """

    picked_at = Signal(int, int)      # 原图像素坐标

    def __init__(self, pm, parent=None):
        super().__init__(parent)
        self.pm = pm
        self._scale = 1.0
        self.cur = None               # (x, y) 原图像素
        self.on_move = None           # 外部用它刷新放大镜
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setMouseTracking(True)

    def _pos(self, ev):
        s = self._scale or 1.0
        return (int(ev.position().x() / s), int(ev.position().y() / s))

    def mouseMoveEvent(self, ev):
        self.cur = self._pos(ev)
        self.update()
        if self.on_move:
            self.on_move(self.cur[0], self.cur[1])

    def mousePressEvent(self, ev):
        x, y = self._pos(ev)
        self.picked_at.emit(x, y)

    def leaveEvent(self, ev):
        self.cur = None
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pm.scaled(self.size(), Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        if self.cur:
            s = self._scale or 1.0
            x, y = self.cur[0] * s, self.cur[1] * s
            # 贯穿整张图的十字线：鼠标在哪一眼就看到
            p.setPen(QPen(QColor("#FF3B30"), 1))
            p.drawLine(0, int(y), self.width(), int(y))
            p.drawLine(int(x), 0, int(x), self.height())
            # 高亮小方框：黑白两道，任何底色上都看得清
            r = max(int(7 * s), 7)
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.drawRect(int(x - r), int(y - r), r * 2, r * 2)
            p.setPen(QPen(QColor("#000000"), 1))
            p.drawRect(int(x - r), int(y - r), r * 2, r * 2)
        p.end()


class ScreenPickDialog(QDialog):
    """抓取屏幕取色：主图上画十字线标出鼠标位置，右下角放大镜看细节"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("吸管：移动看十字位置，点击取色")
        self.resize(1100, 760)
        self.color = None
        screen = QGuiApplication.primaryScreen()
        self.pm = screen.grabWindow(0) if screen else QPixmap()
        if self.pm.isNull():
            QMessageBox.warning(self, "吸管",
                                "没能截取到屏幕画面，无法取色。")
            self.color = None
        lay = QVBoxLayout(self)
        scale = min((self.width() - 20) / max(self.pm.width(), 1),
                    (self.height() - 150) / max(self.pm.height(), 1))
        disp_w = int(self.pm.width() * scale)
        disp_h = int(self.pm.height() * scale)
        self.view = 屏幕视图(self.pm, self)
        self.view._scale = scale
        self.view.setFixedSize(disp_w, disp_h)
        self.view.on_move = self._on_move
        self.view.picked_at.connect(self._pick)
        lay.addWidget(self.view, alignment=Qt.AlignCenter)

        # 底部：放大镜 + 当前像素信息
        bot = QHBoxLayout()
        self.mag = QLabel("移动鼠标查看放大区域")
        self.mag.setFixedSize(150, 150)
        self.mag.setStyleSheet("background:#222; border:1px solid #888;")
        self.mag.setAlignment(Qt.AlignCenter)
        bot.addWidget(self.mag)
        info = QVBoxLayout()
        self.lab_px = QLabel("像素：—")
        self.lab_px.setStyleSheet("font-family:Consolas; font-size:14px;")
        self.lab_cur = QLabel()
        self.lab_cur.setFixedSize(60, 60)
        self.lab_cur.setStyleSheet("border:1px solid #888;")
        info.addWidget(self.lab_px)
        info.addWidget(self.lab_cur)
        bot.addLayout(info)
        bot.addStretch(1)
        tip = QLabel("主图上的十字线就是鼠标位置，对准目标点击取色；Esc 取消")
        tip.setObjectName("hint")
        bot.addWidget(tip)
        lay.addLayout(bot)

    def _on_move(self, x, y):
        """鼠标在主图上移动：刷新右下角放大镜 + 当前像素信息"""
        if self.pm.isNull():
            return
        img = self.pm.toImage()
        if not (0 <= x < img.width() and 0 <= y < img.height()):
            return
        # 放大 15x15 像素到 150x150，中心画十字
        half, mag_size = 7, 150
        box = img.copy(max(x - half, 0), max(y - half, 0),
                       half * 2 + 1, half * 2 + 1)
        big = box.scaled(mag_size, mag_size,
                         Qt.IgnoreAspectRatio, Qt.FastTransformation)
        pm2 = QPixmap.fromImage(big)
        p = QPainter(pm2)
        pen = QPen(QColor("#FF3333"))
        pen.setWidth(2)
        p.setPen(pen)
        cell = mag_size / (half * 2 + 1)
        cx = mag_size / 2
        p.drawLine(int(cx), int(cx - cell / 2 - 2),
                   int(cx), int(cx + cell / 2 + 2))
        p.drawLine(int(cx - cell / 2 - 2), int(cx),
                   int(cx + cell / 2 + 2), int(cx))
        p.end()
        self.mag.setPixmap(pm2)
        col = QColor(img.pixel(x, y))
        self.lab_px.setText(
            f"像素 ({x}, {y})\n{col.name().upper()}\n"
            f"RGB {col.red()}, {col.green()}, {col.blue()}")
        self.lab_cur.setStyleSheet(
            f"background:{col.name()}; border:1px solid #888;")

    def _pick(self, x, y):
        if self.pm.isNull():
            self.reject()
            return
        img = self.pm.toImage()
        if 0 <= x < img.width() and 0 <= y < img.height():
            self.color = QColor(img.pixel(x, y)).name().upper()
        self.accept()



class 色调带(QWidget):
    """真实的彩虹色相条，点哪跳到哪 —— 比数字滑块直观得多"""

    huePicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self._hue = 0
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_hue(self, h):
        self._hue = int(h) % 360
        self.update()

    def hue(self):
        return self._hue

    def hueAt(self, x):
        return max(0, min(359, int(x / max(self.width(), 1) * 359)))

    def mousePressEvent(self, ev):
        h = self.hueAt(ev.position().x())
        self.set_hue(h)
        self.huePicked.emit(h)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            h = self.hueAt(ev.position().x())
            self.set_hue(h)
            self.huePicked.emit(h)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        n = 360
        for i in range(n):
            x0 = int(i * w / n)
            x1 = int((i + 1) * w / n)
            p.fillRect(x0, 0, max(x1 - x0, 1), self.height(),
                       QColor.fromHsv(i, 255, 255))
        # 当前色相位置画个黑框，一眼看到自己在哪
        x = int(self._hue / 360 * w)
        p.setPen(QPen(QColor("#101010"), 2))
        p.drawRect(x - 4, 1, 8, self.height() - 2)
        p.setPen(QPen(QColor("#FFFFFF"), 1))
        p.drawRect(x - 3, 2, 6, self.height() - 4)
        p.end()


class 明度参照条(QWidget):
    """当前颜色的明暗层次条：一眼看出这个色加深/变浅会是什么样"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base = "#1F6E5A"
        self.setFixedHeight(30)
        self.setToolTip("从最暗到最亮，方便对比同一色系的不同深浅")

    def set_base(self, hexcolor):
        self.base = hexcolor or "#1F6E5A"
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = 11
        gap = 2
        w = (self.width() - gap * (n - 1)) / n
        col = QColor(self.base)
        if not col.isValid():
            col = QColor("#888888")
        for i in range(n):
            f = 0.35 + i * 0.065          # 0.35~1.0 的明度系数
            c = QColor(col)
            c.setHsvF(max(col.hsvHueF(), 0.0001), col.hsvSaturationF(), f)
            x = int(i * (w + gap))
            p.fillRect(x, 0, int(w), self.height(), c)
            p.setPen(QPen(QColor("#909090"), 1))
            p.drawRect(x, 0, int(w) - 1, self.height() - 1)
        p.end()


class 色块按钮(QPushButton):
    """一个颜色小方块，点击就调出调色盘

    取代原来那些"下拉框里挑颜色"的控件 —— 下拉框一打开一屏灰，
    还要手打 HEX。现在直接看到色块，点一下弹调色盘。
    留空（跟线条颜色）也能选。
    """

    def __init__(self, parent=None, color="", allow_empty=False,
                 empty_text="跟随线条"):
        super().__init__(parent)
        self.setProperty("colorBtn", True)   # 标记：主题 QSS 不覆盖
        self.allow_empty = allow_empty
        self.empty_text = empty_text
        self._color = ""
        self.set_color(color)
        self.setFixedHeight(24)
        self.setMinimumWidth(78)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.clicked.connect(self._open)

    def color(self):
        return self._color

    def set_color(self, c):
        """设置颜色；空字符串表示"跟随线条"这类留空状态"""
        c = (c or "").strip()
        self._color = c.upper() if (c.startswith("#")
                                    and len(c) in (4, 7)) else ""
        self._repaint()

    def _repaint(self):
        c = self._color
        if not c:
            # 留空态：斜纹底 + 提示文字，别让人以为是白色
            self.setText(self.empty_text if self.allow_empty else "选颜色")
            self.setStyleSheet(
                "QPushButton{background:#f2f2f2; border:1px solid #b8b8b8;"
                "border-radius:4px; color:#8a8a8a; padding:4px 10px;}")
            self.setToolTip("当前：跟随线条颜色")
            return
        self.setText(c)
        # 深色底用白字，浅色底用黑字，保证读得清
        col = QColor(c)
        fg = "#FFFFFF" if col.lightness() < 128 else "#1A1A1A"
        self.setStyleSheet(
            f"QPushButton{{background:{c}; border:1px solid #808080;"
            f"border-radius:4px; color:{fg}; padding:4px 10px;}}"
            f"QPushButton:hover{{border:2px solid #4C8DFF;}}")
        rgb = f"RGB({col.red()}, {col.green()}, {col.blue()})"
        self.setToolTip(f"{c}\n{rgb}\n点击可重新调色")

    def _open(self):
        # 仅选色模式：色块按钮是从别处再调出来的子调色盘，
        # 不给"改颜色组 / 改方案"的入口，避免无限嵌套（Bug 4）
        dlg = ColorPickerDialog(self, self._color, select_only=True)
        dlg.allow_empty = self.allow_empty
        dlg.empty_text = self.empty_text
        dlg.btn_empty.setVisible(self.allow_empty)
        dlg.btn_empty.setText(self.empty_text)
        dlg.btn_empty.setChecked(not self._color)
        dlg.is_empty = not self._color
        if self._color:
            dlg._last_picked = self._color
        else:
            dlg._toggle_empty(True)
        if dlg.exec():
            # 用户点"确定"才写回；点取消保持原样
            self.set_color(dlg.result_color())
            self._after(self._color)

    def _after(self, c):
        """子类可覆盖：颜色变了要做什么（比如刷新预览）"""
        pass


class 颜色格子(QWidget):
    """一排/一列颜色格，点哪个就选哪个（带悬停描边和选中加粗）"""

    def __init__(self, parent=None, colors=(), cols=12, size=26,
                 on_pick=None, tip_for=None):
        super().__init__(parent)
        self.on_pick = on_pick
        self.tip_for = tip_for
        self._btns = []
        self.set_colors(colors, cols, size)

    def set_colors(self, colors, cols=None, size=None):
        cols = cols or getattr(self, "_cols", 12)
        size = size or getattr(self, "_size", 26)
        self._cols, self._size = cols, size
        for b in self._btns:
            b.setParent(None)
            b.deleteLater()
        self._btns = []
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        for i, c in enumerate(colors):
            b = QPushButton()
            b.setFixedSize(size, size)
            b.setCursor(QCursor(Qt.PointingHandCursor))
            b.setProperty("colorBtn", True)   # 主题不覆盖
            col = QColor(c)
            fg = "#FFFFFF" if col.lightness() < 128 else "#1A1A1A"
            b.setStyleSheet(
                f"QPushButton{{background:{c}; border:1px solid #7a7a7a;"
                f"padding:0px;}}"
                f"QPushButton:hover{{border:3px solid #1A1A1A;}}")
            tip = self.tip_for(c) if self.tip_for else c
            b.setToolTip(tip)
            # on_pick 可能在构造之后才被赋值，所以这里要在点击时再读取
            b.clicked.connect(
                lambda _=False, cc=c: self.on_pick(cc) if self.on_pick
                else None)
            lay.addWidget(b, i // cols, i % cols)
            self._btns.append(b)
        self._lay = lay
        lay.setRowStretch(lay.rowCount(), 1)


class ColorPickerDialog(QDialog):
    """调色盘：标准色 / RGB / 滑块 三种方式，外加用色记忆和配色方案

    这是全软件共用的选色控件，以后别处要用直接 pick_color() 即可。
    """

    # 功能按钮（确定/取消/吸管/存配色等）锁定固定样式，
    # 不随当前选中的颜色变化；色板按钮用自己的 inline 样式不受影响
    _FIXED_BTN_QSS = """
        QPushButton[colorBtn!="true"] {
            background: #F5F6F7; color: #1A1A1A;
            border: 1px solid #C9CDD2; border-radius: 4px;
            padding: 5px 12px;
        }
        QPushButton[colorBtn!="true"]:hover { background: #E3E9F2; }
        QPushButton[colorBtn!="true"]:checked {
            background: #D7E3F4; border: 1px solid #4C8DFF;
        }
    """

    def __init__(self, parent=None, color="#1F6E5A", select_only=False):
        super().__init__(parent)
        self._select_only = select_only
        self.setWindowTitle("调色盘（仅选色）" if select_only else "调色盘")
        # 调色盘专属图标：彩虹扇环，跟主程序图标区分开
        for base in (BASE_DIR, getattr(sys, "_MEIPASS", BASE_DIR)):
            _pi = os.path.join(base, "palette_icon.png")
            if os.path.isfile(_pi):
                self.setWindowIcon(QIcon(_pi))
                break
        self.resize(700, 620)
        q = QColor(color)
        self.picked = (q.name().upper()
                       if q.isValid() and color else "#1F6E5A")
        self.picked = color.upper() if (color and color.startswith("#")
                                       and len(color) in (4, 7)) else \
            QColor(self.picked).name().upper()
        self._loading = False
        self._group_colors = []      # 最近一次整套套用的配色（存方案时用）
        # 允许选"空 = 跟随线条"（数据点的填充色/边线色/垂直线色都要）
        self.allow_empty = False
        self.empty_text = "跟随线条"
        self.is_empty = False        # 当前是不是"空"这个状态
        self._build()
        self.setStyleSheet(self._FIXED_BTN_QSS)
        self._set(self.picked, sync=True)

    # ---------------- 界面 ----------------
    def _build(self):
        lay = QVBoxLayout(self)

        # 顶部：当前颜色 + HEX + 确认取消，一眼看到选了什么
        top = QHBoxLayout()
        self.lab_cur = QLabel()
        self.lab_cur.setFixedSize(96, 46)
        self.lab_cur.setFrameShape(QLabel.Box)
        top.addWidget(self.lab_cur)
        top.addWidget(QLabel("HEX"))
        self.ed_hex = QLineEdit(self.picked)
        self.ed_hex.setMaximumWidth(120)
        self.ed_hex.editingFinished.connect(self._on_hex)
        self.ed_hex.textChanged.connect(self._on_hex_live)
        top.addWidget(self.ed_hex)
        self.lab_rgb = QLabel("")
        self.lab_rgb.setObjectName("hint")
        top.addWidget(self.lab_rgb)
        # 选"空 = 跟随线条"。以前这个状态没法点回去，只能关掉重开
        self.btn_empty = QPushButton(self.empty_text)
        self.btn_empty.setCheckable(True)
        self.btn_empty.setToolTip(
            "不单独指定颜色，跟随曲线本身的颜色")
        self.btn_empty.clicked.connect(self._toggle_empty)
        self.btn_empty.setVisible(True)      # 默认显示，随时可切"空色"
        top.addWidget(self.btn_empty)
        top.addStretch(1)
        b_pipe = QPushButton("屏幕吸管")
        b_pipe.setToolTip("抓取屏幕上任何一个颜色")
        b_pipe.clicked.connect(self._pipette)
        top.addWidget(b_pipe)
        b_save = QPushButton("存为我的配色")
        b_save.setToolTip("把这套颜色存进我的配色（固定目录，"
                          "不用选保存位置）")
        b_save.clicked.connect(self._save_scheme)
        top.addWidget(b_save)
        lay.addLayout(top)

        # 三种选色方式
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_standard(), "标准色")
        self.tabs.addTab(self._tab_rgb(), "RGB")
        self.tabs.addTab(self._tab_slider(), "滑块")
        self._schemes_tab = self._tab_schemes()
        self.tabs.addTab(self._schemes_tab, "配色方案")
        lay.addWidget(self.tabs, stretch=1)

        # ---- Bug 4：当调色盘是从别处"再调出来"的子调色盘时，只给选色 ----
        # 藏掉一切"改颜色组 / 改方案"的入口，避免
        # 「调色盘 → 修改颜色组 → 点色块 → 又调出调色盘 → 又修改…」无限嵌套。
        if self._select_only:
            self.tabs.setTabVisible(self.tabs.indexOf(self._schemes_tab),
                                    False)
            # 标准色页里的"我的颜色组"编辑也藏掉（那也是改颜色组）
            if getattr(self, "gb_my_group", None) is not None:
                self.gb_my_group.setVisible(False)

        # 我用过的颜色：常驻在调色盘底部，不管在哪个页签都能看到、直接点
        gb_rec = QGroupBox("我用过（最近用的颜色，点一下直接用）")
        rv = QVBoxLayout(gb_rec)
        rv.setContentsMargins(6, 4, 6, 6)
        self.box_rec = QVBoxLayout()
        rv.addLayout(self.box_rec)
        # 之前 setMaximumHeight(120) 会被页签区挤到看不到，改成给足最小高度
        gb_rec.setMinimumHeight(64)
        gb_rec.setMaximumHeight(170)
        lay.addWidget(gb_rec)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _scroll(self, inner):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa

    def _tab_standard(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("按名字分组挑，不用想 RGB 是多少："))
        for name, cols in STANDARD_COLORS:
            gb = QGroupBox(f"{name}（{len(cols)} 色）")
            g = QGridLayout(gb)
            g.setContentsMargins(6, 6, 6, 6)
            grid = 颜色格子(self, cols, cols=12,
                            tip_for=lambda c: self._tip(c))
            grid.on_pick = lambda c: self._set(c)
            g.addWidget(grid)
            v.addWidget(gb)
        # 我的颜色组：自己编辑一组常用色，保存后下次还在
        gb_my = QGroupBox("我的颜色组（自己编辑，保存后下次还在）")
        self.gb_my_group = gb_my
        gv = QVBoxLayout(gb_my)
        row = QHBoxLayout()
        self.ed_my_group = QLineEdit()
        self.ed_my_group.setPlaceholderText(
            "填一组颜色，逗号分隔，如 #1F6E5A, #38699E, #D2603A")
        row.addWidget(self.ed_my_group, stretch=1)
        b_save_g = QPushButton("保存颜色组")
        b_save_g.setToolTip("把上面这组颜色存下来，以后随时点用")
        b_save_g.clicked.connect(self._save_my_color_group)
        row.addWidget(b_save_g)
        gv.addLayout(row)
        self.grid_my_group = 颜色格子(self, [], cols=12,
                                      tip_for=lambda c: c)
        self.grid_my_group.on_pick = lambda c: self._set(c)
        gv.addWidget(self.grid_my_group)
        self._load_my_color_group()
        v.addWidget(gb_my)
        v.addStretch(1)
        return self._scroll(w)

    def _load_my_color_group(self):
        cols = ecpal.load_memory().get("my_color_group", [])
        if cols:
            self.ed_my_group.setText(", ".join(cols))
            self.grid_my_group.set_colors(cols, cols=12)

    def _save_my_color_group(self):
        txt = self.ed_my_group.text().replace("，", ",")
        cols = []
        for tok in txt.split(","):
            t = tok.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t
            if len(t) in (4, 7):
                cols.append(t.upper())
        if not cols:
            QMessageBox.information(self, "没有有效颜色",
                                    "请按 #RRGGBB 格式填写，逗号分隔")
            return
        mem = ecpal.load_memory()
        mem["my_color_group"] = cols
        ecpal.save_memory(mem)
        self.grid_my_group.set_colors(cols, cols=12)
        QMessageBox.information(self, "已保存",
                                f"颜色组已保存（{len(cols)} 色），下次打开还在")

    def _tab_rgb(self):
        """RGB 三格数字，想精确到某个值就填数字"""
        w = QWidget()
        f = QFormLayout(w)
        self.sp_r = QSpinBox()
        self.sp_g = QSpinBox()
        self.sp_b = QSpinBox()
        for sp in (self.sp_r, self.sp_g, self.sp_b):
            sp.setRange(0, 255)
            sp.setSuffix("  (0-255)")
            sp.setFixedWidth(160)
            sp.valueChanged.connect(self._on_rgb_spin)
        f.addRow("红 R", self.sp_r)
        f.addRow("绿 G", self.sp_g)
        f.addRow("蓝 B", self.sp_b)
        f.addRow(QLabel("HEX", ))
        self.ed_hex2 = QLineEdit(self.picked)
        self.ed_hex2.setMaximumWidth(160)
        self.ed_hex2.editingFinished.connect(self._on_hex)
        f.addRow("", self.ed_hex2)

        self.lab_preview = QLabel()
        self.lab_preview.setFixedHeight(70)
        f.addRow("效果", self.lab_preview)

        self.cb_named = QComboBox()
        self.cb_named.addItem("— 常用 RGB 数值 —", None)
        for nm, rgb in [("纯黑", (0, 0, 0)), ("纯白", (255, 255, 255)),
                        ("中灰 128", (128, 128, 128)),
                        ("深绿", (31, 110, 90)), ("蓝", (56, 105, 158)),
                        ("砖红", (163, 62, 118)), ("橙", (210, 96, 58)),
                        ("深紫", (122, 90, 168))]:
            self.cb_named.addItem(f"{nm}  RGB{rgb}", rgb)
        self.cb_named.currentIndexChanged.connect(self._on_named)
        f.addRow("快速填入", self.cb_named)
        lay = QVBoxLayout()
        lay.addWidget(w)
        lay.addStretch(1)
        box = QWidget()
        box.setLayout(lay)
        return box

    def _tab_slider(self):
        """HSV 三滑块 + 一条真实的色调带（比数字直观）"""
        w = QWidget()
        v = QVBoxLayout(w)
        self.sl_h = self._slider(0, 359, 0, "色相")
        self.sl_s = self._slider(0, 255, 0, "饱和")
        self.sl_v = self._slider(0, 255, 0, "明度")
        for sl in (self.sl_h, self.sl_s, self.sl_v):
            v.addWidget(sl)
        self.lab_hsv = QLabel("")
        self.lab_hsv.setObjectName("hint")
        v.addWidget(self.lab_hsv)

        # 色调带：点一下直接跳到那个色相
        self.band = 色调带()
        self.band.huePicked.connect(self._on_band)
        v.addWidget(QLabel("点色调带快速选色相："))
        v.addWidget(self.band)

        # 常用明度的直观参照
        self.bar_shades = 明度参照条()
        v.addWidget(QLabel("明暗层次参照（跟着当前颜色走）："))
        v.addWidget(self.bar_shades)
        v.addStretch(1)
        return w

    # 配色方案一行里的小按钮：压到 22px 高，不然一屏放不下几套
    _TINY_QSS = ("QPushButton{padding:0px 2px; font-size:12px;"
                 "background:#F5F6F7; color:#1A1A1A;"
                 "border:1px solid #C9CDD2; border-radius:3px;}"
                 "QPushButton:hover{background:#E3E9F2;}")

    def _tiny_btn(self, text, tip, w=40):
        b = QPushButton(text)
        b.setFixedSize(w, 22)
        b.setToolTip(tip)
        b.setStyleSheet(self._TINY_QSS)
        return b

    def _scheme_card(self, name, cols, item=None):
        """一套配色方案占一格（高度固定 24px，一屏能看很多套）

        item 传 None = 内置方案，只能「整套用上」和「另存」；
        传 scan_palettes() 的一条 = 用户自己存的，多给「修改 / 删除」。
        """
        cols = self._clean_cols(cols)
        host = QWidget()
        host.setFixedHeight(24)
        hb = QHBoxLayout(host)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(3)
        name = str(name or "")
        lb = QLabel()
        lb.setFixedWidth(74)
        fm = QFontMetrics(lb.font())
        lb.setText(fm.elidedText(name, Qt.ElideRight, 70))
        lb.setToolTip(name)
        hb.addWidget(lb)
        grid = 颜色格子(self, cols, cols=max(1, len(cols)), size=18,
                        tip_for=lambda c: self._tip(c))
        grid.setFixedHeight(20)
        grid.on_pick = lambda c, cs=list(cols): self._pick_from_scheme(c, cs)
        hb.addWidget(grid)
        b_all = self._tiny_btn("整套用上",
                               "把这一整套配色记住，存方案时按整套存", 52)
        b_all.clicked.connect(
            lambda _=False, cs=list(cols): self._set_group(cs))
        hb.addWidget(b_all)
        b_save = self._tiny_btn("另存", "复制成我自己的方案（防撞名）", 32)
        b_save.clicked.connect(
            lambda _=False, cs=list(cols), nm=name: self._save_group_as(cs, nm))
        hb.addWidget(b_save)
        if item is not None and not self._select_only:
            b_ed = self._tiny_btn("修改", "改这套方案的名字和颜色", 32)
            b_ed.clicked.connect(
                lambda _=False, it=dict(item): self._edit_my_scheme(it))
            hb.addWidget(b_ed)
            b_del = self._tiny_btn("删除", "删掉这套方案（删了找不回来）", 32)
            b_del.clicked.connect(
                lambda _=False, it=dict(item): self._del_my_scheme(it))
            if not self._can_del(item):
                # 不是自己存的（记忆 / 外部目录），点了也删不掉 —— 直接置灰
                b_del.setEnabled(False)
                b_del.setToolTip("这份不在「我的配色」目录里，删不掉；"
                                 "先「另存」成自己的方案就能删了")
            hb.addWidget(b_del)
        hb.addStretch(1)
        return host

    @staticmethod
    def _can_del(item):
        """只有存在「我的配色」目录里的方案能删/能直接改"""
        src = item.get("来源") or ""
        return bool(src) and (os.path.normpath(os.path.dirname(src))
                              == os.path.normpath(ecpal.PALETTE_DIR))

    def _tab_schemes(self):
        """内置论文配色 + 用户存的配色方案（紧凑网格，一屏多显示几套）

        点单个色块 = 用那个颜色；点「整套用上」= 整套配色记住，
        存方案时按整套存。用户存的方案还能「修改」和「删除」。
        """
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        # 顶部：编辑一组颜色（逗号分隔），另存为自己的方案
        gb_edit = QGroupBox("编辑颜色组 → 另存为自己的方案")
        ge = QVBoxLayout(gb_edit)
        ge.setSpacing(3)
        row_e = QHBoxLayout()
        row_e.setSpacing(4)
        self.ed_scheme_cols = QLineEdit()
        self.ed_scheme_cols.setPlaceholderText(
            "颜色组，逗号分隔，如 #0A6E8A, #C1440E, #F2A900")
        row_e.addWidget(self.ed_scheme_cols, stretch=1)
        b_load_cur = QPushButton("取当前方案")
        b_load_cur.setToolTip("把上面点选的那套配色填进这个框，方便改")
        b_load_cur.clicked.connect(self._load_group_into_edit)
        row_e.addWidget(b_load_cur)
        b_save_edit = QPushButton("另存为我的方案")
        b_save_edit.clicked.connect(self._save_edited_group)
        row_e.addWidget(b_save_edit)
        ge.addLayout(row_e)
        v.addWidget(gb_edit)

        # 整套套用后的回显：以前直接往 lab_rgb 上写，会把 RGB/HSV 那行数字顶掉
        self.lab_group_tip = QLabel("")
        self.lab_group_tip.setObjectName("hint")
        self.lab_group_tip.setWordWrap(True)
        v.addWidget(self.lab_group_tip)

        # 内置方案：每行放两套（以前一行一套，上下间距巨大，一屏只看得到几套）
        lab_in = QLabel("内置方案（软件自带，不可改；点单个色块用该色，"
                        "「另存」可存成自己的方案再改）：")
        lab_in.setObjectName("hint")
        lab_in.setWordWrap(True)
        v.addWidget(lab_in)
        g_in = QGridLayout()
        g_in.setContentsMargins(0, 0, 0, 0)
        g_in.setHorizontalSpacing(14)
        g_in.setVerticalSpacing(2)
        for i, (name, cols) in enumerate(STANDARD_SCHEMES):
            g_in.addWidget(self._scheme_card(name, cols), i // 2, i % 2)
        g_in.setColumnStretch(g_in.columnCount(), 1)
        v.addLayout(g_in)

        v.addSpacing(6)
        self.lab_my = QLabel("我存的方案（可整套用上 / 修改 / 另存 / 删除）：")
        self.lab_my.setObjectName("hint")
        v.addWidget(self.lab_my)
        # 用独立容器 + 每次重建网格：清空比 takeAt 干净，也不会残留行列
        self.my_host = QWidget()
        v.addWidget(self.my_host)
        self._my_grid = None
        v.addStretch(1)
        box = QWidget()
        box.setLayout(v)
        self._reload_my_schemes()
        return self._scroll(box)

    def _edit_my_scheme(self, item):
        """改自己存的方案：能直接改就改，改不了（记忆里的）就先复制一份"""
        editable = self._can_del(item)
        if editable:
            # 用「原名」而不是显示名初始化：重名方案显示名带「 (2)」后缀，
            # 若直接把显示名传进去，用户不改名时 update_palette 会把「 (2)」
            # 烤进存储名，破坏重名家族的显示去重。
            dlg = 颜色组编辑(self,
                             item.get("原名", item.get("名称", "")),
                             item.get("颜色", []),
                             item=item, is_copy=False)
        else:
            nm = (item.get("名称") or "配色方案") + " 副本"
            QMessageBox.information(
                self, "这份不能直接改",
                "它不在「我的配色」目录里（多半是记忆里的），"
                "已经给你复制一份，改这份就行。")
            dlg = 颜色组编辑(self, nm, item.get("颜色", []), item=None,
                             is_copy=True)
        if not dlg.exec():
            return
        name, cols = dlg.result()
        if not cols:
            return
        if editable:
            ecpal.update_palette(item, name, cols)
        else:
            ecpal.save_palette(name, cols)
        self._group_colors = self._clean_cols(cols)
        self._say(f"「{name}」已更新，{len(self._group_colors)} 色")
        self._reload_my_schemes()

    def _del_my_scheme(self, item):
        """删自己存的方案：二次确认，删完立刻重画列表"""
        name = item.get("名称", "")
        if not self._can_del(item):
            QMessageBox.information(
                self, "删不了",
                "只有存在「我的配色」目录里的方案能删，"
                "这份是从别处读进来的，删了也没用。")
            return
        if QMessageBox.question(
                self, "删除配色方案",
                f"确定删掉「{name}」？\n\n删了就找不回来了。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        if not ecpal.delete_palette(item):
            QMessageBox.information(self, "删失败", "文件删不掉，可能是被占用")
            return
        self._reload_my_schemes()

    def _slider(self, lo, hi, val, name):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(val))
        s.valueChanged.connect(self._on_slider)
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        lb = QLabel(name)
        lb.setFixedWidth(38)
        h.addWidget(lb)
        h.addWidget(s, stretch=1)
        self._slider_rows = getattr(self, "_slider_rows", [])
        self._slider_rows.append((name, s))
        s._label = lb
        return w

    # ---------------- 交互 ----------------
    def _tip(self, c):
        col = QColor(c)
        return (f"{c}\nRGB({col.red()}, {col.green()}, {col.blue()})\n"
                f"点击选中这个颜色")

    def _pick(self, c):
        self._set(c)

    def _toggle_empty(self, on):
        """切到"空 = 跟随线条"，或者切回上一个具体颜色"""
        if on:
            self._last_picked = self.picked
            self.is_empty = True
            self.lab_cur.setStyleSheet(
                "background:#F2F2F2; border:2px dashed #9AA0A6;")
            self.lab_rgb.setText(f"当前：{self.empty_text}"
                                 "（不单独指定颜色，跟随曲线）")
            self.ed_hex.setText("")
        else:
            self.is_empty = False
            self._set(getattr(self, "_last_picked", None) or "#1F6E5A")

    def _set(self, hexcolor, sync=False):
        c = (hexcolor or "").strip().upper()
        q = QColor(c)
        if not q.isValid():
            return
        self.picked = c
        # 手动选了具体颜色 -> 退出"空"状态
        if self.is_empty:
            self.is_empty = False
            self.btn_empty.setChecked(False)
        col = QColor(self.picked)
        self.lab_cur.setStyleSheet(
            f"background:{self.picked}; border:1px solid #808080;")
        self.lab_rgb.setText(f"RGB {col.red()}, {col.green()}, {col.blue()}"
                             f"   HSV {col.hue()}, {col.saturation()},"
                             f" {col.value()}")
        if not self._loading:
            self._loading = True
            self.ed_hex.setText(self.picked)
            self.ed_hex2.setText(self.picked)
            for sp, v in ((self.sp_r, col.red()), (self.sp_g, col.green()),
                          (self.sp_b, col.blue())):
                sp.blockSignals(True)
                sp.setValue(v)
                sp.blockSignals(False)
            for name, sl in self._slider_rows:
                v = {"色相": col.hue(), "饱和": col.saturation(),
                     "明度": col.value()}[name]
                sl.blockSignals(True)
                sl.setValue(int(v))
                sl.blockSignals(False)
            sl = self.band
            self.band.set_hue(col.hue())
            self._loading = False
        self.lab_hsv.setText(
            f"HSV({col.hue()}, {col.saturation()}, {col.value()})"
            f"   RGB({col.red()}, {col.green()}, {col.blue()})")
        self.lab_preview.setStyleSheet(
            f"background:{self.picked}; border:1px solid #808080;")
        # 明度参照条：自己画（HTML 空 span 画不出来）
        self.bar_shades.set_base(self.picked)
        if not sync:
            self._paint_band()

    def _paint_band(self):
        """色调带由 色调带 控件自己画，这里只需刷新提示"""
        pass

    def _on_hex(self):
        t = self.ed_hex.text().strip()
        if t.startswith("#") and QColor(t).isValid():
            self._set(t)

    def _on_hex_live(self):
        t = self.ed_hex.text().strip()
        if t.startswith("#") and len(t) == 7 and QColor(t).isValid():
            self._set(t)

    def _on_rgb_spin(self, _v=None):
        if self._loading:
            return
        c = f"#{self.sp_r.value():02X}{self.sp_g.value():02X}" \
            f"{self.sp_b.value():02X}"
        self._set(c)

    def _on_named(self, i):
        rgb = self.cb_named.itemData(i)
        if rgb:
            self._set("#%02X%02X%02X" % rgb)

    def _on_slider(self, _v=None):
        if self._loading:
            return
        sv = {nm: sl.value() for nm, sl in self._slider_rows}
        col = QColor(self.picked)
        col.setHsv(sv.get("色相", 0), sv.get("饱和", 0), sv.get("明度", 0))
        self._set(col.name().upper())

    def _on_band(self, v):
        if self._loading:
            return
        col = QColor(self.picked)
        col.setHsv(int(v), max(col.saturation(), 200),
                   max(col.value(), 170))
        self._set(col.name().upper())

    def _set_band(self):
        self._on_band(self.band.value())

    @staticmethod
    def _clean_cols(cols):
        """把一套颜色洗成干净的 [#RRGGBB, ...]

        None / 空串 / 空格 / 短的 #abc 都处理掉 —— 单色方案、坏数据都能安全用。
        """
        out = []
        for c in (cols or []):
            if c is None:
                continue
            t = str(c).strip().upper()
            if not t or not QColor(t).isValid():
                continue
            out.append(t)
        return out

    def _say(self, text):
        """配色方案页的提示行（页面还没建好时静默跳过）"""
        lb = getattr(self, "lab_group_tip", None)
        if lb is not None:
            lb.setText(text)

    def _set_group(self, cols):
        """整套用上：取第一色作为当前色，并记住整套，方便直接存方案。

        单色方案也照样能用 —— 只有一个颜色时就是"选中这一个颜色"，
        不再因为 len==1 就把整套丢掉（以前会出现"点了没反应"）。
        """
        cols = self._clean_cols(cols)
        if not cols:
            # 空方案要把记住的整套也清掉，否则上一次的整套会"幽灵残留"，
            # 后面一存方案就存成了不相干的那一套
            self._group_colors = []
            self._say("这套方案里一个有效颜色都没有")
            return
        self._group_colors = cols
        self._set(cols[0])
        self._say(f"已套用「{len(cols)} 色」整套配色，当前色 = {cols[0]}"
                  + ("（存方案就存这一整套）" if len(cols) > 1 else "（只有 1 色）"))

    def _pick_from_scheme(self, color, cols):
        """点配色方案里的单个色块：用那个颜色，同时记住整套备用"""
        self._group_colors = self._clean_cols(cols)
        self._set(color)
        if len(self._group_colors) > 1:
            self._say(f"已选 {color}，同时记住整套 "
                      f"{len(self._group_colors)} 色")

    def _save_group_as(self, cols, base_name=""):
        """把一套配色（软件自带方案等）另存为自己的方案，防撞名"""
        d, ok = QInputDialog.getText(
            self, "另存为我的方案", "给这套方案起个名字：",
            QLineEdit.Normal, base_name or time.strftime("配色 %m-%d %H:%M"))
        if not ok or not d.strip():
            return
        path = ecpal.save_palette(d.strip(), cols)
        if path:
            self._group_colors = self._clean_cols(cols)
            self._reload_my_schemes()
            self._say(f"已另存「{d.strip()}」，{len(self._group_colors)} 色")
            QMessageBox.information(
                self, "已另存", f"已存成你自己的方案：\n{path}")

    def _load_group_into_edit(self):
        cols = self._group_colors or []
        self.ed_scheme_cols.setText(", ".join(cols))

    def _save_edited_group(self):
        txt = self.ed_scheme_cols.text().replace("，", ",")
        cols = []
        for tok in txt.split(","):
            t = tok.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t
            if len(t) in (4, 7):
                cols.append(t.upper())
        if not cols:
            QMessageBox.information(self, "没有有效颜色",
                                    "请按 #RRGGBB 格式填写，逗号分隔")
            return
        self._save_group_as(cols)

    def _pipette(self):
        d = ScreenPickDialog(self)
        if d.exec() and d.color:
            self._set(d.color)

    def _pipette_store(self):
        d = ScreenPickDialog(self)
        if d.exec() and d.color:
            self._set(d.color)
            ecpal.remember_color(d.color)
            self._reload_recents()

    def _reload_recents(self):
        while self.box_rec.count():
            it = self.box_rec.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        rec = ecpal.load_memory().get("recents", [])
        if not rec:
            self.box_rec.addWidget(QLabel("还没有记住的颜色，"
                                          "选一个就会自动记住。"))
            return
        row, cols = 0, 12
        for i in range(0, len(rec), cols):
            chunk = rec[i:i + cols]
            g = 颜色格子(self, chunk, cols=len(chunk), tip_for=self._tip)
            g.on_pick = self._pick
            self.box_rec.addWidget(g)

    def _reload_my_schemes(self):
        """重画「我存的方案」区。

        数据源换成 ecpal.scan_palettes() 而不是 load_memory()["groups"] ——
        后者只有名字和颜色，拿不到文件路径，就没法改、也没法删。
        单色方案也照样显示（以前 >=2 的过滤会把它们悄悄吞掉，
        于是"只配了一个颜色"的方案点整套用上之后就没了）。
        """
        if self._my_grid is not None:
            old = self._my_grid
            old.deleteLater()
            self._my_grid = None
        g = QGridLayout(self.my_host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(2)
        self._my_grid = g
        mine = [it for it in ecpal.scan_palettes() if it.get("颜色")]
        if not mine:
            g.addWidget(QLabel(
                "还没有存过配色方案。选好几个颜色后，"
                "点上面「另存为我的方案」就能存进来。"), 0, 0)
            return
        for i, it in enumerate(mine[:40]):
            nm = it.get("名称", "")
            src = it.get("来源", "")
            w = self._scheme_card(nm, it["颜色"], item=it)
            w.setToolTip(f"{nm}\n{len(it['颜色'])} 色\n来自：{src or '内置记忆'}")
            g.addWidget(w, i // 2, i % 2)
        g.setColumnStretch(g.columnCount(), 1)

    def _save_scheme(self):
        """把当前这一套存进我的配色 —— 不问保存到哪，直接存"""
        d, ok = QInputDialog.getText(
            self, "存为我的配色", "给这套配色起个名字：",
            QLineEdit.Normal, time.strftime("配色 %m-%d %H:%M"))
        if not ok or not d.strip():
            return
        # "这一套" = 当前颜色 + 配色列表里的全部颜色（去重、保持顺序）
        group, seen = [], set()
        for t in self._clean_cols([self.picked] + list(self._group_colors or [])):
            if t not in seen:
                seen.add(t)
                group.append(t)
        path = ecpal.save_palette(d.strip(), group)
        if not path:
            QMessageBox.information(self, "没存成", "没有有效的颜色，存不了")
            return
        ecpal.remember_color(self.picked)
        self._group_colors = group
        self._reload_my_schemes()
        self._reload_recents()
        QMessageBox.information(
            self, "已存好",
            f"配色已保存（固定目录，不用再选位置）：\n"
            f"{ecpal.PALETTE_DIR}\n\n文件名：{os.path.basename(path)}"
            f"\n共 {len(group)} 色"
            + ("" if len(group) > 1 else "（只有 1 色，想要多色就先点「整套用上」）"))

    def _ok(self):
        ecpal.remember_color(self.picked)
        self.accept()

    def result_color(self):
        """空状态返回空字符串 —— 上游就当"没指定"，去跟随曲线颜色"""
        return "" if self.is_empty else self.picked


def pick_color(edit, parent=None, colors=None):
    """调出调色盘，把结果写回输入框 / 色块按钮"""
    cur = ""
    if hasattr(edit, "color") and hasattr(edit, "set_color"):
        cur = edit.color()
    else:
        cur = (edit.text() or "").strip()
    dlg = ColorPickerDialog(parent, cur)
    if dlg.exec():
        if hasattr(edit, "set_color"):
            edit.set_color(dlg.picked)
        else:
            edit.setText(dlg.picked)
        return True
    return False


# ==================================================================
# 颜色组：看颜色块挑一组，可复制成自己的再改
# ==================================================================
class 颜色组编辑(QDialog):
    """改一组颜色：点色块 → 调色盘（里面有吸管）选色，不用手敲编码

    内置/记忆里的组本身改不了，调用方会先复制一份再把这个窗口打开，
    所以这里只负责"改成什么样"，存到哪儿由外面决定。
    """

    def __init__(self, parent=None, name="", colors=(), item=None,
                 is_copy=False):
        super().__init__(parent)
        self.item = item
        self._cols = [c for c in (colors or [])]
        self.setWindowTitle("编辑颜色组" + ("（这是副本，随便改）"
                                            if is_copy else ""))
        self.resize(560, 430)
        self._build(name)

    def _build(self, name):
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.ed_name = QLineEdit(name or "")
        self.ed_name.setPlaceholderText("给这组颜色起个名字")
        f.addRow("组名", self.ed_name)
        lay.addLayout(f)
        tip = QLabel("点色块改颜色 —— 调色盘里有「吸管」，"
                     "可以直接吸屏幕上任何地方的颜色，不用手敲编码。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.box = QVBoxLayout(self.host)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll, stretch=1)

        hb = QHBoxLayout()
        b_add = QPushButton("＋ 加一个颜色")
        b_add.clicked.connect(self._add)
        hb.addWidget(b_add)
        hb.addStretch(1)
        self.lab_n = QLabel("")
        self.lab_n.setObjectName("hint")
        hb.addWidget(self.lab_n)
        lay.addLayout(hb)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("保存")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rebuild()

    def _rebuild(self):
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        n = len(self._cols)
        for i, c in enumerate(self._cols):
            row = QHBoxLayout()
            b = 色块按钮(self, c)
            b.setMinimumWidth(140)
            b._after = lambda _c, i=i: self._set(i, _c)
            row.addWidget(b)
            # 删除（Bug 3：能删掉这一格颜色）
            b_del = QPushButton("删除")
            b_del.setFixedWidth(48)
            b_del.setToolTip("删掉这个颜色（下面的会自动补上来）")
            b_del.clicked.connect(lambda _=False, i=i: self._del(i))
            row.addWidget(b_del)
            # 上移 / 下移（Bug 3：能调整颜色顺序）
            b_up = QPushButton("↑")
            b_up.setFixedWidth(30)
            b_up.setToolTip("上移一格")
            b_up.setEnabled(i > 0)
            b_up.clicked.connect(lambda _=False, i=i: self._move(i, -1))
            row.addWidget(b_up)
            b_down = QPushButton("↓")
            b_down.setFixedWidth(30)
            b_down.setToolTip("下移一格")
            b_down.setEnabled(i < n - 1)
            b_down.clicked.connect(lambda _=False, i=i: self._move(i, 1))
            row.addWidget(b_down)
            row.addStretch(1)
            self.box.addLayout(row)
        self.box.addStretch(1)
        self.lab_n.setText(f"共 {len(self._cols)} 色")

    def _set(self, i, c):
        if 0 <= i < len(self._cols):
            self._cols[i] = c

    def _add(self):
        self._cols.append("#8899AA")
        self._rebuild()

    def _del(self, i):
        if 0 <= i < len(self._cols):
            self._cols.pop(i)
            self._rebuild()

    def _move(self, i, d):
        """上移一格（d=-1）/ 下移一格（d=1）"""
        j = i + d
        if 0 <= j < len(self._cols):
            self._cols[i], self._cols[j] = self._cols[j], self._cols[i]
            self._rebuild()

    def result(self):
        return (self.ed_name.text().strip(), [c for c in self._cols if c])


class 颜色组管理(QDialog):
    """颜色组：一屏颜色块，挑一组就用

    这里直接看颜色块，挑中一组
    就灌进逐点配色；还能把一组复制成自己的副本再改，改色走调色盘/吸管，
    不用手敲颜色编码。颜色组本质上就是配色方案的一份拷贝。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("颜色组 — 看颜色块挑一组")
        self.resize(880, 620)
        self.items = []
        self.picked = None
        self._build()
        self.reload()

    # ---------- 界面 ----------
    def _build(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        b_new = QPushButton("新建一组")
        b_new.setToolTip("从零挑几个颜色，存成自己的颜色组")
        b_new.clicked.connect(self._new)
        top.addWidget(b_new)
        b_copy = QPushButton("复制为新组")
        b_copy.setToolTip("把选中的这组原样复制一份，复制出来的可以随便改")
        b_copy.clicked.connect(self._copy)
        top.addWidget(b_copy)
        b_edit = QPushButton("编辑选中组")
        b_edit.setToolTip("改选中这组的颜色和名字；\n"
                          "内置/记忆里的不能直接改，会自动先复制一份给你改")
        b_edit.clicked.connect(self._edit)
        top.addWidget(b_edit)
        b_del = QPushButton("删除选中")
        b_del.setToolTip("只能删自己存进来的颜色组")
        b_del.clicked.connect(self._del)
        top.addWidget(b_del)
        top.addStretch(1)
        self.lab_dir = QLabel("")
        self.lab_dir.setObjectName("hint")
        top.addWidget(self.lab_dir)
        lay.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.box = QVBoxLayout(self.host)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll, stretch=1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("用这个组填满")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ---------- 数据 ----------
    def reload(self):
        self.items = []
        for name, cols in STANDARD_SCHEMES:
            self.items.append({"名称": name, "颜色": list(cols),
                               "来源": "", "内置": True})
        for it in ecpal.scan_palettes():
            self.items.append({"名称": it.get("名称", ""),
                               "颜色": list(it.get("颜色", [])),
                               "来源": it.get("来源", ""), "内置": False})
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.grp = QButtonGroup(self)     # 每行一个圆点，靠它互斥
        self.grp.setExclusive(True)
        for it in self.items:
            row = QHBoxLayout()
            tag = "　［内置，改前先复制］" if it["内置"] else ""
            rb = QRadioButton(f"{it['名称']}{tag}")
            rb.setMinimumWidth(240)
            rb.setToolTip("选中这一组；双击颜色块看色值")
            rb.toggled.connect(lambda _=False, i=it: self._on_sel(i))
            self.grp.addButton(rb)
            row.addWidget(rb)
            grid = 颜色格子(self, it["颜色"], cols=12, size=24,
                            tip_for=lambda c: c)
            grid.on_pick = lambda c: ecpal.remember_color(c)
            row.addWidget(grid, stretch=1)
            row.addStretch(1)
            host = QWidget()
            host.setLayout(row)
            self.box.addWidget(host)
        self.box.addStretch(1)
        self.lab_dir.setText(f"自己存的颜色组放在：{ecpal.PALETTE_DIR}")
        if self.items and self.picked is None:
            self.grp.buttons()[0].setChecked(True)

    def _on_sel(self, item):
        self.picked = item

    def _cur(self):
        if not self.picked:
            QMessageBox.information(self, "先选一组", "请先点一组颜色组")
            return None
        return self.picked

    @staticmethod
    def _editable(it):
        """自己存进配色目录的才能直接改；内置/记忆里的要先复制"""
        if it.get("内置"):
            return False
        src = it.get("来源") or ""
        return (os.path.normpath(os.path.dirname(src))
                == os.path.normpath(ecpal.PALETTE_DIR))

    # ---------- 操作 ----------
    def _new(self):
        dlg = 颜色组编辑(self, "我的颜色组", [], item=None, is_copy=True)
        if dlg.exec():
            name, cols = dlg.result()
            if not cols:
                return
            ecpal.save_palette(name or "我的颜色组", cols)
            self.picked = None
            self.reload()

    def _copy(self):
        it = self._cur()
        if not it:
            return
        nm = (it["名称"] or "颜色组") + " 副本"
        if ecpal.save_palette(nm, it["颜色"]):
            self.picked = None
            self.reload()
            QMessageBox.information(
                self, "已复制",
                f"已复制成新颜色组「{nm}」。\n"
                f"在下面列表里选中它，再点「编辑选中组」就能改了。")

    def _edit(self):
        it = self._cur()
        if not it:
            return
        if self._editable(it):
            dlg = 颜色组编辑(self, it["名称"], it["颜色"], item=it,
                             is_copy=False)
        else:
            QMessageBox.information(
                self, "先复制一份",
                "「内置 / 记忆」里的颜色组不能直接改，已经给你复制了一份，"
                "改这份就行。")
            dlg = 颜色组编辑(self, (it["名称"] or "颜色组") + " 副本",
                             it["颜色"], item=None, is_copy=True)
        if dlg.exec():
            name, cols = dlg.result()
            if not cols:
                return
            if dlg.item is not None:
                ecpal.update_palette(dlg.item, name, cols)
            else:
                ecpal.save_palette(name or "我的颜色组", cols)
            self.picked = None
            self.reload()

    def _del(self):
        it = self._cur()
        if not it:
            return
        if not self._editable(it):
            QMessageBox.information(
                self, "删不了", "只有自己存进来的颜色组能删，"
                                "内置的和记忆里的删不了。")
            return
        if ecpal.delete_palette({"来源": it["来源"]}):
            self.picked = None
            self.reload()

    def result_colors(self):
        return list(self.picked.get("颜色", [])) if self.picked else None


# ==================================================================
# 数据点形状预览（所见即所得）
# ==================================================================
class 标题预览(QWidget):
    """轴标题实时预览：横排/竖排都画，上下标按真实比例缩放

    改任何一项立刻重画 —— 不用切回出图预览才知道长什么样。
    自己 paintEvent 画，不用 HTML（空的span 画不出东西）。
    """

    MARK_RE = __import__("re").compile(r"([_^])\{([^}]*)\}|([_^])(\S)")

    def __init__(self, parent=None, vertical=False):
        super().__init__(parent)
        self.text = "A g^{-1}"
        self.size = 15.0
        self.color = "#000000"
        self.sub_ratio = 0.68
        self.rise = 0.40
        self.drop = 0.18
        self.sup_dx = 0.0
        self.sub_dx = 0.0
        self.vertical = vertical
        self.weight = "normal"
        self.style = "normal"
        self.rich = True                # 关掉后 ^{} / _{} 原样显示
        self.setMinimumHeight(210 if vertical else 78)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if vertical:
            # 竖排标题往往比控件高（长标题会被裁掉），
            # 所以按文字长度撑高，宁可控件高一点，也不能显示不全
            self._auto_h = True
        else:
            self._auto_h = False

    def set_all(self, text=None, size=None, color=None, sub_ratio=None,
                rise=None, drop=None, weight=None, style=None,
                sup_dx=None, sub_dx=None, rich=None):
        if text is not None:
            self.text = text
        if rich is not None:
            self.rich = bool(rich)
        if size is not None:
            self.size = float(size)
        if color is not None:
            self.color = color
        if sub_ratio is not None:
            self.sub_ratio = float(sub_ratio)
        if rise is not None:
            self.rise = float(rise)
        if drop is not None:
            self.drop = float(drop)
        if sup_dx is not None:
            self.sup_dx = float(sup_dx)
        if sub_dx is not None:
            self.sub_dx = float(sub_dx)
        if weight is not None:
            self.weight = weight or "normal"
        if style is not None:
            self.style = style or "normal"
        self.update()

    @classmethod
    def _segments(cls, text):
        """按上下标记号切段：[('A g', 0), ('-1', 1)]；角色 0/1/-1"""
        text = text or ""
        out, pos = [], 0
        for m in cls.MARK_RE.finditer(text):
            if m.start() > pos:
                out.append((text[pos:m.start()], 0))
            if m.group(2) is not None:
                out.append((m.group(2), 1 if m.group(1) == "^" else -1))
            else:
                out.append((m.group(4), 1 if m.group(3) == "^" else -1))
            pos = m.end()
        if pos < len(text):
            out.append((text[pos:], 0))
        return [s for s in out if s[0]]

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), QColor("#FBFCFD"))
        p.setPen(QPen(QColor("#E3E6E9"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # 富文本关掉时整串当一个普通段，^{} / _{} 原样显示
        if self.rich:
            segs = self._segments(self.text) or [("（空）", 0)]
        else:
            segs = [(self.text or "", 0)] or [("（空）", 0)]
        # 竖排时长标题放不下就自动缩小字号，保证"显示全"优先于"字号大"
        fs = max(6.0, float(self.size))
        if self.vertical and self._auto_h:
            need = fs * sum(
                max(1, len(t)) for t, _ in segs) * 0.62 + 26
            if need > self.height():
                fs = max(6.0, (self.height() - 26) /
                         max(1.0, sum(max(1, len(t)) for t, _ in segs)
                             * 0.62))
        fm = QFont("Times New Roman")
        fm.setPointSizeF(fs)
        fm.setBold(self.weight == "bold")
        fm.setItalic(self.style == "italic")
        fsmall = QFont(fm)
        fsmall.setPointSizeF(fs * self.sub_ratio)
        col = QColor(self.color)
        p.setPen(col if col.isValid() else QColor("#000000"))

        widths, asc, desc = [], 0.0, 0.0
        for txt, role in segs:
            p.setFont(fsmall if role else fm)
            widths.append(p.fontMetrics().horizontalAdvance(txt))
            fm_t = p.fontMetrics()
            asc, desc = max(asc, fm_t.ascent()), max(desc, fm_t.descent())
        total = sum(widths)

        # 横排/竖排统一：把每段按"文字框旋转角"摆到正确位置，
        # 上标始终垂直于基线在外侧（CCW 90° 时上标在左、下标在右），
        # 与 matplotlib 引擎（richlabel）完全对齐。
        rot = 90.0 if self.vertical else 0.0
        th = math.radians(rot)
        # 旋转后 reading 方向 (rx, ry)、垂直于基线向外(上) (nx, ny)
        # 取 matplotlib 约定（逆时针为正、+y 向上）；Qt 绘制时 y 取反。
        rx, ry = math.cos(th), math.sin(th)
        nx, ny = -math.sin(th), math.cos(th)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        half_read = total / 2.0
        cum = -half_read
        for (txt, role), w in zip(segs, widths):
            p.setFont(fsmall if role else fm)
            perp = (self.rise * fs if role == 1
                    else (-self.drop * fs if role == -1 else 0.0))
            along = ((self.sup_dx if role == 1
                      else (self.sub_dx if role == -1 else 0.0)) * fs)
            # display 偏移（相对中心，+y 向上）
            ox = rx * (cum + along) + nx * perp
            oy = ry * (cum + along) + ny * perp
            qx = cx + ox
            qy = cy - oy          # Qt y 向下：取反
            p.save()
            p.translate(qx, qy)
            p.rotate(rot)
            p.drawText(QPointF(0.0, 0.0), txt)
            p.restore()
            cum += w
        p.end()


class 逐点配色表(QWidget):
    """每个数据点一行，单独给它配色；也能一键把整套配色灌进去

    数据点比配色多时会自动循环套用（跟图例那套配色逻辑一致）。
    颜色格留空 = 跟随曲线本身的颜色。
    """

    def __init__(self, parent=None, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self._rows = []            # [(标签, 色块按钮, QLineEdit)]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.addWidget(QLabel("批量："))
        b_from_pal = QPushButton("用选中的颜色组填满")
        b_from_pal.setToolTip("把「线条/配色」里当前选中的颜色组（配色方案）"
                             "依次套到每个数据点上；\n"
                             "数据点比颜色多时会自动循环")
        b_from_pal.clicked.connect(self.apply_palette)
        top.addWidget(b_from_pal)
        b_grp = QPushButton("颜色组…")
        b_grp.setToolTip("打开颜色组：一屏颜色块，挑一组就用；\n"
                         "还能复制成自己的组再改（点色块用调色盘/吸管选色）")
        b_grp.clicked.connect(self.pick_from_group)
        top.addWidget(b_grp)
        b_clr = QPushButton("全部清空（都跟随曲线色）")
        b_clr.clicked.connect(self.clear_all)
        top.addWidget(b_clr)
        top.addStretch(1)
        lay.addLayout(top)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["#", "名称", "这个点的颜色"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.tbl.setMinimumHeight(160)
        lay.addWidget(self.tbl)
        self.lab = QLabel("")
        self.lab.setObjectName("hint")
        self.lab.setWordWrap(True)
        lay.addWidget(self.lab)

    # ---------- 填 / 读 ----------
    def set_rows(self, labels, face_colors, vline_colors, edge_colors):
        """labels 是每个数据点的名字；三个颜色列表可为空"""
        self.tbl.setRowCount(len(labels))
        self._rows = []
        for r, lb in enumerate(labels):
            idx = self.tbl.item(r, 0)
            if idx is None:
                idx = QTableWidgetItem(str(r + 1))
                self.tbl.setItem(r, 0, idx)
            name = self.tbl.item(r, 1)
            if name is None:
                name = QTableWidgetItem(str(lb))
                self.tbl.setItem(r, 1, name)
            else:
                name.setText(str(lb))
            host = QWidget()
            h = QHBoxLayout(host)
            h.setContentsMargins(2, 1, 2, 1)
            h.setSpacing(4)
            fb = 色块按钮(host, _pick(face_colors, r), allow_empty=True,
                           empty_text="跟随曲线")
            fb.setMinimumWidth(104)
            fb._after = lambda _c, row=r: self._emit()
            vb = 色块按钮(host, _pick(vline_colors, r), allow_empty=True,
                           empty_text="竖线跟随")
            vb.setMinimumWidth(104)
            vb._after = lambda _c, row=r: self._emit()
            eb = 色块按钮(host, _pick(edge_colors, r), allow_empty=True,
                           empty_text="边线跟随")
            eb.setMinimumWidth(104)
            eb._after = lambda _c, row=r: self._emit()
            h.addWidget(fb)
            h.addWidget(vb)
            h.addWidget(eb)
            self.tbl.setCellWidget(r, 2, host)
            self._rows.append((fb, vb, eb))
        self.lab.setText(f"共 {len(labels)} 个数据点。"
                         "左边三个色块依次是：点的填充色 / 竖线色 / 边线色。"
                         "留空 = 跟随该曲线本身的颜色。")

    def values(self):
        """读出三组颜色列表"""
        f = [b.color() for b, _, _ in self._rows]
        v = [b.color() for _, b, _ in self._rows]
        e = [b.color() for _, _, b in self._rows]
        return f, v, e

    # ---------- 批量操作 ----------
    def apply_palette(self, colors=None):
        """把一套配色依次灌进去；配色不够就循环"""
        cols = list(colors or [])
        if not cols:
            cols = self._palette_from_panel()
        if not cols:
            return
        for i, (fb, vb, eb) in enumerate(self._rows):
            c = cols[i % len(cols)]           # 循环套用
            fb.set_color(c)
            vb.set_color(c)
            eb.set_color(c)
        self._tell_cycles(len(cols))
        self._emit()

    def pick_from_group(self):
        """打开颜色组：看颜色块挑一组；可复制成自己的组再改"""
        dlg = 颜色组管理(self)
        if dlg.exec():
            cols = dlg.result_colors()
            if cols:
                self.apply_palette(cols)

    def clear_all(self):
        for fb, vb, eb in self._rows:
            fb.set_color("")
            vb.set_color("")
            eb.set_color("")
        self.lab.setText("已全部清空 → 所有点都跟随各自曲线颜色。")
        self._emit()

    def _palette_from_panel(self):
        try:
            return self.window().panel._parse_colors()
        except Exception:
            return []

    def _tell_cycles(self, ncols):
        n = len(self._rows)
        if n > ncols:
            self.lab.setText(
                f"共 {n} 个数据点，配色只有 {ncols} 个 → 已自动循环套用"
                f"（第 {ncols + 1} 个点用第 1 个颜色，依此类推）。")
        else:
            self.lab.setText(f"已把 {ncols} 个配色套到 {n} 个数据点上。")

    def _emit(self):
        if self.on_change:
            self.on_change()


def _pick(lst, i):
    """取列表第 i 项，越界返回空"""
    if not lst:
        return ""
    try:
        return lst[i] if i < len(lst) else ""
    except (TypeError, IndexError):
        return ""


class 轴标题编辑(QWidget):
    """一个轴的标题设置

    结构（按用户要求收紧）：
      · 标题文字直接填在输入框里，开面板就是这个图的默认标题，改哪张
        图就在「正在调的图」里切；留空 = 真的不画这个标题
      · 字号/颜色/字型、距离/微调，各自一个勾选框：不勾就跟随全局，
        对应的设置整排藏起来（默认隐藏），勾上才出现
      · 没有预览白框了（Y 轴那个白框本来就显示不全，预览以出图预览为准）
    """

    def __init__(self, parent=None, which="x", name="X"):
        super().__init__(parent)
        self.which = which
        self.name = name
        self._timer = QTimer(self, singleShot=True, timeout=self._queue)
        self._build()

    def _num(self, lo, hi, val, step=1.0, decimals=0):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setValue(val)
        sp.setKeyboardTracking(False)   # 输入途中不触发，免得卡
        return sp

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        f = QFormLayout()
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(4)

        self.ed_text = QLineEdit()
        self.ed_text.setPlaceholderText("留空 = 不画这个标题")
        self.ed_text.setToolTip(
            "写法：上标 x^{-1}、下标 F_{x}，多个字符用大括号包住。\n"
            "上下标大小/偏移在「画布/字体」页统一调，整张图一起生效。")
        self.ed_text.textChanged.connect(self._queue)
        # 富文本开关紧挨着标题文字，直观；说明悬停才看（tooltip）
        self.ck_rich = QCheckBox("富文本")
        self.ck_rich.setChecked(True)
        self.ck_rich.setToolTip(
            "勾上：文字里的 ^{上标} / _{下标} 按上下标渲染，\n"
            "字形跟正文一致，大小/偏移在「画布/字体」页统一调。\n"
            "取消：^{} / _{} 当普通字符原样显示。")
        self.ck_rich.toggled.connect(self._queue)
        hb_txt = QHBoxLayout()
        hb_txt.setContentsMargins(0, 0, 0, 0)
        hb_txt.addWidget(self.ed_text, stretch=1)
        hb_txt.addWidget(self.ck_rich)
        f.addRow(f"{self.name} 标题文字", hb_txt)

        # ---- 字号与颜色：不勾就跟随全局 ----
        self.ck_font = QCheckBox("单独设置字号、颜色、字型")
        self.ck_font.setToolTip(
            "不勾：字号跟「画布/字体」页的坐标轴标题字号一致，颜色、"
            "字型用全局默认。\n勾上：下面三项才生效，各轴互不影响。")
        self.ck_font.toggled.connect(self._sync_groups)
        f.addRow(self.ck_font)

        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        self.cb_size = QComboBox()
        for s in (0, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28):
            self.cb_size.addItem("跟随全局" if s == 0 else str(s), s)
        self.cb_size.currentIndexChanged.connect(self._queue)
        hb.addWidget(self.cb_size, stretch=1)
        hb.addWidget(QLabel("颜色"))
        self.btn_color = 色块按钮(self, "#000000")
        self.btn_color.setMinimumWidth(96)
        self.btn_color._after = lambda _c: self._queue()
        hb.addWidget(self.btn_color)
        self.w_size = QWidget()
        self.w_size.setLayout(hb)
        f.addRow("字号 / 颜色", self.w_size)

        hb2 = QHBoxLayout()
        hb2.setContentsMargins(0, 0, 0, 0)
        self.cb_weight = QComboBox()
        self.cb_weight.addItems(["正常字形", "粗体"])
        self.cb_weight.currentIndexChanged.connect(self._queue)
        self.cb_style = QComboBox()
        self.cb_style.addItems(["正常字形", "斜体"])
        self.cb_style.currentIndexChanged.connect(self._queue)
        hb2.addWidget(self.cb_weight)
        hb2.addWidget(self.cb_style)
        self.w_face = QWidget()
        self.w_face.setLayout(hb2)
        f.addRow("字型", self.w_face)

        # ---- 距离与微调：不勾就用默认 ----
        self.ck_pos = QCheckBox("单独设置距离、上下左右微调")
        self.ck_pos.setToolTip(
            "不勾：标题离刻度的距离用默认，也不做手动微调。\n"
            "勾上：下面三个才生效。")
        self.ck_pos.toggled.connect(self._sync_groups)
        f.addRow(self.ck_pos)

        self.sp_pad = self._num(-60, 240, 0)
        self.sp_pad.setSuffix(" 点")
        self.sp_pad.setToolTip("标题离刻度文字的距离。\n"
                                "刻度多、字号大时 matplotlib 会自动重算，\n"
                                "这里填的是额外加的距离。")
        self.sp_sx = self._num(-240, 240, 0)
        self.sp_sx.setSuffix(" 点")
        self.sp_sy = self._num(-240, 240, 0)
        self.sp_sy.setSuffix(" 点")
        for sp in (self.sp_pad, self.sp_sx, self.sp_sy):
            sp.valueChanged.connect(self._queue)
        f.addRow("离刻度距离", self.sp_pad)
        f.addRow("左右微调（往右为正）", self.sp_sx)
        f.addRow("上下微调（往上为正）", self.sp_sy)

        lay.addLayout(f)
        # 上下标的大小/偏移整张图统一，走「画布/字体」页的上下标栏
        self._mt = {"sub_ratio": 0.68, "rise": 0.40, "drop": 0.18,
                    "sup_dx": 0.0, "sub_dx": 0.0}
        self._sync_groups()

    def _sync_groups(self, *_):
        """两个勾选框分别控制两排设置的显示；默认都不勾 → 都不显示"""
        on_f = self.ck_font.isChecked()
        self.w_size.setVisible(on_f)
        self.w_face.setVisible(on_f)
        on_p = self.ck_pos.isChecked()
        for sp in (self.sp_pad, self.sp_sx, self.sp_sy):
            sp.setEnabled(on_p)
        # 距离/微调是直接加进行表的，标签跟着一起隐藏
        form = self.layout().itemAt(0).layout()
        for i in (5, 6, 7):          # 离刻度距离 / 左右微调 / 上下微调
            item = form.itemAt(i, QFormLayout.LabelRole)
            if item is not None and item.widget() is not None:
                item.widget().setVisible(on_p)

    def set_mt(self, sub_ratio=None, rise=None, drop=None,
               sup_dx=None, sub_dx=None):
        """同步全局上下标参数（不再有预览框，这里只记下来备用）"""
        if sub_ratio is not None:
            self._mt["sub_ratio"] = float(sub_ratio)
        if rise is not None:
            self._mt["rise"] = float(rise)
        if drop is not None:
            self._mt["drop"] = float(drop)
        if sup_dx is not None:
            self._mt["sup_dx"] = float(sup_dx)
        if sub_dx is not None:
            self._mt["sub_dx"] = float(sub_dx)

    # ---------- 读写 ----------

    def values(self):
        return {
            "font_on": self.ck_font.isChecked(),
            "pos_on": self.ck_pos.isChecked(),
            "color": self.btn_color.color() or "#000000",
            "pad": int(self.sp_pad.value()),
            "shift_x": float(self.sp_sx.value()),
            "shift_y": float(self.sp_sy.value()),
            "weight": "bold" if self.cb_weight.currentIndex() else "normal",
            "style": "italic" if self.cb_style.currentIndex() else "normal",
            "rich": self.ck_rich.isChecked(),
        }

    def size_value(self):
        """字号（0 = 跟随全局）；没勾"单独设置"时一律当 0"""
        if not self.ck_font.isChecked():
            return 0
        return int(self.cb_size.currentData() or 0)

    def set_values(self, text, size, cfg):
        cfg = cfg or {}
        # 老配置没有这两个开关，默认当作"单独设置"（保持以前的观感）
        self.ed_text.setText(text or "")
        self.ck_rich.setChecked(cfg.get("rich", True) is not False)
        self.ck_font.setChecked(cfg.get("font_on", True) is not False)
        self.ck_pos.setChecked(cfg.get("pos_on", True) is not False)
        idx = self.cb_size.findData(int(size or 0))
        self.cb_size.setCurrentIndex(idx if idx >= 0 else 0)
        self.btn_color.set_color(cfg.get("color") or "#000000")
        self.sp_pad.setValue(cfg.get("pad", 0) or 0)
        self.sp_sx.setValue(cfg.get("shift_x", 0) or 0)
        self.sp_sy.setValue(cfg.get("shift_y", 0) or 0)
        self.cb_weight.setCurrentIndex(1 if cfg.get("weight") == "bold" else 0)
        self.cb_style.setCurrentIndex(
            1 if cfg.get("style") == "italic" else 0)
        self._sync_groups()

    def set_text(self, txt):
        """外部（样式回填 / 换图种）直接改标题文字，不触发信号风暴"""
        self.ed_text.blockSignals(True)
        self.ed_text.setText(txt or "")
        self.ed_text.blockSignals(False)

    def _queue(self, *_):
        self._timer.start(180)


class 坐标微调(QWidget):
    """坐标输入：0~1 的范围 + 上下微调按钮，不再用下拉框

    坐标只有 0~1 一个区间，下拉框列一堆小数点反而不直观。这里给一个
    数字显示 + ▲▼ 两个按钮（步进 0.01，按住可以连点），想精确填就直接
    点数字那一块改。范围和 0/1 各代表什么写在悬停提示里。
    """

    STEP = 0.01

    def __init__(self, parent=None, value=0.5, axis="x"):
        super().__init__(parent)
        self.axis = axis
        self._v = 0.5
        self._build()
        self.set_value(value)
        self.setFixedHeight(24)

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(0)
        tip = ("范围 0~1。X：0 = 左边缘，1 = 右边缘；"
               if self.axis == "x" else
               "范围 0~1。Y：0 = 底部，1 = 顶部；")
        tip += "点箭头按 0.01 微调，也可以直接在这里改数字。"
        self.lab = QLineEdit()
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.setToolTip(tip)
        self.lab.setStyleSheet("border:1px solid #c8c8c8; border-radius:3px;")
        self.lab.setMinimumWidth(44)
        self.lab.editingFinished.connect(self._from_text)
        lay.addWidget(self.lab, stretch=1)
        for arrow, d in (("▲", +1), ("▼", -1)):
            b = QToolButton()
            b.setText(arrow)
            b.setFixedSize(20, 22)
            b.setToolTip(tip)
            b.setAutoRepeat(True)          # 按住能连点
            b.clicked.connect(lambda _=False, dd=d: self.nudge(dd))
            lay.addWidget(b)
        self.setToolTip(tip)

    def value(self):
        try:
            return max(0.0, min(1.0, float(self._v)))
        except (TypeError, ValueError):
            return 0.5

    def set_value(self, v):
        try:
            f = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            f = 0.5
        self._v = f
        self._show()

    def _show(self):
        self.lab.setText(f"{self._v:g}")
        self.lab.setToolTip(f"当前 {self._v:g}")

    def _from_text(self, *_):
        try:
            f = float(self.lab.text())
        except (TypeError, ValueError):
            self._show()
            return
        self.set_value(f)

    def nudge(self, d):
        self.set_value(round(self.value() + d * self.STEP, 4))


class 线型预览(QWidget):
    """一小段真实线型的示意图，选线型时一眼看清长短疏密

    直接调 QPainter 的 setDashPattern —— matplotlib 内部也是同一套，
    所以这里看到的跟出图一致（dash 序列按点数给，不随线宽变形）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._code = "-"
        self._lw = 1.8
        self.setToolTip("线型示意")

    def set_style(self, name, lw=1.8):
        self._code = dict(eclab.LINE_STYLES).get(name, "-")
        self._lw = float(lw or 1.8)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#222222"))
            pen.setWidthF(max(0.6, self._lw))
            pen.setCapStyle(Qt.FlatCap)
            if isinstance(self._code, tuple):
                pen.setDashPattern([max(0.5, float(v))
                                    for v in self._code[1]])
            elif self._code in (":", "-.", "--"):
                pen.setStyle({":": Qt.DotLine,
                              "-.": Qt.DashDotLine,
                              "--": Qt.DashLine}[self._code])
            p.setPen(pen)
            y = self.height() / 2.0
            p.drawLine(QPointF(2.0, y), QPointF(self.width() - 2.0, y))
        finally:
            p.end()


class 色条预览(QWidget):
    """当前配色的一排色块，肉眼看出这套好不好看

    注意：不能用 HTML 的空 <span> 来画 —— 那种没内容的 span 根本不画，
    界面上就是一条空白。所以这里自己 paintEvent 画。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = []
        self.setFixedHeight(26)

    def set_colors(self, cols):
        self.colors = list(cols)
        self.setToolTip(", ".join(self.colors))
        self.update()

    def paintEvent(self, ev):
        if not self.colors:
            p = QPainter(self)
            p.setPen(QColor("#9AA0A6"))
            p.drawText(self.rect(), Qt.AlignCenter, "（还没定颜色）")
            p.end()
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.colors)
        gap = 3
        w = (self.width() - gap * (n - 1)) / n
        h = self.height() - 2
        for i, c in enumerate(self.colors):
            x = int(i * (w + gap))
            ww = int(w)
            col = QColor(c)
            if not col.isValid():
                col = QColor("#DDDDDD")
            p.fillRect(x, 1, ww, h, col)
            p.setPen(QPen(QColor("#7A7A7A"), 1))
            p.drawRect(x, 1, ww - 1, h - 1)
        # 超过 12 色时只画前面几个，后面用省略号提示
        if n > 12:
            p.setPen(QColor("#555555"))
            p.drawText(QRect(self.width() - 30, 0, 30, self.height()),
                       Qt.AlignCenter, "…")
        p.end()


class MarkerPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.marker, self.fill = "o", "实心"
        self.face = self.edge = ""
        self.color = "#1F6E5A"

    def set_style(self, marker, fill, face, edge, color):
        self.marker = marker or "o"
        self.fill = fill or "实心"
        self.face = face or ""
        self.edge = edge or ""
        self.color = color or "#1F6E5A"
        self.update()

    def _path(self, cx, cy, r, kind):
        import math
        if kind == "s":
            return [QPointF(cx - r * .9, cy - r * .9),
                    QPointF(cx + r * .9, cy - r * .9),
                    QPointF(cx + r * .9, cy + r * .9),
                    QPointF(cx - r * .9, cy + r * .9)]
        if kind == "^":
            return [QPointF(cx, cy - r), QPointF(cx + r * .95, cy + r * .8),
                    QPointF(cx - r * .95, cy + r * .8)]
        if kind == "v":
            return [QPointF(cx, cy + r), QPointF(cx + r * .95, cy - r * .8),
                    QPointF(cx - r * .95, cy - r * .8)]
        if kind in ("D", "d"):
            return [QPointF(cx, cy - r), QPointF(cx + r, cy),
                    QPointF(cx, cy + r), QPointF(cx - r, cy)]
        if kind == "p":
            n = 5
        elif kind == "*":
            n = 10
        elif kind == "h":
            n = 6
        elif kind == "8":
            n = 8
        else:
            return None       # 圆
        pts = []
        for i in range(n):
            rr = r if (kind != "*" or i % 2 == 0) else r * .45
            a = math.pi / 2 + i * 2 * math.pi / n
            pts.append(QPointF(cx + rr * math.cos(a),
                               cy - rr * math.sin(a)))
        return pts

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(self.width(), self.height()) / 4.5
        col = QColor(self.color if QColor(self.color).isValid()
                     else "#1F6E5A")
        edge = QColor(self.edge) if QColor(self.edge or "").isValid() else col
        face = QColor(self.face) if QColor(self.face or "").isValid() else col
        if self.fill == "立体":
            p.setOpacity(.45)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#808080"))
            p.drawEllipse(QRectF(cx - r + 3, cy - r + 3, 2 * r, 2 * r))
            p.setOpacity(1.0)
            p.setPen(QPen(QColor("#FFFFFF"), 1.6))
            p.setBrush(face)
        elif self.fill == "空心":
            p.setPen(QPen(edge, 2.0))
            p.setBrush(Qt.NoBrush)
        else:
            p.setPen(QPen(edge, 1.4))
            p.setBrush(face)
        pts = self._path(cx, cy, r, self.marker)
        if pts is None:
            p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        else:
            p.drawPolygon(QPolygon(pts))
        p.end()


# ==================================================================
# 样式面板：每张图一套
# ==================================================================
class StylePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.changed = None
        self.cur = "cv_overlay"
        self._point_labels_cache = []    # 预览窗送来的真实数据点名字
        self._last_fig = None            # 预览窗送来的当前图（用来读真实轴标题）
        self._auto_titles = ("", "")     # 最近一次"自动填"进编辑框的标题
        self.styles = {k: json.loads(json.dumps(eclab.DEFAULT_STYLE))
                       for k in KIND_CODES}
        self.out = {"formats": ["png", "pdf"], "dpi": 600}
        self._timer = QTimer(self, singleShot=True, timeout=self._fire)
        self._build()

    def _fire(self):
        if self.changed:
            self.changed()

    def _queue(self, *a):
        self._timer.start(100)

    def _scroll(self, inner):
        """页签内容套滚动区：窗口不够高时上下滚动，不再把控件压扁"""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setWidget(inner)
        return sa

    # ---------- 对外 ----------
    def set_styles(self, styles, out):
        self.styles = {k: json.loads(json.dumps(
            styles.get(k) or eclab.DEFAULT_STYLE)) for k in KIND_CODES}
        self.out = dict(out or self.out)
        self._fill(self.styles[self.cur], self.out)

    def styles_all(self):
        self._save_cur()
        return ({k: json.loads(json.dumps(v))
                 for k, v in self.styles.items()}, dict(self.out))

    def set_kind(self, kind):
        if kind not in KIND_CODES or kind == self.cur:
            return
        self._save_cur()
        self.cur = kind
        # 换图了，之前那份数据点名字作废，否则表格行数对不上
        self._point_labels_cache = []
        self.cb_kind.setCurrentIndex(KIND_CODES.index(kind))
        self.kind_display.setText(self.cb_kind.currentText())
        # 重填上百个控件时暂停重绘，切图不再一顿一顿
        self.setUpdatesEnabled(False)
        try:
            self._fill(self.styles[kind], self.out)
            self._sync_eis_tab()
            self._sync_scatter_tab()
        finally:
            self.setUpdatesEnabled(True)

    def set_legend_labels(self, labels):
        """把当前图真实的图例文字填进表里，方便整张图一起改"""
        cur = self.tb_leg.rowCount()
        if cur == len(labels):
            return
        self.tb_leg.blockSignals(True)
        self.tb_leg.setRowCount(0)
        for i, t in enumerate(labels):
            r = self.tb_leg.rowCount()
            self.tb_leg.insertRow(r)
            it0 = QTableWidgetItem(str(i + 1))
            it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
            self.tb_leg.setItem(r, 0, it0)
            self.tb_leg.setItem(r, 1, QTableWidgetItem(str(t)))
            it = QTableWidgetItem("")
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setIcon(color_icon(self._nth_color(i)))
            self.tb_leg.setItem(r, 2, it)
        self.tb_leg.blockSignals(False)
        self._queue()

    def _nth_color(self, i):
        cs = self.styles[self.cur].get("colors") or ["#1F6E5A"]
        return cs[i % len(cs)]

    def set_point_labels(self, labels):
        """外部（预览窗口）把当前图真实的数据点名字送进来

        比电容图一个点对应一条曲线，所以"逐点配色"就是逐曲线配色。
        """
        labels = list(labels or [])
        cur = self._point_labels_cache
        if cur == labels:
            return
        self._point_labels_cache = labels
        sc = self.styles[self.cur].get("scatter", {}) or {}
        self.pt_table.set_rows(labels, sc.get("face_colors") or [],
                               sc.get("vline_colors") or [],
                               sc.get("edge_colors") or [])

    def _point_labels(self):
        """当前图有几个数据点、分别叫什么

        优先级：预览窗送来的真实名字 > 已经存过的逐点配色长度 >
        配色数量（保证表格不空着）。已存过的颜色一个都不能少显示，
        否则重新打开样式时颜色会被截断。
        """
        if self._point_labels_cache:
            return self._point_labels_cache
        sc = self.styles[self.cur].get("scatter", {}) or {}
        stored = max(len(sc.get(k) or []) for k in
                     ("face_colors", "vline_colors", "edge_colors")) \
            if sc else 0
        n = max(stored, len(self.styles[self.cur].get("colors") or
                            ["#1F6E5A"]))
        return [f"数据点 {i + 1}" for i in range(max(n, 1))]

    def _save_cur(self):
        self.styles[self.cur], self.out = self._read(
            self.styles[self.cur], self.out)

    def _color_row(self, edit):
        b = QPushButton("调色盘")
        b.setMaximumWidth(74)
        b.clicked.connect(lambda: (pick_color(edit, self), self._queue()))
        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(edit, stretch=1)
        hb.addWidget(b)
        box = QWidget()
        box.setLayout(hb)
        return box

    # ---------- 界面 ----------
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("正在调的图："))
        self.cb_kind = QComboBox()
        self.cb_kind.addItems([n for n, _ in KINDS])
        self.cb_kind.currentIndexChanged.connect(self._on_kind)
        top.addWidget(self.cb_kind, stretch=1)
        self.kind_display = QLabel(self.cb_kind.currentText())
        self.kind_display.hide()
        top.addWidget(self.kind_display, stretch=1)
        lay.addLayout(top)

        tabs = QTabWidget()
        self.tabs = tabs          # 留个引用，外部（如截图/测试）能切页签
        lay.addWidget(tabs, stretch=1)

        # ---------- 画布 / 字体 ----------
        w1 = QWidget()
        f1 = QFormLayout(w1)
        self.cb_unit = QComboBox()
        for n, _ in UNIT_NAMES:
            self.cb_unit.addItem(n)
        self.cb_unit.currentIndexChanged.connect(self._on_unit)
        self.c_w = combo_edit(CANVAS_PRESETS["mm"], 180)
        self.c_h = combo_edit(CANVAS_PRESETS["mm"], 140)
        self.c_dpi = combo_edit(DPI_PRESETS, 600)
        self.ck_transparent = QCheckBox("图片背景透明")
        f1.addRow("画布单位", self.cb_unit)
        f1.addRow("画布宽", self.c_w)
        f1.addRow("画布高", self.c_h)
        f1.addRow("导出分辨率 dpi", self.c_dpi)
        f1.addRow(self.ck_transparent)

        gb_m = QGroupBox("绘图区到画布四边的距离（单位跟画布一致，0 = 默认）")
        gm = QGridLayout(gb_m)
        gm.setHorizontalSpacing(6)
        gm.setVerticalSpacing(6)
        self.c_ml = combo_edit(MARGIN_PRESETS, 22)
        self.c_mr = combo_edit(MARGIN_PRESETS, 4)
        self.c_mt = combo_edit(MARGIN_PRESETS, 4)
        self.c_mb = combo_edit(MARGIN_PRESETS, 16)
        # 四个框原来挤在一行，每个只剩 59 像素，"120"这种三位数看不全。
        # 改成每边一行，且给足宽度。
        for row, (lab, cmb, tip) in enumerate((
                ("左边距", self.c_ml, "绘图区到画布左边的距离"),
                ("右边距", self.c_mr, "绘图区到画布右边的距离"),
                ("上边距", self.c_mt, "绘图区到画布上边的距离"),
                ("下边距", self.c_mb, "绘图区到画布下边的距离"))):
            cmb.setMinimumWidth(132)
            cmb.setToolTip(tip + "\n留空或填 0 = 用软件默认边距")
            gm.addWidget(QLabel(lab), row, 0)
            gm.addWidget(cmb, row, 1)
        self.b_mreset = QPushButton("四个都归 0（用默认边距）")
        self.b_mreset.clicked.connect(
            lambda: [c.setCurrentText("0") for c in
                     (self.c_ml, self.c_mr, self.c_mt, self.c_mb)])
        gm.addWidget(self.b_mreset, 4, 0, 1, 2)
        gm.setColumnStretch(1, 1)
        f1.addRow(gb_m)

        self.c_font = combo_edit(FONT_WEST, "Arial")
        self.c_cjk = combo_edit(FONT_CJK, "SimSun")
        self.c_f_label = combo_edit(SIZE_PRESETS, 14)
        self.c_f_tick = combo_edit(SIZE_PRESETS, 14)
        self.c_f_leg = combo_edit(SIZE_PRESETS, 14)
        f1.addRow("西文字体", self.c_font)
        f1.addRow("中文字体", self.c_cjk)
        f1.addRow("轴标题字号", self.c_f_label)
        f1.addRow("刻度字号", self.c_f_tick)
        f1.addRow("图例字号", self.c_f_leg)

        gb_sup = QGroupBox("上下标（按字号等比缩放 + 偏移，字形与正文一致）")
        gs = QFormLayout(gb_sup)
        self.c_sup_ratio = combo_edit(
            [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.68, 0.7, 0.75, 0.8, 0.9],
            0.68)
        self.c_sup_rise = combo_edit(
            [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6], 0.4)
        self.c_sup_drop = combo_edit(
            [0.05, 0.1, 0.15, 0.18, 0.2, 0.25, 0.3, 0.4, 0.5], 0.18)
        gs.addRow("上下标字号比例", self.c_sup_ratio)
        gs.addRow("上标抬高（×字号）", self.c_sup_rise)
        gs.addRow("下标下压（×字号）", self.c_sup_drop)
        # 全局一改，轴标题编辑器里的预览也要跟着变（整张图统一）
        for _w in (self.c_sup_ratio, self.c_sup_rise, self.c_sup_drop):
            _w.currentTextChanged.connect(self._sync_mt_editors)
        tip = QLabel("写法：上标 x^{-1} 或 x^-1；"
                     "下标 Fe_{3}O_{4} 或 F_3。\n"
                     "不用 $ 符号了，直接写在文字里。\n"
                     "轴标题、图例、文本框都吃这里的比例和偏移。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        gs.addRow(tip)
        f1.addRow(gb_sup)
        tabs.addTab(self._scroll(w1), "画布/字体")

        # ---------- 线条 / 配色 ----------
        w2 = QWidget()
        f2 = QFormLayout(w2)
        self.c_lw = combo_edit(LW_PRESETS, 1.8)
        self.c_mk = combo_edit([0, 2, 3, 4, 5, 6, 8, 10, 12], 5)
        self.cb_ls = QComboBox()
        self.cb_ls.addItems(eclab.LINE_STYLE_NAMES)
        self.cb_ls.setToolTip("曲线线型：虚线族都给了，长短点划线按比例排，\n"
                              "改线宽时疏密不会乱。")
        self.cb_ls.currentIndexChanged.connect(self._refresh_marker)
        self.ls_prev = 线型预览()
        self.ls_prev.setFixedHeight(22)
        self.ls_prev.setMinimumWidth(150)
        self.cb_ls.currentIndexChanged.connect(
            lambda _i: self.ls_prev.set_style(
                self.cb_ls.currentText(), num_val(self.c_lw, float, 1.8)))
        hb_ls = QHBoxLayout()
        hb_ls.setContentsMargins(0, 0, 0, 0)
        hb_ls.addWidget(self.cb_ls, stretch=1)
        hb_ls.addWidget(self.ls_prev)
        self.c_lw.currentTextChanged.connect(
            lambda _t: self.ls_prev.set_style(
                self.cb_ls.currentText(), num_val(self.c_lw, float, 1.8)))
        f2.addRow("线宽", self.c_lw)
        f2.addRow("线型", hb_ls)
        f2.addRow("曲线标记大小", self.c_mk)
        self.cb_pal = QComboBox()
        self.cb_pal.addItems(["（跟图上现有配色）"] + list(PALETTES.keys()))
        self.cb_pal.currentTextChanged.connect(self._on_palette)
        self.ed_colors = QLineEdit()
        self.ed_colors.setPlaceholderText("#1F6E5A, #38699E, #A63E76 …")
        f2.addRow("配色方案", self.cb_pal)
        # 色块条：一眼看清这套配色长什么样，比一串 HEX 直观
        self.lab_swatch = 色条预览()
        self.lab_swatch.setMinimumWidth(160)
        f2.addRow("当前配色", self.lab_swatch)
        f2.addRow("颜色列表", self.ed_colors)
        self.ed_colors.textChanged.connect(self._refresh_swatch)
        hb2 = QHBoxLayout()
        b_ps = QPushButton("保存配色…")
        b_ps.setToolTip("存进我的配色（固定目录，不用选保存位置）")
        b_ps.clicked.connect(self._save_palette)
        b_pk = QPushButton("调色盘…")
        b_pk.setToolTip("标准色 / RGB / 滑块 三种方式选单个颜色")
        b_pk.clicked.connect(lambda: pick_color(
            self.ed_colors, self, self.styles[self.cur].get("colors")))
        for b in (b_ps, b_pk):
            hb2.addWidget(b)
        hb2.addStretch(1)
        f2.addRow(hb2)
        self.ck_grid = QCheckBox("显示网格")
        self.cb_gridsty = QComboBox()
        self.cb_gridsty.addItems(["-", "--", ":", "-."])
        self.c_gridw = combo_edit([0.3, 0.5, 0.6, 0.8, 1.0, 1.5], 0.6)
        self.c_gridal = combo_edit([0.2, 0.3, 0.4, 0.5, 0.7], 0.4)
        self.ed_gridcol = QLineEdit("#999999")
        w_gridcol = self._color_row(self.ed_gridcol)
        f2.addRow(self.ck_grid)
        f2.addRow("网格线型", self.cb_gridsty)
        f2.addRow("网格粗细", self.c_gridw)
        f2.addRow("网格透明度", self.c_gridal)
        f2.addRow("网格颜色", w_gridcol)
        # 不勾"显示网格"就把四个设置项收起来（跟图例边框一个做法）
        self._grid_rows = [f2.labelForField(w) for w in
                           (self.cb_gridsty, self.c_gridw,
                            self.c_gridal, w_gridcol)]
        self.ck_grid.toggled.connect(self._sync_grid_rows)
        self._sync_grid_rows()
        tabs.addTab(self._scroll(w2), "线条/配色")

        # ---------- 数据点 ----------
        ws = QWidget()
        sv = QVBoxLayout(ws)

        # 配色模式：统一更改 vs 组独立
        # 单独框成一组、字加粗、圆点放大 —— 原来两个小圆点太不起眼
        gb_mode = QGroupBox("配色模式（二选一）")
        mode_row = QHBoxLayout(gb_mode)
        self.rb_unified = QRadioButton("统一更改（推荐）")
        self.rb_unified.setToolTip(
            "所有数据点用同一套设置；\n"
            "多种颜色时自动按配色方案循环匹配；\n"
            "一种颜色时统一使用")
        self.rb_unified.setChecked(True)
        self.rb_indep = QRadioButton("组独立（逐点配色）")
        self.rb_indep.setToolTip(
            "每个数据点单独配色，\n"
            "下面的逐点配色表可用")
        self.rb_unified.toggled.connect(self._on_scatter_mode)
        for rb in (self.rb_unified, self.rb_indep):
            rb.setStyleSheet(
                "QRadioButton{ font-size:13px; font-weight:600;"
                " padding:5px 12px; }"
                "QRadioButton::indicator{ width:16px; height:16px; }")
            mode_row.addWidget(rb)
        mode_row.addStretch(1)
        sv.addWidget(gb_mode)

        self.mk_prev = MarkerPreview()
        sv.addWidget(self.mk_prev)
        fs = QFormLayout()
        self.cb_marker = QComboBox()
        self.cb_marker.addItems(["圆", "正方形", "三角形", "倒三角", "菱形",
                                 "五边形", "五角星", "六边形", "八边形"])
        self.cb_marker.currentTextChanged.connect(self._refresh_marker)
        self.cb_fill = QComboBox()
        self.cb_fill.addItems(["实心", "空心", "立体"])
        self.cb_fill.currentTextChanged.connect(self._refresh_marker)
        self.cb_facecol = 色块按钮(self, "", allow_empty=True,
                                   empty_text="填充色 跟随线条")
        self.cb_edgecol = 色块按钮(self, "", allow_empty=True,
                                   empty_text="边线色 跟随线条")
        self.cb_vcol = 色块按钮(self, "", allow_empty=True,
                                empty_text="竖线色 跟随线条")
        for b in (self.cb_facecol, self.cb_edgecol, self.cb_vcol):
            b._after = lambda _c: self._refresh_marker()
        self.c_edgew = combo_edit([0.5, 0.8, 1.0, 1.2, 1.5, 2.0], 1.2)
        self.c_psize = combo_edit([4, 6, 8, 10, 12, 14, 16, 18], 8)
        fs.addRow("点的形状", self.cb_marker)
        fs.addRow("填充方式", self.cb_fill)
        fs.addRow("填充色（空=跟线）", self.cb_facecol)
        fs.addRow("边线色（空=跟线）", self.cb_edgecol)
        fs.addRow("边线粗细", self.c_edgew)
        fs.addRow("点的大小", self.c_psize)
        self.ck_vline = QCheckBox("画垂直线（0 到数据点）")
        self.c_vw = combo_edit([0.5, 0.8, 1.0, 1.2, 1.5, 1.8, 2.5], 1.8)
        self.cb_vstyle = QComboBox()
        self.cb_vstyle.addItems(["-", "--", ":", "-."])
        fs.addRow(self.ck_vline)
        fs.addRow("垂直线颜色（空=跟线）", self.cb_vcol)
        fs.addRow("垂直线粗细", self.c_vw)
        fs.addRow("垂直线线型", self.cb_vstyle)
        sv.addLayout(fs)
        sv.addSpacing(8)
        self.gb_point = QGroupBox("每个数据点单独配色（组独立模式下可用）")
        gpv = QVBoxLayout(self.gb_point)
        self.pt_table = 逐点配色表(self, on_change=self._queue)
        gpv.addWidget(self.pt_table)
        sv.addWidget(self.gb_point)
        sv.addStretch(1)
        self.idx_scatter = tabs.addTab(self._scroll(ws), "数据点")
        self._on_scatter_mode()   # 初始化：统一模式 → 逐点配色禁用

        # ---------- 刻度 / 轴 ----------
        w3 = QWidget()
        f3 = QFormLayout(w3)
        gbcat = QGroupBox("类别轴")
        gc = QGridLayout(gbcat)
        # X、Y 分别启用：勾选 = 按类别排列（适合 2/5/10/20/50 这种
        # 不均匀刻度），不勾选 = 按数值大小正常排列。说明放悬浮提示里。
        self.ck_catx = QCheckBox("启用 X 轴类别")
        self.ck_catx.setToolTip(
            "勾选：把横轴按「类别」均匀排开，适合扫速/电流密度这类"
            "不均匀间隔的取值（2/5/10/20/50…）。\n"
            "不勾选：X 轴按数值大小正常排列（间隔不等时点会挤在一起）。")
        self.ck_catx.toggled.connect(self._sync_cat_edit)
        self.ck_caty = QCheckBox("启用 Y 轴类别")
        self.ck_caty.setToolTip(
            "勾选：把纵轴按「类别」均匀排开。\n"
            "不勾选：Y 轴按数值大小正常排列。")
        self.ck_caty.toggled.connect(self._sync_cat_edit)
        self.ed_catx = QLineEdit()
        self.ed_catx.setPlaceholderText("类别文字，逗号分隔；留空用原数值")
        self.ed_caty = QLineEdit()
        self.ed_caty.setPlaceholderText("类别文字，逗号分隔；留空用原数值")
        gc.addWidget(self.ck_catx, 0, 0)
        gc.addWidget(QLabel("X 轴类别文字"), 0, 1)
        gc.addWidget(self.ed_catx, 0, 2)
        gc.addWidget(self.ck_caty, 1, 0)
        gc.addWidget(QLabel("Y 轴类别文字"), 1, 1)
        gc.addWidget(self.ed_caty, 1, 2)
        f3.addRow(gbcat)

        gb = QGroupBox("四条边刻度（默认只显示下轴与左轴）")
        gl = QGridLayout(gb)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(6)
        gl.setColumnStretch(0, 0)
        for j in (1, 2, 3):
            gl.setColumnStretch(j, 1)
        self.sides = {}
        SIDE_NAMES = (("bottom", "下轴"), ("top", "上轴"),
                      ("left", "左轴"), ("right", "右轴"))
        for i, (side, nm) in enumerate(SIDE_NAMES):
            lab = QLabel(nm)
            lab.setMinimumWidth(34)
            gl.addWidget(lab, i, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
            row = {}
            # 每格都带文字，挤在一起也认得出是哪一项
            for j, (key, txt) in enumerate((("major", "主"),
                                            ("minor", "副"),
                                            ("labels", "字"))):
                ck = QCheckBox(txt)
                ck.setToolTip({"major": "主刻度线与主刻度数字",
                               "minor": "副刻度线（每主刻度之间那几根短的）",
                               "labels": "这一边要不要显示刻度数字"}[key])
                ck.setChecked(side in ("bottom", "left"))
                gl.addWidget(ck, i, j + 1)
                row[key] = ck
            self.sides[side] = row
        gl.setRowStretch(len(SIDE_NAMES), 1)
        f3.addRow(gb)
        # 图例式的对照说明，省得看不出"主/副/字"是什么
        tip_side = QLabel("主 = 主刻度线　副 = 副刻度线　字 = 刻度数字\n"
                          "勾哪几项就显示哪几项，Origin 风格一般只勾下轴和左轴")
        tip_side.setObjectName("hint")
        tip_side.setWordWrap(True)
        f3.addRow(tip_side)
        self.c_ticklen = combo_edit([2, 3, 4, 5, 6, 8, 10], 5)
        self.c_ticklen_min = combo_edit([1, 2, 3, 4, 5], 3)
        self.c_tickw = combo_edit([0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0], 0)
        self.c_axlw = combo_edit([0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5], 1.2)
        self.cb_tickdir = QComboBox()
        self.cb_tickdir.addItems(["刻度朝内 (in)", "刻度朝外 (out)"])
        self.c_ticklab = combo_edit([0] + SIZE_PRESETS, 0)
        f3.addRow("主刻度线长度", self.c_ticklen)
        f3.addRow("副刻度线长度", self.c_ticklen_min)
        f3.addRow("刻度线粗细（0=跟轴线）", self.c_tickw)
        f3.addRow("轴线粗细", self.c_axlw)
        f3.addRow("刻度方向", self.cb_tickdir)
        f3.addRow("刻度文字字号（0=跟随）", self.c_ticklab)
        self.c_xstep = combo_edit([0, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50,
                                   100], 0)
        self.c_ystep = combo_edit([0, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50,
                                   100], 0)
        f3.addRow("X 主刻度步长（0=自动）", self.c_xstep)
        f3.addRow("Y 主刻度步长（0=自动）", self.c_ystep)

        gb2 = QGroupBox("坐标轴范围（留空 = 自动；填了数值就锁死，"
                        "改配色也不会被改回去）")
        g2 = QGridLayout(gb2)
        self.ed_xmin = QLineEdit()
        self.ed_xmax = QLineEdit()
        self.ed_ymin = QLineEdit()
        self.ed_ymax = QLineEdit()
        for e in (self.ed_xmin, self.ed_xmax,
                  self.ed_ymin, self.ed_ymax):
            e.setPlaceholderText("自动")
        g2.addWidget(QLabel("X 最小值"), 0, 0)
        g2.addWidget(self.ed_xmin, 0, 1)
        g2.addWidget(QLabel("X 最大值"), 0, 2)
        g2.addWidget(self.ed_xmax, 0, 3)
        g2.addWidget(QLabel("Y 最小值"), 1, 0)
        g2.addWidget(self.ed_ymin, 1, 1)
        g2.addWidget(QLabel("Y 最大值"), 1, 2)
        g2.addWidget(self.ed_ymax, 1, 3)
        b_clear = QPushButton("清空这四个框（恢复自动）")
        b_clear.clicked.connect(self._clear_limits)
        g2.addWidget(b_clear, 2, 0, 1, 4)
        f3.addRow(gb2)
        tip2 = QLabel("提示：先用左下角「框选放大」把范围调好，"
                      "再点「把当前范围填到设置里」，"
                      "范围就固定了，之后随便改配色都不会变回去。")
        tip2.setObjectName("hint")
        tip2.setWordWrap(True)
        f3.addRow(tip2)
        f3.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        f3.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f3.setRowWrapPolicy(QFormLayout.DontWrapRows)
        tabs.addTab(self._scroll(w3), "刻度/轴")

        # ---------- 轴标题（单独一页：X/Y 各一份，互不影响）----------
        wt = QWidget()
        vt = QVBoxLayout(wt)
        vt.setContentsMargins(6, 6, 6, 6)
        tip0 = QLabel(
            "X 轴和 Y 轴各改各的，互不影响。改完切到出图预览看整体效果。")
        tip0.setObjectName("hint")
        tip0.setWordWrap(True)
        vt.addWidget(tip0)
        self.gb_tx = QGroupBox("X 轴标题（横排）")
        vx = QVBoxLayout(self.gb_tx)
        self.ed_x = 轴标题编辑(self, "x", "X")
        vx.addWidget(self.ed_x)
        vt.addWidget(self.gb_tx)
        self.gb_ty = QGroupBox("Y 轴标题（竖排）")
        vy = QVBoxLayout(self.gb_ty)
        self.ed_y = 轴标题编辑(self, "y", "Y")
        vy.addWidget(self.ed_y)
        vt.addWidget(self.gb_ty)
        vt.addStretch(1)
        tabs.addTab(self._scroll(wt), "轴标题")

        # ---------- 图例 ----------
        w4 = QWidget()
        v4 = QVBoxLayout(w4)
        f4 = QFormLayout()
        self.ck_legshow = QCheckBox("显示图例")
        self.ck_legframe = QCheckBox("图例带边框")
        self.cb_legloc = QComboBox()
        self.cb_legloc.addItems([n for n, _ in LEGEND_LOCS])
        self.c_legcol = combo_edit([1, 2, 3, 4], 1)
        self.c_legbw = combo_edit([0.5, 0.8, 1.0, 1.5, 2.0], 0.8)
        self.c_handlen = combo_edit([1.0, 1.5, 2.0, 2.5, 3.0, 4.0], 2.0)
        self.c_handleh = combo_edit([0.5, 0.7, 1.0, 1.5, 2.0], 0.7)
        self.c_htpad = combo_edit([0.3, 0.5, 0.8, 1.0, 1.5, 2.0], 0.8)
        self.c_lspace = combo_edit([0.2, 0.3, 0.5, 0.8, 1.0], 0.5)
        self.c_cspace = combo_edit([1.0, 1.5, 2.0, 2.5, 3.0], 2.0)
        f4.addRow(self.ck_legshow)
        f4.addRow("位置", self.cb_legloc)
        # 自定义锚点：图例的某个角对齐到画布任意点（精确摆放）
        self.ck_leganchor = QCheckBox("自定义位置（下面填画布坐标 0~1）")
        self.ck_leganchor.setToolTip(
            "勾上后忽略上面的「位置」，用精确坐标摆图例：\n"
            "图例的「对齐角」放到画布的 (X, Y) 点上。\n"
            "右上角 = X 1.0 / Y 1.0；左上 = 0.0 / 1.0；\n"
            "右下 = 1.0 / 0.0；左下 = 0.0 / 0.0；正中 = 0.5 / 0.5。\n"
            "数值可以超过 1 或为负，把图例放到画布外。")
        self.ck_leganchor.toggled.connect(self._sync_leg_anchor)
        self.cb_legcorner = QComboBox()
        self.cb_legcorner.addItems(["右上角", "左上角", "右下角", "左下角",
                                    "正中间"])
        self.ed_legax = combo_edit([0.0, 0.25, 0.5, 0.75, 1.0], 1.0)
        self.ed_legay = combo_edit([0.0, 0.25, 0.5, 0.75, 1.0], 1.0)
        self.w_leganchor = QWidget()
        fa = QFormLayout(self.w_leganchor)
        fa.setContentsMargins(16, 0, 0, 0)
        fa.addRow("图例对齐角", self.cb_legcorner)
        fa.addRow("画布 X 坐标", self.ed_legax)
        fa.addRow("画布 Y 坐标", self.ed_legay)
        f4.addRow(self.ck_leganchor)
        f4.addRow(self.w_leganchor)
        f4.addRow("列数", self.c_legcol)
        # 富文本开关：关掉后图例里的 ^{} / _{} 原样显示
        self.ck_legrich = QCheckBox("富文本（解析 ^{上标} / _{下标}）")
        self.ck_legrich.setChecked(True)
        self.ck_legrich.setToolTip(
            "勾上：图例里的上下标按缩放比渲染，字形跟正文一致；\n"
            "取消：^{} / _{} 原样显示成一串普通字符。")
        f4.addRow(self.ck_legrich)
        f4.addRow(self.ck_legframe)
        # 边框粗细只在勾了"带边框"后才出现 —— 标签和输入框要一起收，
        # 光把输入框藏起来会剩一个孤零零的"边框粗细"字样在外面。
        self.w_legbw = QWidget()
        _hb = QHBoxLayout(self.w_legbw)
        _hb.setContentsMargins(0, 0, 0, 0)
        _hb.addWidget(QLabel("边框粗细"))
        _hb.addWidget(self.c_legbw, stretch=1)
        f4.addRow(self.w_legbw)
        self.ck_legframe.toggled.connect(self._sync_leg_frame)
        self._sync_leg_frame()
        f4.addRow("示意图宽度", self.c_handlen)
        f4.addRow("示意图大小", self.c_handleh)
        f4.addRow("示意图与文字间距", self.c_htpad)
        f4.addRow("行间距", self.c_lspace)
        f4.addRow("列间距", self.c_cspace)
        v4.addLayout(f4)
        lab_leg = QLabel("图例文字（整张图一起改）：上标写 ^{-1}，下标写 _{x}；"
                         "例：扫描速率 50 mV s^{-1}、Fe_{3}O_{4}。"
                         "清空某行 = 用默认文字")
        lab_leg.setObjectName("hint")
        lab_leg.setWordWrap(True)
        v4.addWidget(lab_leg)
        self.tb_leg = QTableWidget(0, 3)
        self.tb_leg.setHorizontalHeaderLabels(["#", "图例文字", "颜色"])
        self.tb_leg.setToolTip(
            "点「图例文字」那列随时改，改完回车立刻生效；\n"
            "上标 ^{-1}、下标 _{x}，例：A g^{-1}、Fe_{3}O_{4}\n"
            "点「颜色」那列换这条曲线用的颜色")
        self.tb_leg.verticalHeader().setVisible(False)
        self.tb_leg.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.tb_leg.setColumnWidth(0, 34)
        self.tb_leg.setColumnWidth(2, 56)
        # 单击即可编辑文字（不用双击）
        self.tb_leg.setEditTriggers(
            QAbstractItemView.CurrentChanged
            | QAbstractItemView.EditKeyPressed)
        self.tb_leg.itemChanged.connect(self._queue)
        # 点文字列进编辑、点颜色列弹调色盘
        self.tb_leg.cellClicked.connect(self._on_leg_cell_clicked)
        v4.addWidget(self.tb_leg, stretch=1)
        tabs.addTab(w4, "图例")

        # ---------- 文本框 ----------
        w5 = QWidget()
        v5 = QVBoxLayout(w5)
        lab5 = QLabel(
            "在图上加自己的文字（可多个）。坐标 0~1：X=0 左边缘，X=1 右边缘；"
            "Y=1 顶部，Y=0 底部。坐标用 ▲▼ 微调、范围就是 0~1，不再用下拉框。"
            "支持上下标和任意角度旋转。")
        lab5.setWordWrap(True)
        v5.addWidget(lab5)
        self.tb_texts = QTableWidget(0, 10)
        self.tb_texts.setHorizontalHeaderLabels(
            ["#", "文字内容", "X", "Y", "字号", "颜色", "水平位置", "带边框",
             "富文本", "旋转°"])
        # 列宽：除文字内容外都给固定宽度，全部加起来不超过面板宽度，
        # 所以永远不出现横向滚动条 —— 序号列也就不会被推出去看不见
        self.tb_texts.setColumnWidth(0, 34)      # 序号：冻住不动
        self.tb_texts.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)             # 文字内容吃掉剩余宽度
        for j, wdt in enumerate((58, 58, 52, 84, 66, 56, 50, 54)):
            self.tb_texts.setColumnWidth(j + 2, wdt)
        self.tb_texts.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Interactive)
        self.tb_texts.horizontalHeader().setMinimumSectionSize(28)
        self.tb_texts.horizontalHeader().setStretchLastSection(False)
        self.tb_texts.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tb_texts.setToolTip(
            "第 1 列是序号，横向拉不动也关不掉滚动条，改哪一行一目了然。\n"
            "X / Y 用 ▲▼ 按 0.01 微调，也可以点数字直接改。\n"
            "文字内容里可写上下标：x^{-1}、F_{3}O_{4}。")
        self.tb_texts.cellChanged.connect(self._queue)
        v5.addWidget(self.tb_texts, stretch=1)
        hb5 = QHBoxLayout()
        b_add = QPushButton("添加一条")
        b_add.clicked.connect(lambda: self._add_text_row())
        b_del = QPushButton("删除选中行")
        b_del.clicked.connect(self._del_text_rows)
        hb5.addWidget(b_add)
        hb5.addWidget(b_del)
        hb5.addStretch(1)
        v5.addLayout(hb5)
        tabs.addTab(self._scroll(w5), "文本框")

        # ---------- EIS ----------
        w6 = QWidget()
        f6 = QFormLayout(w6)
        self.ck_equal = QCheckBox("横纵坐标等比（看半圆圆润度）")
        self.c_ex = combo_edit([0, 10, 20, 50, 100, 200, 500, 1000], 0)
        self.c_ey = combo_edit([0, 10, 20, 50, 100, 200, 500, 1000], 0)
        self.ck_inset = QCheckBox("放大低频区（inset 子图）")
        f6.addRow(self.ck_equal)
        f6.addRow("Z' 轴最大（0=自动）", self.c_ex)
        f6.addRow("Z'' 轴最大（0=自动）", self.c_ey)
        f6.addRow(self.ck_inset)
        # EIS 相关选项只在"正在调 EIS 图"时才出现 —— 别的时候这几个框
        # 放在页签里毫无意义（大部分人根本不处理 EIS）
        self.idx_eis = tabs.addTab(self._scroll(w6), "EIS")
        self._hook_all()
        self._refresh_marker()
        self._sync_eis_tab()
        self._sync_scatter_tab()

    # 用散点的图类型：比电容图 + EIS 原始数据
    _SCATTER_KINDS = {"cv_cap", "gcd_cap", "EIS"}

    def _sync_scatter_tab(self):
        """按当前调的图决定数据点页签显示还是隐藏"""
        i = getattr(self, "idx_scatter", -1)
        if i < 0:
            return
        want = (self.cur in self._SCATTER_KINDS)
        tabs = self.tabs
        if want and tabs.isTabVisible(i) is False:
            tabs.setTabVisible(i, True)
        elif not want and tabs.isTabVisible(i):
            tabs.setTabVisible(i, False)
        if not want and tabs.currentIndex() == i:
            tabs.setCurrentIndex(0)

    def _sync_eis_tab(self):
        """按当前调的图决定EIS 页签显示还是隐藏"""
        i = getattr(self, "idx_eis", -1)
        if i < 0:
            return
        want = (self.cur == "EIS")
        tabs = self.tabs
        if want and tabs.isTabVisible(i) is False:
            tabs.setTabVisible(i, True)
        elif not want and tabs.isTabVisible(i):
            tabs.setTabVisible(i, False)
        # 页签被隐藏时如果正停在它上面，自动跳回第一个
        if not want and tabs.currentIndex() == i:
            tabs.setCurrentIndex(0)

    def _hook_all(self):
        for name in dir(self):
            if name.startswith(("c_", "ed_", "ck_", "cb_", "tb_")):
                w = getattr(self, name)
                if isinstance(w, QComboBox):
                    w.currentTextChanged.connect(self._queue)
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.valueChanged.connect(self._queue)
                elif isinstance(w, QLineEdit):
                    w.textChanged.connect(self._queue)
                elif isinstance(w, QCheckBox):
                    w.stateChanged.connect(self._queue)

    def set_limits(self, x0, x1, y0, y1):
        """外部（图内工具条）把范围塞进来"""
        self.ed_xmin.setText(f"{x0:.6g}")
        self.ed_xmax.setText(f"{x1:.6g}")
        self.ed_ymin.setText(f"{y0:.6g}")
        self.ed_ymax.setText(f"{y1:.6g}")
        self._queue()

    def _clear_limits(self):
        for e in (self.ed_xmin, self.ed_xmax,
                  self.ed_ymin, self.ed_ymax):
            e.clear()
        self._queue()

    def _on_scatter_mode(self, *_):
        """统一更改 vs 组独立：统一下禁用逐点配色表"""
        unified = self.rb_unified.isChecked()
        self.gb_point.setEnabled(not unified)
        if unified:
            self.gb_point.setToolTip(
                "统一更改模式下逐点配色不可用。\n"
                "多种颜色时会自动按配色方案循环匹配")
        else:
            self.gb_point.setToolTip("逐点配色：每个数据点单独设置颜色")
        self._queue()

    def _refresh_marker(self, *a):
        face = self.cb_facecol.color()
        edge = self.cb_edgecol.color()
        col = face or edge or self._nth_color(0)
        self.mk_prev.set_style(MARKER_NAMES.get(self.cb_marker.currentText(),
                                                 "o"),
                               self.cb_fill.currentText(), face, edge, col)

    def _on_kind(self, i):
        if i >= 0:
            self.set_kind(KIND_CODES[i])

    def _on_unit(self, i):
        unit = UNIT_NAMES[i][1]
        presets = CANVAS_PRESETS.get(unit, CANVAS_PRESETS["mm"])
        # 换单位时把当前宽高按物理尺寸等值换算，别让人自己重填
        cur_w = num_val(self.c_w, float, 180)
        cur_h = num_val(self.c_h, float, 140)
        prev = getattr(self, "_last_unit", "mm")
        k_old = CANVAS_SCALE.get(prev, 1.0)
        k_new = CANVAS_SCALE.get(unit, 1.0)
        for combo, cur in ((self.c_w, cur_w), (self.c_h, cur_h)):
            newv = cur * k_old / k_new
            combo.clear()
            for p in presets:
                combo.addItem(str(p))
            combo.setCurrentText(f"{newv:g}")
        self._last_unit = unit
        self._queue()

    def _sync_cat_edit(self, *_):
        """X、Y 各自勾选后，对应类别文字框才可输入；不勾选禁用"""
        self.ed_catx.setEnabled(self.ck_catx.isChecked())
        self.ed_caty.setEnabled(self.ck_caty.isChecked())

    def _sync_leg_anchor(self, *_):
        """勾选自定义位置才显示坐标输入区，未勾选时收起避免误改"""
        self.w_leganchor.setVisible(self.ck_leganchor.isChecked())

    def _sync_leg_frame(self, *_):
        """没勾"图例带边框"就把边框粗细整行收掉（含标签）"""
        self.w_legbw.setVisible(self.ck_legframe.isChecked())

    def _sync_grid_rows(self, *_):
        """不勾"显示网格"就把线型/粗细/透明度/颜色四行收起来"""
        on = self.ck_grid.isChecked()
        for lab in getattr(self, "_grid_rows", []):
            if lab is not None:
                lab.setVisible(on)
        for w in (self.cb_gridsty, self.c_gridw, self.c_gridal,
                  self.ed_gridcol):
            w.setEnabled(on)

    def _on_leg_cell_clicked(self, row, col):
        """图例：点文字列直接进编辑（改完回车还能再点进来改），
        点颜色列弹调色盘改这条曲线用的颜色"""
        if col == 1:
            it = self.tb_leg.item(row, 1)
            if it is not None:
                self.tb_leg.setCurrentCell(row, 1)
                self.tb_leg.editItem(it)
            return
        if col != 2:
            return
        cur_color = self._nth_color(row)
        dlg = ColorPickerDialog(self, cur_color)
        if dlg.exec():
            new_color = dlg.picked
            colors = self._parse_colors()
            if row < len(colors):
                colors[row] = new_color
            else:
                while len(colors) <= row:
                    colors.append(new_color)
            self.ed_colors.setText(", ".join(colors))
            # 更新表格里的颜色块
            it = self.tb_leg.item(row, 2)
            if it:
                it.setIcon(color_icon(new_color))
            self._refresh_swatch()
            self._queue()

    def _on_palette(self, name):
        cols = PALETTES.get(name)
        if cols:
            self.ed_colors.setText(", ".join(cols))
            self._queue()

    def _sync_mt_editors(self, *_):
        """全局上下标参数 → 轴标题编辑器的预览（整张图统一用一套）"""
        try:
            kw = dict(sub_ratio=num_val(self.c_sup_ratio, float, 0.68),
                      rise=num_val(self.c_sup_rise, float, 0.40),
                      drop=num_val(self.c_sup_drop, float, 0.18))
        except Exception:
            return
        for ed in (getattr(self, "ed_x", None), getattr(self, "ed_y", None)):
            if ed is not None:
                ed.set_mt(**kw)

    def _refresh_swatch(self, *_):
        """把颜色列表画成一排色块，肉眼就能看出这套好不好看"""
        self.lab_swatch.set_colors(self._parse_colors())

    def _save_palette(self):
        """保存配色：只问名字，不选路径，固定存进我的配色"""
        cols = self._parse_colors()
        if not cols:
            QMessageBox.information(self, "还没颜色", "先选几个颜色再保存")
            return
        d, ok = QInputDialog.getText(
            self, "保存配色", "给这套配色起个名字（留空用时间命名）：",
            QLineEdit.Normal, time.strftime("配色 %m-%d %H:%M"))
        if not ok:
            return
        path = ecpal.save_palette(d.strip(), cols)
        if path:
            QMessageBox.information(
                self, "已保存",
                f"配色已存好（固定目录，不用选位置）：\n"
                f"{ecpal.PALETTE_DIR}\n\n"
                f"文件名：{os.path.basename(path)}\n"
                f"共 {len(cols)} 色，已记住。")
        self._queue()

    def _add_text_row(self, text="", x=0.5, y=0.9, size=12, color="#000000",
                      ha="center", frame="否", rich=True, rotation=0.0):
        r = self.tb_texts.rowCount()
        self.tb_texts.insertRow(r)
        # 第 0 列是序号：只读、内容居中，保证横向永远看不到它被推走
        it_no = QTableWidgetItem(str(r + 1))
        it_no.setFlags(Qt.ItemIsEnabled)        # 不可编辑
        it_no.setTextAlignment(Qt.AlignCenter)
        it_no.setToolTip("第 %d 条" % (r + 1))
        self.tb_texts.setItem(r, 0, it_no)
        self.tb_texts.setItem(r, 1, QTableWidgetItem(text))
        w_x = 坐标微调(self, x, "x")
        w_y = 坐标微调(self, y, "y")
        for col, w in ((2, w_x), (3, w_y)):
            w._after = lambda *_a: self._queue()
            self.tb_texts.setCellWidget(r, col, w)
        c_sz = combo_edit(SIZE_PRESETS, size)
        c_sz.setToolTip("字号（点）")
        c_sz.currentTextChanged.connect(self._queue)
        self.tb_texts.setCellWidget(r, 4, c_sz)
        cb_col = 色块按钮(self, color, allow_empty=True,
                          empty_text="跟线条")
        cb_col.setToolTip("这条文字的颜色，留空 = 跟线条颜色一致")
        cb_col._after = lambda _c: self._queue()
        self.tb_texts.setCellWidget(r, 5, cb_col)
        c_ha = QComboBox()
        c_ha.addItems(["left", "center", "right"])
        c_ha.setCurrentText(ha)
        c_ha.setToolTip("以文字的左/中/右对齐放在那个坐标上")
        c_ha.currentIndexChanged.connect(self._queue)
        self.tb_texts.setCellWidget(r, 6, c_ha)
        c_fr = QComboBox()
        c_fr.addItems(["否", "是"])
        c_fr.setCurrentText(frame)
        c_fr.setToolTip("是 = 给这段文字加一个白底圆角框")
        c_fr.currentIndexChanged.connect(self._queue)
        self.tb_texts.setCellWidget(r, 7, c_fr)
        # 富文本开关：关掉后这条文字里的 ^{} / _{} 原样显示
        w_rich = QWidget()
        hb = QHBoxLayout(w_rich)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setAlignment(Qt.AlignCenter)
        ck = QCheckBox()
        ck.setChecked(bool(rich))
        ck.setToolTip("勾上：按上下标渲染（大小/偏移在「画布/字体」页调）；"
                      "取消：^{} / _{} 原样显示")
        ck.stateChanged.connect(self._queue)
        hb.addWidget(ck)
        self.tb_texts.setCellWidget(r, 8, w_rich)
        # 旋转角度（度，逆时针）：0=正常横排；90=竖排（跟 Y 轴标题同向）。
        # 旋转后抬高/下压/左右微调都跟着文字框一起转
        c_rot = combo_edit([0, 30, 45, 60, 90, 135, 180, 225, 270, 315],
                           float(rotation or 0))
        c_rot.setToolTip("逆时针旋转角度（度）。\n"
                         "抬高/下压/左右微调都跟着文字框一起转：\n"
                         "比如 90° 时「抬高」是往左、「左右微调」是往上。")
        c_rot.currentTextChanged.connect(self._queue)
        self.tb_texts.setCellWidget(r, 9, c_rot)
        self._queue()

    def _sync_text_rownos(self):
        """序号列跟着行号走（增删行后调用）"""
        for r in range(self.tb_texts.rowCount()):
            it = self.tb_texts.item(r, 0)
            if it is not None:
                it.setText(str(r + 1))

    def _text_rich(self, r):
        """读第 r 行文本框的「富文本」勾选状态"""
        w = self.tb_texts.cellWidget(r, 8)
        if w is None:
            return True
        ck = w.findChild(QCheckBox)
        return True if ck is None else ck.isChecked()

    def _del_text_rows(self):
        for r in sorted({i.row() for i in self.tb_texts.selectedIndexes()},
                        reverse=True):
            self.tb_texts.removeRow(r)
        self._sync_text_rownos()
        self._queue()

    def _parse_colors(self):
        out = []
        for tok in self.ed_colors.text().replace("，", ",").split(","):
            t = tok.strip()
            if not t:
                continue
            if not t.startswith("#"):
                t = "#" + t
            if len(t) in (4, 7):
                out.append(t)
        return out or list(eclab.DEFAULT_STYLE["colors"])

    # ---------- 填充 / 读取 ----------
    def _fill(self, st, out):
        unit = st["canvas"].get("unit", "inch")
        self.cb_unit.setCurrentIndex(
            [u for _, u in UNIT_NAMES].index(unit)
            if unit in [u for _, u in UNIT_NAMES] else 0)
        self.c_w.setCurrentText(str(st["canvas"]["width"]))
        self.c_h.setCurrentText(str(st["canvas"]["height"]))
        self.c_dpi.setCurrentText(str(out.get("dpi", st["canvas"]["dpi"])))
        self.ck_transparent.setChecked(
            bool(st["canvas"].get("transparent", False)))
        self.c_font.setCurrentText(st["font"]["family"])
        self.c_cjk.setCurrentText(st["font"]["cjk"])
        self.c_f_label.setCurrentText(str(st["font"]["label"]))
        self.c_f_tick.setCurrentText(str(st["font"]["tick"]))
        self.c_f_leg.setCurrentText(str(st["font"]["legend"]))
        mg = st["canvas"].get("margin") or {}
        self.c_ml.setCurrentText(_num_str(mg.get("left", 0)))
        self.c_mr.setCurrentText(_num_str(mg.get("right", 0)))
        self.c_mt.setCurrentText(_num_str(mg.get("top", 0)))
        self.c_mb.setCurrentText(_num_str(mg.get("bottom", 0)))
        mt = st.get("mathtext") or {}
        self.c_sup_ratio.setCurrentText(str(mt.get("sub_ratio", 0.68)))
        self.c_sup_rise.setCurrentText(str(mt.get("rise", 0.4)))
        self.c_sup_drop.setCurrentText(str(mt.get("drop", 0.18)))
        self._sync_mt_editors()
        self.c_lw.setCurrentText(str(st["line"]["width"]))
        self.c_mk.setCurrentText(str(st["line"]["marker"]))
        _ls = str(st["line"].get("linestyle", "实线"))
        if _ls not in eclab.LINE_STYLE_NAMES:
            _ls = "实线"
        self.cb_ls.setCurrentText(_ls)
        self.ls_prev.set_style(_ls, num_val(self.c_lw, float, 1.8))
        self.ed_colors.setText(", ".join(st["colors"]))
        self._refresh_swatch()
        self.ed_colors.textChanged.connect(self._refresh_marker)

        g = st.get("grid") or {}
        self.ck_grid.setChecked(bool(g.get("show", False)))
        self.cb_gridsty.setCurrentText(str(g.get("style", "--")))
        self.c_gridw.setCurrentText(_num_str(g.get("width", 0.6)))
        self.c_gridal.setCurrentText(_num_str(g.get("alpha", 0.4)))
        self.ed_gridcol.setText(g.get("color", "#999999"))
        self._sync_grid_rows()

        sc = st.get("scatter", {})
        # 配色模式（统一/组独立）
        mode = sc.get("mode", "unified")
        self.rb_unified.setChecked(mode != "independent")
        self.rb_indep.setChecked(mode == "independent")
        rev = {v: k for k, v in MARKER_NAMES.items()}
        self.cb_marker.setCurrentText(rev.get(sc.get("marker", "o"), "圆"))
        self.cb_fill.setCurrentText(sc.get("fill", "实心"))
        self.cb_facecol.set_color(sc.get("face_color", ""))
        self.cb_edgecol.set_color(sc.get("edge_color", ""))
        self.c_edgew.setCurrentText(str(sc.get("edge_width", 1.2)))
        self.c_psize.setCurrentText(str(sc.get("size", 8)))
        self.ck_vline.setChecked(bool(sc.get("vline", True)))
        self.cb_vcol.set_color(sc.get("vline_color", ""))
        self.c_vw.setCurrentText(str(sc.get("vline_width", 1.8)))
        self.cb_vstyle.setCurrentText(sc.get("vline_style", "-"))
        self.pt_table.set_rows(self._point_labels(),
                               sc.get("face_colors") or [],
                               sc.get("vline_colors") or [],
                               sc.get("edge_colors") or [])

        a = st["axis"]
        sides = a.get("sides") or {}
        for side, row in self.sides.items():
            cfg = sides.get(side) or {}
            row["major"].setChecked(cfg.get("major", side in ("bottom",
                                                              "left")))
            row["minor"].setChecked(cfg.get("minor", side in ("bottom",
                                                              "left")))
            row["labels"].setChecked(cfg.get("labels", side in ("bottom",
                                                                "left")))
        self.c_ticklen.setCurrentText(str(a.get("tick_len", 5)))
        self.c_ticklen_min.setCurrentText(str(a.get("tick_len_minor", 3)))
        self.c_tickw.setCurrentText(str(a.get("tick_width", 0)))
        self.c_axlw.setCurrentText(str(a.get("linewidth", 1.2)))
        self.cb_tickdir.setCurrentIndex(1 if a.get("tick_dir") == "out" else 0)
        self.c_ticklab.setCurrentText(str(a.get("tick_label_size", 0)))
        tc = a.get("title_cfg") or {}
        # 标题文字：优先用这张图"图上真实在画的"标题（自动填扫描结果），
        # 用户可以直接改；留空 = 真的不画。
        # 早先这里只查 default_titles 固定表，跟引擎实际画出来的那份
        # 各走各的 —— 一旦串图，框里和图上就两个字面不同的东西。
        dt_x, dt_y = eclab.default_titles(self.cur)
        if self._last_fig is not None:
            ax_t, ay_t = eclab.titles_on_figure(self._last_fig, self.cur)
            dt_x, dt_y = ax_t or dt_x, ay_t or dt_y
        ti = a.get("titles")
        tx = ti.get("x", dt_x) if isinstance(ti, dict) else dt_x
        ty = ti.get("y", dt_y) if isinstance(ti, dict) else dt_y
        tx = tx if tx is not None else dt_x
        ty = ty if ty is not None else dt_y
        # 记住这次"自动填"的值：用户没动过就不写进样式（见 _read），
        # 这样引擎那边始终用"图上真实在画的"那份，两边不会各说各话。
        self._auto_titles = (tx, ty)
        self.ed_x.set_values(tx,
                             a.get("title_size", {}).get("x", 0),
                             tc.get("x") or {})
        self.ed_y.set_values(ty,
                             a.get("title_size", {}).get("y", 0),
                             tc.get("y") or {})
        self.c_xstep.setCurrentText(str(a.get("x_major", 0)))
        self.c_ystep.setCurrentText(str(a.get("y_major", 0)))
        self.ed_xmin.setText(_lim_str(a.get("x_min")))
        self.ed_xmax.setText(_lim_str(a.get("x_max")))
        self.ed_ymin.setText(_lim_str(a.get("y_min")))
        self.ed_ymax.setText(_lim_str(a.get("y_max")))
        cat = a.get("categorical", {})
        self.ck_catx.setChecked(bool(cat.get("x")))
        self.ck_caty.setChecked(bool(cat.get("y")))
        self.ed_catx.setText(a.get("cat_labels", {}).get("x", ""))
        self.ed_caty.setText(a.get("cat_labels", {}).get("y", ""))
        self._sync_cat_edit()

        lg = st["legend"]
        self.ck_legshow.setChecked(lg.get("show", True))
        loc = lg.get("loc", "best")
        for name, code in LEGEND_LOCS:
            if code == loc:
                self.cb_legloc.setCurrentText(name)
                break
        anc = lg.get("anchor") or {}
        self.ck_leganchor.setChecked(bool(anc.get("on")))
        corner_rev = {"upper right": "右上角", "upper left": "左上角",
                      "lower right": "右下角", "lower left": "左下角",
                      "center": "正中间"}
        self.cb_legcorner.setCurrentText(
            corner_rev.get(anc.get("leg_corner", "upper right"), "右上角"))
        try:
            self.ed_legax.setCurrentText(str(float(anc.get("x", 1.0))))
            self.ed_legay.setCurrentText(str(float(anc.get("y", 1.0))))
        except (TypeError, ValueError):
            pass
        self._sync_leg_anchor()
        self._sync_leg_frame()
        self.c_legcol.setCurrentText(str(lg.get("ncol", 1)))
        self.ck_legrich.setChecked(lg.get("rich", True) is not False)
        self.ck_legframe.setChecked(lg.get("frameon", False))
        self.c_legbw.setCurrentText(str(lg.get("border_width", 0.8)))
        self.c_handlen.setCurrentText(str(lg.get("handle_length", 2.0)))
        self.c_handleh.setCurrentText(str(lg.get("handle_height", 0.7)))
        self.c_htpad.setCurrentText(str(lg.get("handle_textpad", 0.8)))
        self.c_lspace.setCurrentText(str(lg.get("label_spacing", 0.5)))
        self.c_cspace.setCurrentText(str(lg.get("column_spacing", 2.0)))
        self.tb_leg.blockSignals(True)
        self.tb_leg.setRowCount(0)
        for i, t in enumerate(lg.get("items") or []):
            r = self.tb_leg.rowCount()
            self.tb_leg.insertRow(r)
            self.tb_leg.setItem(r, 0, QTableWidgetItem(str(i + 1)))
            self.tb_leg.setItem(r, 1, QTableWidgetItem(str(t)))
            it = QTableWidgetItem("")
            it.setIcon(color_icon(self._nth_color(i)))
            self.tb_leg.setItem(r, 2, it)
        self.tb_leg.blockSignals(False)

        self.ck_equal.setChecked(st["eis"].get("equal_scale", True))
        self.c_ex.setCurrentText(str(st["eis"].get("x_max", 0)))
        self.c_ey.setCurrentText(str(st["eis"].get("y_max", 0)))
        self.ck_inset.setChecked(st["eis"].get("inset", False))

        self.tb_texts.setRowCount(0)
        for t in st.get("texts", []) or []:
            self._add_text_row(t.get("text", ""), t.get("x", 0.5),
                               t.get("y", 0.9), t.get("size", 12),
                               t.get("color", "#000000"),
                               t.get("ha", "center"),
                               "是" if t.get("frame") else "否",
                               t.get("rich", True) is not False,
                               t.get("rotation", 0) or 0)
        self._refresh_marker()

    def _read(self, st, out):
        st = json.loads(json.dumps(st))
        out = dict(out or {})
        st["canvas"]["unit"] = UNIT_NAMES[self.cb_unit.currentIndex()][1]
        st["canvas"]["width"] = num_val(self.c_w, float, 180)
        st["canvas"]["height"] = num_val(self.c_h, float, 140)
        st["canvas"]["transparent"] = self.ck_transparent.isChecked()
        st["canvas"]["margin"] = {
            "left": num_val(self.c_ml, float, 0),
            "right": num_val(self.c_mr, float, 0),
            "top": num_val(self.c_mt, float, 0),
            "bottom": num_val(self.c_mb, float, 0)}
        out["dpi"] = num_val(self.c_dpi, int, 600)
        st["font"]["family"] = self.c_font.currentText().strip() or "Arial"
        st["font"]["cjk"] = self.c_cjk.currentText().strip() or "SimSun"
        st["font"]["base"] = 14
        st["font"]["title"] = 14
        st["font"]["label"] = num_val(self.c_f_label, int, 14)
        st["font"]["tick"] = num_val(self.c_f_tick, int, 14)
        st["font"]["legend"] = num_val(self.c_f_leg, int, 14)
        st["mathtext"] = {
            "fontset": "custom", "rm": "", "it": "", "bf": "",
            "sub_ratio": num_val(self.c_sup_ratio, float, 0.68),
            "rise": num_val(self.c_sup_rise, float, 0.4),
            "drop": num_val(self.c_sup_drop, float, 0.18)}
        st["line"]["width"] = num_val(self.c_lw, float, 1.8)
        st["line"]["marker"] = num_val(self.c_mk, float, 5)
        st["line"]["linestyle"] = self.cb_ls.currentText() or "实线"
        st["grid"] = {
            "show": self.ck_grid.isChecked(),
            "style": self.cb_gridsty.currentText() or "--",
            "width": num_val(self.c_gridw, float, 0.6),
            "alpha": num_val(self.c_gridal, float, 0.4),
            "color": self.ed_gridcol.text().strip() or "#999999"}
        st["colors"] = self._parse_colors()
        pf, pv, pe = self.pt_table.values()

        st["scatter"] = {
            "mode": "independent" if self.rb_indep.isChecked() else "unified",
            "marker": MARKER_NAMES.get(self.cb_marker.currentText(), "o"),
            "fill": self.cb_fill.currentText(),
            "face_color": self.cb_facecol.color(),
            "edge_color": self.cb_edgecol.color(),
            "edge_width": num_val(self.c_edgew, float, 1.2),
            "size": num_val(self.c_psize, float, 8),
            "vline": self.ck_vline.isChecked(),
            "vline_color": self.cb_vcol.color(),
            "vline_width": num_val(self.c_vw, float, 1.8),
            "vline_style": self.cb_vstyle.currentText(),
            "vline_alpha": 1.0,
            # 逐点配色（留空的项在引擎里自动跟曲线色）
            "face_colors": pf,
            "vline_colors": pv,
            "edge_colors": pe,
        }

        a = st["axis"]
        a["sides"] = {side: {k: ck.isChecked() for k, ck in row.items()}
                      for side, row in self.sides.items()}
        a["tick_len"] = num_val(self.c_ticklen, float, 5)
        a["tick_len_minor"] = num_val(self.c_ticklen_min, float, 3)
        a["tick_width"] = num_val(self.c_tickw, float, 0)
        a["linewidth"] = num_val(self.c_axlw, float, 1.2)
        a["tick_dir"] = "out" if self.cb_tickdir.currentIndex() else "in"
        a["tick_label_size"] = num_val(self.c_ticklab, int, 0)
        # 轴标题：只有用户真的动过才写进样式。框里那份是自动填的
        # （图上真实在画的标题），原样不动就别存 —— 存了就成了
        # "用户写的死值"，下次图变了标题也不跟着变，还会顺着样式
        # 渗到别的图上（串图）。留空仍然是"真的不画"，那个照存。
        tx = self.ed_x.ed_text.text().strip()
        ty = self.ed_y.ed_text.text().strip()
        ax_, ay_ = getattr(self, "_auto_titles", ("", ""))
        if (tx, ty) == (ax_, ay_):
            a.pop("titles", None)
        else:
            a["titles"] = {"x": tx, "y": ty}
        a["title_size"] = {"x": self.ed_x.size_value(),
                            "y": self.ed_y.size_value()}
        a["title_cfg"] = {"x": self.ed_x.values(),
                          "y": self.ed_y.values()}
        a["x_major"] = num_val(self.c_xstep, float, 0)
        a["y_major"] = num_val(self.c_ystep, float, 0)
        a["x_min"] = self.ed_xmin.text().strip()
        a["x_max"] = self.ed_xmax.text().strip()
        a["y_min"] = self.ed_ymin.text().strip()
        a["y_max"] = self.ed_ymax.text().strip()
        # X、Y 各自勾选 = 按类别排列；不勾选 = 按数值正常排列
        a["categorical"] = {"x": self.ck_catx.isChecked(),
                            "y": self.ck_caty.isChecked()}
        a["cat_labels"] = {"x": self.ed_catx.text().strip(),
                           "y": self.ed_caty.text().strip()}

        lg = st["legend"]
        lg["show"] = self.ck_legshow.isChecked()
        lg["loc"] = dict(LEGEND_LOCS)[self.cb_legloc.currentText()]
        corner_map = {"右上角": "upper right", "左上角": "upper left",
                      "右下角": "lower right", "左下角": "lower left",
                      "正中间": "center"}
        lg["anchor"] = {
            "on": self.ck_leganchor.isChecked(),
            "leg_corner": corner_map.get(self.cb_legcorner.currentText(),
                                         "upper right"),
            "x": num_val(self.ed_legax, float, 1.0),
            "y": num_val(self.ed_legay, float, 1.0),
        }
        lg["ncol"] = num_val(self.c_legcol, int, 1)
        lg["rich"] = self.ck_legrich.isChecked()
        lg["frameon"] = self.ck_legframe.isChecked()
        lg["border_width"] = num_val(self.c_legbw, float, 0.8)
        lg["handle_length"] = num_val(self.c_handlen, float, 2.0)
        lg["handle_height"] = num_val(self.c_handleh, float, 0.7)
        lg["handle_textpad"] = num_val(self.c_htpad, float, 0.8)
        lg["label_spacing"] = num_val(self.c_lspace, float, 0.5)
        lg["column_spacing"] = num_val(self.c_cspace, float, 2.0)
        lg["items"] = [self.tb_leg.item(r, 1).text()
                       if self.tb_leg.item(r, 1) else ""
                       for r in range(self.tb_leg.rowCount())]

        st["eis"]["equal_scale"] = self.ck_equal.isChecked()
        st["eis"]["x_max"] = num_val(self.c_ex, float, 0)
        st["eis"]["y_max"] = num_val(self.c_ey, float, 0)
        st["eis"]["inset"] = self.ck_inset.isChecked()

        texts = []
        for r in range(self.tb_texts.rowCount()):
            def cell(j, r=r):
                """取单元格的值：优先控件（取它自己的读数），其次表格项"""
                w = self.tb_texts.cellWidget(r, j)
                if w is not None:
                    if isinstance(w, 色块按钮):
                        return w.color()      # QPushButton 没有 currentText
                    if isinstance(w, 坐标微调):
                        return "%.4f" % w.value()
                    try:
                        return w.currentText()
                    except AttributeError:
                        return w.text()
                it = self.tb_texts.item(r, j)
                return it.text() if it else ""
            txt = cell(1).strip()
            if not txt:
                continue
            try:
                try:
                    rot = float(str(cell(9)).strip() or 0.0)
                except ValueError:
                    rot = 0.0
                try:
                    xf = float(cell(2) or 0.5)
                except ValueError:
                    xf = 0.5
                try:
                    yf = float(cell(3) or 0.9)
                except ValueError:
                    yf = 0.9
                try:
                    sz = int(float(cell(4) or 12))
                except ValueError:
                    sz = 12
                texts.append({
                    "text": txt, "x": xf, "y": yf, "size": sz,
                    "color": cell(5).strip() or "",
                    "ha": cell(6) or "center",
                    "frame": cell(7).strip() in ("是", "true", "True", "y"),
                    "rich": self._text_rich(r),
                    "rotation": rot})
            except ValueError:
                continue
        st["texts"] = texts
        return st, out


class PlotStyleDialog(QDialog):
    """单独打开绘图设置（不跑数据也能先把外观调好）"""

    def __init__(self, parent, styles, output):
        super().__init__(parent)
        self.setWindowTitle("绘图设置（每张图各一套）")
        self.resize(620, 660)
        lay = QVBoxLayout(self)
        self.panel = StylePanel(self)
        self.panel.set_styles(styles or {}, output)
        lay.addWidget(self.panel, stretch=1)
        hb = QHBoxLayout()
        hb.addWidget(QLabel("输出格式："))
        self.fmt = {}
        for k in ("png", "pdf", "svg", "eps", "tiff"):
            c = QCheckBox(k)
            c.setChecked(k in output.get("formats", ["png", "pdf"]))
            self.fmt[k] = c
            hb.addWidget(c)
        hb.addStretch(1)
        lay.addLayout(hb)
        hb2 = QHBoxLayout()
        b_def = QPushButton("恢复默认")
        b_def.clicked.connect(lambda: self.panel.set_styles(
            {}, {"formats": ["png", "pdf"], "dpi": 600}))
        hb2.addWidget(b_def)
        hb2.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        hb2.addWidget(bb)
        lay.addLayout(hb2)

    def result_values(self):
        styles, out = self.panel.styles_all()
        out["formats"] = [k for k, c in self.fmt.items()
                          if c.isChecked()] or ["png"]
        return styles, out


# ==================================================================
# 保比例画布：预览图绝不被拉伸变形
# ==================================================================

class 固定画布(FigureCanvasQTAgg):
    """预览专用画布：窗口/缩放只改"显示大小"，绝不改 figure 的真实尺寸。

    matplotlib 的 FigureCanvasQT.resizeEvent 会在画布控件尺寸变化时自动
    调 figure.set_size_inches——把"显示缩放"误当成"改图形尺寸"。
    结果预览里拉一下窗口或切个缩放档，导出图的真实大小就跟着变了（Bug 1）。
    这里覆盖 resizeEvent：只让 Qt 完成缩放 + 重绘，但不再回写 figure 尺寸，
    于是屏幕上是放大/缩小/适应窗口，而图形本身的英寸尺寸始终恒定。
    """

    def resizeEvent(self, event):
        if getattr(self, "_in_resize_event", False):
            return
        if self.figure is None:
            return
        self._in_resize_event = True
        try:
            # 只调用 QWidget 的 resizeEvent 完成 Qt 侧缩放；不调
            # figure.set_size_inches（那是父类的 resizeEvent 干的事，会改尺寸）
            QWidget.resizeEvent(self, event)
            self.draw_idle()
        finally:
            self._in_resize_event = False

    def paintEvent(self, event):
        """Scale the complete Agg image; QtAgg otherwise crops at native pixels."""
        self._draw_idle()
        if not hasattr(self, "renderer"):
            return
        pixels = memoryview(self.buffer_rgba())
        picture = QImage(pixels, pixels.shape[1], pixels.shape[0],
                         QImage.Format_RGBA8888)
        painter = QPainter(self)
        try:
            painter.eraseRect(event.rect())
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(QRectF(self.rect()), picture)
            # Matplotlib's rubber-band callback uses renderer pixels / DPR.
            painter.scale(self.width() * self.device_pixel_ratio / pixels.shape[1],
                          self.height() * self.device_pixel_ratio / pixels.shape[0])
            self._draw_rect_callback(painter)
        finally:
            painter.end()

    def mouseEventCoords(self, pos=None):
        """Map a click on the scaled preview back to figure coordinates."""
        if pos is None:
            pos = self.mapFromGlobal(QCursor.pos())
        elif hasattr(pos, "position"):
            pos = pos.position()
        elif hasattr(pos, "pos"):
            pos = pos.pos()
        return (pos.x() * self.figure.bbox.width / max(1, self.width()),
                (self.height() - pos.y()) * self.figure.bbox.height
                / max(1, self.height()))

    def blit(self, bbox=None):
        # Partial QtAgg blits assume an unscaled canvas. Repaint the scaled view.
        self.update()


class 比例画布框(QWidget):
    """把 matplotlib 画布按 figure 的真实宽高比放进容器，绝不拉伸。

    之前的 bug：FigureCanvas 直接扔进布局里，尺寸完全由布局说了算。
    容器是 1000×300 而图形是 6×4.6 英寸（1.30:1）时，图会被横向拉成
    3.33:1，看起来很宽但其实是变形的 —— 而变形后的图看着"挺正常"，
    输出后才发现比例不对。

    现在按 figure 的比例算出应有的像素尺寸，居中摆放，多余空间留白。
    这样你在屏幕上看到的形状，就是论文里的形状。
    """

    # 缩放档位：屏幕 96 dpi 下，1 英寸 = 96 像素
    ZOOM_FIT = 0        # 适应窗口（留白）
    ZOOM_100 = 1        # 实际大小（论文里的真实视觉比例）
    ZOOM_150 = 2
    ZOOM_200 = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self._fig = None
        self._mode = self.ZOOM_FIT
        self._scale = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # 画布外面套一个滚动区：小图在窗口里居中留白，大图可以滚动查看。
        # 两种情况都不变形。注意属性名不能叫 scroll —— QWidget 已有同名方法。
        # 背景设为透明：画布（figure）之外是"无限透明"的背景，不再有灰框，
        # 缩放窗口时也不会出现一块灰色把图挤小（诉求 3）。
        self.sview = QScrollArea()
        self.sview.setWidgetResizable(False)
        self.sview.setAlignment(Qt.AlignCenter)
        self.sview.setFrameShape(QScrollArea.NoFrame)
        self.sview.setStyleSheet("background:#F2F2F2;")

        self.holder = QWidget()
        self.holder.setObjectName("canvasHolder")
        hl = QVBoxLayout(self.holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addStretch(1)
        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.addStretch(1)
        hl.addLayout(self.row)
        hl.addStretch(1)
        self.sview.setWidget(self.holder)
        lay.addWidget(self.sview)

        self._size_note = QLabel("")
        self._size_note.setObjectName("hint")
        self._size_note.setWordWrap(True)   # 窗口一小就换行，不把画布往下挤
        lay.addWidget(self._size_note)

    # ---------- 对外接口 ----------

    def set_canvas(self, canvas):
        """挂上新画布并立刻按比例摆好

        重要：旧画布绝对不能 deleteLater！
        预览把每张图的 (fig, canvas) 都缓存在 self._cache 里，切图时直接
        把缓存里的 canvas 挂上来。若这里把"上一个挂着的 canvas"销毁了，它
        多半是另一张图的缓存项——下次切回那张图，缓存返回的就是 C++ 对象
        已销毁的僵尸，setSizePolicy 立刻报
        "FigureCanvasQTAgg already deleted"，整个预览卡死（Bug 5）。
        所以旧画布只从布局里摘掉、断开父子关系，让它继续活在缓存里复用。
        """
        old = self.canvas
        if old is not None and old is not canvas:
            try:
                self.row.removeWidget(old)
                old.setParent(None)
            except Exception:
                pass
        self.canvas = canvas
        self._fig = canvas.figure
        # 关键：禁止布局动这个画布的尺寸，尺寸只由我们算
        canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.row.addWidget(canvas)
        canvas.show()  # setParent(None) hides a cached canvas when switching away.
        # 布局还没跑完时视口尺寸是旧的，先让它算一次再定画布大小，
        # 否则刚挂上时会按默认 640×480 定尺寸，看起来就是"适应窗口没生效"
        self.sview.updateGeometry()
        QTimer.singleShot(0, self.relayout)
        self.relayout()

    def set_mode(self, mode):
        self._mode = mode
        self.relayout()

    def get_mode(self):
        return self._mode

    def mode_label(self):
        return {self.ZOOM_FIT: "适应窗口（留白不变形）",
                self.ZOOM_100: "实际大小 100%（论文真实比例）",
                self.ZOOM_150: "放大 150%",
                self.ZOOM_200: "放大 200%"}[self._mode]

    # ---------- 核心：按比例算尺寸 ----------

    def fig_ratio(self):
        """figure 的真实宽高比（像素口径）"""
        try:
            w, h = self._fig.get_size_inches()
            return float(w) / float(h)
        except Exception:
            return 1.3

    def natural_size(self):
        """图的物理尺寸换算成屏幕像素。

        必须用 figure 自己的 dpi，不能写死 96 —— relayout() 里是拿
        dw / fig.dpi 去 set_size_inches 的，回头再用 96 换算回来就
        差了 100/96 这一档，每 resize 一次画布就缩 4%，
        反复几次窗口里那图就越来越小（老毛病"缩小后画布越来越小"）。
        """
        try:
            dpi = self._fig.dpi or 100.0
            w, h = self._fig.get_size_inches()
            return int(round(w * dpi)), int(round(h * dpi))
        except Exception:
            return 600, 460

    def relayout(self):
        """容器尺寸变化时重新计算画布该多大"""
        if self.canvas is None or self._fig is None:
            return
        # 以滚动区的可视区域为准（用 holder 会跟滚动条互相触发死循环）。
        # 视口还没初始化好时退回自己的尺寸，避免算出 1×1 的畸形画布。
        vp = self.sview.viewport()
        aw = vp.width() if vp and vp.width() > 2 else self.width()
        ah = vp.height() if vp and vp.height() > 2 else self.height()
        aw, ah = max(1, aw), max(1, ah)
        ratio = self.fig_ratio()

        if self._mode == self.ZOOM_FIT:
            # 取能放进容器的最大等比尺寸
            if aw / ah > ratio:
                dw, dh = int(ah * ratio), ah
            else:
                dw, dh = aw, int(aw / ratio)
        else:
            nw, nh = self.natural_size()
            k = {self.ZOOM_100: 1.0, self.ZOOM_150: 1.5,
                 self.ZOOM_200: 2.0}[self._mode]
            dw, dh = int(nw * k), int(nh * k)
            # 真的比容器大才启用放大，否则还是适应窗口
            if dw <= aw and dh <= ah:
                if aw / ah > ratio:
                    dw, dh = int(ah * ratio), ah
                else:
                    dw, dh = aw, int(aw / ratio)
            else:
                # 超大画布会吃掉几百 MB 内存还看不清，限制在 3 倍以内
                # 多出来的部分靠 QScrollArea 滚动查看
                cap_w, cap_h = aw * 3, ah * 3
                if dw > cap_w or dh > cap_h:
                    if dw / cap_w > dh / cap_h:
                        dh = int(dh * cap_w / dw)
                        dw = cap_w
                    else:
                        dw = int(dw * cap_h / dh)
                        dh = cap_h

        dw, dh = max(1, dw), max(1, dh)
        self.canvas.setFixedSize(dw, dh)
        self.canvas.setMinimumSize(dw, dh)
        self.canvas.setMaximumSize(dw, dh)
        # widgetResizable=False leaves an initially empty holder at 0 x 0.
        # Give the scroll area's content an explicit size so it cannot clip
        # the entire figure, including after switching back to a cached view.
        self.holder.setFixedSize(dw, dh)
        self.holder.layout().activate()

        # 注意：绝不在这里调 figure.set_size_inches！
        # 预览缩放/适应窗口只是"显示缩放"，图形本身的真实英寸尺寸必须恒定，
        # 否则导出图的尺寸会被预览窗口大小带偏（Bug 1）。
        # 真实尺寸由 固定画布.resizeEvent 保证不被回写；这里只定显示大小，
        # canvas 尺寸变化时它会自动重绘（render 在原生尺寸、由 Qt 缩放到控件）。

        note = (f"显示 {dw}×{dh} 像素（仅缩放）· 图形真实尺寸 "
                f"{self._fig.get_figwidth():.2f}×{self._fig.get_figheight():.2f}"
                f" 英寸（导出不变）· {self.mode_label()}")
        self._size_note.setText(note)

    def fit_window(self):
        """一键适应窗口：按当前视口大小重算一次画布显示尺寸并居中，
        但不改 _mode（不影响缩放档位选择）。平时缩小窗口不会自动压缩预览图，
        要重新适应就手动点「居中 / 适应窗口」按钮。"""
        if self.canvas is None or self._fig is None:
            return
        saved = self._mode
        try:
            self._mode = self.ZOOM_FIT
            self.relayout()
        finally:
            self._mode = saved

    def resizeEvent(self, ev):
        # 关键：这里绝不能再调 self.relayout()！
        # 以前每次窗口缩放都重算画布尺寸并 draw_idle，图一大就卡成 PPT，
        # 而且小窗会被"压缩"成小方块、永远不出滚动条（用户原话：很卡、最后被压缩）。
        # 现在画布尺寸只在「换图 / 切缩放档 / 点『居中/适应窗口』」时变；
        # 窗口缩放只改视口，画布保持原大小（小了出滚动条，大了居中留白）。
        super().resizeEvent(ev)


# ==================================================================
# 出图预览窗
# ==================================================================
class 图内工具条(QWidget):
    """自绘的中文工具条：只留真正有用的几件事

    故意不要 matplotlib 官方工具条：
    1. 官方那个齿轮（Figure options）弹的是 rcParams 编辑器，全英文，
       而且它改的是 matplotlib 全局参数 —— 点一下"应用"整个软件的默认样式
       都会被改掉，正是「改完又被弹回去」的元凶之一。
    2. 官方工具条清一色英文 tooltip，同样看不懂。
    这里只保留：还原、平移、框选放大、缩小、填入坐标范围。
    """

    def __init__(self, parent, on_pick_limits=None):
        super().__init__(parent)
        self.canvas = None
        self.nav = None
        self._origin = None
        self.on_pick_limits = on_pick_limits
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        b_home = QPushButton("还原")
        b_home.setToolTip("回到这张图刚画出来的样子（撤销所有缩放拖动）")
        b_home.clicked.connect(self._reset_view)
        lay.addWidget(b_home)

        self.b_pan = QPushButton("平移")
        self.b_pan.setCheckable(True)
        self.b_pan.setToolTip("按住左键拖动画面")
        self.b_pan.clicked.connect(lambda c: self._mode("pan", c))
        lay.addWidget(self.b_pan)

        self.b_zoom = QPushButton("框选放大")
        self.b_zoom.setCheckable(True)
        self.b_zoom.setToolTip("按住左键框一个矩形，把这块放大")
        self.b_zoom.clicked.connect(lambda c: self._mode("zoom", c))
        lay.addWidget(self.b_zoom)

        b_out = QPushButton("缩小一半")
        b_out.setToolTip("以画面中心为基准缩小")
        b_out.clicked.connect(self._zoom_out)
        lay.addWidget(b_out)

        b_fix = QPushButton("把当前范围填到设置里")
        b_fix.setToolTip("把现在看到的坐标范围写进右边的设置框，"
                         "以后输出就固定成这个范围")
        b_fix.clicked.connect(self._emit_limits)
        lay.addWidget(b_fix)

        lay.addStretch(1)
        self.lab = QLabel("")
        self.lab.setObjectName("hint")
        lay.addWidget(self.lab)

    # ---------- 内部 ----------
    def attach(self, canvas):
        self.canvas = canvas
        # matplotlib 3.11 把平移/缩放/还原的实现全放在官方工具条里，
        # canvas 上没有这些方法。所以留一个隐藏的官方工具条当"发动机"，
        # 但把它的按钮统统删光 —— 那个齿轮（Figure options，全英文的
        # rcParams 编辑器）就是从这里来的，绝不能出现在界面上。
        if self.nav is None or self.nav.canvas is not canvas:
            if self.nav is not None:
                self.nav.deleteLater()
            self.nav = NavigationToolbar2QT(canvas, self)
            self.nav.setVisible(False)
            for a in self.nav.actions():
                self.nav.removeAction(a)
        # 官方工具条的"还原"依赖鼠标按下时才压入的历史栈，
        # 刚画好还没按过鼠标时它是空的，按了没反应。
        # 所以自己记一份初始范围，还原时直接写回去。
        try:
            ax = canvas.figure.axes[0]
            self._origin = (ax.get_xlim(), ax.get_ylim())
        except Exception:
            self._origin = None
        self.b_pan.setChecked(False)
        self.b_zoom.setChecked(False)
        self._tick_label()

    def _reset_view(self):
        """回到刚画出来的样子"""
        if self.canvas is not None and self._origin is not None:
            try:
                ax = self.canvas.figure.axes[0]
                ax.set_xlim(*self._origin[0])
                ax.set_ylim(*self._origin[1])
                self.canvas.draw_idle()
                self._tick_label()
                return
            except Exception:
                pass
        self._call("home")

    def _call(self, name):
        if self.canvas is None or self.nav is None:
            return
        try:
            getattr(self.nav, name)()
            self.canvas.draw_idle()
            self._tick_label()
        except Exception:
            pass

    def _mode(self, mode, on):
        if self.canvas is None or self.nav is None:
            return
        other = self.b_pan if mode == "zoom" else self.b_zoom
        other.setChecked(False)          # 平移和放大互斥
        try:
            (self.nav.pan if mode == "pan" else self.nav.zoom)(on)
            self.canvas.draw_idle()
        except Exception:
            pass

    def _zoom_out(self):
        """自己实现缩小：官方工具条没有单独暴露这个动作"""
        if self.canvas is None:
            return
        try:
            ax = self.canvas.figure.axes[0]
            for get, set_ in ((ax.get_xlim, ax.set_xlim),
                              (ax.get_ylim, ax.set_ylim)):
                lo, hi = get()
                mid = (lo + hi) / 2.0
                half = (hi - lo)      # 半宽翻倍 = 整个范围放大一倍
                set_(mid - half, mid + half)
            self.canvas.draw_idle()
            self._tick_label()
        except Exception:
            pass

    def _emit_limits(self):
        if self.on_pick_limits is None or self.canvas is None:
            return
        try:
            ax = self.canvas.figure.axes[0]
            self.on_pick_limits(*ax.get_xlim(), *ax.get_ylim())
        except Exception:
            pass

    def _tick_label(self):
        """实时显示当前范围，让用户知道自己停在哪儿"""
        if self.canvas is None:
            return
        try:
            ax = self.canvas.figure.axes[0]
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
            self.lab.setText(f"X {x0:.4g} ~ {x1:.4g}   "
                             f"Y {y0:.4g} ~ {y1:.4g}")
        except Exception:
            pass


class PreviewDialog(QDialog):
    """左边看图，右边调样式；改完点「重新绘制」才重画，确认后才真正写文件

    以前是改一个参数就自动重画：拖着滑块会连续重画几十次，
    matplotlib 每次都要新建 Figure + Canvas，内存涨得快、还会卡。
    现在改成手动触发——改完参数点一下左图上方的「重新绘制」。
    """

    def __init__(self, parent, data, cfg):
        super().__init__(parent)
        self.setWindowTitle("出图预览 — 调整好了再输出")
        # 默认开大一点，之前 1300×820 左边分不到 600 像素，图看不全
        self.resize(1500, 950)
        # 最小尺寸 = 左边绘图区 + 右边参数区 + 底部长度条刚好放得下的宽度。
        # 定得比这个更小，底部的"更改/输出到/重新绘制"那一行就会被挤没。
        self.setMinimumSize(900, 560)
        self.data = data
        self.cfg = json.loads(json.dumps(
            {k: v for k, v in cfg.items() if not k.startswith("_")},
            default=str))
        self.items = eclab.preview_list(data, self.cfg)
        self.idx = 0
        self.fig = None
        self._dirty = False       # 参数改过但还没重画
        self._stale = set()       # 改参数后哪些缓存的图变旧了
        self._drawing = False
        self._busy = False        # 正在回填控件（这期间的信号不算用户改的）
        self._cache = {}          # 最多保留最近三张，避免批量 EIS 占满内存
        self._build()
        if self.items:
            self._on_pick(0)

    def _build(self):
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("当前预览："))
        self.cb_fig = QComboBox()
        self.cb_fig.addItems([n for _, n in self.items])
        self.cb_fig.currentIndexChanged.connect(self._on_pick)
        top.addWidget(self.cb_fig, stretch=1)
        b_prev = QPushButton("上一张")
        b_prev.clicked.connect(lambda: self._step(-1))
        b_next = QPushButton("下一张")
        b_next.clicked.connect(lambda: self._step(1))
        top.addWidget(b_prev)
        top.addWidget(b_next)
        self.lab_dirty = QLabel("")
        self.lab_dirty.setObjectName("hint")
        top.addWidget(self.lab_dirty)
        self.lab_hint = QLabel("")
        self.lab_hint.setObjectName("hint")
        top.addWidget(self.lab_hint)
        lay.addLayout(top)

        # 计算日志删掉后就不需要上下分栏了，图 + 参数横向分割直接占满窗口

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        # 画布区和工具条分开两层：重画时只清画布，工具条一直留着
        self.canvas_box = 比例画布框()
        ll.addWidget(self.canvas_box, stretch=1)

        self.bar = 图内工具条(self, self._take_limits)
        ll.addWidget(self.bar)

        # 缩放档位：解决"看不出输出到底是多大"的问题
        zrow = QHBoxLayout()
        zrow.setSpacing(6)
        zrow.addWidget(QLabel("看图大小："))
        self.cb_zoom = QComboBox()
        self.cb_zoom.setToolTip(
            "「实际大小」= 屏幕上 1 英寸 = 96 像素，\n"
            "这个比例下看到的字号和线宽，跟论文印刷出来一致。\n"
            "「适应窗口」= 缩放到刚好放进左边，比例永远正确。")
        for t in ("适应窗口（留白不变形）", "实际大小 100%（论文比例）",
                  "放大 150%", "放大 200%"):
            self.cb_zoom.addItem(t)
        self.cb_zoom.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_zoom.setMinimumContentsLength(12)
        self.cb_zoom.currentIndexChanged.connect(self._on_zoom)
        zrow.addWidget(self.cb_zoom)
        b_fit = QPushButton("居中 / 适应窗口")
        b_fit.setToolTip("按当前绘图区大小重新居中并适应窗口。\n"
                         "平时缩小窗口不会自动压缩预览图（避免卡顿），"
                         "要重新适应就点这里。")
        b_fit.clicked.connect(self._fit_window)
        zrow.addWidget(b_fit)
        zrow.addStretch(1)
        ll.addLayout(zrow)

        body.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("改完参数 → 点左图上方「重新绘制」生效："))
        self.panel = StylePanel(self)
        self.panel.set_styles({k: eclab.get_style(self.cfg, k)
                               for k in KIND_CODES},
                              self.cfg.get("output", {}))
        # 不再改一个参数就重画：标记为"待重画"，等用户点按钮
        self.panel.cb_kind.hide()
        self.panel.kind_display.show()
        self.panel.changed = self._mark_dirty
        rl.addWidget(self.panel, stretch=1)
        body.addWidget(right)
        # 左图右参数。两边的最小宽度都不能太大 —— 最小宽加起来超过窗口宽度时，
        # QSplitter 会把左边的控件挤到画布下方去（看着就是"重叠/错位"）。
        # 这里把最小宽压到能用的下限，窗口再小也保持左右并排。
        left.setMinimumWidth(380)
        right.setMinimumWidth(400)
        body.setSizes([1010, 470])
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)

        self.body = body
        lay.addWidget(body, stretch=1)

        # ① 输出格式占一行
        hb = QHBoxLayout()
        hb.addWidget(QLabel("输出格式："))
        self.fmt = {}
        for k in ("png", "pdf", "svg", "eps", "tiff"):
            c = QCheckBox(k)
            c.setChecked(k in self.cfg.get("output", {}).get(
                "formats", ["png", "pdf"]))
            self.fmt[k] = c
            hb.addWidget(c)
        hb.addStretch(1)
        lay.addLayout(hb)

        # ② 「输出到」一行，从左到右固定顺序：
        #    [更改按钮] [输出到] [位置框] [重新绘制]
        #    三个宽度全部写死：以前"位置框"跟着左边绘图区伸缩，
        #    窗口一小它就缩到只剩几个字、字被挤成两行。现在一律固定。
        hb_out = QHBoxLayout()
        b_dir = QPushButton("更改…")
        b_dir.setToolTip("换一个输出文件夹（只影响导出到哪，不影响图）")
        b_dir.setFixedWidth(66)
        b_dir.clicked.connect(self._choose_dir)
        hb_out.addWidget(b_dir)
        hb_out.addSpacing(6)
        hb_out.addWidget(QLabel("输出到："))
        self.lab_dir = QLabel(self.cfg.get("output", {}).get(
            "dir") or eclab.OUTPUT_DIR)
        self.lab_dir.setObjectName("hint")
        self.lab_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lab_dir.setFixedWidth(360)
        self.lab_dir.setMinimumWidth(360)
        # 长路径缩中间（…），宽度不变；完整路径看悬停提示
        self.lab_dir.setToolTip(self.lab_dir.text())
        hb_out.addWidget(self.lab_dir)
        hb_out.addSpacing(6)
        # 「重新绘制」固定在这行最右端，宽度不变：只有改了参数才点它
        self.b_draw = QPushButton("重新绘制")
        self.b_draw.setFixedWidth(self.b_draw.sizeHint().width() + 10)
        self.b_draw.setToolTip(
            "按当前参数把这张图重新画一遍。\n"
            "改完右边参数不会自动重画（自动重画很占内存、还会卡），\n"
            "改完点这个按钮才画。\n"
            "只是切换看的图不用点它 —— 切图直接调已经画好的。")
        self.b_draw.clicked.connect(self._redraw)
        self.b_draw.setDefault(True)
        hb_out.addWidget(self.b_draw)
        lay.addLayout(hb_out)

        hb2 = QHBoxLayout()
        b_tpl = QPushButton("当前参数存为绘图模板")
        b_tpl.setToolTip("把当前样式存进软件目录的「绘图模板」文件夹，"
                          "起个名字就行，不用选位置")
        b_tpl.clicked.connect(self._save_template)
        b_cancel = QPushButton("取消（不输出）")
        b_cancel.clicked.connect(self.reject)
        b_one = QPushButton("只输出当前这张")
        b_one.setToolTip("按当前样式只输出左边正在看的这一张图")
        b_one.clicked.connect(self._save_current)
        b_ok = QPushButton("保存参数")
        b_ok.setObjectName("primary")
        b_ok.setToolTip("保存当前绘图参数，之后点「直接输出」选择图片")
        b_ok.clicked.connect(self.accept)
        hb2.addWidget(b_tpl)
        hb2.addStretch(1)
        hb2.addWidget(b_cancel)
        hb2.addWidget(b_one)
        hb2.addWidget(b_ok)
        lay.addLayout(hb2)

    def _on_pick(self, i):
        """切换正在看的图：只显示（走缓存），绝不偷偷重画"""
        if i < 0 or i >= len(self.items):
            return
        if self.panel._timer.isActive():
            self.panel._timer.stop()
            self._mark_dirty()
        self._sync_cfg()
        self.idx = i
        kind = eclab.kind_of_key(self.items[i][0])
        # 先显示、再填控件：填控件时要从这张图上读真实轴标题自动填进
        # 标题框（用户要的就是"框里自动是图上扫出来的标题"），
        # 顺序反了就只能读到上一张图的标题。
        self._show_current()
        self.panel._last_fig = self.fig
        # set_kind 会连触 changed 信号，那是切图带出来的，不是用户改参数
        self._busy = True
        try:
            self.panel.set_kind(kind)
            self.panel.kind_display.setText(self.items[i][1])
        finally:
            self._busy = False
        # set_kind 会顺手清掉"数据点名字"的缓存，这里补回来。
        # 顺序很关键：必须在显示之后，因为要把这张图真实的名字
        # 送进"逐点配色"表。
        self._busy = True
        try:
            self._push_point_labels()
        finally:
            self.panel._timer.stop()
            self._busy = False

    def _push_point_labels(self):
        """把当前图真实的数据点名字推进「逐点配色」表"""
        try:
            labels = [t.get_text()
                      for t in self.fig.axes[0].get_legend().get_texts()]
        except Exception:
            labels = []
        kind = eclab.kind_of_key(self.items[self.idx][0])
        self.panel.set_point_labels(
            labels if kind in ("cv_cap", "gcd_cap") else [])

    def _on_zoom(self, i):
        """切换看图大小档位：0=适应窗口 1=100% 2=150% 3=200%"""
        self.canvas_box.set_mode(i)

    def _fit_window(self):
        """一键居中 / 适应窗口：按当前绘图区大小重算画布显示尺寸并居中。"""
        try:
            self.canvas_box.fit_window()
        except Exception:
            pass

    def _step(self, d):
        if not self.items:
            return
        self.cb_fig.setCurrentIndex((self.idx + d) % len(self.items))

    def _sync_cfg(self):
        styles, out = self.panel.styles_all()
        out["formats"] = [k for k, c in self.fmt.items()
                          if c.isChecked()] or ["png"]
        out["dir"] = self.lab_dir.toolTip() or self.lab_dir.text()
        self.cfg["plot_style"] = styles["cv_overlay"]
        self.cfg["plot_style_by_kind"] = {k: v for k, v in styles.items()
                                          if k != "cv_overlay"}
        self.cfg["output"] = out
        return styles, out

    def _mark_dirty(self, *_a):
        """参数改了：只提示，不重画（省内存、也不卡）

        真正的重画交给「重新绘制」按钮。切换看的图不算改参数，不提示。
        """
        if self._busy:      # 切图 / 回填控件时连触的信号，不是用户改的
            return
        if not self._dirty:
            self._dirty = True
            # 已经画好在缓存里的图全部变旧：切过去时要提示"还没同步"
            self._stale.update(self._cache.keys())
            self.lab_dirty.setText("参数已改，点「重新绘制」看效果")
            self.b_draw.setText("● 重新绘制")
            self._style_draw_button()

    def _style_draw_button(self):
        try:
            self.b_draw.setStyleSheet(
                "QPushButton { font-weight: bold; }")
        except Exception:
            pass

    def _figure_at(self, i):
        """第 i 张图的 (fig, canvas)：缓存里有直接拿，没有才现画"""
        got = self._cache.get(i)
        if got is not None:
            return got
        self._sync_cfg()
        fig, _title = eclab.draw_figure(self.data, self.items[i][0],
                                        self.cfg)
        if fig is None:
            raise RuntimeError("这张图画不出来")
        canvas = 固定画布(fig)
        canvas.draw()
        self._cache[i] = (fig, canvas)
        # Never evict the currently displayed canvas while it is in its layout.
        while len(self._cache) > 3:
            victim = next((k for k in self._cache
                           if k != i and self._cache[k][0] is not self.fig), None)
            if victim is None:
                break
            old_fig, old_canvas = self._cache.pop(victim)
            import matplotlib.pyplot as plt
            plt.close(old_fig)
            old_canvas.deleteLater()
        return fig, canvas

    def _warm_cache(self):
        """打开预览时把所有图都画一遍存进内存

        这是"切图卡顿"的正解：以前每切一次都要新建 Figure + Canvas
        （上百毫秒，还连带整窗重排），现在切图只是换一个已经画好的画布。
        """
        for i in range(min(3, len(self.items))):
            try:
                self._figure_at(i)
            except Exception:
                pass      # 某张图画不出来不影响别的图

    def _legend_texts(self, fig):
        """这张图的图例文字（表格里显示用）

        优先用用户自己写过的图例文字（保留 ^{}/_{} 上下标写法），
        没写过才用图上画出来的。画上去的文字是"去标记"的——
        上下标由富文本画，原生文字里已经没有 ^{} 记号了。
        """
        try:
            labels = [t.get_text()
                      for t in fig.axes[0].get_legend().get_texts()]
        except Exception:
            return []
        try:
            kind = eclab.kind_of_key(self.items[self.idx][0])
            items = ((self.panel.styles.get(kind, {}) or {})
                     .get("legend", {}) or {}).get("items") or []
        except Exception:
            items = []
        if len(items) == len(labels) and any(str(x).strip() for x in items):
            labels = [str(x) for x in items]
        return labels

    def _show_current(self):
        """把当前这张图摆上画布：缓存有就直接摆，没有才现画补进缓存

        这条路径永远不会"重画"——切图再多次也只动显示，不动计算。
        """
        if not self.items or self._drawing:
            return
        self._drawing = True
        self._busy = True
        self.setUpdatesEnabled(False)
        try:
            fig, canvas = self._figure_at(self.idx)
        except Exception as exc:
            self.fig = None
            self.lab_hint.setText("无法预览：" + str(exc))
            self.lab_hint.setToolTip(traceback.format_exc())
            self.setUpdatesEnabled(True)
            self._drawing = False
            self._busy = False
            return
        self.fig = fig
        self.canvas_box.set_canvas(canvas)
        self.bar.attach(canvas)
        self.panel.set_legend_labels(self._legend_texts(fig))
        if self.idx in self._stale:
            self.lab_dirty.setText("参数已改 · 这张还是旧样式，点「重新绘制」同步")
        else:
            self.lab_dirty.setText("")
        try:
            out = self.cfg.get("output", {})
            self.lab_hint.setText(
                f"第 {self.idx + 1}/{len(self.items)} 张 · "
                f"{', '.join(out.get('formats', ['png']))} @ "
                f"{out.get('dpi', 600)} dpi")
        except Exception:
            pass
        self.setUpdatesEnabled(True)
        self._drawing = False
        self._busy = False

    def _redraw(self):
        """「重新绘制」按钮：把当前这张按新参数真画一遍（切图不会走到这）"""
        if not self.items or self._drawing:
            return
        # Consume edits even when the 100 ms style debounce has not fired yet.
        self.panel._timer.stop()
        self._drawing = True
        self._busy = True
        self.setUpdatesEnabled(False)
        try:
            old = self._cache.pop(self.idx, None)
            if old is not None:
                try:
                    import matplotlib.pyplot as plt
                    plt.close(old[0])
                except Exception:
                    pass
                # 旧画布被新画布替换，且不会再被缓存复用 —— 显式销毁。
                # 先把它从布局摘掉、并置 self.canvas=None，避免下面
                # set_canvas 去碰一个即将销毁的旧画布（Bug 5 同源坑）。
                try:
                    self.row.removeWidget(old[1])
                except Exception:
                    pass
                try:
                    old[1].deleteLater()
                except Exception:
                    pass
            self.canvas = None
            fig, canvas = self._figure_at(self.idx)
        except Exception as exc:
            self.fig = None
            self.lab_hint.setText("无法预览：" + str(exc))
            self.lab_hint.setToolTip(traceback.format_exc())
            self.setUpdatesEnabled(True)
            self._drawing = False
            self._busy = False
            return
        self.fig = fig
        # 交给比例画布框：它会按图形真实比例定尺寸，图不会被拉变形
        self.canvas_box.set_canvas(canvas)
        self.bar.attach(canvas)
        self.panel.set_legend_labels(self._legend_texts(fig))
        self.panel._timer.stop()  # legend/control population is not a user edit
        self._dirty = False
        self._stale.discard(self.idx)
        self.b_draw.setText("重新绘制")
        self.lab_dirty.setText("")
        try:
            out = self.cfg.get("output", {})
            self.lab_hint.setText(
                f"第 {self.idx + 1}/{len(self.items)} 张 · "
                f"{', '.join(out.get('formats', ['png']))} @ "
                f"{out.get('dpi', 600)} dpi")
        except Exception:
            pass
        self.setUpdatesEnabled(True)
        self._drawing = False
        self._busy = False

    def _take_limits(self, x0, x1, y0, y1):
        """把工具条上看到的范围写进右侧设置框，之后就固定住了"""
        self.panel.set_limits(x0, x1, y0, y1)
        self._mark_dirty()
        self.lab_hint.setText("已把当前范围填进设置 · 点「重新绘制」生效")

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "选择输出文件夹", self.lab_dir.toolTip()
            or self.lab_dir.text())
        if d:
            self.lab_dir.setToolTip(d)      # 完整路径永远留在提示里
            self._fit_dir_text()
            # 只影响导出到哪，不影响图本身 → 不标"待重画"
            self.lab_hint.setText("输出文件夹已改 · 影响导出，不用重画图")

    def _fit_dir_text(self):
        """框宽固定，路径太长就掐中间（完整路径看悬停提示）"""
        full = self.lab_dir.toolTip() or self.lab_dir.text()
        txt = full
        if len(full) > 42:
            txt = full[:18] + " … " + full[-20:]
        self.lab_dir.setText(txt)

    def closeEvent(self, ev):
        # 窗口关掉时把缓存的 Figure 全放掉，避免 matplotlib 一直记着
        try:
            import matplotlib.pyplot as plt
            for _i, (fig, _c) in list(self._cache.items()):
                try:
                    plt.close(fig)
                except Exception:
                    pass
        except Exception:
            pass
        self._cache = {}
        self.fig = None
        super().closeEvent(ev)

    def _save_current(self):
        if self.panel._timer.isActive():
            self.panel._timer.stop()
            self._mark_dirty()
        if self._dirty or self.idx in self._stale:
            self._redraw()
            if self._dirty or self.idx in self._stale:
                QMessageBox.warning(self, "输出未完成", "新样式重绘失败，请先检查图形参数。")
                return
        styles, out = self._sync_cfg()
        if self.fig is None:
            return
        key = self.items[self.idx][0]
        try:
            output_dir = validate_output(self.cfg, eclab.OUTPUT_DIR)
        except ValueError as exc:
            QMessageBox.warning(self, "请选择输出位置", str(exc))
            return
        made = eclab.save_fig(
            self.fig, key.replace(":", "_").replace("/", "_"),
            styles[eclab.kind_of_key(key)], out["formats"], out["dpi"],
            out_dir=output_dir)
        QMessageBox.information(self, "已输出", "已保存：\n" + "\n".join(made))

    def _save_template(self):
        """当前参数存为绘图模板：存软件目录固定子文件夹，起名防撞名"""
        styles, out = self._sync_cfg()
        out.pop("dir", None)
        tpl_dir = os.path.join(BASE_DIR, "绘图模板")
        os.makedirs(tpl_dir, exist_ok=True)
        name, ok = QInputDialog.getText(
            self, "当前参数存为绘图模板", "给模板起个名字：",
            QLineEdit.Normal, time.strftime("绘图模板 %m-%d %H:%M"))
        if not ok or not name.strip():
            return
        path = os.path.join(tpl_dir, name.strip() + ".json")
        if os.path.isfile(path):
            ret = QMessageBox.question(
                self, "模板已存在",
                f"「{name.strip()}」已经存在，要替换它吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_模板类型": "绘图模板",
                       "_说明": "画图外观（每张图各一套）+ 输出格式",
                       # 标记已按新规则存过（空的 titles 就是真不画标题），
                       # 加载时不要再当老配置迁移
                       "_titles_migrated": True,
                       "plot_style": styles["cv_overlay"],
                       "plot_style_by_kind": {k: v for k, v in styles.items()
                                              if k != "cv_overlay"},
                       "output": out}, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "已保存", f"绘图模板已存到：\n{path}")

    def final_cfg(self):
        self._sync_cfg()
        return self.cfg


# ==================================================================
# 主窗口
# ==================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Microsoft YaHei", 9))
        self.setWindowTitle("ec-lab · 数据处理与一键绘图")
        self.setWindowIcon(app_icon())
        self.resize(1360, 880)
        self.log_q = queue.Queue()
        self.mass_override = {}
        self._cfg_comments = {}
        self._dir_history = []      # 记住用过的文件夹，下次添加时能一键回来
        self._startup = True        # 启动时只恢复记忆路径，不把文件夹塞进列表
        self._running = False
        self._pending = None
        self._last_data = None
        self._last_signature = None
        self._last_workbook = None
        self.workspaces = None
        self._job_result = None
        self._job_error = None
        self.theme = "classic"
        self.style_cfg = json.loads(json.dumps(eclab.DEFAULT_STYLE))
        self.style_by_kind = {}
        self.output_cfg = {"formats": ["png", "pdf"], "dpi": 600,
                           "dir": eclab.OUTPUT_DIR}
        self._build_ui()
        self._first_run_bootstrap()
        self._load_config_file(CONFIG_PATH, silent=True)
        self._startup = False
        self.dir_list.clear()        # 每次打开都从空的开始，列表里显示=有文件
        from ec_workspaces import WorkspaceHost
        self.workspaces = WorkspaceHost(self, self.takeCentralWidget())
        self.setCentralWidget(self.workspaces)
        if self._dir_history:
            self._append("上次用过的文件夹路径已记住，点「添加…」会直接打开")
        QTimer(self, interval=150, timeout=self._drain_log).start()

    def _build_ui(self):
        self._build_menu()
        tb = QToolBar("主工具栏")
        self._main_toolbar = tb
        tb.setMovable(False)
        for text, slot, tip in (
                ("添加文件夹", self.add_dir, "选择数据文件夹（添加后自动扫描）"),
                ("开始处理", self.run, "按原脚本与模板生成 Excel，保留原来的布局"),
                ("电导率处理", self.open_conductivity, "导入电导率原始表格，统一时间与单位并导出 Excel"),
                ("Excel 一键绘图", self.open_plot_studio, "打开处理后的 Excel 或 CSV，选模板并批量出图"),
                ("预览图形", self.open_preview, "打开预览窗修改绘图参数"),
                ("直接输出", self.quick_render, "选择图片、名称与保存位置后输出"),
                ("绘图模板", self.open_plot_settings, "加载 / 保存绘图样式模板"),
                ("输出位置", self.choose_out_dir, "选择图片保存文件夹"),
                ("打开结果", self.open_out_dir, "打开输出文件夹")):
            if text in ("添加文件夹", "Excel 一键绘图"):
                if text == "Excel 一键绘图":
                    tb.addSeparator()
                label = QLabel("  数据处理  " if text == "添加文件夹" else "  一键绘图  ")
                label.setObjectName("hint")
                tb.addWidget(label)
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if text == "开始处理":
                b.setObjectName("primary")
            tb.addWidget(b)
        # 右上角常驻显示输出路径，一眼看清图会存到哪
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.lab_out_bar = QLabel("输出：" + (self.output_cfg.get("dir")
                                              or eclab.OUTPUT_DIR))
        self.lab_out_bar.setObjectName("hint")
        self.lab_out_bar.setToolTip("输出文件夹（点「输出位置」可改）")
        tb.addWidget(self.lab_out_bar)
        self.addToolBar(tb)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(8, 8, 8, 8)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        lay.addWidget(split, stretch=1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        gb_dir = QGroupBox("数据文件夹")
        dl = QVBoxLayout(gb_dir)
        self.dir_list = QListWidget()
        self.dir_list.setSelectionMode(QListWidget.ExtendedSelection)
        dl.addWidget(self.dir_list)
        hb = QHBoxLayout()
        b_add = QPushButton("添加…")
        b_add.setToolTip("选一个放原始数据的文件夹，可以多选")
        b_add.clicked.connect(self.add_dir)
        b_rm = QPushButton("移除选中")
        b_rm.setToolTip("把列表里选中的文件夹移掉（不会删硬盘上的文件）")
        b_rm.clicked.connect(self.remove_dir)
        b_clr = QPushButton("清空")
        b_clr.setToolTip("把列表里的文件夹全清空（不会删硬盘上的文件）")
        b_clr.clicked.connect(self.dir_list.clear)
        for b in (b_add, b_rm, b_clr):
            # QPushButton 默认就是箭头光标，但父级样式可能把它继承成文字，
            # 这里显式钉死，免得鼠标移上去出现"插入文本"的光标
            b.setCursor(Qt.PointingHandCursor)
            hb.addWidget(b)
        dl.addLayout(hb)
        ll.addWidget(gb_dir)

        gb_par = QGroupBox("处理参数")
        pl = QVBoxLayout(gb_par)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("电极面积 cm²"))
        self.sp_area = QDoubleSpinBox()
        self.sp_area.setRange(0.01, 100)
        self.sp_area.setSingleStep(0.5)
        h1.addWidget(self.sp_area)
        h1.addStretch(1)
        pl.addLayout(h1)

        # --- 详细参数：CV / GCD / 循环 / EIS 的数据处理 ---
        self.ck_detail = QCheckBox("展开详细参数（CV / GCD / 循环 / EIS）")
        self.ck_detail.setChecked(False)
        self.ck_detail.toggled.connect(self._toggle_detail)
        pl.addWidget(self.ck_detail)

        self.w_detail = QWidget()
        dvl = QVBoxLayout(self.w_detail)
        dvl.setContentsMargins(0, 0, 0, 0)
        dvl.setSpacing(6)
        self.w_detail.setVisible(False)
        dvl.addWidget(self._build_cv_group())
        dvl.addWidget(self._build_gcd_group())
        dvl.addWidget(self._build_cycle_group())
        dvl.addWidget(self._build_eis_group())
        pl.addWidget(self.w_detail)
        # 输出参数属于程序设置，不属于数据处理，常驻显示不折叠
        pl.addWidget(self._build_out_group())
        ll.addWidget(gb_par)
        self.scroll_left = QScrollArea()
        self.scroll_left.setWidgetResizable(True)
        self.scroll_left.setFrameShape(QScrollArea.NoFrame)
        self.scroll_left.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self.scroll_left.setWidget(left)
        split.addWidget(self.scroll_left)
        ll.addStretch(1)

        right = QSplitter(Qt.Vertical)
        right.setChildrenCollapsible(False)
        gb_tab = QGroupBox("文件（点“处理”方框=勾/不勾该文件；点行=选中，"
                          "可多选后删除；双击“质量 mg”可改）")
        tl = QVBoxLayout(gb_tab)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["处理 ✓", "类型", "文件",
                                              "质量 mg", "质量来源",
                                              "创建日期"])
        hh = self.table.horizontalHeader()
        hh.setSectionsClickable(True)
        hh.sectionClicked.connect(self._on_header_clicked)
        # 全部列都设成可拖动；文件名列用自动填满，随宽度变化再算
        hh.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 62)
        self.table.setColumnWidth(3, 78)
        self.table.setColumnWidth(4, 96)
        self.table.setColumnWidth(5, 140)
        # 允许拖列宽，但每列都有最小宽度，防止拖太窄把列挤没了
        self._col_min = {0: 46, 1: 46, 2: 110, 3: 56, 4: 66, 5: 90}
        hh.setMinimumSectionSize(min(self._col_min.values()))
        hh.sectionResized.connect(self._clamp_col)
        hh.setToolTip("拖动列边可调列宽（每列有最小宽度，拖不没）")
        self._sort_col = -1
        self._sort_asc = True
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.EditKeyPressed)
        self.table.cellChanged.connect(self._on_cell_changed)
        tlb = QHBoxLayout()
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: self._check_all(Qt.Checked))
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: self._check_all(Qt.Unchecked))
        b_inv = QPushButton("反选")
        b_inv.clicked.connect(self._invert_all)
        b_ck_sel = QPushButton("勾选选中行")
        b_ck_sel.setToolTip("先用鼠标拖选 / Ctrl 点选几行，再点这个批量勾上")
        b_ck_sel.clicked.connect(lambda: self._check_selected(Qt.Checked))
        b_uck_sel = QPushButton("取消勾选选中行")
        b_uck_sel.clicked.connect(lambda: self._check_selected(Qt.Unchecked))
        b_del = QPushButton("删除选中行")
        b_del.clicked.connect(self._delete_rows)
        self.lab_count = QLabel("")
        self.lab_count.setObjectName("hint")
        for b in (b_all, b_none, b_inv, b_ck_sel, b_uck_sel, b_del):
            tlb.addWidget(b)
        tlb.addStretch(1)
        tlb.addWidget(self.lab_count)
        tl.addLayout(tlb)
        tl.addWidget(self.table)
        self.table.itemChanged.connect(lambda it: self._update_count())
        self.table.itemSelectionChanged.connect(self._update_count)
        self._update_count()
        right.addWidget(gb_tab)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("log")
        self.log.setFont(QFont("Consolas", 9))
        # 标签和日志必须包在同一个 QWidget 里再放进分割器 ——
        # 以前 QLabel 单独占一个分割段，默认 220px 全是空白，
        # 日志被挤成底部一条细缝，看着像程序出问题了
        logbox = QWidget()
        lv = QVBoxLayout(logbox)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        lab_log = QLabel("运行日志")
        lab_log.setFixedHeight(18)
        lv.addWidget(lab_log)
        lv.addWidget(self.log)
        right.addWidget(logbox)
        # 默认展开：日志约 1/3 高度，用户拖中间分隔线自行调节
        right.setSizes([640, 300])
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 1)
        split.addWidget(right)
        split.setSizes([440, 900])

        # ---- Bug 2：主窗口两栏平铺、可调大小，但各自有最小区域 ----
        # 以前窗口一缩小，左边「数据文件夹」栏会被压成几十像素的一条，
        # 视觉上就像被右边「文件栏」盖住了。这里给两栏各自定最小宽度，
        # 并给整个窗口定最小尺寸，保证怎么缩两栏都并排、都不被压垮。
        MIN_LEFT = 300      # 数据文件夹 + 处理参数 栏最小宽
        MIN_RIGHT = 460     # 文件表 + 日志 栏最小宽
        self.scroll_left.setMinimumWidth(MIN_LEFT)
        right.setMinimumWidth(MIN_RIGHT)
        self.setMinimumSize(MIN_LEFT + MIN_RIGHT + 40, 600)
        self._name_locked = False
        split.splitterMoved.connect(self._fit_name_col)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit_name_col()

    def _fit_name_col(self, *_):
        """文件名列自动吃掉表格剩余宽度（用户手动拖过之后就不再抢）"""
        if getattr(self, "_name_locked", False):
            return
        self._clamping = True
        try:
            others = sum(self.table.columnWidth(c) for c in (0, 1, 3, 4, 5))
            free = self.table.viewport().width() - others
            if free < self._col_min.get(2, 110):
                free = self._col_min.get(2, 110)
            self.table.setColumnWidth(2, free)
        except Exception:
            pass
        finally:
            self._clamping = False

    # ---------------- 详细参数的六个分组 ----------------
    def _fold_group(self, title, tip=""):
        """可勾选展开/收起的分组框（复选框在标题上）"""
        gb = QGroupBox(title)
        gb.setCheckable(True)
        gb.setChecked(False)
        gb.setToolTip(tip or "点标题左侧方框展开 / 收起")
        lay = QVBoxLayout(gb)
        lay.setSpacing(4)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        gb.toggled.connect(body.setVisible)
        body.setVisible(False)
        lay.addWidget(body)
        return gb, bl

    def _toggle_detail(self, on):
        self.w_detail.setVisible(on)

    def _build_cv_group(self):
        gb, lay = self._fold_group("CV 参数")
        h = QHBoxLayout()
        h.addWidget(QLabel("取 segment（默认取 2、3）"))
        self.ck_cv_segs = QCheckBox("自定义")
        self.ck_cv_segs.toggled.connect(
            lambda v: (self.ed_cv_segs.setVisible(v),
                       self.ed_cv_segs.setEnabled(v)))
        h.addWidget(self.ck_cv_segs)
        self.ed_cv_segs = QLineEdit("2, 3")
        self.ed_cv_segs.setVisible(False)
        self.ed_cv_segs.setEnabled(False)
        h.addWidget(self.ed_cv_segs, stretch=1)
        lay.addLayout(h)
        self.ck_skip_act = QCheckBox("跳过文件名含“活化”的 CV")
        self.ck_skip_act.setChecked(True)
        self.ck_dedupe = QCheckBox("每个条件只取一个文件作图（撞数据忽略）")
        self.ck_dedupe.setChecked(True)
        self._fold_body = {}
        lay.addWidget(self.ck_skip_act)
        lay.addWidget(self.ck_dedupe)
        self._fold_body["cv"] = gb
        return gb

    def _build_gcd_group(self):
        gb, lay = self._fold_group("GCD 参数")
        h = QHBoxLayout()
        h.addWidget(QLabel("取 segment（默认取 2、3）"))
        self.ck_gcd_segs = QCheckBox("自定义")
        self.ck_gcd_segs.toggled.connect(
            lambda v: (self.ed_gcd_segs.setVisible(v),
                       self.ed_gcd_segs.setEnabled(v)))
        h.addWidget(self.ck_gcd_segs)
        self.ed_gcd_segs = QLineEdit("2, 3")
        self.ed_gcd_segs.setVisible(False)
        self.ed_gcd_segs.setEnabled(False)
        h.addWidget(self.ed_gcd_segs, stretch=1)
        lay.addLayout(h)
        self.ck_ir = QCheckBox("扣除 IR drop 后算比电容")
        self.ck_cont = QCheckBox("按连续充放电处理（不拆成单次充放）")
        lay.addWidget(self.ck_ir)
        lay.addWidget(self.ck_cont)
        self._fold_body["gcd"] = gb
        return gb

    def _build_cycle_group(self):
        gb, lay = self._fold_group("循环参数（CV / GCD 分开）")

        # 两者共用放上面
        self.w_shared_cyc = QWidget()
        hb = QHBoxLayout(self.w_shared_cyc)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addWidget(QLabel("两者共用：起始圈"))
        self.sp_cstart = QSpinBox()
        self.sp_cstart.setRange(1, 100000)
        self.sp_cstart.setValue(30)
        hb.addWidget(self.sp_cstart)
        hb.addWidget(QLabel("每 N 圈"))
        self.sp_cstep = QSpinBox()
        self.sp_cstep.setRange(1, 1000)
        self.sp_cstep.setValue(10)
        hb.addWidget(self.sp_cstep)
        hb.addStretch(1)
        lay.addWidget(self.w_shared_cyc)

        # 单独设置勾选后，共用自动禁用
        self.ck_cv_cyc = QCheckBox("CV 循环单独设置")
        self.ck_gcd_cyc = QCheckBox("GCD 循环单独设置")
        self.ck_cv_cyc.toggled.connect(self._sync_cycle_shared)
        self.ck_gcd_cyc.toggled.connect(self._sync_cycle_shared)
        self.ck_cv_cyc.toggled.connect(
            lambda v: (self.w_cv_cyc.setVisible(v),
                       self.sp_cv_cstart.setEnabled(v),
                       self.sp_cv_cstep.setEnabled(v)))
        self.ck_gcd_cyc.toggled.connect(
            lambda v: (self.w_gcd_cyc.setVisible(v),
                       self.sp_gcd_cstart.setEnabled(v),
                       self.sp_gcd_cstep.setEnabled(v)))
        lay.addWidget(self.ck_cv_cyc)
        self.w_cv_cyc = QWidget()
        h1 = QHBoxLayout(self.w_cv_cyc)
        h1.setContentsMargins(0, 0, 0, 0)
        h1.addWidget(QLabel("CV 起始圈"))
        self.sp_cv_cstart = QSpinBox()
        self.sp_cv_cstart.setRange(1, 100000)
        h1.addWidget(self.sp_cv_cstart)
        h1.addWidget(QLabel("每 N 圈"))
        self.sp_cv_cstep = QSpinBox()
        self.sp_cv_cstep.setRange(1, 1000)
        h1.addWidget(self.sp_cv_cstep)
        self.w_cv_cyc.setVisible(False)
        lay.addWidget(self.w_cv_cyc)

        lay.addWidget(self.ck_gcd_cyc)
        self.w_gcd_cyc = QWidget()
        h2 = QHBoxLayout(self.w_gcd_cyc)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.addWidget(QLabel("GCD 起始圈"))
        self.sp_gcd_cstart = QSpinBox()
        self.sp_gcd_cstart.setRange(1, 100000)
        h2.addWidget(self.sp_gcd_cstart)
        h2.addWidget(QLabel("每 N 圈"))
        self.sp_gcd_cstep = QSpinBox()
        self.sp_gcd_cstep.setRange(1, 1000)
        h2.addWidget(self.sp_gcd_cstep)
        self.w_gcd_cyc.setVisible(False)
        lay.addWidget(self.w_gcd_cyc)
        # QGroupBox 勾选展开时 Qt 会强制启用全部子控件，
        # 覆盖掉"共用禁用"的状态，所以展开后要重新同步一次
        gb.toggled.connect(lambda _v: self._sync_cycle_shared())
        self._fold_body["cycle"] = gb
        return gb

    def _sync_cycle_shared(self, *_):
        """任一单独设置勾上后，两者共用就禁用并禁止输入"""
        any_on = (self.ck_cv_cyc.isChecked()
                  or self.ck_gcd_cyc.isChecked())
        self.sp_cstart.setEnabled(not any_on)
        self.sp_cstep.setEnabled(not any_on)
        self.w_shared_cyc.setToolTip(
            "已勾选单独设置，共用值不参与计算" if any_on else "")
        self._shared_cyc_disabled = any_on   # 记住状态，折叠组展开时用

    def _build_eis_group(self):
        gb, lay = self._fold_group("EIS 拟合参数")
        self.ck_fit = QCheckBox("拟合等效电路")
        self.ck_fit.setChecked(True)
        h = QHBoxLayout()
        h.addWidget(QLabel("等效电路："))
        self.cb_circuit = QComboBox()
        self.cb_circuit.setEditable(True)   # 常见模板没有时可以自己写
        self.cb_circuit.addItems([
            "自动择优（W / Wo / Ws 选 R² 最高）",
            "Rs-[(Rp+W)‖CPE]（平面扩散）",
            "Rs-[(Rp+Wo)‖CPE]（有限短路）",
            "Rs-[(Rp+Ws)‖CPE]（有限阻塞）",
        ])
        self.cb_circuit.setToolTip(
            "常见模板在上面选；\n"
            "模板里没有你要的电路时：\n"
            "1. 用 ZView 自己拟合\n"
            "2. 把拟合结果文件名改成 xx-fit.txt 放进数据文件夹\n"
            "3. 勾下面的「优先用 ZView 拟合结果」即可")
        h.addWidget(self.cb_circuit, stretch=1)
        lay.addWidget(self.ck_fit)
        lay.addLayout(h)
        self.ck_extfit = QCheckBox("优先用 ZView 拟合结果（xx-fit.txt）")
        self.ck_extfit.setChecked(True)
        lay.addWidget(self.ck_extfit)
        lab_z = QLabel("需要 .z 文件拖进 ZView 拟合？用 ZView 自带导入即可，"
                       "本软件不再单独导出。")
        lab_z.setObjectName("hint")
        lab_z.setWordWrap(True)
        lay.addWidget(lab_z)
        self._fold_body["eis"] = gb
        return gb

    def _build_out_group(self):
        """输出参数（常驻显示：这是程序设置，不是数据处理参数）"""
        gb = QGroupBox("输出参数")
        lay = QVBoxLayout(gb)
        h = QHBoxLayout()
        h.addWidget(QLabel("图片格式："))
        self.fmt_boxes = {}
        for k in ("png", "pdf", "svg"):
            c = QCheckBox(k)
            c.setChecked(k in ("png", "pdf"))
            self.fmt_boxes[k] = c
            h.addWidget(c)
        h.addWidget(QLabel("  DPI"))
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(72, 2400)
        self.sp_dpi.setSingleStep(50)
        self.sp_dpi.setValue(600)
        h.addWidget(self.sp_dpi)
        h.addStretch(1)
        lay.addLayout(h)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("输出文件夹："))
        self.lab_out = QLabel(eclab.OUTPUT_DIR)
        self.lab_out.setObjectName("hint")
        self.lab_out.setWordWrap(True)
        h2.addWidget(self.lab_out, stretch=1)
        lay.addLayout(h2)
        h3 = QHBoxLayout()
        b_ch = QPushButton("更改文件夹…")
        b_ch.clicked.connect(self.choose_out_dir)
        b_op = QPushButton("打开文件夹")
        b_op.clicked.connect(self.open_out_dir)
        h3.addWidget(b_ch)
        h3.addWidget(b_op)
        h3.addStretch(1)
        lay.addLayout(h3)
        self._fold_body["out"] = gb
        return gb

    def _build_menu(self):
        mb = self.menuBar()
        self._workspace_actions = []
        def action(menu, title, callback):
            item = menu.addAction(title, callback)
            self._workspace_actions.append(item)
            return item
        m = mb.addMenu("文件")
        action(m, "添加文件夹…", lambda: self.workspaces.process_action("add_folder"))
        action(m, "输出位置…", self.choose_out_dir)
        m.addAction("结果文件夹", self.open_out_dir)
        m.addSeparator()
        m.addAction("退出", self.close)
        m = mb.addMenu("处理")
        action(m, "加载数据处理模板…", lambda: self.workspaces.process_action("load_processing_template"))
        action(m, "保存数据处理模板…", lambda: self.workspaces.process_action("save_processing_template"))
        action(m, "修改数据处理模板", lambda: self.workspaces.process_action("edit_processing_template"))
        m = mb.addMenu("绘图")
        templates = m.addMenu("绘图模板")
        action(templates, "加载模板…", lambda: self.workspaces.plot_action("load_style_template"))
        action(templates, "编辑模板…", lambda: self.workspaces.plot_action("edit_style_template"))
        action(m, "绘图设置", lambda: self.workspaces.plot_action("show_plot_settings"))
        action(m, "调色盘…", lambda: self.workspaces.plot_action("choose_palette"))
        m = mb.addMenu("外观")
        m.addAction("浅色模式", lambda: self.set_theme("classic"))
        m.addAction("深色模式", lambda: self.set_theme("dark"))
        m = mb.addMenu("帮助")
        m.addAction("使用说明", self.show_help)
        m.addAction("科研绘图设计学习报告", lambda: self._open_project_doc("科研绘图项目设计学习报告-20261024.md"))
        advanced = m.addMenu("高级电化学工具")
        action(advanced, "打开高级工作区", lambda: self.workspaces.show_advanced())
        action(advanced, "原绘图模板与详细设置…", lambda: self._advanced_action(self.open_plot_settings))
        action(advanced, "原数据处理模板加载…", lambda: self._advanced_action(lambda: self.load_template("数据处理模板")))
        action(advanced, "原数据处理模板保存…", lambda: self._advanced_action(lambda: self.save_template("数据处理模板")))
        m.addAction("查看错误日志", self._view_error_log)
        m.addAction("关于 ec-lab", lambda: QMessageBox.information(
            self, "关于 ec-lab", "ec-lab · 数据处理与一键绘图\n\n"
            "保留原 Excel 数据处理格式；基于 PySide6 与 Matplotlib。\n"
            "科研绘图设计参考及开源来源见帮助中的学习报告。"))

    def _advanced_action(self, callback):
        if self._running or (self.workspaces and self.workspaces.is_busy()):
            return
        if self.workspaces:
            self.workspaces.show_advanced()
        callback()

    def _open_project_doc(self, filename):
        path = os.path.join(BASE_DIR, "docs", filename)
        try:
            os.startfile(path)
        except Exception as exc:
            QMessageBox.information(self, "文档位置", path + "\n\n" + str(exc))

    def show_help(self):
        QMessageBox.information(self, "使用说明",
            "数据处理\n"
            "① 选择处理类型，添加文件或文件夹。左侧保留本批文件清单。\n"
            "② 核对质量、体积和采样方式；需要时展开参数。\n"
            "③ 开始处理生成 Excel；完成后选择结果，进入一键绘图。\n\n"
            "一键绘图\n"
            "① 打开处理后的 Excel，自动列出常用图，也可以按列绘图。\n"
            "② 在上方“当前预览”切图，展开“绘图设置”修改坐标轴、图例、颜色、字体和尺寸。\n"
            "③ 点击输出，勾选图片、修改名称、格式和保存位置；至少选择一张。\n"
            "④ 完成后可以选择是否打开保存位置。\n\n"
            "模板与文件\n"
            "· 处理菜单管理数据处理参数；绘图模板保存外观，绘图配方记录本次数据与设置。\n"
            "· CDI 默认 50 mL；质量自动建议可改，混合质量分批处理；原始数据只读。\n"
            "· 切换工作区保留当前内容。浅色/深色只改变软件外观，论文画布保持白底。\n"
            "· 比电容、EIS、原详细预览仍在“帮助 → 高级电化学工具”。")

    def _show_legacy_help(self):
        QMessageBox.information(
            self, "使用说明",
            "① 添加文件夹 → ② 扫描并勾选文件（质量双击可改）\n"
            "③ 开始处理：算数并保存数据，算完提示完成\n"
            "④ 点「预览图形」改绘图参数；满意后点「直接输出」出图\n"
            "   （输出完可选择是否打开结果文件夹）\n\n"
            "处理参数怎么用：\n"
            "· 取 segment 默认就是 2、3，不用动；只有确实要改时，"
            "才勾「自定义要取的 segment」。\n"
            "· 勾「展开详细参数」后，按 CV / GCD / 循环 / EIS / 输出"
            "五块分开设置，各块点标题左侧方框可折叠。\n"
            "· CV 与 GCD 可以各写各的 segment 和循环起始圈；"
            "不单独设就都用上面那个共用值。\n"
            "· 输出文件夹在「输出参数」里改，也可以用「更改文件夹…」。\n\n"
            "文件表：\n"
            "· 「处理 ✓」列的方框 = 该文件要不要参与处理；点表头可全选。\n"
            "· 点行选中（可 Ctrl/Shift 多选）后「删除选中行」删掉。\n"
            "· 右上角实时显示「共 N 个文件，已勾选 M 个」。\n\n"
            "要点：\n"
            "· 样式按图分开：CV 叠加 / CV 比电容 / GCD 曲线 / GCD 比电容 /"
            " EIS / 循环稳定性；预览切图时自动切到对应样式。\n"
            "· 类别轴：在「刻度/轴」页签最上面的方框里勾选。\n"
            "· 轴标题：在「轴标题」页签里，X 轴和 Y 轴各改各的。\n"
            "  文字、字号、颜色、离刻度的距离、上下左右微调、粗体斜体、\n"
            "  上下标大小和偏移，全都能单独调；上面白框是实时预览。\n"
            "  上下标写法：上标 x^{-1}、下标 F_{x}，多个字符用大括号。\n"
            "  上标/下标除了大小和上下，还能单独往左右挪。\n"
            "· 数据点逐个配色：在「数据点」页签最下面，每个点一行，\n"
            "  三个色块分别是填充色 / 竖线色 / 边线色，留空＝跟随该曲线。\n"
            "  点「用选中的颜色组填满」把当前配色套到每个点上；颜色比数据点\n"
            "  少时会自动循环。点「颜色组…」看颜色块挑一组，还能复制后改。\n"
            "· EIS 页签只在调 EIS 图时出现，其它图看不到它。\n"
            "· 「图片背景透明」勾上后，导出的 PNG 背景是透明的\n"
            "  （jpg 本身不支持透明，会自动存成不透明）。\n"
            "· 图例文字：在「图例」页签表格里整张一起改；\n"
            "  上标写 ^{-1}、下标写 _{x}（例：50 mV s^{-1}、Fe_{3}O_{4}）。\n"
            "  点文字那列就能改，改完回车生效，还能再点进去接着改。\n"
            "· 坐标轴范围：在「刻度/轴」页签底部四个框里填数值就锁死，\n"
            "  以后改配色、字号都不会被弹回去；留空＝自动。\n"
            "  或者先用图下工具条的「框选放大」调好，再点\n"
            "  「把当前范围填到设置里」。\n\n"
            "颜色怎么挑：\n"
            "· 选单个颜色：所有色块按钮点一下都弹调色盘，\n"
            "  里面分「标准色 / RGB / 滑块」三页，随便挑。\n"
            "· 选一整套：调色盘里的「配色方案」页，点一下就用；\n"
            "  自己存的方案可以在那儿改名、删除、整套用上。\n"
            "· 保存配色：只问名字，固定存在\n"
            "  %s\n"
            "  同名不会覆盖，自动加序号。\n"
            "· 用过的颜色和配色方案会自动记住，下次打开就在\n"
            "  调色盘的「我用过」和「配色方案」页里。\n\n"
            "· 直接输出：按当前参数把全部图片输出到目标文件夹，"
            "输出后自动打开结果文件夹。"
            % ecpal.PALETTE_DIR)

    def set_theme(self, name):
        self.theme = name
        apply_theme(QApplication.instance(), name)

    # ---------------- 日志与后台 ----------------
    def _drain_log(self):
        buf, done, preview, open_dir = [], False, False, False
        cached_preview = False
        output_ready = output_finished = None
        warn_anom = 0
        try:
            while True:
                s = self.log_q.get_nowait()
                if isinstance(s, tuple) and s[0] == "job_result":
                    result = s[1]
                    if result.get("kind") == "scan":
                        self._populate_scan(result["files"], result["skipped"], result["cfg"])
                        continue
                    if result.get("kind") == "preview_ready":
                        cached_preview = True
                    if result.get("kind") == "output_ready":
                        output_ready = result
                    if result.get("kind") == "output_finished":
                        output_finished = result
                        continue
                    self._last_data = result["data"]
                    self._last_signature = result["signature"]
                    self._last_workbook = result.get("workbook", self._last_workbook)
                    self._pending = self._last_data
                    warn_anom = len(self._last_data.get("anomalies") or [])
                    continue
                if isinstance(s, tuple) and s[0] == "job_error":
                    self._job_error = s[1]
                    continue
                if s == "<<DONE>>":
                    done = True
                elif s == "<<PREVIEW>>":
                    preview = True
                elif s == "<<OPEN_DIR>>":
                    open_dir = True
                elif s.startswith("<<WARN_ANOM:"):
                    try:
                        warn_anom = int(s[13:-2])
                    except Exception:
                        warn_anom = 0
                else:
                    buf.append(s)
        except queue.Empty:
            pass
        if buf:
            self.log.append("".join(buf).rstrip())
        if warn_anom:
            self._warn_anomaly()
        if preview:
            self._open_preview()
        if open_dir:
            try:
                os.startfile(self.output_cfg.get("dir") or eclab.OUTPUT_DIR)
            except Exception:
                pass
        if done:
            self._running = False
            self.centralWidget().setEnabled(True)
            self._main_toolbar.setEnabled(True)
            self.menuBar().setEnabled(True)
            self.statusBar().showMessage("处理失败，请查看日志" if self._job_error else "完成")
            if self._job_error:
                QMessageBox.warning(self, "处理未完成", self._job_error)
                self._job_error = None
        if cached_preview:
            self._show_preview_dialog()
        if output_ready:
            self._choose_plot_output(output_ready["data"], output_ready["cfg"])
        if output_finished:
            from ec_output_dialog import offer_open_folder
            offer_open_folder(self, output_finished["folder"], len(output_finished["files"]))

    def _warn_anomaly(self):
        """弹窗列出物理上不合理的结果，拦一道，别让错数据流进论文"""
        anom = (getattr(self, "_pending", None) or {}).get("anomalies")
        if not anom:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("结果有异常，请先核对")
        box.setText("有 %d 处计算结果在物理上不合理：\n\n%s"
                    % (len(anom),
                       "\n".join("· " + str(a) for a in anom[:6])))
        if len(anom) > 6:
            box.setText(box.text() + "\n…（其余 %d 条见下方日志）"
                        % (len(anom) - 6))
        box.setInformativeText("这些数不能直接抄进论文。\n"
                               "常见原因：样品起始没放空、测试圈数太少、"
                               "质量登记错了。")
        box.setDetailedText("\n\n".join(str(a) for a in anom))
        box.exec()

    def _open_preview(self):
        data = self._pending
        self._pending = None
        if data is None:
            return
        self._last_data = data
        if not eclab.preview_list(data):
            QMessageBox.information(self, "没有可画的图",
                                    "这批数据没算出可作图的结果。")
            return
        dlg = PreviewDialog(self, data, data["cfg"])
        if dlg.exec():
            cfg = dlg.final_cfg()
            self.style_cfg = cfg.get("plot_style", self.style_cfg)
            self.style_by_kind = cfg.get("plot_style_by_kind",
                                         self.style_by_kind)
            out = cfg.get("output", {})
            self.output_cfg = {
                "formats": out.get("formats", self.output_cfg["formats"]),
                "dpi": out.get("dpi", self.output_cfg["dpi"]),
                "dir": out.get("dir", self.output_cfg["dir"])}
            self.lab_out.setText(self.output_cfg["dir"])
            for k, c in self.fmt_boxes.items():
                c.setChecked(k in self.output_cfg["formats"])
            self._do_render(data, cfg)
        else:
            self._append("已取消，没有输出任何图片")
        self._running = False     # 关闭预览后必复位，"开始处理"随时可再点
        self.statusBar().showMessage("就绪")

    def open_preview(self):
        self._prepare_for_plot("preview_ready")

    def _prepare_for_plot(self, action):
        if self._running:
            return
        cfg = self._processing_cfg(validate_destination=False)
        if cfg is None:
            return
        previous, previous_signature = self._last_data, self._last_signature
        def work():
            signature = calculation_signature(cfg)
            data = previous if previous is not None and signature == previous_signature else eclab.prepare(cfg)
            if not eclab.preview_list(data, cfg):
                raise ValueError("没有可绘制的数据，请检查文件选择、质量与日志中的跳过原因。")
            return {"kind": action, "data": data, "signature": signature, "cfg": cfg}
        self._start_job(work, "正在准备图形数据…")

    def _show_preview_dialog(self):
        dlg = PreviewDialog(self, self._last_data, self.current_cfg())
        if dlg.exec():
            cfg = dlg.final_cfg()
            self.style_cfg = cfg.get("plot_style", self.style_cfg)
            self.style_by_kind = cfg.get("plot_style_by_kind",
                                         self.style_by_kind)
            out = cfg.get("output", {})
            self.output_cfg = {
                "formats": out.get("formats", self.output_cfg["formats"]),
                "dpi": out.get("dpi", self.output_cfg["dpi"]),
                "dir": out.get("dir", self.output_cfg["dir"])}
            self.lab_out.setText(self.output_cfg["dir"])
            if hasattr(self, "lab_out_bar"):
                self.lab_out_bar.setText("输出：" + self.output_cfg["dir"])
            for k, c in self.fmt_boxes.items():
                c.setChecked(k in self.output_cfg["formats"])
            self._append("参数已保存，点「直接输出」按新参数出图。")

    def _do_render(self, data, cfg):
        if self._running:
            return
        try:
            cfg["output"]["dir"] = validate_output(cfg, eclab.OUTPUT_DIR)
        except ValueError as exc:
            QMessageBox.warning(self, "请选择输出位置", str(exc))
            return
        def work():
            eclab.render(data, cfg)
            print("[完成] 图片与 Excel 已保存到：" + cfg["output"]["dir"])
        self._start_job(work, "正在输出图片…")

    def _start_job(self, work, message):
        """One computation/export at a time; all widget access stays on the UI thread."""
        if self._running or (self.workspaces and self.workspaces.is_busy()):
            return
        self._running = True
        self._job_error = None
        self.centralWidget().setEnabled(False)
        self._main_toolbar.setEnabled(False)
        self.menuBar().setEnabled(False)
        self.statusBar().showMessage(message)
        def worker():
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = sys.stderr = QueueWriter(self.log_q)
                result = work()
                if result is not None:
                    self.log_q.put(("job_result", result))
            except Exception as exc:
                self.log_q.put("\n[出错]\n" + traceback.format_exc() + "\n")
                self.log_q.put(("job_error", str(exc)))
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
                self.log_q.put("<<DONE>>")
        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def open_plot_studio(self):
        if self._running:
            return
        if self.workspaces:
            self.workspaces.show_plot(self._last_workbook)
            return
        from ec_plot_studio import PlotStudio
        PlotStudio(self, initial_path=self._last_workbook).exec()

    def open_conductivity(self):
        if self._running:
            return
        if self.workspaces:
            self.workspaces.show_data("cdi")
            return
        from ec_legacy_ui import LegacyExcelDialog
        dialog = LegacyExcelDialog(self, mode="cdi", output_dir=self.output_cfg.get("dir"))
        dialog.exec()
        if dialog.result_files:
            self._last_workbook = dialog.result_files[0]

    # ---------------- 配置 ----------------
    @staticmethod
    def _parse_segs(text):
        out = []
        for x in str(text).replace("，", ",").replace(" ", ",").split(","):
            if not x:
                continue
            try:
                out.append(int(float(x)))
            except ValueError:
                continue
        return out

    def current_cfg(self, include_files=True):
        cv_segs = (self._parse_segs(self.ed_cv_segs.text())
                   if self.ck_cv_segs.isChecked() else [])
        gcd_segs = (self._parse_segs(self.ed_gcd_segs.text())
                    if self.ck_gcd_segs.isChecked() else [])
        cfg = {
            "protected_data_dirs": ["E:/Data"] if os.name == "nt" else [],
            "data_dir": [self.dir_list.item(i).text()
                         for i in range(self.dir_list.count())],
            "area_cm2": self.sp_area.value(),
            "pick_segments": [2, 3],
            "cv_segments": cv_segs,
            "gcd_segments": gcd_segs,
            "cycle_start": self.sp_cstart.value(),
            "cycle_step": self.sp_cstep.value(),
            "cv_cycle_start": (self.sp_cv_cstart.value()
                               if self.ck_cv_cyc.isChecked()
                               else self.sp_cstart.value()),
            "cv_cycle_step": (self.sp_cv_cstep.value()
                              if self.ck_cv_cyc.isChecked()
                              else self.sp_cstep.value()),
            "gcd_cycle_start": (self.sp_gcd_cstart.value()
                                if self.ck_gcd_cyc.isChecked()
                                else self.sp_cstart.value()),
            "gcd_cycle_step": (self.sp_gcd_cstep.value()
                               if self.ck_gcd_cyc.isChecked()
                               else self.sp_cstep.value()),
            "skip_keywords_cv": (["活化"] if self.ck_skip_act.isChecked()
                                 else []),
            "ir_free": self.ck_ir.isChecked(),
            "gcd_continuous": self.ck_cont.isChecked(),
            "dedupe_condition": self.ck_dedupe.isChecked(),
            "exclude_filename": ["-fit", "副本"],
            "mass_mg": dict(self.mass_override),
            "eis": {
                "fit": self.ck_fit.isChecked(),
                "circuit": self._circuit_code(),
                "use_external_fit": self.ck_extfit.isChecked(),
                "export_zview": False,
            },
            "output": {"formats": [k for k, c in self.fmt_boxes.items()
                                   if c.isChecked()] or ["png"],
                       "dpi": self.sp_dpi.value(),
                       "dir": self.output_cfg.get("dir", eclab.OUTPUT_DIR)},
            "plot_style": json.loads(json.dumps(self.style_cfg)),
            "plot_style_by_kind": json.loads(
                json.dumps(self.style_by_kind or {})),
        }
        if include_files:
            checked = []
            for r in range(self.table.rowCount()):
                if self.table.item(r, 0).checkState() == Qt.Checked:
                    checked.append(self.table.item(r, 2).data(Qt.UserRole))
            if checked and len(checked) < self.table.rowCount():
                cfg["include_files"] = checked
        return cfg

    def _apply_cfg(self, cfg):
        # 文件夹路径只进"最近用过"的记忆，不再自动塞进列表：
        # 列表里一旦显示，左边就必须有文件，否则看着像程序坏了
        for d in eclab.dirs_of(cfg):
            self._remember_dir(d, add=False)
        if not getattr(self, "_startup", False):
            self.dir_list.clear()
            for d in eclab.dirs_of(cfg):
                self.dir_list.addItem(d)
        self.sp_area.setValue(float(cfg.get("area_cm2", 1.0)))
        segs = cfg.get("pick_segments") or [2, 3]
        cv_segs = cfg.get("cv_segments") or []
        self.ck_cv_segs.setChecked(bool(cv_segs))
        self.ed_cv_segs.setText(", ".join(str(x) for x in cv_segs) or
                               ", ".join(str(x) for x in segs))
        gcd_segs = cfg.get("gcd_segments") or []
        self.ck_gcd_segs.setChecked(bool(gcd_segs))
        self.ed_gcd_segs.setText(", ".join(str(x) for x in gcd_segs) or
                                ", ".join(str(x) for x in segs))
        self.sp_cstart.setValue(int(cfg.get("cycle_start", 30)))
        self.sp_cstep.setValue(int(cfg.get("cycle_step", 10)))
        self.ck_cv_cyc.setChecked("cv_cycle_start" in cfg)
        self.sp_cv_cstart.setValue(int(cfg.get("cv_cycle_start",
                                               cfg.get("cycle_start", 30))))
        self.sp_cv_cstep.setValue(int(cfg.get("cv_cycle_step",
                                              cfg.get("cycle_step", 10))))
        self.ck_gcd_cyc.setChecked("gcd_cycle_start" in cfg)
        self.sp_gcd_cstart.setValue(int(cfg.get("gcd_cycle_start",
                                                cfg.get("cycle_start", 30))))
        self.sp_gcd_cstep.setValue(int(cfg.get("gcd_cycle_step",
                                               cfg.get("cycle_step", 10))))
        self.ck_cont.setChecked(bool(cfg.get("gcd_continuous", False)))
        self.ck_skip_act.setChecked(bool(cfg.get("skip_keywords_cv")
                                         or ["活化"]))
        self.ck_ir.setChecked(bool(cfg.get("ir_free", False)))
        self.ck_dedupe.setChecked(bool(cfg.get("dedupe_condition", True)))
        eis = cfg.get("eis", {})
        if "eis_fit" in cfg and not eis:
            eis = {"fit": bool(cfg["eis_fit"])}
        self.ck_fit.setChecked(bool(eis.get("fit", True)))
        circuit = eis.get("circuit", "auto")
        idx = {"auto": 0, "W": 1, "Wo": 2, "Ws": 3}.get(circuit)
        if idx is not None:
            self.cb_circuit.setCurrentIndex(idx)
        else:
            self.cb_circuit.setCurrentText(str(circuit))   # 自定义电路
        self.ck_extfit.setChecked(bool(eis.get("use_external_fit", True)))
        self.mass_override = {k: v for k, v in cfg.get("mass_mg", {}).items()
                              if not k.startswith("_")}
        if cfg.get("plot_style"):
            merged = json.loads(json.dumps(eclab.DEFAULT_STYLE))
            merged = eclab.deep_merge(merged, cfg["plot_style"])
            self.style_cfg = merged
        self.style_by_kind = dict(cfg.get("plot_style_by_kind") or {})
        out = cfg.get("output") or {}
        self.output_cfg = {"formats": out.get("formats", ["png", "pdf"]),
                           "dpi": out.get("dpi", 600),
                           "dir": out.get("dir") or eclab.OUTPUT_DIR}
        self.sp_dpi.setValue(int(self.output_cfg["dpi"]))
        self.lab_out.setText(self.output_cfg["dir"])
        if hasattr(self, "lab_out_bar"):
            self.lab_out_bar.setText("输出：" + self.output_cfg["dir"])
        for k, c in self.fmt_boxes.items():
            c.setChecked(k in self.output_cfg["formats"])
        if self.workspaces:
            self.workspaces.set_output_dir(self.output_cfg["dir"])

    # ---------------- 事件 ----------------
    def _circuit_code(self):
        """下拉框文字 -> 引擎电路代码；自定义文字原样传给引擎

        先 strip 去首尾空格，避免「auto 」这类带尾随空格的输入
        原样进引擎后匹配不到任何代码，被当成未知电路误报“无法收敛”。
        """
        txt = self.cb_circuit.currentText().strip()
        for key, code in (("自动择优", "auto"), ("+W)", "W"),
                          ("+Wo)", "Wo"), ("+Ws)", "Ws")):
            if key in txt:
                return code
        return txt or "auto"

    def _recent_dir(self):
        """添加文件夹时对话框的初始位置：优先用上次添加过的路径，
        没有记录就给空串——交给系统打开上次浏览的位置，不再强制跳文档。"""
        for d in self._dir_history:
            if d and os.path.isdir(d):
                return d
        return ""

    def _remember_dir(self, d, add=True):
        """记进"最近用过"的列表（最多 15 条，最新在前）"""
        if not d:
            return
        nd = os.path.normpath(d)
        hist = [x for x in self._dir_history
                if os.path.normpath(x or "") != nd]
        hist.insert(0, d)
        self._dir_history = hist[:15]
        if add:
            exists = any(
                os.path.normpath(self.dir_list.item(i).text()) == nd
                for i in range(self.dir_list.count()))
            if not exists:
                self.dir_list.addItem(d)

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择数据文件夹",
                                             self._recent_dir())
        if d:
            self._remember_dir(d)
            self.scan()          # 添加文件夹后自动扫描，不用再多点一下

    def quick_render(self):
        self._prepare_for_plot("output_ready")

    def _choose_plot_output(self, data, cfg):
        from ec_output_dialog import OutputSelectionDialog, render_selected
        from ec_export import input_directories
        dlg = OutputSelectionDialog(self, eclab.preview_list(data, cfg),
            cfg["output"].get("dir") or eclab.OUTPUT_DIR,
            cfg["output"].get("formats", ["png"]), input_directories(data, cfg))
        if not dlg.exec():
            self._append("已取消输出，没有保存图片。")
            return
        cfg["output"]["dir"] = dlg.output_dir
        cfg["output"]["formats"] = dlg.formats
        self.output_cfg.update(cfg["output"])
        self.lab_out.setText(dlg.output_dir)
        self.lab_out_bar.setText("输出：" + dlg.output_dir)
        for fmt, box in self.fmt_boxes.items():
            box.setChecked(fmt in dlg.formats)
        selected = dlg.selection
        def work():
            files = render_selected(data, cfg, selected)
            print("已保存：\n" + "\n".join(files))
            return {"kind": "output_finished", "folder": dlg.output_dir, "files": files}
        self._start_job(work, "正在输出选中的图片…")

    def remove_dir(self):
        for item in self.dir_list.selectedItems():
            self.dir_list.takeItem(self.dir_list.row(item))

    def choose_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹",
                                             self.output_cfg["dir"])
        if d:
            self.output_cfg["dir"] = d
            self.lab_out.setText(d)
            if hasattr(self, "lab_out_bar"):
                self.lab_out_bar.setText("输出：" + d)
            if self.workspaces:
                self.workspaces.set_output_dir(d)

    def open_out_dir(self):
        try:
            folder = self.workspaces.result_directory() if self.workspaces else self.output_cfg.get("dir")
            os.startfile(folder or eclab.OUTPUT_DIR)
        except Exception as exc:
            QMessageBox.warning(self, "打不开", str(exc))

    def _view_error_log(self):
        """打开统一错误日志：报错和查看报错都在这一个文件里"""
        try:
            d = os.path.dirname(ERROR_LOG)
            os.makedirs(d, exist_ok=True)
            if not os.path.isfile(ERROR_LOG):
                open(ERROR_LOG, "w", encoding="utf-8").close()
            os.startfile(ERROR_LOG)
        except Exception as exc:
            QMessageBox.warning(self, "打不开", str(exc))

    def scan(self):
        if self._running:
            return
        cfg = self.current_cfg(include_files=False)
        if not cfg["data_dir"]:
            QMessageBox.information(self, "提示", "请先添加数据文件夹")
            return
        def work():
            files, skipped = eclab.scan_files(cfg)
            if sum(len(paths) for paths in files.values()) > 5000:
                raise ValueError("一次扫描超过 5000 个实验文件，请选择具体样品的子文件夹。")
            return {"kind": "scan", "files": files, "skipped": skipped, "cfg": cfg}
        self._start_job(work, "正在扫描文件，窗口保持响应…")

    def _populate_scan(self, files, skipped, cfg):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for kind in ("CV", "GCD", "EIS"):
            for path in files[kind]:
                tag = eclab.unique_tag(path, cfg["data_dir"])
                key = os.path.splitext(os.path.basename(path))[0]
                if kind == "EIS":
                    mg, src = "—", "不需要"
                else:
                    mg_v = self.mass_override.get(
                        tag, self.mass_override.get(key))
                    if mg_v is not None:
                        mg, src = f"{mg_v:g}", "手动/模板"
                    else:
                        mg_v = eclab.mass_from_name([tag, key, path])
                        mg, src = ((f"{mg_v:g}", "文件名") if mg_v
                                   else ("", "待填写"))
                r = self.table.rowCount()
                self.table.insertRow(r)
                ck = QTableWidgetItem()
                ck.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                            | Qt.ItemIsSelectable)
                ck.setCheckState(Qt.Checked)
                ck.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 0, ck)
                it_k = QTableWidgetItem(kind)
                it_k.setFlags(it_k.flags() & ~Qt.ItemIsEditable)
                it_k.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 1, it_k)
                it = QTableWidgetItem(tag)
                it.setData(Qt.UserRole, os.path.abspath(path))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if kind == "EIS":
                    it.setForeground(QColor(
                        THEMES.get(self.theme, THEMES["classic"])["muted"]))
                self.table.setItem(r, 2, it)
                mgi = QTableWidgetItem(mg)
                mgi.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 3, mgi)
                its = QTableWidgetItem(src)
                its.setFlags(its.flags() & ~Qt.ItemIsEditable)
                its.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 4, its)
                # 创建日期列
                try:
                    import datetime
                    mtime = os.path.getmtime(path)
                    dt_str = datetime.datetime.fromtimestamp(
                        mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    dt_str = "—"
                it_dt = QTableWidgetItem(dt_str)
                it_dt.setFlags(it_dt.flags() & ~Qt.ItemIsEditable)
                it_dt.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, 5, it_dt)
        self.table.blockSignals(False)
        self._fit_name_col()
        self._update_count()
        self._append(f"扫描完成：CV {len(files['CV'])} | GCD "
                     f"{len(files['GCD'])} | EIS {len(files['EIS'])}"
                     f"（另有 {len(skipped)} 个按规则排除）")

    def _check_selected(self, state):
        """把选中的行批量勾上/取消（拖选或 Ctrl 点选后一键操作）"""
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            self._append("没有选中的行（先用鼠标拖选或 Ctrl 点选）")
            return
        self.table.blockSignals(True)
        for r in rows:
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(state)
        self.table.blockSignals(False)
        self._update_count()
        self._append(f"已{'勾选' if state == Qt.Checked else '取消勾选'}"
                     f" {len(rows)} 行")

    def _check_all(self, state):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)
        self.table.blockSignals(False)
        self._update_count()

    def _invert_all(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked
                            else Qt.Checked)
        self.table.blockSignals(False)
        self._update_count()

    def _clamp_col(self, idx, _old, new):
        """列被拖到小于最小宽度时顶回去，防止整列消失"""
        if getattr(self, "_clamping", False):
            return
        if idx == 2:
            self._name_locked = True      # 用户拖过就不抢了
        m = (self._col_min or {}).get(idx)
        if m and new < m:
            self._clamping = True
            try:
                self.table.setColumnWidth(idx, m)
            finally:
                self._clamping = False

    def _on_header_clicked(self, idx):
        if idx == 0:                    # 点"处理 ✓"表头 = 全选 / 全不选
            first = self.table.item(0, 0) if self.table.rowCount() else None
            all_on = first is not None and first.checkState() == Qt.Checked
            self._check_all(Qt.Unchecked if all_on else Qt.Checked)
        else:
            self._sort_by_column(idx)

    def _sort_by_column(self, col):
        """点击表头排序：类型/文件名/质量/来源/日期"""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc   # 同列再点 = 反向
        else:
            self._sort_col = col
            self._sort_asc = True

        # 收集所有行数据
        rows = []
        for r in range(self.table.rowCount()):
            row_data = {
                "checked": self.table.item(r, 0).checkState() == Qt.Checked,
                "kind": self.table.item(r, 1).text(),
                "name": self.table.item(r, 2).text(),
                "path": self.table.item(r, 2).data(Qt.UserRole) or "",
                "mass": self.table.item(r, 3).text(),
                "src": self.table.item(r, 4).text(),
                "date": self.table.item(r, 5).text() if self.table.item(r, 5) else "",
                "eis_dim": (self.table.item(r, 2).foreground().color().name()
                            != "#000000" and self.table.item(r, 1).text() == "EIS"),
            }
            rows.append(row_data)

        # 排序键
        def sort_key(rd):
            if col == 1:    # 类型
                order = {"CV": 0, "GCD": 1, "EIS": 2}
                return (order.get(rd["kind"], 9), rd["name"])
            elif col == 2:  # 文件名
                return rd["name"].lower()
            elif col == 3:  # 质量（数值排序，空/— 排最后）
                try:
                    return (0, float(rd["mass"]))
                except (ValueError, TypeError):
                    return (1, 0)
            elif col == 4:  # 来源
                return rd["src"]
            elif col == 5:  # 日期
                return rd["date"]
            return rd["name"]

        rows.sort(key=sort_key, reverse=not self._sort_asc)

        # 重新填入
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for rd in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            ck = QTableWidgetItem()
            ck.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                        | Qt.ItemIsSelectable)
            ck.setCheckState(Qt.Checked if rd["checked"] else Qt.Unchecked)
            ck.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 0, ck)
            it_k = QTableWidgetItem(rd["kind"])
            it_k.setFlags(it_k.flags() & ~Qt.ItemIsEditable)
            it_k.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, it_k)
            it = QTableWidgetItem(rd["name"])
            it.setData(Qt.UserRole, rd["path"])
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if rd["eis_dim"]:
                it.setForeground(QColor(
                    THEMES.get(self.theme, THEMES["classic"])["muted"]))
            self.table.setItem(r, 2, it)
            mgi = QTableWidgetItem(rd["mass"])
            mgi.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, mgi)
            its = QTableWidgetItem(rd["src"])
            its.setFlags(its.flags() & ~Qt.ItemIsEditable)
            its.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 4, its)
            it_dt = QTableWidgetItem(rd["date"])
            it_dt.setFlags(it_dt.flags() & ~Qt.ItemIsEditable)
            it_dt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 5, it_dt)
        self.table.blockSignals(False)

        arrow = " ↑" if self._sort_asc else " ↓"
        col_name = {1: "类型", 2: "文件名", 3: "质量", 4: "来源", 5: "日期"}.get(col, "")
        self._append(f"按 {col_name}{arrow} 排序")

    def _update_count(self):
        n = self.table.rowCount()
        c = sum(1 for r in range(n)
                if self.table.item(r, 0).checkState() == Qt.Checked)
        sel = len({i.row() for i in self.table.selectedIndexes()})
        self.lab_count.setText(f"共 {n} 个文件，已勾选 {c} 个"
                               + (f"，选中 {sel} 行" if sel else ""))

    def _delete_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._update_count()

    def _on_cell_changed(self, row, col):
        if col != 3:
            return
        tag = self.table.item(row, 2).text()
        kind = self.table.item(row, 1).text()
        txt = self.table.item(row, 3).text().strip()
        if kind == "EIS":
            return
        try:
            self.mass_override[tag] = float(txt) if txt else None
        except ValueError:
            return
        if self.mass_override[tag] is None:
            del self.mass_override[tag]
        self.table.blockSignals(True)
        self.table.setItem(row, 4, QTableWidgetItem(
            "手动/模板" if txt else "待填写"))
        self.table.blockSignals(False)

    def open_plot_settings(self):
        """绘图模板：主打加载 / 保存模板，也能进完整绘图设置"""
        box = QMessageBox(self)
        box.setWindowTitle("绘图模板")
        box.setText("要对绘图样式做什么？")
        b_load = box.addButton("加载模板…", QMessageBox.AcceptRole)
        b_save = box.addButton("保存当前为模板…", QMessageBox.DestructiveRole)
        b_full = box.addButton("打开完整绘图设置…", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_load:
            self.load_template("绘图模板")
        elif clicked is b_save:
            self.save_template("绘图模板")
        elif clicked is b_full:
            self._open_full_style_dialog()

    def _open_full_style_dialog(self):
        styles = dict(self.style_by_kind)
        styles["cv_overlay"] = self.style_cfg
        dlg = PlotStyleDialog(self, styles, self.output_cfg)
        if dlg.exec():
            styles, out = dlg.result_values()
            self.style_cfg = styles.get("cv_overlay", self.style_cfg)
            self.style_by_kind = {k: v for k, v in styles.items()
                                  if k != "cv_overlay"}
            self.output_cfg["formats"] = out.get(
                "formats", self.output_cfg["formats"])
            self.output_cfg["dpi"] = out.get("dpi", self.output_cfg["dpi"])
            for k, c in self.fmt_boxes.items():
                c.setChecked(k in self.output_cfg["formats"])

    def run(self):
        if self._running:
            return
        from ec_legacy_ui import LegacyExcelDialog
        paths, masses = [], set()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() != Qt.Checked:
                continue
            if self.table.item(row, 1).text() == "EIS":
                continue
            paths.append(self.table.item(row, 2).data(Qt.UserRole))
            try:
                masses.add(float(self.table.item(row, 3).text()))
            except ValueError:
                pass
        dialog = LegacyExcelDialog(self, paths=paths, mass_mg=next(iter(masses)) if len(masses)==1 else None,
                                   output_dir=self.output_cfg.get("dir"))
        if len(masses)>1:
            dialog.log.appendPlainText("所选文件有多个质量，请按同一样品、同一质量分批生成原样 Excel，并核对本次质量。")
            dialog.files.clear()
        dialog.exec()
        if dialog.result_files:
            self._last_workbook = dialog.result_files[0]
            self._append("原样 Excel 已生成：\n" + "\n".join(dialog.result_files))
        if dialog.want_analysis:
            self.run_analysis()

    def run_analysis(self):
        if self._running:
            return
        cfg = self._processing_cfg()
        if cfg is None:
            return
        def work():
            signature = calculation_signature(cfg)
            data = eclab.prepare(cfg)
            workbook = eclab.export_tables(data, cfg)
            if not workbook:
                raise ValueError("没有可导出的数据。请检查样品质量、文件勾选和日志中的跳过原因。")
            print("\n[处理完成] Excel 已保存：" + str(workbook))
            print("点击「Excel 一键绘图」可选科研模板出图；也可以打开「预览图形」调整详细样式。")
            return {"data": data, "signature": signature, "workbook": str(workbook)}
        self._start_job(work, "正在处理数据并保存 Excel…")

    def _processing_cfg(self, validate_destination=True):
        cfg = self.current_cfg()
        if not cfg["data_dir"]:
            QMessageBox.information(self, "提示", "请先添加数据文件夹")
            return None
        for r in range(self.table.rowCount()):
            if self.table.item(r, 1).text() == "EIS":
                continue
            txt = self.table.item(r, 3).text().strip()
            tag = self.table.item(r, 2).text()
            try:
                v = float(txt)
            except ValueError:
                cfg["mass_mg"].pop(tag, None)
            else:
                cfg["mass_mg"][tag] = v
        self.mass_override = dict(cfg["mass_mg"])
        if self.table.rowCount() and not any(
                self.table.item(r, 0).checkState() == Qt.Checked
                for r in range(self.table.rowCount())):
            QMessageBox.information(self, "提示", "没有勾选任何文件")
            return None
        if validate_destination:
            try:
                cfg["output"]["dir"] = validate_output(cfg, eclab.OUTPUT_DIR)
            except ValueError as exc:
                QMessageBox.warning(self, "请选择输出位置", str(exc))
                return None
        return cfg

    # ---------------- 模板 ----------------
    def save_template(self, kind):
        if kind == "绘图模板":
            data = {"_模板类型": "绘图模板",
                    "_说明": "画图外观（每张图各一套）+ 输出格式",
                    "plot_style": self.style_cfg,
                    "plot_style_by_kind": self.style_by_kind,
                    "output": {k: v for k, v in self.output_cfg.items()
                               if k != "dir"}}
            default = os.path.join(BASE_DIR, "绘图模板.json")
        else:
            data = self.current_cfg(include_files=False)
            for k in ("plot_style", "plot_style_by_kind", "output"):
                data.pop(k, None)
            data["_模板类型"] = "数据处理模板"
            default = os.path.join(BASE_DIR, "数据处理模板.json")
        path, _ = QFileDialog.getSaveFileName(
            self, f"保存{kind}", default, "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._append(f"{kind}已保存：{path}")

    def load_template(self, kind):
        path, _ = QFileDialog.getOpenFileName(
            self, f"加载{kind}", BASE_DIR, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            try:      # 模板里空的 titles 同样是老写法，先迁一遍
                eclab._migrate_titles(data)
            except Exception:
                pass
            t = data.get("_模板类型")
            if t and t != kind:
                QMessageBox.warning(
                    self, "类型不符",
                    f"这是「{t}」，不能当「{kind}」加载。")
                return
            if kind == "绘图模板":
                merged = json.loads(json.dumps(eclab.DEFAULT_STYLE))
                merged = eclab.deep_merge(merged, data.get("plot_style", {}))
                self.style_cfg = merged
                self.style_by_kind = dict(data.get("plot_style_by_kind") or {})
                out = data.get("output") or {}
                self.output_cfg["formats"] = out.get(
                    "formats", self.output_cfg["formats"])
                self.output_cfg["dpi"] = out.get("dpi",
                                                 self.output_cfg["dpi"])
                for k, c in self.fmt_boxes.items():
                    c.setChecked(k in self.output_cfg["formats"])
            else:
                self._apply_cfg(data)
            self._append(f"{kind}已加载：{path}")
        except Exception as exc:
            QMessageBox.warning(self, "加载失败", str(exc))

    def _first_run_bootstrap(self):
        """首次运行：把打包的默认 config.json 复制到 exe 旁边"""
        if os.path.isfile(CONFIG_PATH):
            return
        bundled = os.path.join(_MEI, "config.json")
        if os.path.isfile(bundled):
            try:
                import shutil
                shutil.copy2(bundled, CONFIG_PATH)
            except Exception:
                pass

    def _load_config_file(self, path, silent=False):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 老配置里空的 axis.titles 以前是"用默认标题"，现在改成
            # "真的不画"，所以读进来先迁一遍（迁过的有标记位，不重复做）
            try:
                eclab._migrate_titles(cfg)
            except Exception:
                pass
            self._cfg_comments = {k: v for k, v in cfg.items()
                                  if k.startswith("_")}
            self._apply_cfg(cfg)
            th = self._cfg_comments.get("_主题")
            if th in THEMES:
                self.set_theme(th)
            if not silent:
                self._append(f"已加载：{path}")
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, "加载失败", str(exc))

    def _append(self, s):
        self.log.append(s.rstrip())

    def closeEvent(self, event):
        if self._running or (self.workspaces and self.workspaces.is_busy()):
            self.statusBar().showMessage("正在处理，请等待完成后再关闭，以免中断文件写入。")
            event.ignore()
            return
        try:
            merged = dict(self._cfg_comments)
            merged.update(self.current_cfg(include_files=False))
            # 列表可能被清空了，但"最近用过"的文件夹要接着记住，下次好加回来
            all_dirs = list(merged.get("data_dir") or [])
            for d in self._dir_history:
                nd = os.path.normpath(d)
                if not any(os.path.normpath(x) == nd for x in all_dirs):
                    all_dirs.append(d)
            merged["data_dir"] = all_dirs[:15]
            merged["_主题"] = self.theme
            # 走保险箱：写回前自动备份 + 原子替换，手抖改坏也不丢设置
            ok, msg = cfg_guard.save_config(merged)
            if not ok:
                self._append(f"[警告] 设置没能保存（{msg}），"
                             f"下次打开会沿用上次的设置")
        except Exception as exc:
            self._append(f"[警告] 保存设置时出错：{exc}")
        event.accept()


def _install_excepthook(app):
    """pythonw 启动时没有控制台，未捕获异常必须弹窗 + 写日志，
    否则程序出错会静默消失，用户只看到“双击没反应”."""
    log_path = ERROR_LOG
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def hook(exc_type, exc, tb):
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(detail + "\n")
        except Exception:
            pass
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle("程序出错")
            box.setText(f"{exc_type.__name__}: {exc}")
            box.setInformativeText(f"详细信息已写入：\n{log_path}")
            box.setDetailedText(detail)
            box.exec()
        except Exception:
            pass

    sys.excepthook = hook


def main():
    # 依赖自检：缺包时立刻弹窗说清楚怎么装，不让小白对着"双击没反应"发呆
    if not _check_deps(app_only=True):
        return

    # 高 DPI 适配：高分屏（2K/4K、125%/150% 缩放）上界面不模糊
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    app.setWindowIcon(app_icon())
    _install_excepthook(app)

    # 配置保险箱：坏文件自动恢复，并把提示弹给用户看
    try:
        cfg0, note = cfg_guard.load_config()
    except Exception:
        cfg0, note = {}, None
    th = (cfg0 or {}).get("_主题")
    theme = th if th in THEMES else "classic"
    apply_theme(app, theme)

    win = MainWindow()
    win.setWindowIcon(app_icon())
    win.show()

    if note:
        try:
            QMessageBox.information(win, "配置已自动修复", note)
        except Exception:
            pass

    sys.exit(app.exec())


def _check_deps(app_only=False):
    """启动前检查依赖。缺了就弹窗告诉怎么装，返回能不能继续。

    app_only=True 时不创建 QApplication（用 ctypes 弹窗，最稳）。
    """
    need = ["numpy", "pandas", "matplotlib", "scipy", "openpyxl"]
    if not app_only:
        need.append("PySide6")
    missing = []
    for m in need:
        try:
            __import__(m)
        except Exception:
            missing.append(m)

    if not missing:
        return True

    lines = ["软件缺少这些运行库：\n\n    " + "  ".join(missing),
             "\n\n最省事的解决办法（复制到命令行回车）：\n",
             '    "%s" -m pip install %s\n'
             % (sys.executable, " ".join(missing)),
             "\n如果提示网络不通，说明这台电脑暂时无法联网安装。",
             "\n可以改用打包好的 exe 版本，它自带所有库。"]
    text = "\n".join(lines)

    # 记一份日志，方便事后查
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        with open(ERROR_LOG, "a",
                  encoding="utf-8") as f:
            f.write("[依赖缺失] %s\n" % ", ".join(missing))
    except Exception:
        pass

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "CHI电化学一键绘图 缺少运行库", 0x10)
    except Exception:
        print(text)
    return False


if __name__ == "__main__":
    main()
