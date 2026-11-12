"""物理屏幕截图。"""
import os
import time

import pyautogui

from .subject_utils import safe_path_name


def screenshot_pyautogui(company_folder, filename, retries=3, interval=0.8):
    save_path = os.path.join(company_folder, f"{safe_path_name(filename)}.png")
    # 纯物理屏幕截图（带任务栏）。
    # ImageGrab 偶发 OSError('screen grab failed')（屏幕句柄瞬时被占用等），
    # 一次失败就丢一张图太可惜，重试几次再放弃。
    last_err = None
    for _ in range(retries):
        try:
            pyautogui.screenshot(save_path)
            return
        except OSError as err:
            last_err = err
            time.sleep(interval)
    raise last_err
