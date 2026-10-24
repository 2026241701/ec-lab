# -*- coding: utf-8 -*-
"""A small Qt plotting workbench. Source files are always read-only."""
from __future__ import annotations

import copy
import os

from PySide6.QtCore import QThread, QTimer, Qt, Signal, QSignalBlocker, QRectF
from PySide6.QtGui import QFont, QColor, QImage, QPainter, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QDoubleSpinBox, QSpinBox, QColorDialog, QDialogButtonBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

import ec_plotting as plotting


class _PreviewCanvas(FigureCanvasQTAgg):
    """Display-scale the Agg image without letting Qt change physical inches.

    This uses the same fixed-figure approach as ec_gui.固定画布; importing that
    large module here would couple the standalone workbench to the old window.
    """
    def resizeEvent(self, event):
        QWidget.resizeEvent(self, event)
        self.update()

    def paintEvent(self, event):
        self._draw_idle()
        if not hasattr(self, "renderer"):
            return
        pixels = memoryview(self.buffer_rgba())
        picture = QImage(pixels, pixels.shape[1], pixels.shape[0], QImage.Format_RGBA8888)
        painter = QPainter(self)
        try:
            painter.eraseRect(event.rect())
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(QRectF(self.rect()), picture)
        finally:
            painter.end()

    def mouseEventCoords(self, pos=None):
        if pos is None:
            pos = self.mapFromGlobal(QCursor.pos())
        elif hasattr(pos, "position"):
            pos = pos.position()
        elif hasattr(pos, "pos"):
            pos = pos.pos()
        return (pos.x() * self.figure.bbox.width / max(1, self.width()),
                (self.height() - pos.y()) * self.figure.bbox.height / max(1, self.height()))

    def blit(self, bbox=None):
        self.update()


class _PreviewFrame(QWidget):
    """Center one canvas at its figure ratio; resizing only scales the display."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.setMinimumHeight(110)

    def set_canvas(self, canvas):
        if self.canvas is not None and self.canvas is not canvas:
            self.canvas.hide()
            self.canvas.setParent(None)
        self.canvas = canvas
        canvas.setParent(self)
        self._fit_canvas()
        canvas.show()

    def _fit_canvas(self):
        if self.canvas is None:
            return
        fw, fh = self.canvas.figure.get_size_inches()
        scale = min(max(1, self.width()) / fw, max(1, self.height()) / fh)
        width, height = max(1, round(fw * scale)), max(1, round(fh * scale))
        self.canvas.setGeometry((self.width() - width) // 2, (self.height() - height) // 2,
                                width, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_canvas()


class _Work(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            result = self.function()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)


class PlotStudio(QDialog):
    """Standalone entry: PlotStudio(parent=None, initial_path=None).exec()."""
    busyChanged = Signal(bool)
    outputReady = Signal(str)

    def __init__(self, parent=None, initial_path=None, embedded=False):
        super().__init__(parent)
        self.embedded = embedded
        if embedded:
            self.setWindowFlags(Qt.Widget)
        self.setFont(QFont("Microsoft YaHei", 9))
        self.setWindowTitle("一键绘图 · Excel / CSV 工作台")
        self.resize(1180, 780)
        self.setMinimumSize(740, 500) if embedded else self.setMinimumSize(850, 580)
        self.book = None
        self.auto_specs = []
        self.worker = None
        self._busy = False
        self._populating = False
        self.last_output = ""
        self.output_dir = str(plotting.BASE_DIR / "output")
        self._active_auto_index = -1
        self._active_tab = 0
        self._manual_spec = None
        self._default_style = {}
        self._style_original = {}
        self._style_baseline = {}
        self._series_labels = []
        self._displayed_mapping = None
        self._outcome = None
        self._build()
        if initial_path:
            QTimer.singleShot(0, lambda: self.load_path(str(initial_path)))

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        top = QHBoxLayout()
        self.open_button = QPushButton("打开 Excel / CSV")
        self.open_button.clicked.connect(self._choose_file)
        self.recipe_button = QPushButton("恢复绘图配方…")
        self.recipe_button.setToolTip("恢复上次绘图所用的源文件与样式；加载样式模板不要求同一份数据。")
        self.recipe_button.clicked.connect(self._choose_recipe)
        self.path_label = QLabel("支持处理后的 Excel，也支持自己的数值表格")
        self.path_label.setWordWrap(True)
        top.addWidget(self.open_button)
        top.addWidget(self.recipe_button)
        top.addWidget(self.path_label, 1)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        self.options = QWidget()
        options_layout = QVBoxLayout(self.options)
        options_layout.setContentsMargins(0, 0, 8, 0)
        options_layout.addWidget(QLabel("图形列表"))
        self.tabs = QTabWidget()
        automatic = QWidget()
        automatic_layout = QVBoxLayout(automatic)
        auto_hint = QLabel("识别本软件导出的常用图，选择后即可预览。")
        auto_hint.setWordWrap(True)
        automatic_layout.addWidget(auto_hint)
        self.plot_list = QListWidget()
        self.plot_list.currentRowChanged.connect(self._auto_selected)
        automatic_layout.addWidget(self.plot_list)
        self.tabs.addTab(automatic, "常用图")

        manual = QWidget()
        form = QFormLayout(manual)
        self.sheet_combo = QComboBox()
        self.sheet_combo.currentIndexChanged.connect(self._sheet_selected)
        form.addRow("工作表", self.sheet_combo)
        self.x_combo = QComboBox()
        form.addRow("X 数值列", self.x_combo)
        self.y_list = QListWidget()
        self.y_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.y_list.setMinimumHeight(120)
        self.y_list.setToolTip("按住 Ctrl 选择多个 Y 列；同一张图的 Y 列请使用相同单位。")
        form.addRow("Y 列（可多选）", self.y_list)
        self.group_combo = QComboBox()
        form.addRow("按列分组", self.group_combo)
        self.mode_combo = QComboBox()
        for name, value in (("折线", "line"), ("折线与点", "line_points"), ("散点", "scatter")):
            self.mode_combo.addItem(name, value)
        form.addRow("图形", self.mode_combo)
        manual_hint = QLabel("第一行需为列名。保留原始采样顺序；空值显示为断点。多个 Y 列应使用相同单位。")
        manual_hint.setWordWrap(True)
        form.addRow(manual_hint)
        self.tabs.addTab(manual, "按列绘图")
        self.tabs.currentChanged.connect(self._tab_changed)
        options_layout.addWidget(self.tabs, 1)

        details = QFormLayout()
        self.preset_combo = QComboBox()
        for key, value in plotting.PRESETS.items():
            self.preset_combo.addItem(value["name"], key)
        details.addRow("全部图基础样式", self.preset_combo)
        self.preset_combo.setToolTip("影响所有未自定义的样式；各图手动设置优先。")
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        options_layout.addLayout(details)
        self.options.setMinimumWidth(200)
        self.options.setMaximumWidth(340)
        splitter.addWidget(self.options)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        current = QHBoxLayout()
        current.addWidget(QLabel("当前预览"))
        self.current_preview = QComboBox()
        self.current_preview.currentIndexChanged.connect(self._auto_selected)
        current.addWidget(self.current_preview, 1)
        self.preview_button = QPushButton("更新预览")
        self.preview_button.clicked.connect(self._preview)
        current.addWidget(self.preview_button)
        self.settings_button = QPushButton("绘图设置 ▸")
        self.settings_button.setCheckable(True)
        self.settings_button.toggled.connect(self._toggle_settings)
        current.addWidget(self.settings_button)
        right_layout.addLayout(current)
        self.canvas = _PreviewCanvas(Figure(figsize=(6.4, 4.5), dpi=100, facecolor="white"))
        self.preview_frame = _PreviewFrame()
        self.preview_frame.set_canvas(self.canvas)
        right_layout.addWidget(self.preview_frame, 1)
        self.plot_note = QLabel("打开表格后选择常用图；设置默认收起。")
        self.plot_note.setWordWrap(True)
        right_layout.addWidget(self.plot_note)
        self.canvas_layout = right_layout
        self.settings_panel = self._build_settings()
        self.settings_panel.hide()
        right_layout.addWidget(self.settings_panel)
        splitter.addWidget(right)
        splitter.setSizes([240, 920])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        output = QHBoxLayout()
        output.addWidget(QLabel("输出格式"))
        self.format_boxes = {}
        for extension in ("png", "pdf", "svg"):
            box = QCheckBox(extension.upper())
            box.setChecked(True)
            output.addWidget(box)
            self.format_boxes[extension] = box
        output.addStretch()
        self.export_button = QPushButton("输出当前图…")
        self.export_button.clicked.connect(lambda: self._export(False))
        self.export_all_button = QPushButton("选择图片输出…")
        self.export_all_button.clicked.connect(lambda: self._export(True))
        self.folder_button = QPushButton("打开结果")
        self.folder_button.clicked.connect(self._open_output)
        self.folder_button.setEnabled(False)
        output.addWidget(self.export_button)
        output.addWidget(self.export_all_button)
        output.addWidget(self.folder_button)
        layout.addLayout(output)
        self.status = QLabel("选择文件开始。源文件只读；结果和绘图配方存入所选保存位置。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.status.setToolTip(plotting.LIMIT_NOTE)
        self._fill_style({})
        self._set_busy(False)

    def _build_settings(self):
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        line = QHBoxLayout()
        self.kind_display = QLabel("正在调的图：尚未选择")
        line.addWidget(self.kind_display, 1)
        load = QPushButton("加载样式模板…")
        save = QPushButton("保存样式模板…")
        load.clicked.connect(lambda: self.load_style_template())
        save.clicked.connect(self._save_style_template)
        line.addWidget(load)
        line.addWidget(save)
        box.addLayout(line)
        pages = QTabWidget()
        self.settings_tabs = pages
        axes = QWidget()
        form = QFormLayout(axes)
        self.name_edit = QLineEdit("自定义绘图")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("可留空")
        self.xlabel_edit, self.ylabel_edit = QLineEdit(), QLineEdit()
        for label, field in (("图片名称", self.name_edit), ("图内标题", self.title_edit),
                             ("X 轴标题", self.xlabel_edit), ("Y 轴标题", self.ylabel_edit)):
            form.addRow(label, field)
        self.range_edits = {}
        for key, label in (("xlim", "X 轴范围"), ("ylim", "Y 轴范围")):
            row = QHBoxLayout()
            low, high = QLineEdit(), QLineEdit()
            low.setPlaceholderText("最小值；两格留空为自动")
            high.setPlaceholderText("最大值")
            row.addWidget(low)
            row.addWidget(QLabel("至"))
            row.addWidget(high)
            form.addRow(label, row)
            self.range_edits[key] = (low, high)
        pages.addTab(self._scroll_settings(axes), "坐标轴")
        legend = QWidget()
        lv = QVBoxLayout(legend)
        lf = QFormLayout()
        self.legend_visible = QComboBox()
        for label, value in (("自动（较多曲线时省略）", None), ("显示", True), ("隐藏", False)):
            self.legend_visible.addItem(label, value)
        self.legend_location = QComboBox()
        for label, value in (("自动", "best"), ("右上", "upper right"), ("左上", "upper left"),
                             ("左下", "lower left"), ("右下", "lower right"), ("右侧", "right"),
                             ("左侧居中", "center left"), ("右侧居中", "center right"),
                             ("下方居中", "lower center"), ("上方居中", "upper center"), ("居中", "center")):
            self.legend_location.addItem(label, value)
        lf.addRow("图例", self.legend_visible)
        lf.addRow("图例位置", self.legend_location)
        palette_row = QHBoxLayout()
        self.palette_edit = QLineEdit()
        self.palette_edit.setPlaceholderText("颜色以逗号分隔")
        palette_row.addWidget(self.palette_edit, 1)
        palette_button = QPushButton("调色盘…")
        palette_button.clicked.connect(self.choose_palette)
        palette_row.addWidget(palette_button)
        lf.addRow("整组配色", palette_row)
        lv.addLayout(lf)
        self.series_table = QTableWidget(0, 2)
        self.series_table.setHorizontalHeaderLabels(["图例名称（留空沿用原名）", "曲线颜色（留空跟随配色）"])
        self.series_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.series_table.setMinimumHeight(110)
        self.series_table.cellDoubleClicked.connect(self._choose_series_color)
        lv.addWidget(self.series_table)
        hint = QLabel("名称可直接编辑；双击颜色格选色，也可输入颜色代码。")
        hint.setWordWrap(True)
        lv.addWidget(hint)
        pages.addTab(self._scroll_settings(legend), "图例与颜色")
        sizes = QWidget()
        sf = QFormLayout(sizes)
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.addItems(["Times New Roman", "Arial", "Microsoft YaHei", "DejaVu Sans"])
        sf.addRow("字体", self.font_combo)
        self.style_numbers = {}
        for key, label, low, high, decimals in (
                ("axis_font_size", "轴标题字号 / pt", 1, 96, 1),
                ("tick_font_size", "刻度字号 / pt", 1, 96, 1),
                ("legend_font_size", "图例字号 / pt", 1, 96, 1),
                ("width_cm", "宽度 / cm", 2, 60, 3),
                ("height_cm", "高度 / cm", 2, 60, 3),
                ("linewidth", "线宽 / pt", .1, 20, 2),
                ("dpi", "输出分辨率 / dpi", 72, 1200, 0)):
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(low, high)
            self.style_numbers[key] = field
            sf.addRow(label, field)
        pages.addTab(self._scroll_settings(sizes), "字体与尺寸")
        pages.setMinimumHeight(210)
        pages.setMaximumHeight(310)
        box.addWidget(pages)
        return panel

    @staticmethod
    def _scroll_settings(widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _toggle_settings(self, show):
        self.settings_panel.setVisible(show)
        self.settings_button.setText("绘图设置 ▾" if show else "绘图设置 ▸")

    def show_plot_settings(self):
        self.settings_button.setChecked(True)
        if self.book is None:
            self.status.setText("可先设置外观并保存样式模板；打开 Excel / CSV 后可编辑当前图的轴标题与曲线名称。")

    def edit_style_template(self):
        self.show_plot_settings()

    def set_output_dir(self, path):
        self.output_dir = str(path or plotting.BASE_DIR / "output")

    def _read_style_controls(self):
        style = {"font_family": self.font_combo.currentText().strip(),
                 "legend_visible": self.legend_visible.currentData(),
                 "legend_location": self.legend_location.currentData(),
                 "palette": [x.strip() for x in self.palette_edit.text().replace("，", ",").split(",") if x.strip()],
                 "series_labels": [], "series_colors": []}
        for key, (low, high) in self.range_edits.items():
            values = (low.text().strip(), high.text().strip())
            if not any(values):
                style[key] = None
            elif not all(values):
                raise ValueError("手动坐标范围请同时填写最小值和最大值；自动范围请将两格都留空。")
            else:
                try:
                    style[key] = [float(value) for value in values]
                except ValueError as exc:
                    raise ValueError("坐标范围必须是数值。") from exc
        for key, field in self.style_numbers.items():
            style[key] = field.value()
        for row in range(self.series_table.rowCount()):
            label = self.series_table.item(row, 0).text().strip()
            original = self._series_labels[row] if row < len(self._series_labels) else ""
            style["series_labels"].append("" if label == original else label)
            style["series_colors"].append(self.series_table.item(row, 1).text().strip())
        for key in ("series_labels", "series_colors"):
            while style[key] and not style[key][-1]:
                style[key].pop()
        return style

    def _read_style(self):
        current = self._read_style_controls()
        style = copy.deepcopy(self._style_original)
        for key, value in current.items():
            if value != self._style_baseline.get(key):
                style[key] = value
        return plotting.validate_plot_style(style)

    def _fill_style(self, style, spec=None):
        self._style_original = copy.deepcopy(style or {})
        resolved = plotting.resolve_plot_style(style, self.preset_combo.currentData())
        for key, (low, high) in self.range_edits.items():
            value = resolved[key]
            low.setText("" if value is None else str(value[0]))
            high.setText("" if value is None else str(value[1]))
        self.font_combo.setCurrentText(resolved["font_family"])
        self.legend_visible.setCurrentIndex({None: 0, True: 1, False: 2}[resolved["legend_visible"]])
        self.legend_location.setCurrentIndex(max(0, self.legend_location.findData(resolved["legend_location"])))
        self.palette_edit.setText(", ".join(resolved["palette"]))
        for key, field in self.style_numbers.items():
            field.setValue(resolved[key])
        self._series_labels = []
        self._displayed_mapping = self._mapping(spec) if spec is not None else None
        if self.book is not None and spec is not None:
            try:
                self._series_labels = [item[2] for item in plotting._series_data(self.book, spec)]
            except ValueError:
                pass
        self.series_table.setRowCount(len(self._series_labels))
        for row, label in enumerate(self._series_labels):
            labels, colors = resolved["series_labels"], resolved["series_colors"]
            text = labels[row] if row < len(labels) and labels[row] else label
            color = colors[row] if row < len(colors) else ""
            self.series_table.setItem(row, 0, QTableWidgetItem(text))
            self.series_table.setItem(row, 1, QTableWidgetItem(color))
        self._style_baseline = self._read_style_controls()

    @staticmethod
    def _mapping(spec):
        return tuple((item.sheet, item.x, item.y, item.group, item.filter_column,
                      item.filter_value, item.negate_y) for item in spec.series)

    def load_style_template(self, path=None):
        if self._busy:
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "加载绘图样式模板", self.output_dir, "样式模板 (*.json)")
        if not path:
            return
        try:
            style = plotting.load_style_template(path)
            self._default_style = copy.deepcopy(style)
            spec = self._current_spec() if self.book is not None else None
            self._fill_style(style, spec)
            if self.book is not None:
                self._preview()
            self.status.setText("样式模板已加载。" + ("将用于随后导入的图。" if self.book is None else "已应用到当前图；其他图保持原样式。"))
        except Exception as exc:
            self._failed(str(exc))

    def _save_style_template(self):
        if self._busy:
            return
        try:
            style = plotting.resolve_plot_style(self._read_style(), self.preset_combo.currentData())
            path, _ = QFileDialog.getSaveFileName(self, "保存绘图样式模板", os.path.join(self.output_dir, "绘图样式模板.json"), "样式模板 (*.json)")
            if path:
                plotting.save_style_template(path, style)
                self.status.setText("样式模板已保存：" + path)
        except Exception as exc:
            self._failed(str(exc))

    def choose_palette(self):
        if self._busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("选择配色")
        form = QVBoxLayout(dialog)
        choices = QComboBox()
        palettes = [("科研常用", list(plotting.COLORS)), ("黑白印刷", ["#222222", "#666666", "#999999"]),
                    ("蓝橙对照", ["#0072B2", "#D55E00", "#56B4E9", "#E69F00"]),
                    ("青紫对照", ["#208A83", "#9B66A6", "#4B9CC4", "#BB7D40"])]
        try:
            import ec_palette
            palettes += [(item.get("name", "我的配色"), item["colors"]) for item in ec_palette.load_memory().get("groups", []) if item.get("colors")]
        except (ValueError, KeyError, TypeError):
            pass
        for name, colors in palettes:
            choices.addItem(name, colors)
        form.addWidget(choices)
        swatches = QLabel()
        def show_colors():
            swatches.setText(" ".join(f'<span style="color:{QColor(c).name()}">■</span>' for c in choices.currentData()))
        choices.currentIndexChanged.connect(show_colors)
        show_colors()
        form.addWidget(swatches)
        hint = QLabel("整组配色应用于当前图。已单独指定颜色的曲线保持其颜色。")
        hint.setWordWrap(True)
        form.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addWidget(buttons)
        if dialog.exec():
            self.palette_edit.setText(", ".join(choices.currentData()))
            if self.book is not None:
                self._preview()
            else:
                self._default_style = self._read_style()
            self.status.setText("配色已应用到当前图。" if self.book is not None else "配色已保存，随后导入数据即可预览。")

    def _choose_series_color(self, row, column):
        if column != 1:
            return
        value = self.series_table.item(row, column).text().strip()
        palette = [c.strip() for c in self.palette_edit.text().split(",") if c.strip()]
        color = QColorDialog.getColor(QColor(value or (palette[row % len(palette)] if palette else "#0072B2")), self, "曲线颜色")
        if color.isValid():
            self.series_table.item(row, column).setText(color.name())

    def _set_busy(self, busy, message=""):
        changed = self._busy != busy
        self._busy = busy
        self.open_button.setEnabled(not busy)
        self.recipe_button.setEnabled(not busy)
        self.options.setEnabled(not busy and self.book is not None)
        self.settings_panel.setEnabled(not busy)
        for field in (self.name_edit, self.title_edit, self.xlabel_edit, self.ylabel_edit, self.series_table):
            field.setEnabled(not busy and self.book is not None)
        self.preview_button.setEnabled(not busy and self.book is not None)
        self.settings_button.setEnabled(not busy)
        self.current_preview.setEnabled(not busy and bool(self.auto_specs) and self.tabs.currentIndex() == 0)
        self.export_button.setEnabled(not busy and self.book is not None)
        self.export_all_button.setEnabled(not busy and bool(self.auto_specs))
        for box in self.format_boxes.values():
            box.setEnabled(not busy)
        if message:
            self.status.setText(message)
        if changed:
            self.busyChanged.emit(busy)

    def _start(self, function, success, message):
        if self._busy:
            return
        self._set_busy(True, message)
        worker = _Work(function, self)
        self.worker = worker
        self._outcome = None
        self._success_callback = success
        worker.succeeded.connect(lambda result: setattr(self, "_outcome", (True, result)))
        worker.failed.connect(lambda error: setattr(self, "_outcome", (False, error)))
        worker.finished.connect(self._finished)
        worker.start()

    def _finished(self):
        worker = self.worker
        self.worker = None
        self._set_busy(False)
        if worker is not None:
            worker.deleteLater()
        outcome = self._outcome
        self._outcome = None
        if outcome is not None:
            if outcome[0]:
                self._success_callback(outcome[1])
            else:
                self._failed(outcome[1])

    def _failed(self, message):
        self.status.setText("未完成：" + message)
        QMessageBox.warning(self, "请检查数据", message)

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开表格", "", "表格 (*.xlsx *.xlsm *.csv *.tsv);;所有文件 (*)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        """Public integration hook; import runs in a single background worker."""
        if self._busy:
            return
        if self.book is None:
            try:
                self._default_style = self._read_style()
            except ValueError as exc:
                self._failed(str(exc))
                return
        self._start(lambda: plotting.load_table_book(path), self._loaded, "正在读取表格，请稍候…")

    def _choose_recipe(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开绘图配方", str(plotting.BASE_DIR / "output"), "绘图配方 (*.json)")
        if path:
            self._start(lambda: plotting.load_recipe(path), self._recipe_loaded, "正在校验源文件并读取绘图配方…")

    def _recipe_loaded(self, result):
        book, specs, preset = result
        with QSignalBlocker(self.preset_combo):
            self.preset_combo.setCurrentIndex(self.preset_combo.findData(preset))
        self._loaded(book, specs)
        self.status.setText("绘图配方已恢复，源文件 SHA256 校验一致。 " + " ".join(book.notes))

    def _loaded(self, book, specs=None):
        self.book = book
        self.auto_specs = specs if specs is not None else plotting.automatic_plots(book)
        if specs is None and self._default_style:
            for spec in self.auto_specs:
                spec.style = copy.deepcopy(self._default_style)
        self._active_auto_index = -1
        self._manual_spec = None
        self._populating = True
        try:
            self.path_label.setText(os.path.basename(book.path))
            self.path_label.setToolTip(book.path)
            self.sheet_combo.clear()
            self.sheet_combo.addItems(list(book.tables))
            self.plot_list.clear()
            self.plot_list.addItems([spec.name for spec in self.auto_specs])
            self.current_preview.clear()
            self.current_preview.addItems([spec.name for spec in self.auto_specs])
            self.tabs.setCurrentIndex(0 if self.auto_specs else 1)
            self.plot_list.setCurrentRow(0 if self.auto_specs else -1)
            self._sheet_selected()
        finally:
            self._populating = False
        if self.auto_specs:
            self._active_tab = 0
            self._auto_selected(0)
        else:
            self._active_tab = 1
            self._set_details(None)
            self._sync_auto_choices()
            self._preview()
        count = sum(len(frame) for frame in book.tables.values())
        self.status.setText(f"已读入 {len(book.tables)} 张工作表、{count:,} 行，识别 {len(self.auto_specs)} 张常用图。 " + " ".join(book.notes))
        self._set_busy(self._busy)

    def _sheet_selected(self, *_args):
        if self.book is None:
            return
        sheet = self.sheet_combo.currentText()
        if sheet not in self.book.tables:
            return
        columns = plotting.numeric_columns(self.book.tables[sheet])
        self.x_combo.clear()
        self.x_combo.addItems(columns)
        self.y_list.clear()
        self.y_list.addItems(columns)
        if columns:
            self.y_list.setCurrentRow(1 if len(columns) > 1 else 0)
        self.group_combo.clear()
        self.group_combo.addItem("不分组", "")
        for column in self.book.tables[sheet].columns:
            self.group_combo.addItem(str(column), str(column))
        if "file" in self.book.tables[sheet]:
            self.group_combo.setCurrentIndex(self.group_combo.findData("file"))
        if not self._populating:
            self._manual_spec = None
            self._set_details(None)

    def _tab_changed(self, index):
        if self._populating or self.book is None:
            return
        try:
            self._commit_active()
        except ValueError as exc:
            self.status.setText("请先修正设置：" + str(exc))
            with QSignalBlocker(self.tabs):
                self.tabs.setCurrentIndex(self._active_tab)
            return
        self._active_tab = index
        if index == 0:
            self._active_auto_index = -1
            self._auto_selected(self.plot_list.currentRow())
        else:
            self._set_details(self._manual_spec)
            self._sync_auto_choices()

    def _sync_auto_choices(self):
        with QSignalBlocker(self.current_preview), QSignalBlocker(self.plot_list):
            self.current_preview.clear()
            if self._active_tab == 0:
                self.current_preview.addItems([spec.name for spec in self.auto_specs])
                self.current_preview.setCurrentIndex(self._active_auto_index)
                self.plot_list.setCurrentRow(self._active_auto_index)
                for row, spec in enumerate(self.auto_specs):
                    self.plot_list.item(row).setText(spec.name)
            else:
                self.current_preview.addItem("按列绘图")
        self.current_preview.setEnabled(not self._busy and self._active_tab == 0 and bool(self.auto_specs))

    def _set_details(self, spec):
        self.name_edit.setText(spec.name if spec else "自定义绘图")
        self.title_edit.setText(spec.title if spec else "")
        self.xlabel_edit.setText(spec.xlabel if spec else "")
        self.ylabel_edit.setText(spec.ylabel if spec else "")
        self.xlabel_edit.setPlaceholderText(self.x_combo.currentText())
        self.ylabel_edit.setPlaceholderText("留空自动使用列名")
        self.kind_display.setText("正在调的图：" + (spec.name if spec else "按列绘图"))
        if spec is None and self.book is not None:
            try:
                spec = self._generic_spec()
            except ValueError:
                pass
        self._fill_style(getattr(spec, "style", {}) if spec is not None else self._default_style, spec)

    def _auto_selected(self, index):
        if self._populating or not 0 <= index < len(self.auto_specs):
            return
        if self._active_tab != 0:
            return
        if index != self._active_auto_index:
            try:
                self._commit_active()
            except ValueError as exc:
                self.status.setText("请先修正设置：" + str(exc))
                self._sync_auto_choices()
                return
        self._active_auto_index = index
        self._sync_auto_choices()
        self._set_details(self.auto_specs[index])
        self._preview()

    def _generic_spec(self):
        ys = [item.text() for item in self.y_list.selectedItems()]
        spec = plotting.generic_plot(self.sheet_combo.currentText(), self.x_combo.currentText(), ys,
                                     self.group_combo.currentData() or "", self.mode_combo.currentData())
        spec.style = copy.deepcopy(self._default_style)
        return spec

    def _capture_manual_spec(self):
        result = self._capture_spec(self._generic_spec())
        if self._mapping(result) != self._displayed_mapping:
            result.style.pop("series_labels", None)
            result.style.pop("series_colors", None)
        return result

    def _capture_spec(self, spec):
        spec = copy.deepcopy(spec)
        spec.name = self.name_edit.text().strip() or spec.name
        spec.title = self.title_edit.text().strip()
        spec.xlabel = self.xlabel_edit.text().strip() or spec.xlabel
        spec.ylabel = self.ylabel_edit.text().strip() or spec.ylabel
        spec.style = self._read_style()
        return spec

    def _commit_active(self):
        if self.book is None:
            return
        if self._active_tab == 0:
            if 0 <= self._active_auto_index < len(self.auto_specs):
                self.auto_specs[self._active_auto_index] = self._capture_spec(self.auto_specs[self._active_auto_index])
        else:
            self._manual_spec = self._capture_manual_spec()

    def _preset_changed(self, *_):
        if self._populating or not hasattr(self, "settings_panel"):
            return
        try:
            spec = self._current_spec() if self.book is not None else None
            self._fill_style(spec.style if spec else self._default_style, spec)
            if self.book is not None:
                self._preview()
        except ValueError as exc:
            self.status.setText("请先修正设置：" + str(exc))

    def _current_spec(self):
        if self.book is None:
            raise ValueError("请先打开表格。")
        if self.tabs.currentIndex() == 0:
            index = self._active_auto_index
            if not 0 <= index < len(self.auto_specs):
                raise ValueError("没有识别到常用图，请切换到「按列绘图」。")
            spec = copy.deepcopy(self.auto_specs[index])
        else:
            # Per-curve overrides belong to the old column mapping. Keep global
            # appearance, but never relabel a different selected column silently.
            return self._capture_manual_spec()
        return self._capture_spec(spec)

    def _preview(self):
        if self.book is None:
            return
        try:
            spec = self._current_spec()
            figure = plotting.draw_plot(self.book, spec, self.preset_combo.currentData(), dpi=100)
            new_canvas = _PreviewCanvas(figure)
            old_canvas = self.canvas
            self.preview_frame.set_canvas(new_canvas)
            self.canvas = new_canvas
            new_canvas.draw()
            old_canvas.figure.clear()
            old_canvas.setParent(None)
            old_canvas.deleteLater()
            if self.tabs.currentIndex() == 0:
                self.auto_specs[self._active_auto_index] = copy.deepcopy(spec)
            else:
                self._manual_spec = copy.deepcopy(spec)
            self._fill_style(spec.style, spec)
            self._sync_auto_choices()
            self.kind_display.setText("正在调的图：" + spec.name)
            dpi = plotting.resolve_plot_style(spec.style, self.preset_combo.currentData())["dpi"]
            self.plot_note.setText(f"{spec.name} · PNG {dpi:g} dpi / PDF / SVG；保留原始采样顺序。")
        except Exception as exc:
            self.status.setText("预览提示：" + str(exc))

    def _export(self, all_plots):
        if self._busy or self.book is None:
            return
        try:
            formats = tuple(key for key, box in self.format_boxes.items() if box.isChecked())
            if not formats:
                raise ValueError("请至少选择一种输出格式。")
            if all_plots:
                specs = copy.deepcopy(self.auto_specs)
                if self.tabs.currentIndex() == 0 and specs:
                    specs[self._active_auto_index] = self._current_spec()
                elif self.tabs.currentIndex() == 1:
                    # Y6: when exporting all plots from the manual "按列绘图"
                    # tab, the current hand-built plot was previously ignored.
                    manual = self._current_spec()
                    if manual is not None:
                        specs.append(manual)
            else:
                specs = [self._current_spec()]
            from ec_output_dialog import OutputSelectionDialog
            dialog = OutputSelectionDialog(self, [(str(i), spec.name) for i, spec in enumerate(specs)],
                self.output_dir, formats, [str(plotting.Path(self.book.path).parent)],
                available_formats=("png", "pdf", "svg"))
            if not dialog.exec():
                return
            selected = []
            for key, name in dialog.selection:
                spec = specs[int(key)]
                spec.name = name
                selected.append(spec)
            specs, formats, destination = selected, tuple(dialog.formats), dialog.output_dir
            book, preset = self.book, self.preset_combo.currentData()
            self._last_export_count = len(specs)*len(formats)
            self._start(lambda: plotting.export_plots(book, specs, preset, formats, output_dir=destination), self._exported,
                        f"正在按完整数据输出 {len(specs)} 张图，请稍候…")
        except Exception as exc:
            self._failed(str(exc))

    def _exported(self, path):
        self.last_output = path
        self.folder_button.setEnabled(True)
        self.status.setText("已完成：" + path + "（包含图片与可复现绘图配方）")
        self.outputReady.emit(str(path))
        from ec_output_dialog import offer_open_folder
        offer_open_folder(self, path, self._last_export_count)

    def _open_output(self):
        if self.last_output:
            try:
                os.startfile(self.last_output)
            except Exception as exc:
                QMessageBox.warning(self, "无法打开目录", str(exc))

    def reject(self):
        if self._busy:
            # Y1: loading/exporting used to swallow Esc/X with only a status
            # line; surface an explicit notice so the window is not "stuck".
            self.status.setText("当前正在读取或输出，完成后可关闭窗口。")
            QMessageBox.warning(self, "请稍候", "当前正在读取或输出，请等待完成后再关闭窗口。")
            return
        if self.embedded:
            return
        self.canvas.figure.clear()
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            self.status.setText("当前正在读取或输出，完成后可关闭窗口。")
            QMessageBox.warning(self, "请稍候", "当前正在读取或输出，请等待完成后再关闭窗口。")
            event.ignore()
            return
        if self.embedded:
            event.ignore()
            return
        self.canvas.figure.clear()
        super().closeEvent(event)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    studio = PlotStudio(initial_path=sys.argv[1] if len(sys.argv) > 1 else None)
    studio.show()
    sys.exit(app.exec())
