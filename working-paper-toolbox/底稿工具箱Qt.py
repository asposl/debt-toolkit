# -*- coding: utf-8 -*-
"""底稿工具箱Qt.py —— 债承底稿处理工具箱（PySide6 图形界面入口）。

与 Tk 版（底稿工具箱GUI.py）功能一一对应：
    左侧侧边栏功能选项 + 右侧页面堆叠 + 底部共享日志区；
    任务仍经 gui_runner.py 子进程执行，配置协议完全一致。
    Qt6 默认启用高 DPI 感知，150% 缩放笔记本无需额外处理。

运行方式：
    python 底稿工具箱Qt.py
"""

import importlib.util
import os
import runpy
import sys

from PySide6.QtWidgets import QApplication

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = BASE_DIR
RUNNER = os.path.join(RES_DIR, "gui_runner.py")


def _run_frozen_dispatch():
    """打包(exe)模式下的子进程入口（与 Tk 版同机制）。

    windowed 打包下未捕获异常会触发模态错误对话框导致子进程永不退出，
    因此必须兜底捕获所有异常并返回非零码。
    """
    try:
        # 打包后脚本位于 _MEIPASS 临时目录，日志写那里会随进程退出被删除。
        # 统一重定向到 exe 同级的 logs/ 下（各模块自带子目录，见 toolkit/config.py）。
        os.environ.setdefault("IBDW_LOG_ROOT", os.path.join(BASE_DIR, "logs"))
        if "--gui-runner" in sys.argv:
            spec_json = sys.argv[sys.argv.index("--gui-runner") + 1]
            spec = importlib.util.spec_from_file_location("gui_runner", RUNNER)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.argv = [RUNNER, spec_json]
            return mod.main() or 0
        if "--run-script" in sys.argv:
            i = sys.argv.index("--run-script")
            script = os.path.abspath(sys.argv[i + 1])
            args = sys.argv[i + 2:]
            sys.argv = [script] + list(args)
            sys.path.insert(0, os.path.dirname(script))
            runpy.run_path(script, run_name="__main__")
            return 0
        return 2
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    except BaseException:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        sys.stdout.flush()
        return 1


def main():
    if getattr(sys, "frozen", False) and (
            "--gui-runner" in sys.argv or "--run-script" in sys.argv):
        sys.exit(_run_frozen_dispatch())
    app = QApplication(sys.argv)
    app.setApplicationName("债承底稿处理工具箱")
    app.setOrganizationName("IBDW")

    from qtui.main_window import MainWindow

    win = MainWindow()
    # 窗口尺寸随屏幕分辨率自适应
    screen = app.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        w = min(1280, max(1000, int(geo.width() * 0.82)))
        h = max(640, int(geo.height() * 0.88))
        win.resize(w, h)
        win.move(max(0, geo.x() + (geo.width() - w) // 2),
                 max(0, geo.y() + (geo.height() - h) // 3))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
