"""Single-worker conductivity import/export dialog."""
from pathlib import Path

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QPushButton, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QAbstractItemView, QHeaderView,
)

from ec_conductivity import default_output_dir, export_conductivity, process_files
from ec_jobs import Worker as _Worker


class ConductivityDialog(QDialog):
    def __init__(self, parent=None, output_dir=None):
        super().__init__(parent)
        self._output_dir = output_dir or ""
        self.setWindowTitle("电导率处理 · 原始数据 → 标准 Excel → 一键绘图")
        self.resize(1000, 740)
        self._paths = []
        self._result = None
        self._export_path = None
        self._thread = None
        self._worker = None
        self._busy = False
        self._outcome = None
        self._success_handler = None

        layout = QVBoxLayout(self)
        heading = QLabel("① 添加电导率文件　→　② 检查单位并读取　→　③ 导出 Excel / 一键绘图")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        protection = QLabel("原始文件只读。支持 DDSJ 仪器 Excel、CSV 和两列 TXT；每批最多 10 万行，结果保存在项目 output 的独立文件夹。")
        protection.setWordWrap(True)
        layout.addWidget(protection)
        row = QHBoxLayout()
        self.add_button = QPushButton("添加文件…")
        self.remove_button = QPushButton("移除选中")
        self.clear_button = QPushButton("清空列表")
        for button in (self.add_button, self.remove_button, self.clear_button):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.files = QListWidget()
        self.files.setMaximumHeight(135)
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.files)

        form = QFormLayout()
        self.units = QComboBox()
        self.units.addItem("自动识别；裸数值缺单位时报告错误", None)
        self.units.addItem("裸数值使用 μS/cm", "uS/cm")
        self.units.addItem("裸数值使用 mS/cm", "mS/cm")
        self.units.addItem("裸数值使用 S/m", "S/m")
        self.time_units = QComboBox()
        for label, value in (("秒 s", "s"), ("分钟 min", "min"), ("小时 h", "h")):
            self.time_units.addItem(label, value)
        form.addRow("电导率单位", self.units)
        form.addRow("无单位数字时间", self.time_units)
        layout.addLayout(form)
        hint = QLabel("文件中明确写出的单位优先。日期时间自动换算为相对秒；时间重复/倒退会提示，不会自动排序。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        actions = QHBoxLayout()
        self.read_button = QPushButton("读取并检查")
        self.read_button.setObjectName("primary")
        self.export_button = QPushButton("导出标准 Excel")
        self.plot_button = QPushButton("导出并一键绘图")
        self.close_button = QPushButton("关闭")
        for button in (self.read_button, self.export_button, self.plot_button, self.close_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.summary = QLabel("尚未读取文件。浓度、吸盐量需要实验标定参数，本工具不会自动猜测。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.preview = QTableWidget(0, 5)
        self.preview.setHorizontalHeaderLabels(["来源", "原始行", "相对时间 / s", "电导率 / μS·cm⁻¹", "状态"])
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.preview, 2)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1500)
        layout.addWidget(self.log, 1)

        self.add_button.clicked.connect(self._add)
        self.remove_button.clicked.connect(self._remove)
        self.clear_button.clicked.connect(self._clear)
        self.read_button.clicked.connect(self._read)
        self.export_button.clicked.connect(lambda: self._export(False))
        self.plot_button.clicked.connect(lambda: self._export(True))
        self.close_button.clicked.connect(self.reject)
        self.units.currentIndexChanged.connect(self._invalidate)
        self.time_units.currentIndexChanged.connect(self._invalidate)
        self._update_controls()

    def _update_controls(self):
        for control in (self.add_button, self.remove_button, self.clear_button, self.units,
                        self.time_units, self.files, self.close_button):
            control.setEnabled(not self._busy)
        self.read_button.setEnabled(bool(self._paths) and not self._busy)
        available = self._result is not None and not self._result.data.empty and not self._busy
        self.export_button.setEnabled(available)
        self.plot_button.setEnabled(available and self._result.valid_count > 0)

    def _invalidate(self, *_):
        self._result = None
        self._export_path = None
        self.preview.setRowCount(0)
        self.summary.setText(f"已选 {len(self._paths)} 个文件，请点击“读取并检查”。")
        self._update_controls()

    def _add(self):
        start = "E:/Data" if Path("E:/Data").exists() else str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(self, "添加电导率原始文件", start,
                                               "数据文件 (*.xlsx *.csv *.txt *.tsv)")
        self.add_paths(paths)

    def add_paths(self, paths):
        if self._busy:
            return
        for path in paths:
            resolved = str(Path(path).resolve())
            if resolved not in self._paths:
                self._paths.append(resolved)
                self.files.addItem(resolved)
        self._invalidate()

    def _remove(self):
        for item in self.files.selectedItems():
            self._paths.remove(item.text())
            self.files.takeItem(self.files.row(item))
        self._invalidate()

    def _clear(self):
        self._paths.clear()
        self.files.clear()
        self._invalidate()

    def _start(self, job, success):
        if self._busy:
            return
        self._busy = True
        self._outcome = None
        self._success_handler = success
        self._update_controls()
        self._thread = QThread(self)
        self._worker = _Worker(job)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log.appendPlainText)
        self._worker.finished.connect(self._job_success)
        self._worker.failed.connect(self._job_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._job_stopped)
        self._thread.start()

    @Slot(object)
    def _job_success(self, result):
        self._outcome = (True, result)

    @Slot(str)
    def _job_failure(self, message):
        self._outcome = (False, message)

    @Slot()
    def _job_stopped(self):
        thread = self._thread
        self._thread = None
        self._worker = None
        self._busy = False
        if thread is not None:
            thread.deleteLater()
        outcome = self._outcome
        callback = self._success_handler
        self._outcome = None
        self._success_handler = None
        if outcome and outcome[0]:
            callback(outcome[1])
        elif outcome:
            self.log.appendPlainText("失败：" + outcome[1])
            QMessageBox.warning(self, "处理失败", outcome[1])
        self._update_controls()

    def _read(self):
        paths = list(self._paths)
        unit = self.units.currentData()
        time_unit = self.time_units.currentData()
        self.log.clear()
        self._result = None
        self._export_path = None
        self.summary.setText("正在单线程读取，请稍候…")
        self._start(lambda progress: process_files(paths, unit, time_unit, progress), self._show_result)

    def _show_result(self, result):
        self._result = result
        errors = sum(i["severity"] == "error" for i in result.issues)
        warnings = sum(i["severity"] == "warning" for i in result.issues)
        self.summary.setText(f"{len(result.input_paths)} 个文件；{len(result.data):,} 行；"
                             f"有效点 {result.valid_count:,}；错误 {errors:,} 条，提示 {warnings:,} 条。下方预览前 30 行。")
        data = result.data.head(30)
        self.preview.setRowCount(len(data))
        for r, (_, row) in enumerate(data.iterrows()):
            for c, key in enumerate(("file", "source_row", "elapsed_s", "conductivity_uS_cm", "status")):
                self.preview.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))
        for issue in result.issues[:300]:
            self.log.appendPlainText(f"[{issue['severity']}] {Path(issue['source_path']).name} / "
                                     f"{issue['source_sheet']} 第 {issue['source_row'] or '-'} 行：{issue['message']}")
        if len(result.issues) > 300:
            self.log.appendPlainText(f"其余 {len(result.issues) - 300} 条会全部写入 Excel 的 issues 工作表。")
        if not result.issues:
            self.log.appendPlainText("读取完成，未发现缺失值、非法单位或时间倒退。")

    def _export(self, open_plot):
        if self._busy or self._result is None:
            return
        if self._export_path is not None and self._export_path.exists():
            if open_plot:
                self._open_plot(self._export_path)
            else:
                QMessageBox.information(self, "已导出", str(self._export_path))
            return
        # Y5: respect the user-configured output location instead of always
        # writing into a fresh timestamped project-output folder. Fall back to
        # the default only when no output directory was supplied.
        if self._output_dir:
            target = Path(self._output_dir) / "conductivity.xlsx"
        else:
            target = default_output_dir() / "conductivity.xlsx"
        result = self._result
        self.log.appendPlainText("正在导出完整数据与错误清单…")

        def completed(path):
            self._export_path = Path(path)
            self.log.appendPlainText("已导出：" + str(path))
            if open_plot:
                self._open_plot(path)
            else:
                QMessageBox.information(self, "导出完成", f"标准数据、原始值和错误清单已保存：\n{path}")

        self._start(lambda _: export_conductivity(result, target), completed)

    def _open_plot(self, path):
        try:
            from ec_plot_studio import PlotStudio
            studio = PlotStudio(parent=self, initial_path=str(path))
            studio.exec()
        except Exception as exc:
            QMessageBox.warning(self, "绘图工作台", f"Excel 已保存：\n{path}\n\n打开绘图工作台失败：{exc}")

    def reject(self):
        if self._busy:
            self.log.appendPlainText("当前读写任务正在进行，完成后可关闭窗口。")
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            self.log.appendPlainText("当前读写任务正在进行，完成后可关闭窗口。")
        else:
            super().closeEvent(event)
