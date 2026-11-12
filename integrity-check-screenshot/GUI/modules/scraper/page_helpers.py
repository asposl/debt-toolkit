"""页内通用小工具：主体字段提取、安全命名、截图。"""
import re

from .capture import screenshot_pyautogui


def _subject_name(subject):
    if isinstance(subject, dict):
        return str(subject.get("name") or subject.get("raw") or "").strip()
    return str(subject or "").strip()


def _subject_id(subject):
    if isinstance(subject, dict):
        return str(subject.get("id_card") or "").strip()
    return ""


def _safe_filename(value):
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\r\n\t]+', "_", value)
    value = value.strip(" .")
    return value or "未命名"


def _screenshot(company_folder, filename):
    """物理屏幕截图（与主流程 capture 模块保持一致）。"""
    screenshot_pyautogui(company_folder, filename)
