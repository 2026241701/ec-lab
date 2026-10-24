"""Integration contracts for the two persistent desktop workspaces.

DEPRECATED: 界面已回滚为经典单界面（WorkspaceHost 页签被移除），本套
测试针对的 WorkspaceHost 不再存在，故整体跳过。ec_workspaces.py 保留在
仓库里但运行期不再被 import。
"""
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
from PySide6.QtWidgets import QApplication
import ec_gui


@unittest.skip("界面回滚：WorkspaceHost 已移除，回到经典单界面")
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.object(ec_gui.MainWindow, "_first_run_bootstrap"), \
             patch.object(ec_gui.MainWindow, "_load_config_file"):
            self.window = ec_gui.MainWindow()
        self.window.show()
        self.app.processEvents()
        self.host = self.window.workspaces

    def tearDown(self):
        self.host.data._busy = False
        if self.host.plot:
            self.host.plot._busy = False
        with patch.object(ec_gui.cfg_guard, "save_config", return_value=(True, "test")):
            self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_two_workspaces_and_requested_menus(self):
        self.assertEqual([self.host.tabs.tabText(i) for i in range(self.host.tabs.count())],
                         ["数据处理", "一键绘图"])
        self.assertEqual([a.text() for a in self.window.menuBar().actions()],
                         ["文件", "处理", "绘图", "外观", "帮助"])
        self.assertIsNone(self.host.plot)
        self.assertFalse(self.host.data.isWindow())
        self.assertTrue(self.window._main_toolbar.isHidden())
        process_menu = self.window.menuBar().actions()[1].menu()
        self.assertEqual([a.text() for a in process_menu.actions()],
                         ["加载数据处理模板…", "保存数据处理模板…", "修改数据处理模板"])

    def test_result_transfer_reuses_plot_page_and_preserves_data_page(self):
        self.host.show_plot()
        page = self.host.plot
        self.assertIsNotNone(page)
        self.assertFalse(page.isWindow())
        self.host.show_data()
        self.host.data._add_file("example(25mg).xlsx")
        # load_path 会真实地更新 book；用 side_effect 模拟，避免无操作 mock 把
        # 结果就绪后的同路径再打开误判成重复加载。
        def remember(path):
            page.book = SimpleNamespace(path=path)
        with patch.object(page, "load_path", side_effect=remember) as load:
            self.host.data.resultsReady.emit(["new-result.xlsx"], "new-results")
            self.host.data.plotRequested.emit("new-result.xlsx")
            load.assert_called_once_with("new-result.xlsx")
        self.assertEqual(self.host.tabs.currentIndex(), 1)
        self.assertIs(self.host.plot, page)
        self.assertEqual(len(self.host.data._paths()), 1)
        self.assertEqual(self.window._last_workbook, "new-result.xlsx")
        self.assertEqual(self.host.result_directory(), "new-results")
        page.book = SimpleNamespace(path="new-result.xlsx")
        with patch.object(page, "load_path") as load:
            self.host.show_data()
            self.host.data.plotRequested.emit("new-result.xlsx")
            load.assert_not_called()
        self.assertIs(self.host.plot, page)

    def test_busy_page_blocks_second_job_and_window_close(self):
        self.host.show_plot()
        self.host.show_data()
        self.host.data._busy = True
        self.host.data.busyChanged.emit(True)
        self.host.tabs.setCurrentIndex(1)
        self.assertEqual(self.host.tabs.currentIndex(), 1)
        self.assertFalse(self.host.plot.isEnabled())
        self.assertTrue(all(not a.isEnabled() for a in self.window._workspace_actions))
        with patch.object(ec_gui.cfg_guard, "save_config") as save:
            self.assertFalse(self.window.close())
            save.assert_not_called()
        self.host.data._busy = False
        self.host.data.busyChanged.emit(False)
        self.assertTrue(self.host.plot.isEnabled())
        self.assertTrue(all(a.isEnabled() for a in self.window._workspace_actions))

    def test_output_directory_is_shared_and_advanced_tools_remain_accessible(self):
        with tempfile.TemporaryDirectory() as temp:
            self.host.set_output_dir(temp)
            self.assertEqual(self.host.data.output.text(), temp)
            self.assertEqual(self.window.output_cfg["dir"], temp)
            self.assertEqual(self.host.result_directory(), temp)
            self.host.show_plot()
            self.assertEqual(self.host.plot.output_dir, temp)
            restored = str(Path(temp) / "restored-output")
            cfg = self.window.current_cfg()
            cfg["output"]["dir"] = restored
            self.window._apply_cfg(cfg)
            self.assertEqual(self.host.data.output.text(), restored)
            self.assertEqual(self.host.plot.output_dir, restored)
        self.host.show_advanced()
        self.assertEqual(self.host.stack.currentIndex(), 1)
        self.assertFalse(self.window._main_toolbar.isHidden())
        self.host.show_data()
        self.assertEqual(self.host.stack.currentIndex(), 0)
        self.assertTrue(self.window._main_toolbar.isHidden())


if __name__ == "__main__":
    unittest.main()
