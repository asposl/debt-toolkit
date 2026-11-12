# -*- coding: utf-8 -*-
"""qtui.core —— 设置持久化、子进程运行器（QProcess）、文件统计扫描与后台线程。

与 Tk 版的对应关系：
    SETTINGS_PATH / BASE_DIR / RES_DIR / RUNNER   —— 原底稿工具箱GUI.py 顶部常量
    Runner(QProcess)                              —— 原 _launch/_worker/_finish
    scan_tree / StatsWorker                       —— 原 _run_stats 内核与后台线程
"""
from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, Signal

# ---- 目录锚定：与 Tk 版一致（打包后 BASE_DIR=exe 所在目录）----
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR
RUNNER = os.path.join(RES_DIR, "gui_runner.py")
SETTINGS_PATH = os.path.join(BASE_DIR, ".zcode", "gui_settings.json")


class Settings:
    """JSON 设置持久化，沿用 .zcode/gui_settings.json 格式（与 Tk 版互通）。"""

    def __init__(self, path: str = SETTINGS_PATH):
        self.path = path
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            self.data = {}

    def save(self, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass


class Runner(QObject):
    """单实例子进程运行器：stdout 流式发 line_received，结束发 finished(label, code)。"""

    line_received = Signal(str)
    finished = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc: QProcess | None = None
        self.label = ""
        self.busy = False
        # 脱敏模式：置 True 时给子进程注入 IBDW_DEMO_MODE=1，
        # 脚本据此把主体名/落款换成示例值、按 demo 规则命名产物。
        self.demo_mode = False

    def launch(self, label: str, argv: list[str], cwd: str | None = None) -> bool:
        """启动子进程。busy 时返回 False（由调用方提示）。"""
        if self.busy:
            return False
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        if self.demo_mode:
            env.insert("IBDW_DEMO_MODE", "1")
        else:
            env.remove("IBDW_DEMO_MODE")
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.setProcessEnvironment(env)
        if cwd:
            proc.setWorkingDirectory(cwd)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._drain(p))
        proc.errorOccurred.connect(
            lambda err, l=label, p=proc: self._error(l, err, p))
        proc.finished.connect(
            lambda code, _st, l=label, p=proc: self._done(l, int(code), p))
        self._proc = proc
        self.label = label
        self.busy = True
        proc.start(argv[0], argv[1:])
        return True

    def terminate(self) -> None:
        if self._proc is not None and self._proc.state() != QProcess.NotRunning:
            self._proc.terminate()
            if not self._proc.waitForFinished(3000):
                self._proc.kill()
                self._proc.waitForFinished(3000)

    # ---- 内部 ----
    def _error(self, label: str, error, proc: QProcess) -> None:
        """启动失败/崩溃兜底。

        QProcess 启动失败（典型：工作目录不存在）时不会发 finished，
        若不做处理界面会永远停在「运行中」，所有按钮变灰。
        """
        if self._proc is not proc or not self.busy:
            return
        if error == QProcess.FailedToStart:
            reason = "子进程启动失败"
        else:
            reason = "子进程异常"
        self.line_received.emit(f"[错误] {reason}: {proc.errorString()}")
        self._proc = None
        self.busy = False
        self.finished.emit(label, 1)

    def _drain(self, proc: QProcess) -> None:
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        for ln in text.splitlines():
            self.line_received.emit(ln.rstrip())

    def _done(self, label: str, code: int, proc: QProcess) -> None:
        if self._proc is not proc:  # 已由 _error 收尾，避免重复结束任务
            return
        self._drain(proc)  # 收尾再读一次，避免丢尾部日志
        self._proc = None
        self.busy = False
        self.finished.emit(label, code)


# ==================== 文件信息统计 ====================

def scan_tree(target: str) -> tuple[list[str], int]:
    """递归统计 Word/PDF/其他格式文件。返回 (日志行列表, 退出码)。"""
    word = pdf = total = 0
    other_ext: dict[str, int] = {}
    for _dirpath, _dirnames, filenames in os.walk(target):
        for name in filenames:
            total += 1
            ext = os.path.splitext(name)[1].lower()
            if ext in (".doc", ".docx"):
                word += 1
            elif ext == ".pdf":
                pdf += 1
            else:
                key = ext if ext else "（无扩展名）"
                other_ext[key] = other_ext.get(key, 0) + 1
    other = total - word - pdf
    lines = [
        f"扫描完成：共 {total} 个文件",
        f"Word 文件（.doc/.docx）：{word} 个",
        f"PDF 文件（.pdf）：{pdf} 个",
        f"其他格式文件合计：{other} 个",
    ]
    if other_ext:
        lines.append("其他格式明细（按数量降序，最多 20 种）：")
        ranked = sorted(other_ext.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        lines.extend(f"    {ext}: {cnt} 个" for ext, cnt in ranked)
        if len(other_ext) > 20:
            lines.append(f"    …另有 {len(other_ext) - 20} 种扩展名未列出")
    return lines, 0


class StatsWorker(QThread):
    """文件统计后台线程：逐行发 line，结束发 done(退出码)。"""

    line = Signal(str)
    done = Signal(int)

    def __init__(self, target: str, parent=None):
        super().__init__(parent)
        self.target = target

    def run(self) -> None:
        rc = 0
        try:
            lines, rc = scan_tree(self.target)
            for ln in lines:
                self.line.emit(ln)
        except Exception as exc:  # noqa: BLE001
            self.line.emit(f"[异常] {exc}")
            rc = 1
        finally:
            self.done.emit(rc)
