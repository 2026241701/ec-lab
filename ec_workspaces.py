"""Two persistent workspaces around the existing processing and plotting tools."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from ec_legacy_ui import LegacyExcelDialog


class WorkspaceHost(QWidget):
    def __init__(self, owner, advanced):
        super().__init__(owner)
        self.owner = owner
        self.plot = None
        self.last_result_dir = ""
        self._pending_plot_path = None
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 6)
        layout.addWidget(self.stack)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.stack.addWidget(self.tabs)

        self.data = LegacyExcelDialog(owner, embedded=True,
                                      output_dir=owner.output_cfg.get("dir"))
        self.data.resultsReady.connect(self._results_ready)
        self.data.plotRequested.connect(self.show_plot)
        self.data.analysisRequested.connect(self.show_advanced)
        self.data.busyChanged.connect(self._sync_busy)
        self.data.output.textChanged.connect(self._output_changed)
        self.tabs.addTab(self.data, "数据处理")
        self.plot_container = QWidget()
        self.plot_layout = QVBoxLayout(self.plot_container)
        self.plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_hint = QLabel("打开处理后的 Excel，自动生成常用图。")
        self.plot_hint.setAlignment(Qt.AlignCenter)
        self.plot_layout.addWidget(self.plot_hint)
        self.tabs.addTab(self.plot_container, "一键绘图")
        self.tabs.currentChanged.connect(self._tab_changed)

        advanced_page = QWidget()
        advanced_layout = QVBoxLayout(advanced_page)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        back = QPushButton("返回数据处理")
        back.clicked.connect(lambda: self.show_data())
        row.addWidget(back)
        row.addWidget(QLabel("高级电化学工具 · 比电容、EIS 与原有详细预览"), 1)
        advanced_layout.addLayout(row)
        advanced_layout.addWidget(advanced, 1)
        self.stack.addWidget(advanced_page)
        owner._main_toolbar.hide()

    def is_busy(self):
        return (self.data._busy or bool(self.plot and self.plot._busy)
                or bool(self.data._thread and self.data._thread.isRunning())
                or bool(self.plot and self.plot.worker and self.plot.worker.isRunning()))

    def _sync_busy(self, *_):
        data_busy = self.data._busy
        plot_busy = bool(self.plot and self.plot._busy)
        self.data.setEnabled(not plot_busy and not self.owner._running)
        if self.plot:
            self.plot.setEnabled(not data_busy and not self.owner._running)
        # Tabs remain usable to inspect the other workspace. Mutating menu
        # actions cannot start a second computation while either worker runs.
        for action in getattr(self.owner, "_workspace_actions", []):
            action.setEnabled(not (data_busy or plot_busy or self.owner._running))
        if data_busy or plot_busy:
            self.owner.statusBar().showMessage("正在处理，请稍候；可以切换工作区查看已有内容。")
        else:
            self.owner.statusBar().showMessage("就绪" + (" · 最近结果：" + self.last_result_dir if self.last_result_dir else ""))
            if self.tabs.currentIndex() == 1:
                self._ensure_plot()

    def _output_changed(self, path):
        self.owner.output_cfg["dir"] = path
        self.owner.lab_out.setText(path)
        self.owner.lab_out_bar.setText("输出：" + path)
        if self.plot:
            self.plot.set_output_dir(path)

    def set_output_dir(self, path):
        path = str(path)
        if self.data.output.text() != path:
            self.data.set_output_dir(path)
        self._output_changed(path)

    def _results_ready(self, files, folder):
        if files:
            self.owner._last_workbook = str(files[0])
        self._output_ready(folder)

    def _output_ready(self, folder):
        self.last_result_dir = str(folder)
        self.owner.statusBar().showMessage("已保存 · " + self.last_result_dir)

    def show_data(self, mode=None):
        self.stack.setCurrentIndex(0)
        self.owner._main_toolbar.hide()
        self.tabs.setCurrentIndex(0)
        if mode is not None and not self.is_busy():
            index = self.data.mode.findData(mode)
            if index >= 0:
                self.data.mode.setCurrentIndex(index)

    def show_advanced(self):
        if self.is_busy():
            return
        self.stack.setCurrentIndex(1)
        self.owner._main_toolbar.show()

    def _ensure_plot(self):
        if self.plot is None:
            if self.data._busy or self.owner._running:
                self.plot_hint.setText("数据正在处理，完成后即可打开绘图工作区。")
                return None
            from ec_plot_studio import PlotStudio
            self.plot = PlotStudio(self.owner, embedded=True)
            self.plot.set_output_dir(self.owner.output_cfg.get("dir", ""))
            self.plot.busyChanged.connect(self._sync_busy)
            self.plot.outputReady.connect(self._output_ready)
            self.plot_layout.removeWidget(self.plot_hint)
            self.plot_hint.hide()
            self.plot_layout.addWidget(self.plot)
        if self._pending_plot_path and not self.is_busy():
            path, self._pending_plot_path = self._pending_plot_path, None
            # The processing result button also serves as a return-to-plot
            # shortcut. Preserve unsaved appearance edits for this same result.
            # Explicitly opening a workbook in PlotStudio remains the reload path.
            current = self.plot.book
            if current is None or Path(current.path).resolve() != Path(path).resolve():
                self.plot.load_path(path)
        return self.plot

    def _tab_changed(self, index):
        if index == 1:
            self._ensure_plot()

    def show_plot(self, path=None):
        if isinstance(path, str) and path:
            self._pending_plot_path = path
        self.stack.setCurrentIndex(0)
        self.owner._main_toolbar.hide()
        self.tabs.setCurrentIndex(1)
        self._ensure_plot()

    def plot_action(self, name):
        if self.is_busy() or self.owner._running:
            return
        self.show_plot()
        page = self._ensure_plot()
        if page:
            getattr(page, name)()

    def process_action(self, name):
        if self.is_busy() or self.owner._running:
            return
        self.show_data()
        getattr(self.data, name)()

    def result_directory(self):
        return self.last_result_dir or self.data.output.text() or self.owner.output_cfg.get("dir", "")
