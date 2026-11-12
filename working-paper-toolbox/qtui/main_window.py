# -*- coding: utf-8 -*-
"""qtui.main_window —— 主窗口：顶部主功能导航 + 左侧子功能导航 + 共享日志区。

布局：
    ┌──────────────────────────────────────────┐
    │ 底稿工具箱   [签章页] [底稿替换] [文件整理]… │  ← 顶栏（主功能）
    ├────────┬─────────────────────────────────┤
    │ 子功能1 │                                 │
    │ 子功能2 │        当前子功能页面              │
    │ …      │                                 │
    ├────────┴─────────────────────────────────┤
    │ 运行日志                                  │  ← 可拖动分隔
    └──────────────────────────────────────────┘
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QListWidget, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from .core import BASE_DIR, RES_DIR, RUNNER, Runner, Settings
from .pages import build_areas
from .widgets import apply_state, collect_state

THEME = """
* { font-family: "Microsoft YaHei UI"; font-size: 13px; }
QMainWindow, QFrame#Body { background: #f3f5f9; }

/* ---- 顶栏 ---- */
QFrame#TopBar { background: #ffffff; border-bottom: 1px solid #e3e7ef; }
QLabel#Brand { font-size: 17px; font-weight: 700; color: #16233c; padding: 0 6px; }
QPushButton#MainNav {
    background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 12px 18px 10px 18px; color: #5d6b85; font-size: 14px;
}
QPushButton#MainNav:hover { color: #2f6fed; }
QPushButton#MainNav:checked {
    color: #2f6fed; border-bottom: 2px solid #2f6fed; font-weight: 600;
}

/* ---- 左侧子功能导航 ---- */
QListWidget#SideNav {
    background: transparent; border: none; outline: 0; padding-top: 4px;
}
QListWidget#SideNav::item {
    padding: 9px 12px; margin: 2px 8px; border-radius: 8px; color: #43506b;
}
QListWidget#SideNav::item:hover { background: #e7eefb; }
QListWidget#SideNav::item:selected { background: #2f6fed; color: #ffffff; }

/* ---- 卡片 ---- */
QGroupBox {
    background: #ffffff; border: 1px solid #e4e8f0; border-radius: 10px;
    margin-top: 16px; padding: 10px 12px 10px 12px;
    font-weight: 600; color: #16233c;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; top: 4px; padding: 0 4px;
    color: #2f6fed;
}

/* ---- 输入控件 ---- */
QLineEdit, QPlainTextEdit, QSpinBox {
    background: #ffffff; border: 1px solid #d8dee9; border-radius: 6px;
    padding: 5px 8px; selection-background-color: #2f6fed;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {
    border: 1px solid #2f6fed;
}
QCheckBox { spacing: 6px; color: #33405c; }
QSpinBox::up-button, QSpinBox::down-button { width: 16px; }

/* ---- 按钮 ---- */
QPushButton {
    background: #ffffff; border: 1px solid #d8dee9; border-radius: 6px;
    padding: 6px 14px; color: #33405c;
}
QPushButton:hover { background: #f0f4fb; border-color: #b9c6dd; }
QPushButton:pressed { background: #e4ecfa; }
QPushButton:disabled { color: #a5adbd; background: #f2f3f6; }
QPushButton#Primary {
    background: #2f6fed; border: none; color: #ffffff; font-weight: 600;
    padding: 7px 18px;
}
QPushButton#Primary:hover { background: #2761d2; }
QPushButton#Primary:pressed { background: #2155b8; }
QPushButton#Primary:disabled { background: #a9c2f5; }
QPushButton#Step {
    background: #eef3fd; border: 1px solid #c9d9f8; color: #2456b3;
    font-weight: 600; padding: 9px 14px;
}
QPushButton#Step:hover { background: #e0eafa; border-color: #a9c2f5; }
QLabel#Hint { color: #8a94a8; font-size: 12px; }
QLabel#PanelTitle {
    color: #5d6b85; font-size: 12px; font-weight: 600; padding: 6px 10px 2px 10px;
}

/* ---- 日志区工具条（深底上的小按钮 / 复选框）---- */
QPushButton#LogBtn {
    background: #1b2330; border: 1px solid #2d3846; border-radius: 5px;
    color: #93a4bb; padding: 3px 10px; font-size: 12px;
}
QPushButton#LogBtn:hover { background: #26313f; color: #dbe6f3; border-color: #3d4c5e; }
QPushButton#LogBtn:pressed { background: #2f3c4d; }
QCheckBox#LogOpt { color: #8b9bb2; font-size: 12px; spacing: 5px; }
QCheckBox#LogOpt::indicator { width: 13px; height: 13px; }
QCheckBox#LogOpt::indicator:unchecked {
    border: 1px solid #3d4c5e; background: #1b2330; border-radius: 3px;
}
QCheckBox#LogOpt::indicator:checked {
    border: 1px solid #2f6fed; background: #2f6fed; border-radius: 3px;
}

/* ---- 日志区 ---- */
QFrame#LogPanel { background: #10151d; }
QTextEdit, QPlainTextEdit#LogView {
    background: #10151d; color: #c9d4e3; border: none;
    font-family: "Consolas"; font-size: 12px; selection-background-color: #33507e;
}

/* ---- 滚动条 ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c4cede; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #a9b6ca; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #c4cede; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #a9b6ca; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background: #e3e7ef; }
QSplitter::handle:vertical { height: 1px; }
QStatusBar { background: #ffffff; color: #5d6b85; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("债承底稿处理工具箱")
        self.setStyleSheet(THEME)
        self.settings = Settings()
        self.settings.data.pop("LogView", None)  # 旧版本误存进设置的日志内容
        self.run_buttons: list[QPushButton] = []
        self._busy_count = 0
        self._stats_worker = None

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 顶栏：品牌 + 主功能导航 ----
        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setAttribute(Qt.WA_StyledBackground, True)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(18, 0, 18, 0)
        tb.setSpacing(2)
        brand = QLabel("底稿工具箱")
        brand.setObjectName("Brand")
        tb.addWidget(brand)
        tb.addSpacing(18)
        self.main_buttons: list[QPushButton] = []
        self.areas = build_areas(self)
        for i, (title, _icon, _subs) in enumerate(self.areas):
            btn = QPushButton(f"{_icon}  {title}")
            btn.setObjectName("MainNav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self.show_area(idx))
            tb.addWidget(btn)
            self.main_buttons.append(btn)
        tb.addStretch(1)
        root.addWidget(topbar)

        # ---- 中部：左侧子功能导航 + 页面堆叠 ----
        body = QFrame()
        body.setObjectName("Body")
        body.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(body)
        hb.setContentsMargins(12, 10, 12, 10)
        hb.setSpacing(10)
        self.sub_nav = QListWidget()
        self.sub_nav.setObjectName("SideNav")
        self.sub_nav.setFixedWidth(172)
        self.sub_nav.setCursor(Qt.PointingHandCursor)
        self.sub_nav.currentRowChanged.connect(self._on_sub_changed)
        hb.addWidget(self.sub_nav)
        self.stack = QStackedWidget()
        hb.addWidget(self.stack, 1)
        self._current_subs: list[tuple[str, QWidget]] = []

        # ---- 日志区 ----
        log_panel = QFrame()
        log_panel.setObjectName("LogPanel")
        log_panel.setAttribute(Qt.WA_StyledBackground, True)
        lp = QVBoxLayout(log_panel)
        lp.setContentsMargins(0, 0, 0, 0)
        lp.setSpacing(0)
        # 日志工具条：标题 + 自动清屏 + 清屏/保存/打开日志目录
        log_bar = QWidget()
        lb = QHBoxLayout(log_bar)
        lb.setContentsMargins(6, 2, 8, 2)
        lb.setSpacing(6)
        log_title = QLabel("运行日志")
        log_title.setObjectName("PanelTitle")
        lb.addWidget(log_title)
        lb.addStretch(1)

        self.auto_clear = QCheckBox("运行前自动清屏")
        self.auto_clear.setObjectName("log.autoclear")
        self.auto_clear.setCursor(Qt.PointingHandCursor)
        self.auto_clear.setToolTip("勾选后，每次发起新任务时先清空日志区，只保留本次输出")
        lb.addWidget(self.auto_clear)
        for text, slot, tip in (
            ("清屏", self.clear_log, "清空日志区（Ctrl+L），不影响正在运行的任务"),
            ("保存日志", self.save_log, "把当前日志区内容另存为 .log 文件"),
            ("打开日志目录", self.open_log_dir,
             f"打开各模块写入的日志文件目录：{self._log_dir()}"),
        ):
            btn = QPushButton(text)
            btn.setObjectName("LogBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            lb.addWidget(btn)
        lp.addWidget(log_bar)

        self.log_text = QPlainTextEdit()
        self.log_text.setObjectName("LogView")
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        self.log_text.setPlaceholderText("任务输出将显示在这里…（Ctrl+L 清屏）")
        f = self.log_text.font()
        f.setFamily("Consolas")
        self.log_text.setFont(f)
        lp.addWidget(self.log_text, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(body)
        splitter.addWidget(log_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([640, 300])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # ---- 状态栏 ----
        self._set_status("就绪")
        self.demo_box = QCheckBox("脱敏模式")
        self.demo_box.setObjectName("ui.demo_mode")
        self.demo_box.setToolTip(
            "勾选后子进程按脱敏模式运行：主体名/项目组/落款换成示例值，\n"
            "产物命名去掉项目标识（由 IBDW_DEMO_MODE 环境变量传递）。")
        self.statusBar().addPermanentWidget(self.demo_box)

        # ---- 子进程运行器 ----
        self.runner = Runner(self)
        self.runner.line_received.connect(self.append_log)
        self.runner.finished.connect(self.end_task)
        self.demo_box.toggled.connect(self._on_demo_toggled)

        # ---- 清屏快捷键 Ctrl+L ----
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.clear_log)

        # ---- 恢复设置、默认选第一个主功能 ----
        apply_state(self, self.settings.data)
        self._on_demo_toggled(self.demo_box.isChecked())
        self.show_area(0)

    # ------------------------------------------------------------ 导航
    def show_area(self, idx: int):
        """切换主功能区：刷新左侧子功能列表与页面堆叠。"""
        for j, btn in enumerate(self.main_buttons):
            btn.setChecked(j == idx)
        title, _icon, subs = self.areas[idx]
        self._current_subs = subs
        self.sub_nav.blockSignals(True)
        self.sub_nav.clear()
        for sub_title, _w in subs:
            self.sub_nav.addItem(sub_title)
        self.sub_nav.blockSignals(False)
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))
        for _t, w in subs:
            self.stack.addWidget(w)
        self.setWindowTitle(f"{title} · 债承底稿处理工具箱")
        if subs:
            self.sub_nav.setCurrentRow(0)
        self._set_status("就绪" if self._busy_count == 0 else self.status_var)

    def _on_sub_changed(self, row: int):
        if 0 <= row < len(self._current_subs):
            self.stack.setCurrentIndex(row)

    # ------------------------------------------------------------ 状态与日志
    def _set_status(self, text: str):
        self.status_var = text
        self.statusBar().showMessage(text)

    def append_log(self, line: str):
        self.log_text.appendPlainText(line)

    def clear_log(self):
        """清空日志区（Ctrl+L / 「清屏」按钮）。不影响正在运行的子进程。"""
        self.log_text.clear()
        if self._busy_count:
            self.append_log("--- 日志已清空（任务仍在运行，新输出继续追加）---")

    def save_log(self):
        """把当前日志区内容另存为文件（界面日志本身不落盘，需要时手动存）。"""
        text = self.log_text.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "保存日志", "当前日志区是空的，没有可保存的内容。")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        default = os.path.join(BASE_DIR, f"运行日志_{stamp}.log")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存运行日志", default, "日志文件 (*.log);;文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig") as fh:
                fh.write(text)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法写入：\n{exc}")
            return
        self.append_log(f"--- 日志已保存到: {path} ---")

    @staticmethod
    def _log_dir() -> str:
        """各模块写日志的目录。

        打包后统一在 exe 同级 logs\\<模块名>\\；源码运行时分散在各模块目录的 logs\\ 下，
        此时回退到「最近更新过的那个模块日志目录」。
        """
        candidate = os.path.join(BASE_DIR, "logs")
        if os.path.isdir(candidate):
            return candidate
        best, best_mtime = BASE_DIR, -1.0
        for name in ("比较文件夹内容", "签章页工具", "替换底稿内容", "底稿pdf材料"):
            path = os.path.join(BASE_DIR, name, "logs")
            if not os.path.isdir(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime > best_mtime:
                best, best_mtime = path, mtime
        return best

    def open_log_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_dir()))

    def register_button(self, btn: QPushButton):
        self.run_buttons.append(btn)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in self.run_buttons:
            btn.setEnabled(enabled)

    # ------------------------------------------------------------ 任务调度
    def begin_task(self, label: str):
        if self._busy_count == 0 and self.auto_clear.isChecked():
            self.log_text.clear()  # 勾选「运行前自动清屏」：只留本次任务输出
        self._busy_count += 1
        self.save_settings()
        self._set_buttons_enabled(False)
        self._set_status(f"运行中:{label}")
        self.append_log(f"\n=== {label} ===")

    def end_task(self, label: str, rc: int):
        self._busy_count = max(0, self._busy_count - 1)
        if rc == 0:
            self.append_log(f"--- 完成:{label}（退出码 0）---")
        else:
            self.append_log(f"--- 结束:{label}（退出码 {rc}，详见上方日志与 logs\\ 目录）---")
        if self._busy_count == 0:
            self._set_buttons_enabled(True)
            self._set_status("就绪" if rc == 0 else f"上一步失败（退出码 {rc}）")

    def launch(self, label: str, argv: list[str], cwd: str | None = None) -> bool:
        """启动子进程任务；busy 时提示并返回 False。"""
        if self.runner.busy or self._busy_count:
            QMessageBox.information(self, "正在运行",
                                    "已有任务在运行，请等待完成后再发起新任务。")
            return False
        self.begin_task(label)
        self.append_log("$ " + " ".join(argv[1:])[:400])
        return self.runner.launch(label, argv, cwd=cwd)

    def launch_runner(self, label: str, task: str, params: dict):
        """经 gui_runner.py 中转的任务（sign / replace / dirgen / init）。"""
        spec_json = json.dumps({"task": task, "params": params}, ensure_ascii=False)
        if getattr(sys, "frozen", False):
            argv = [sys.executable, "--gui-runner", spec_json]
        else:
            argv = [sys.executable, RUNNER, spec_json]
        self.launch(label, argv, cwd=BASE_DIR)

    def launch_cli(self, label: str, module_dir: str, script: str,
                   args: list[str]):
        """直接执行某模块目录下的 CLI 脚本。

        打包后脚本随包分发在 RES_DIR（_MEIPASS），exe 同级并没有模块目录。
        若仍把工作目录设成 exe 同级，QProcess 会因目录不存在而启动失败，
        表现为按钮一点就永久卡在「运行中」，所以 cwd 必须跟着脚本走。
        """
        frozen = getattr(sys, "frozen", False)
        if frozen:
            script_path = os.path.join(RES_DIR, module_dir, script)
            cwd = os.path.join(RES_DIR, module_dir)
        else:
            script_path = script
            cwd = os.path.join(BASE_DIR, module_dir)
        if not os.path.isdir(cwd):  # 目录缺失时退回 exe/源码根目录，别让进程起不来
            cwd = BASE_DIR if os.path.isdir(BASE_DIR) else None
        if frozen:
            argv = ([sys.executable, "--run-script", script_path] + list(args))
        else:
            argv = [sys.executable, script_path] + list(args)
        self.launch(label, argv, cwd=cwd)

    # ------------------------------------------------------------ 文件统计
    def run_stats(self, target: str, label: str = "文件信息统计"):
        """用后台线程执行统计（不走子进程）。"""
        from .core import StatsWorker

        if self.runner.busy or self._busy_count:
            QMessageBox.information(self, "正在运行",
                                    "已有任务在运行，请等待完成后再发起新任务。")
            return
        self.begin_task(label)
        self.append_log(f"$ 扫描目录:{target}")
        self._stats_worker = StatsWorker(target, self)
        self._stats_worker.line.connect(self.append_log)
        self._stats_worker.done.connect(lambda rc, l=label: self.end_task(l, rc))
        self._stats_worker.finished.connect(
            lambda: setattr(self, "_stats_worker", None))
        self._stats_worker.start()

    def _on_demo_toggled(self, checked: bool):
        """把「脱敏模式」同步给运行器，后续子进程都会带上 IBDW_DEMO_MODE。"""
        self.runner.demo_mode = bool(checked)
        if checked:
            self._set_status("脱敏模式：产物主体名/项目标识按示例值输出")

    # ------------------------------------------------------------ 设置与关闭
    def save_settings(self):
        self.settings.save(collect_state(self))

    def closeEvent(self, event):
        if (self.runner.busy or self._busy_count) and self._confirm_exit():
            self.runner.terminate()
            if self._stats_worker is not None:
                self._stats_worker.wait(3000)
        elif self.runner.busy:
            event.ignore()
            return
        self.save_settings()
        super().closeEvent(event)

    def _confirm_exit(self) -> bool:
        ret = QMessageBox.question(
            self, "退出",
            "仍有任务在运行，退出将尝试终止它。确定退出？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return ret == QMessageBox.Yes
