"""兼容门面：原单文件实现已拆分至各子模块，旧导入路径保持不变。"""
from .batch_runner import run_batch_screenshot_task
from .browser import (
    bring_to_front,
    close_other_tabs,
    get_clean_page,
    tab_url,
    wait_tab_ready,
)
from .capture import screenshot_pyautogui
from .foreground_runner import run_foreground_site
from .subject_utils import (
    ID_PATTERN,
    normalize_subject,
    safe_path_name,
    subject_text,
)
from .url_builder import action_argument, format_target_url
