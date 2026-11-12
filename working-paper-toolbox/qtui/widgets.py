# -*- coding: utf-8 -*-
"""qtui.widgets —— 控件辅助：命名控件构建、整树状态收集/恢复（设置记忆）。

所有需要记忆的控件都通过 objectName 绑定 key；collect/apply 遍历窗口内
全部 QLineEdit / QPlainTextEdit / QCheckBox / QComboBox / QSpinBox。
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QSpinBox, QWidget)

from .core import BASE_DIR


# 不参与设置记忆的控件：日志区属于运行时输出，若写进 json 会越存越大，
# 且下次启动又被恢复出来（表现为「一打开就看到以前的全部日志」）。
_EXCLUDE_STATE_KEYS = {"LogView"}


def collect_state(root: QWidget) -> dict:
    """收集窗口内全部命名控件的值（供 Settings.save）。"""
    data: dict = {}
    for w in root.findChildren(QLineEdit):
        if w.objectName():
            data[w.objectName()] = w.text()
    for w in root.findChildren(QPlainTextEdit):
        if w.objectName() and w.objectName() not in _EXCLUDE_STATE_KEYS:
            data[w.objectName()] = w.toPlainText()
    for w in root.findChildren(QCheckBox):
        if w.objectName():
            data[w.objectName()] = w.isChecked()
    for w in root.findChildren(QComboBox):
        if w.objectName():
            data[w.objectName()] = w.currentIndex()
    for w in root.findChildren(QSpinBox):
        if w.objectName():
            data[w.objectName()] = w.value()
    return data


def apply_state(root: QWidget, data: dict, only_combos: bool = False) -> None:
    """把保存的值恢复到窗口内同名控件。

    only_combos=True 时只恢复 QComboBox（用于两阶段恢复：先确定
    filetoolkit 动态表单的子命令选择，再恢复各字段值）。
    """
    if not data:
        return
    if only_combos:
        for w in root.findChildren(QComboBox):
            if w.objectName() in data:
                val = data[w.objectName()]
                try:
                    idx = int(val)
                except (TypeError, ValueError):
                    idx = w.findText(str(val))  # 兼容 Tk 版存的文本值
                if 0 <= idx < w.count():
                    w.setCurrentIndex(idx)
        return
    for w in root.findChildren(QLineEdit):
        if w.objectName() in data:
            try:
                w.setText(str(data[w.objectName()]))
            except TypeError:
                pass
    for w in root.findChildren(QPlainTextEdit):
        if w.objectName() in data and w.objectName() not in _EXCLUDE_STATE_KEYS:
            w.setPlainText(str(data[w.objectName()]))
    for w in root.findChildren(QCheckBox):
        if w.objectName() in data:
            try:
                w.setChecked(bool(data[w.objectName()]))
            except (TypeError, ValueError):
                pass
    for w in root.findChildren(QSpinBox):
        if w.objectName() in data:
            try:
                w.setValue(int(data[w.objectName()]))
            except (TypeError, ValueError):
                pass


def add_path_row(grid: QGridLayout, row: int, label: str, key: str,
                 default: str = "", is_file: bool = False,
                 page: QWidget | None = None) -> int:
    """路径选择行：标签 + 输入框 + 浏览按钮。返回下一行号。"""
    grid.addWidget(QLabel(label), row, 0)
    edit = QLineEdit(default)
    edit.setObjectName(key)
    grid.addWidget(edit, row, 1)

    def browse():
        cur = edit.text().strip()
        if is_file:
            initdir = os.path.dirname(cur) if cur else BASE_DIR
            chosen, _ = QFileDialog.getOpenFileName(page, "选择文件", initdir)
        else:
            chosen = QFileDialog.getExistingDirectory(page, "选择文件夹",
                                                      cur or BASE_DIR)
        if chosen:
            edit.setText(os.path.normpath(chosen))

    btn = QPushButton("浏览…")
    btn.setFixedWidth(72)
    btn.clicked.connect(browse)
    grid.addWidget(btn, row, 2)
    grid.setColumnStretch(1, 1)
    return row + 1


def add_text_row(grid: QGridLayout, row: int, label: str, key: str,
                 default: str = "", width: int = 0) -> int:
    """单行文本行。返回下一行号。"""
    grid.addWidget(QLabel(label), row, 0)
    edit = QLineEdit(default)
    edit.setObjectName(key)
    if width:
        edit.setFixedWidth(width)
        grid.addWidget(edit, row, 1)
    else:
        grid.addWidget(edit, row, 1, 1, 2)
    grid.setColumnStretch(1, 1)
    return row + 1


def add_note(grid: QGridLayout, row: int, text: str) -> int:
    """灰色说明文字行。返回下一行号。"""
    note = QLabel(text)
    note.setStyleSheet("color:#666;")
    note.setWordWrap(True)
    grid.addWidget(note, row, 0, 1, 3)
    return row + 1
