# -*- coding: utf-8 -*-
"""ec-lab 协作看板：给 Ding 看的图形界面

不用敲命令行。双击 collaboration.bat（由 python make_launchers.py
生成）就能看：
  - 现在谁在改代码、持有多久
  - 三个项目各自在做什么
  - 一键拿锁 / 还锁 / 跑测试
"""

import os
import sys
import json
import time
import subprocess
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.environ.setdefault("QT_QPA_PLATFORM", "")

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton,
                               QTextEdit, QGroupBox)
from PySide6.QtGui import QFont

import ec_lock

PROJECTS = [
    ("参数", "",
     "处理参数区：5 个可折叠分组、输出文件夹按钮、表格可读性"),
    ("绘图", "",
     "绘图引擎：坐标轴范围锁定、中文工具条、样式键位表"),
    ("预览", "",
     "出图预览：比例不变形、上下分栏+日志、缩放档位"),
]


class Board(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ec-lab 协作看板 — 三个项目一起改时用")
        self.resize(760, 620)
        self.me = None
        self._build()
        self._tick()

    def _build(self):
        lay = QVBoxLayout(self)

        # 谁在改
        g1 = QGroupBox("现在谁在改代码")
        g1.setObjectName("box")
        v1 = QVBoxLayout(g1)
        self.lab_who = QLabel("读取中…")
        self.lab_who.setObjectName("big")
        v1.addWidget(self.lab_who)
        self.lab_files = QLabel("")
        self.lab_files.setObjectName("hint")
        v1.addWidget(self.lab_files)

        hb = QHBoxLayout()
        b_take = QPushButton("我要开始改（拿钥匙）")
        b_take.clicked.connect(self.on_take)
        self.ed_name = QLineEditLike("我的名字（参数/绘图/预览）")
        hb.addWidget(self.ed_name)
        hb.addWidget(b_take)
        b_rel = QPushButton("我改完了（还钥匙+跑测试）")
        b_rel.clicked.connect(self.on_release)
        hb.addWidget(b_rel)
        v1.addLayout(hb)

        hb2 = QHBoxLayout()
        b_test = QPushButton("跑全部测试")
        b_test.clicked.connect(self.on_test)
        hb2.addWidget(b_test)
        b_refresh = QPushButton("刷新")
        b_refresh.clicked.connect(self._tick)
        hb2.addWidget(b_refresh)
        b_steal = QPushButton("对方不干了，强行拿钥匙")
        b_steal.clicked.connect(self.on_steal)
        hb2.addWidget(b_steal)
        v1.addLayout(hb2)
        lay.addWidget(g1)

        # 分工
        g2 = QGroupBox("三个项目各管什么")
        g2.setObjectName("box")
        v2 = QVBoxLayout(g2)
        for nm, wid, duty in PROJECTS:
            row = QHBoxLayout()
            l1 = QLabel("【%s】" % nm)
            l1.setStyleSheet("font-weight:bold;color:#1F6E5A")
            row.addWidget(l1)
            l2 = QLabel(duty)
            l2.setObjectName("hint")
            row.addWidget(l2, stretch=1)
            if wid:      # 只有填了工作区目录名才显示（公开仓库里留空）
                l3 = QLabel(wid)
                l3.setObjectName("hint")
                row.addWidget(l3)
            v2.addLayout(row)
        note = QLabel("⚠ 谁碰这三处就会撞车：ec_gui.py 头部 import、"
                      "THEMES 主题定义、main()")
        note.setObjectName("hint")
        v2.addWidget(note)
        lay.addWidget(g2)

        # 交接便条
        g3 = QGroupBox("交接便条（谁改到哪一步）")
        g3.setObjectName("box")
        v3 = QVBoxLayout(g3)
        self.ed_note = QTextEdit()
        self.ed_note.setPlaceholderText(
            "写一句：我改完了什么、下一步要做什么。\n"
            "下一个人拿钥匙时会看到这段话。")
        self.ed_note.setMaximumHeight(90)
        v3.addWidget(self.ed_note)
        b_note = QPushButton("记下这句")
        b_note.clicked.connect(self.on_note)
        v3.addWidget(b_note)
        lay.addWidget(g3)

        # 输出
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setObjectName("log")
        lay.addWidget(self.out, stretch=1)

        self.setStyleSheet("""
            QWidget { font-family: "Microsoft YaHei"; font-size: 9pt; }
            QGroupBox { border: 1px solid #C8CDD2; margin-top: 10px;
                        padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin;
                               left: 8px; padding: 0 4px; }
            QLabel#big { font-size: 12pt; font-weight: bold; }
            QLabel#hint { color: #666666; font-size: 8pt; }
            QTextEdit#log { background: #F7F7F7; border: 1px solid #C8CDD2; }
            QPushButton { border: 1px solid #9AA0A6; padding: 5px 10px;
                          background: #FFFFFF; }
            QPushButton:hover { background: #EAF2F0;
                                border-color: #1F6E5A; }
            QLineEdit { border: 1px solid #9AA0A6; padding: 4px; }
        """)

    # ---------------- 动作 ----------------

    def _name(self):
        t = self.ed_name.text().strip()
        return t or "未命名"

    def _say(self, s):
        self.out.append(time.strftime("%H:%M:%S ") + s)
        self.out.verticalScrollBar().setValue(
            self.out.verticalScrollBar().maximum())

    def on_take(self):
        nm = self._name()
        rc = ec_lock.cmd_take(nm)
        self._say("拿锁 %s：%s" % (nm, "成功" if rc == 0 else "失败（有人在改）"))
        self._tick()

    def on_release(self):
        """还锁。看板场景下不靠名字判断 —— 拿锁时记住是谁，
        还锁时就还那把锁，避免"名字换了还不了"的糊涂。"""
        cur = ec_lock._read_lock() or {}
        holder = cur.get("name")
        if not holder:
            self._say("现在没有人在改，无需还锁。")
            self._tick()
            return
        self._say("以「%s」的身份跑测试…" % holder)
        ok = ec_lock.run_tests()
        if ok:
            ec_lock._write_lock({"name": None, "since": None, "files": []})
            ec_lock._log("[还锁] %s（看板）" % holder)
            self._say("测试全过，钥匙已归还。")
        else:
            self._say("测试没过，钥匙没放。修好后再还。")
        self._tick()

    def on_test(self):
        self._say("跑测试中…")
        ok = ec_lock.run_tests()
        self._say("结果：%s" % ("全部通过" if ok else "有失败，看上面红字"))

    def on_steal(self):
        self._say("强行拿钥匙请用命令行（要确认对方真不干了）："
                  "ec_lock.py steal")

    def on_note(self):
        m = self.ed_note.toPlainText().strip()
        if not m:
            return
        ec_lock.cmd_handover(m)
        self._say("已记下交接便条。")
        self.ed_note.clear()
        self._tick()

    # ---------------- 刷新 ----------------

    def _tick(self):
        cur = ec_lock._read_lock()
        if cur and cur.get("name"):
            held = time.time() - cur.get("since", 0)
            self.lab_who.setText("🔒 %s 正在改（已持有 %.0f 分钟）"
                                 % (cur["name"], held / 60))
            self.lab_who.setStyleSheet("color:#D2603A;font-size:12pt;"
                                       "font-weight:bold;")
            self.lab_files.setText("动的文件：%s"
                                   % "、".join(cur.get("files", [])))
        else:
            self.lab_who.setText("🔓 空闲 — 现在可以开始改")
            self.lab_who.setStyleSheet("color:#1F6E5A;font-size:12pt;"
                                       "font-weight:bold;")
            self.lab_files.setText("先在上面填自己的名字，再点「我要开始改」")

        if os.path.isfile(ec_lock.HANDOVER):
            self.ed_note.setPlaceholderText(
                open(ec_lock.HANDOVER, encoding="utf-8").read())

        from PySide6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(4000)


class QLineEditLike(QLabel):
    """点一下就弹出名字选择，避免 Ding 打字输错"""
    NAMES = ["参数", "绘图", "预览"]

    def __init__(self, tip):
        super().__init__(tip)
        self.setObjectName("hint")
        self._cur = ""
        from PySide6.QtCore import Qt
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("color:#38699E;border:1px dashed #38699E;"
                           "padding:4px;")

    def text(self):
        return self._cur

    def mousePressEvent(self, ev):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for n in self.NAMES:
            m.addAction(n)
        act = m.exec(ev.globalPos())
        if act:
            self._cur = act.text()
            self.setText("我是：%s" % self._cur)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    b = Board()
    b.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
