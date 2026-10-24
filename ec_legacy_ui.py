"""Small front end for the user's existing Excel workflows."""
from pathlib import Path
import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QVBoxLayout, QPlainTextEdit, QAbstractItemView, QWidget,
    QToolButton, QScrollArea)

from ec_jobs import Worker as _Worker
from ec_cdi_metadata import suggest_cdi_mass
from ec_processing_templates import (DEFAULTS, load_template as read_processing_template,
                                     save_template as write_processing_template)
from PySide6.QtCore import QThread

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def run_legacy(*args, **kwargs):
    # Imported from the worker only: opening this dialog must not load SciPy
    # and openpyxl on the GUI thread (13 s on the owner's cold start).
    from ec_legacy import run_legacy as process
    return process(*args, **kwargs)


class LegacyExcelDialog(QDialog):
    resultsReady = Signal(object, str)
    plotRequested = Signal(str)
    busyChanged = Signal(bool)
    analysisRequested = Signal()

    def __init__(self, parent=None, mode="electrochem", paths=(), mass_mg=None, output_dir=None, embedded=False):
        super().__init__(parent, Qt.Widget if embedded else Qt.Dialog)
        self.embedded = embedded
        self.setWindowTitle("数据处理 · 沿用原 Excel 样式")
        self.resize(1060, 760)
        self._busy = False
        self._thread = None
        self._worker = None
        self._outcome = None
        self.result_files = []
        self.want_analysis = False
        self._job_kind = "process"
        self._template_path = None
        self._loading_template = False
        self._mass_suggestions = []
        self._mass_mixed = False
        self._mass_file_key = None
        self._mass_editing = False
        self._mass_manual = False
        layout = QVBoxLayout(self)
        self.controls = QWidget()
        columns = QHBoxLayout(self.controls)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(20)
        self.file_panel = QWidget()
        self.file_panel.setFixedWidth(260)
        sidebar = QVBoxLayout(self.file_panel)
        sidebar.setContentsMargins(0, 0, 0, 0)
        self.file_count = QLabel("文件清单 · 0 个")
        sidebar.addWidget(self.file_count)
        row = QHBoxLayout()
        add, add_folder = QPushButton("添加文件…"), QPushButton("添加文件夹…")
        add.clicked.connect(self._add)
        add_folder.clicked.connect(lambda: self.add_folder())
        row.addWidget(add)
        row.addWidget(add_folder)
        sidebar.addLayout(row)
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.addItems(list(map(str, paths)))
        self.files.setMinimumHeight(240)
        sidebar.addWidget(self.files, 1)
        row = QHBoxLayout()
        remove, clear = QPushButton("移除选中"), QPushButton("清空列表")
        remove.clicked.connect(self._remove)
        clear.clicked.connect(self.files.clear)
        row.addWidget(remove)
        row.addWidget(clear)
        sidebar.addLayout(row)
        sidebar.addWidget(QLabel("原始文件只读 · 每批最多 100 个"))
        columns.addWidget(self.file_panel)
        content = QWidget()
        panel = QVBoxLayout(content)
        panel.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.mode = QComboBox()
        for title, code in (("CV / GCD → CV结果、GCD结果", "electrochem"),
                            ("CP 循环 → 全量数据、放电时间、尾数分表", "cp_cycle"),
                            ("CV 循环 → 原始处理数据、尾号分表", "cv_cycle"),
                            ("CDI 电导率 → 原来的七张工作表", "cdi"),
                            ("电容贡献率 → 填入原来的四表模板", "contribution")):
            self.mode.addItem(title, code)
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        form.addRow("处理类型", self.mode)
        panel.addLayout(form)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        panel.addWidget(self.hint)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("processingSummary")
        panel.addWidget(self.summary)
        self.mass_note = QLabel()
        self.mass_note.setWordWrap(True)
        panel.addWidget(self.mass_note)
        row = QHBoxLayout()
        self.parameter_toggle = QToolButton()
        self.parameter_toggle.setText("展开参数")
        self.parameter_toggle.setCheckable(True)
        self.parameter_toggle.setArrowType(Qt.RightArrow)
        self.parameter_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.parameter_toggle.toggled.connect(self._toggle_parameters)
        row.addWidget(self.parameter_toggle)
        self.mass_edit_button = QPushButton("修改质量")
        self.mass_edit_button.clicked.connect(self._edit_mass)
        row.addWidget(self.mass_edit_button)
        row.addStretch(1)
        panel.addLayout(row)
        self.parameters_container = QWidget()
        self.form = QFormLayout(self.parameters_container)
        self.form.setContentsMargins(0, 8, 0, 8)
        self.fields = {}
        for key, title, default, minimum, maximum, decimals in (
            ("mass_mg", "活性物质质量 / mg", mass_mg if mass_mg is not None else 0, 0, 1e6, 4),
            ("time_step", "GCD / CP 采样间隔 / s", 0.1, 0.00001, 3600, 5),
            ("cdi_step", "CDI 采样间隔 / s", 5, 0.001, 3600, 3),
            ("ads_minutes", "吸附时长 / min", 30, 0.001, 10000, 3),
            ("des_minutes", "脱附时长 / min", 30, 0.001, 10000, 3),
            ("volume_ml", "溶液体积 / mL", 50, 0.0001, 1e6, 4)):
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(minimum, maximum)
            field.setValue(float(default))
            if key == "mass_mg":
                field.setSpecialValueText("请填写本次质量")
            self.fields[key] = field
            self.form.addRow(title, field)

        # 标准曲线 y = 斜率·x + 截距（斜率=原 calibration_scale，截距=原 calibration_base）
        self.fields["calibration_scale"] = QDoubleSpinBox()
        self.fields["calibration_scale"].setDecimals(6)
        self.fields["calibration_scale"].setRange(0.000001, 1e6)
        self.fields["calibration_scale"].setValue(1.97252)
        self.fields["calibration_base"] = QDoubleSpinBox()
        self.fields["calibration_base"].setDecimals(6)
        self.fields["calibration_base"].setRange(-1e6, 1e6)
        self.fields["calibration_base"].setValue(8.2236)
        cal_row = QHBoxLayout()
        cal_row.addWidget(QLabel("y = "))
        cal_row.addWidget(self.fields["calibration_scale"], 1)
        cal_row.addWidget(QLabel(" x + "))
        cal_row.addWidget(self.fields["calibration_base"], 1)
        self.calibration_container = QWidget()
        self.calibration_container.setLayout(cal_row)
        self.form.addRow("标准曲线（电导率）", self.calibration_container)

        self.sampling = QComboBox()
        self.sampling.addItem("从原始时间自动识别（推荐）", "auto")
        self.sampling.addItem("手动填写采样间隔", "manual")
        self.sampling.currentIndexChanged.connect(self._sampling_changed)
        self.form.insertRow(1, "CDI 采样方式", self.sampling)
        self.fields["mass_mg"].valueChanged.connect(self._mass_changed)
        self.split_mode = QComboBox()
        self.split_mode.addItem("按波峰分圈（原默认）", "peak")
        self.split_mode.addItem("按波谷分圈", "valley")
        self.form.addRow("CV 循环分圈", self.split_mode)
        self.units = QComboBox()
        self.units.addItem("μS/cm（原标定单位）", "uS/cm")
        self.units.addItem("mS/cm（自动换算到 μS/cm）", "mS/cm")
        self.units.addItem("S/m（自动换算到 μS/cm）", "S/m")
        self.form.addRow("文件没有标明单位时", self.units)
        self.tail_policy = QComboBox()
        self.tail_policy.addItem("参考规则：结束点不另计圈，其余末圈保留", "reference")
        self.tail_policy.addItem("保留所有末圈，包括单个结束点", "include")
        self.tail_policy.addItem("只计算完整圈，尾部留在原始表", "complete")
        self.form.addRow("CDI 末圈", self.tail_policy)
        self.parameters_container.hide()
        panel.addWidget(self.parameters_container)
        self.template_note = QLabel("数据处理模板：当前参数")
        self.template_note.setWordWrap(True)
        panel.addWidget(self.template_note)
        row = QHBoxLayout()
        row.addWidget(QLabel("保存位置："))
        self.output = QLineEdit(str(output_dir or BASE / "output"))
        row.addWidget(self.output, 1)
        choose = QPushButton("选择文件夹…")
        choose.clicked.connect(self.choose_output)
        row.addWidget(choose)
        panel.addLayout(row)
        actions = QHBoxLayout()
        self.process_button = QPushButton("开始处理并生成 Excel")
        self.process_button.setObjectName("primary")
        self.process_button.clicked.connect(self._run)
        self.analysis_button = QPushButton("比电容 / EIS 计算…")
        self.analysis_button.clicked.connect(self._analysis)
        self.standard_button = QPushButton("仅整理电导率与单位…")
        self.standard_button.clicked.connect(self._standard)
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.reject)
        self.close_button.setVisible(not embedded)
        for button in (self.process_button, self.analysis_button, self.standard_button, self.close_button):
            actions.addWidget(button)
        panel.addLayout(actions)
        panel.addWidget(QLabel("处理进度"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("添加文件并核对本次参数后开始处理。进度和结果位置会显示在这里。")
        self.log.setMinimumHeight(100)
        panel.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("结果文件"))
        self.results = QComboBox()
        row.addWidget(self.results, 1)
        self.plot_button = QPushButton("用这份 Excel 一键绘图")
        self.plot_button.setEnabled(False)
        self.plot_button.clicked.connect(self._plot)
        row.addWidget(self.plot_button)
        panel.addLayout(row)
        scroll = QScrollArea()
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        columns.addWidget(scroll, 1)
        layout.addWidget(self.controls, 1)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        for signal in (self.files.model().rowsInserted, self.files.model().rowsRemoved,
                       self.files.model().modelReset):
            signal.connect(self._files_changed)
        for field in self.fields.values():
            field.valueChanged.connect(self._update_summary)
        self.split_mode.currentIndexChanged.connect(self._update_summary)
        self._mode_changed()
        self._files_changed()

    def _mode_changed(self, *_):
        mode = self.mode.currentData()
        visible = {"electrochem": {"mass_mg", "time_step"}, "cp_cycle": {"time_step"},
                   "cv_cycle": set(), "cdi": set(self.fields)-{"time_step"}, "contribution": set()}[mode]
        for key, field in self.fields.items():
            if key in ("calibration_scale", "calibration_base"):
                continue
            self.form.setRowVisible(field, key in visible)
        self.form.setRowVisible(self.split_mode, mode == "cv_cycle")
        self.form.setRowVisible(self.sampling, mode == "cdi")
        self.form.setRowVisible(self.calibration_container, mode == "cdi")
        self.mass_note.setVisible(mode == "cdi")
        self.mass_edit_button.setVisible(mode in {"cdi", "electrochem"})
        self.form.setRowVisible(self.units, mode == "cdi")
        self.form.setRowVisible(self.tail_policy, mode == "cdi")
        self.standard_button.setVisible(mode == "cdi")
        self.analysis_button.setVisible(mode != "cdi" and (self.embedded or hasattr(self.parent(), "run_analysis")))
        self.hint.setText({
            "electrochem": "添加同一样品、同一质量的 CV/GCD TXT。保留一列横坐标、多列曲线；CV 归一化为 A/g。",
            "cp_cycle": "保留全量 CP 数据、放电时间汇总和尾数分表。Time 按采样间隔生成。原放电时长算法的峰谷检测存在疑点，汇总保留旧值并提示复核。",
            "cv_cycle": "保留原始处理数据和尾号 0–9 分表。电流保留原始 A，不做质量归一化。",
            "cdi": "保留原始数据、电导率、浓度、浓度差、吸附容量、吸附速率、吸附最大值七表。标定按原式 (电导率−截距)/斜率；请按本次实验核对参数。",
            "contribution": "选择 CV结果.xlsx。沿用原四表模板及公式，要求 3201 个电压点、−0.8～0.8 V 往返及 2/5/10/20/50/100/200 mV/s 七列；不自动插值。",
        }[mode])
        self._sampling_changed()
        if mode == "cdi":
            self._suggest_mass()
        self._update_summary()

    def _toggle_parameters(self, expanded):
        self.parameters_container.setVisible(expanded)
        self.parameter_toggle.setText("收起参数" if expanded else "展开参数")
        self.parameter_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def edit_processing_template(self):
        if self._busy:
            return
        self.parameter_toggle.setChecked(True)
        self.parameters_container.setFocus()
        self.template_note.setText("正在修改当前参数；使用“保存数据处理模板”保存为可复用模板。")

    def _edit_mass(self):
        self.edit_processing_template()
        self.fields["mass_mg"].setFocus()
        self.fields["mass_mg"].selectAll()

    def _update_summary(self, *_):
        mode = self.mode.currentData()
        mass = self.fields["mass_mg"].value()
        mass_text = f"质量 {mass:g} mg" if mass > 0 else "质量待填写"
        if mode == "cdi":
            sampling = ("采样间隔自动识别" if self.sampling.currentData() == "auto"
                        else f"采样 {self.fields['cdi_step'].value():g} 秒/点")
            ads = self.fields["ads_minutes"].value()
            des = self.fields["des_minutes"].value()
            self.summary.setText(f"{mass_text}  ·  体积 {self.fields['volume_ml'].value():g} mL  ·  {sampling}"
                                 f"  ·  每圈 吸附 {ads:g} + 脱附 {des:g} = {ads + des:g} 分钟")
        elif mode == "electrochem":
            self.summary.setText(f"{mass_text}  ·  GCD 采样 {self.fields['time_step'].value():g} 秒/点")
        elif mode == "cp_cycle":
            self.summary.setText(f"采样 {self.fields['time_step'].value():g} 秒/点  ·  保留全量及尾数分表")
        elif mode == "cv_cycle":
            self.summary.setText(self.split_mode.currentText() + "  ·  原始电流不按质量归一化")
        else:
            self.summary.setText("沿用原四表模板  ·  3201 个电压点  ·  7 个扫速")

    def _sampling_changed(self, *_):
        self.form.setRowVisible(self.fields["cdi_step"],
                               self.mode.currentData() == "cdi" and self.sampling.currentData() == "manual")
        if self.sampling.currentData() == "manual" and self.isVisible() and not self._loading_template:
            self.parameter_toggle.setChecked(True)
        if hasattr(self, "summary") and hasattr(self, "split_mode"):
            self._update_summary()

    def _paths(self):
        return [self.files.item(i).data(Qt.UserRole) or self.files.item(i).text()
                for i in range(self.files.count())]

    def _files_changed(self, *_):
        self.file_count.setText(f"文件清单 · {self.files.count()} 个")
        for i in range(self.files.count()):
            item = self.files.item(i)
            path = item.data(Qt.UserRole) or item.text()
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setText(Path(path).name)
        self._suggest_mass()

    def _mass_changed(self, *_):
        if not self._mass_editing and not self._loading_template:
            self._mass_manual = True
        self._show_mass()

    def _suggest_mass(self, *_):
        if self.mode.currentData() != "cdi":
            return
        paths = self._paths()
        file_key = tuple(paths)
        preserve_manual = file_key == self._mass_file_key and self._mass_manual
        self._mass_suggestions = [suggest_cdi_mass(path) for path in paths]
        masses = {item["mass_mg"] for item in self._mass_suggestions if item}
        self._mass_mixed = len(masses) > 1
        # A suggestion is applied only when every file identifies the same mass.
        # Any list change requires a fresh check; never carry an earlier sample's
        # mass into a new or unidentified sample silently.
        if not preserve_manual:
            self._mass_manual = False
            self._mass_editing = True
            try:
                if len(masses) == 1 and all(self._mass_suggestions):
                    self.fields["mass_mg"].setValue(next(iter(masses)))
                else:
                    self.fields["mass_mg"].setValue(0)
            finally:
                self._mass_editing = False
        self._mass_file_key = file_key
        self._show_mass()

    def _show_mass(self, *_):
        if self._mass_mixed:
            values = sorted({item["mass_mg"] for item in self._mass_suggestions if item})
            self.mass_note.setText("识别到不同质量：" + "、".join(f"{v:g} mg" for v in values)
                                   + "。请移除其他质量的文件，分批处理。")
        else:
            value = self.fields["mass_mg"].value()
            sources = list(dict.fromkeys(item["source"] for item in self._mass_suggestions if item))
            if self._mass_suggestions and all(self._mass_suggestions):
                detail = "识别来源：" + "；".join(sources)
            else:
                detail = "有文件未识别到明确质量，请填写并核对本批文件使用相同质量。" if self._mass_suggestions else "添加文件后自动识别质量。"
            self.mass_note.setText((f"本次计算质量：{value:g} mg（可修改）。" if value > 0
                                   else "本次质量尚未填写。") + detail)

    def _add(self):
        if self._busy:
            return
        filt = "TXT 数据 (*.txt)" if self.mode.currentData() in ("electrochem", "cp_cycle", "cv_cycle") else "表格 (*.xlsx *.csv *.txt)"
        paths, _ = QFileDialog.getOpenFileNames(self, "选择原始数据", "E:/Data", filt)
        self._merge_paths(paths)

    def _merge_paths(self, paths):
        existing = {str(Path(p).resolve()).casefold() for p in self._paths()}
        added = []
        skipped = 0
        for path in paths:
            path = str(Path(path).resolve())
            key = path.casefold()
            if key in existing:
                continue
            if self.files.count() + len(added) >= 100:
                skipped += 1
                continue
            existing.add(key)
            added.append(path)
        self.files.addItems(added)
        if skipped:
            self.log.appendPlainText("每批最多 100 个文件，其余请分批添加。")
        return len(added)

    def add_folder(self, path=None):
        if self._busy:
            return
        if not path or isinstance(path, bool):
            path = QFileDialog.getExistingDirectory(self, "添加原始数据文件夹", "E:/Data")
        if not path:
            return
        folder = Path(path)
        if not folder.is_dir():
            QMessageBox.information(self, "请选择文件夹", "所选文件夹不存在。")
            return
        mode = self.mode.currentData()
        extensions = ({".txt"} if mode in {"electrochem", "cp_cycle", "cv_cycle"}
                      else {".xlsx"} if mode == "contribution" else {".xlsx", ".csv", ".tsv", ".txt"})
        existing = {str(Path(p).resolve()).casefold() for p in self._paths()}
        remaining = max(0, 100 - self.files.count())
        if not remaining:
            QMessageBox.information(self, "文件已满", "每批最多 100 个文件，请移除部分文件后再添加。")
            return

        def scan(progress):
            found = []
            progress("正在扫描文件夹：" + str(folder))
            errors = []
            for directory, dirs, names in os.walk(folder, followlinks=False, onerror=lambda e: errors.append(str(e))):
                dirs.sort(key=str.casefold)
                for name in sorted(names, key=str.casefold):
                    candidate = Path(directory) / name
                    if (candidate.suffix.lower() not in extensions or name.startswith("~$")
                            or name.lower().endswith(("-处理.xlsx", "_处理结果.xlsx"))):
                        continue
                    resolved = str(candidate.resolve())
                    if resolved.casefold() in existing:
                        continue
                    if len(found) >= remaining:
                        return {"paths": found, "limited": True, "errors": errors}
                    existing.add(resolved.casefold())
                    found.append(resolved)
            return {"paths": found, "limited": False, "errors": errors}

        self._start_job(scan, "folder")

    def _remove(self):
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))

    def choose_output(self):
        if self._busy:
            return
        path = QFileDialog.getExistingDirectory(self, "选择保存位置", self.output.text())
        if path:
            self.set_output_dir(path)

    def _choose_output(self):
        self.choose_output()

    def set_output_dir(self, path):
        if not self._busy:
            self.output.setText(str(path))

    def _parameter_values(self):
        values = {key: field.value() for key, field in self.fields.items()}
        values.update(split_mode=self.split_mode.currentData(), conductivity_unit=self.units.currentData(),
                      cdi_tail=self.tail_policy.currentData())
        if self.sampling.currentData() == "auto":
            values["cdi_step"] = "auto"
        return {key: values[key] for key in DEFAULTS[self.mode.currentData()]}

    def load_processing_template(self, path=None):
        if self._busy:
            return False
        if not path or isinstance(path, bool):
            path, _ = QFileDialog.getOpenFileName(self, "加载数据处理模板", str(BASE / "templates"), "参数模板 (*.json)")
        if not path:
            return False
        try:
            document = read_processing_template(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "模板未加载", str(exc))
            return False
        prior_mass = self.fields["mass_mg"].value()
        prior_manual = self._mass_manual
        had_files = bool(self.files.count())
        old_mode = self.mode.currentData()
        self._loading_template = True
        try:
            self.mode.setCurrentIndex(self.mode.findData(document["mode"]))
            for key, value in document["parameters"].items():
                if key == "mass_mg" and had_files:
                    continue
                if key == "cycle_minutes":
                    # 旧模板的单圈总时长 → 平均拆成吸附/脱附
                    self.fields["ads_minutes"].setValue(value / 2)
                    self.fields["des_minutes"].setValue(value / 2)
                    continue
                if key == "cdi_step":
                    automatic = value == "auto"
                    self.sampling.setCurrentIndex(self.sampling.findData("auto" if automatic else "manual"))
                    if not automatic:
                        self.fields[key].setValue(value)
                elif key in self.fields:
                    self.fields[key].setValue(value)
                else:
                    widget = {"split_mode": self.split_mode, "conductivity_unit": self.units,
                              "cdi_tail": self.tail_policy}[key]
                    widget.setCurrentIndex(widget.findData(value))
            # A template describes reusable settings, never the current sample.
            # Keep current same-mode confirmation; on switching into CDI use
            # the filename suggestions just established by _mode_changed.
            if had_files and old_mode == document["mode"]:
                self.fields["mass_mg"].setValue(prior_mass)
                self._mass_manual = prior_manual
        finally:
            self._loading_template = False
        self._template_path = str(path)
        note = "已加载数据处理模板：" + Path(path).name
        if had_files and "mass_mg" in document["parameters"]:
            note += "；模板质量未覆盖当前文件，请核对本次质量。"
        self.template_note.setText(note)
        self.log.appendPlainText(note)
        self._show_mass()
        self._update_summary()
        return True

    def save_processing_template(self, path=None):
        if self._busy:
            return False
        if not path or isinstance(path, bool):
            default = self._template_path or str(BASE / "templates" / (self.mode.currentData() + "-处理模板.json"))
            path, _ = QFileDialog.getSaveFileName(self, "保存数据处理模板", default, "参数模板 (*.json)")
        if not path:
            return False
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            write_processing_template(path, self.mode.currentData(), self._parameter_values())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "模板未保存", str(exc))
            return False
        self._template_path = str(path)
        self.template_note.setText("已保存数据处理模板：" + path.name)
        self.log.appendPlainText("已保存参数模板：" + str(path))
        return True

    def _set_busy(self, value):
        self._busy = value
        for control in (self.controls, self.process_button, self.analysis_button, self.standard_button, self.close_button):
            control.setEnabled(not value)
        self.plot_button.setEnabled(not value and bool(self.result_files))
        self.busyChanged.emit(value)

    def _run(self):
        if self._busy:
            return
        paths = self._paths()
        if not paths:
            QMessageBox.information(self, "请选择数据", "请先添加文件。")
            return
        if not self.output.text().strip():
            QMessageBox.information(self, "请选择位置", "请填写独立的结果保存文件夹。")
            return
        options = self._parameter_values()
        if self.mode.currentData() == "cdi":
            if self._mass_mixed:
                QMessageBox.information(self, "请按质量分批", self.mass_note.text())
                return
            if options["mass_mg"] <= 0:
                QMessageBox.information(self, "请填写质量", "请填写本次活性物质质量（mg），再开始处理。")
                self.parameter_toggle.setChecked(True)
                self.fields["mass_mg"].setFocus()
                return
        mode, output = self.mode.currentData(), self.output.text().strip()
        self.log.appendPlainText("开始处理，原始文件只读…")
        if mode == "cdi":
            self.log.appendPlainText(f"本次质量：{options['mass_mg']:g} mg；溶液体积：{options['volume_ml']:g} mL；"
                                     + ("采样间隔：从原始时间自动识别。" if options["cdi_step"] == "auto"
                                        else f"采样间隔：{options['cdi_step']:g} s。"))
        def process(progress):
            progress("正在准备处理…")
            return run_legacy(mode, paths, output, options, progress)
        self._start_job(process)

    def _start_job(self, job, kind="process"):
        self._job_kind = kind
        self._set_busy(True)
        self._outcome = None
        self._thread = QThread(self)
        self._worker = _Worker(job)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log.appendPlainText)
        self._worker.finished.connect(lambda result: setattr(self, "_outcome", (True, result)))
        self._worker.failed.connect(lambda message: setattr(self, "_outcome", (False, message)))
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._finished)
        self._thread.start()

    def _finished(self):
        self._thread.deleteLater()
        self._thread = self._worker = None
        self._set_busy(False)
        ok, result = self._outcome
        if not ok:
            self.log.appendPlainText("未完成：" + result)
            QMessageBox.warning(self, "处理未完成", result)
            return
        if self._job_kind == "folder":
            count = self._merge_paths(result["paths"])
            self.log.appendPlainText(f"文件夹扫描完成，添加 {count} 个文件。")
            if result["limited"]:
                self.log.appendPlainText("已达到本批 100 个文件上限，其余请分批处理。")
            for message in result["errors"][:3]:
                self.log.appendPlainText("未读取的目录：" + message)
            return
        self.result_files = result["files"]
        self.results.clear()
        for path in self.result_files:
            self.results.addItem(Path(path).name, path)
        self.plot_button.setEnabled(bool(self.result_files))
        self.log.appendPlainText("已生成：\n" + "\n".join(self.result_files))
        self.resultsReady.emit(list(self.result_files), result["folder"])
        from ec_output_dialog import offer_open_folder
        offer_open_folder(self, result["folder"], len(self.result_files))

    def _plot(self):
        path = self.results.currentData()
        if not path:
            return
        if self.embedded:
            self.plotRequested.emit(path)
            return
        from ec_plot_studio import PlotStudio
        PlotStudio(self, initial_path=path).exec()

    def _analysis(self):
        self.want_analysis = True
        if self.embedded:
            self.analysisRequested.emit()
        else:
            self.accept()

    def _standard(self):
        from ec_conductivity_ui import ConductivityDialog
        dialog = ConductivityDialog(self, output_dir=self.output.text().strip())
        dialog.add_paths(self._paths())
        dialog.exec()

    def accept(self):
        if not self.embedded and not self._busy:
            super().accept()

    def reject(self):
        if not self.embedded and not self._busy:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self._busy or self.embedded else super().closeEvent(event)
