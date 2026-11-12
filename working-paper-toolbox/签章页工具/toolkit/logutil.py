# -*- coding: utf-8 -*-
"""日志工具（原 pdf_toolkit.py 公共日志区）。

LOG_DIR / PROJECT_TAG / LOG_REDACT 经 config 属性读取（晚绑定），测试可覆盖。

两条脱敏约定：
- 日志文件名不带项目标识，只留 task_时间戳，避免 `collect_项目代号_20260823.txt` 这种泄密名。
- 写入前把项目根目录替换成 <ROOT>、本机用户目录替换成 <USER>，日志里不留绝对路径。
"""

import datetime
import logging
import os
import re

from . import config

ROOT_TOKEN = "<ROOT>"
USER_TOKEN = "<USER>"

_USER_PATH = re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s\"'）)]+")
_USER_PATH_POSIX = re.compile(r"/home/[A-Za-z0-9_.-]+")


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def _ensure_log_dir():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    return config.LOG_DIR


def _resolve_input(path):
    """相对路径先按当前目录解析，找不到再尝试 logs/ 目录。"""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(config.LOG_DIR, path)
    if os.path.exists(candidate):
        return candidate
    return path


def _log_path(task_name, ext=".txt"):
    _ensure_log_dir()
    return os.path.join(config.LOG_DIR, f"{task_name}_{_timestamp()}{ext}")


def redact_text(text):
    """把项目根与本机用户名从日志文本里抹掉。"""
    if not getattr(config, "LOG_REDACT", True):
        return text
    root = str(getattr(config, "PROJECT_ROOT", "") or "")
    if root:
        for variant in {root, root.replace("\\", "\\\\"), root.replace("\\", "/")}:
            if variant:
                text = text.replace(variant, ROOT_TOKEN)
    text = _USER_PATH.sub(USER_TOKEN, text)
    text = _USER_PATH_POSIX.sub(USER_TOKEN, text)
    return text


class RedactingFormatter(logging.Formatter):
    """输出前统一脱敏（文件与控制台同款）。"""

    def format(self, record):
        return redact_text(super().format(record))


def setup_logger(task_name):
    """控制台 + logs/ 文件双写日志器。"""
    log_file = _log_path(task_name)
    logger = logging.getLogger(f"pdf_toolkit.{task_name}.{_timestamp()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s"))
    sh = logging.StreamHandler()
    sh.setFormatter(RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info("本次运行日志文件: %s", os.path.basename(log_file))
    return logger
