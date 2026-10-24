"""Choose exactly what to export before creating any output files."""
import os
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHeaderView, QCheckBox)

from ec_export import validate_output_dir


def validate_names(selection):
    if not selection:
        raise ValueError("请至少选择一张图。")
    seen = set()
    for key, name in selection:
        if (not name or name != name.strip(" .") or len(name) > 120
                or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
                or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name, re.I)):
            raise ValueError(f"图片名称无效：{name!s}。请只填写文件名，不要包含路径或特殊字符。")
        if name.casefold() in seen:
            raise ValueError("选中的图片不能使用相同名称：" + name)
        seen.add(name.casefold())


def offer_open_folder(parent, folder, count):
    choice = QMessageBox.question(parent, "输出完成",
        f"已保存 {count} 个文件。\n保存位置：{folder}\n\n是否打开保存位置？",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if choice == QMessageBox.Yes:
        try:
            os.startfile(folder)
        except OSError as exc:
            QMessageBox.warning(parent, "无法打开保存位置", str(exc))


class OutputSelectionDialog(QDialog):
    def __init__(self, parent, items, folder, formats=("png",), input_dirs=(), available_formats=("png", "pdf", "svg", "eps", "tiff")):
        super().__init__(parent)
        self.setWindowTitle("直接输出 · 选择图片")
        self.resize(780, 560)
        self.items = list(items)
        self.input_dirs = list(input_dirs)
        self.selection = []
        self.output_dir = ""
        self.formats = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾选要输出的图，并填写每张图片的名称（不含扩展名）。"))
        self.table = QTableWidget(len(items), 2)
        self.table.setHorizontalHeaderLabels(["输出图片", "图片名称"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, (key, title) in enumerate(items):
            item = QTableWidgetItem(title)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, item)
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
            self.table.setItem(row, 1, QTableWidgetItem(name or f"图片{row+1}"))
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        all_button, none_button = QPushButton("全选"), QPushButton("全不选")
        all_button.clicked.connect(lambda: self.select_all(True))
        none_button.clicked.connect(lambda: self.select_all(False))
        row.addWidget(all_button)
        row.addWidget(none_button)
        self.count_label = QLabel()
        row.addWidget(self.count_label, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("输出格式："))
        self.format_boxes = {}
        for fmt in available_formats:
            box = QCheckBox(fmt.upper())
            box.setChecked(fmt in formats)
            box.toggled.connect(self._update)
            self.format_boxes[fmt] = box
            row.addWidget(box)
        row.addStretch()
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("保存位置："))
        self.directory = QLineEdit(str(folder or ""))
        row.addWidget(self.directory, 1)
        browse = QPushButton("选择文件夹…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(QLabel("同名文件会自动加编号保留；至少选择一张图和一种格式。"))
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("取消输出")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("确认输出")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        self.table.itemChanged.connect(self._update)
        self._update()

    def select_all(self, selected):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if selected else Qt.Unchecked)
        self._update()

    def _update(self, *_):
        count = sum(self.table.item(i, 0).checkState() == Qt.Checked for i in range(self.table.rowCount()))
        self.count_label.setText(f"已选 {count} 张" if count else "至少选择一张图")
        self.save_button.setEnabled(count > 0 and any(c.isChecked() for c in self.format_boxes.values()))

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片保存位置", self.directory.text())
        if folder:
            self.directory.setText(folder)

    def accept(self):
        selected = [(key, self.table.item(i, 1).text().strip())
                    for i, (key, _) in enumerate(self.items)
                    if self.table.item(i, 0).checkState() == Qt.Checked]
        try:
            validate_names(selected)
            formats = [fmt for fmt, c in self.format_boxes.items() if c.isChecked()]
            if not formats:
                raise ValueError("请至少选择一种输出格式。")
            if not self.directory.text().strip():
                raise ValueError("请选择保存位置。")
            folder = validate_output_dir(self.directory.text().strip(), self.input_dirs)
            if os.path.exists(folder) and not os.path.isdir(folder):
                raise ValueError("保存位置必须是文件夹。")
        except ValueError as exc:
            QMessageBox.warning(self, "请检查输出设置", str(exc))
            return
        self.selection, self.output_dir, self.formats = selected, folder, formats
        super().accept()


def render_selected(data, cfg, selection):
    import eclab
    from ec_export import input_directories
    validate_names(selection)
    allowed = dict(eclab.preview_list(data, cfg))
    if any(key not in allowed for key, _ in selection):
        raise ValueError("图片列表已变化，请重新选择。")
    output = cfg.get("output", {})
    folder = validate_output_dir(output.get("dir") or eclab.OUTPUT_DIR, input_directories(data, cfg))
    made = []
    for key, name in selection:
        fig = None
        try:
            fig, _ = eclab.draw_figure(data, key, cfg)
            if fig is None:
                raise ValueError("无法绘制：" + allowed[key])
            made.extend(eclab.save_fig(fig, name, eclab.get_style(cfg, eclab.kind_of_key(key)),
                         output.get("formats"), output.get("dpi"), folder))
        finally:
            if fig is not None:
                fig.clear()
    return made
