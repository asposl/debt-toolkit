# -*- coding: utf-8 -*-
"""日志工具（原 file_toolkit.py 公共日志区）。

LOG_DIR 锚定到包的上一级目录（即入口脚本所在目录），
保证日志仍生成在「脚本同级 logs/」。
"""

import datetime
import logging
import os
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
# 打包运行时脚本位于 _MEIPASS 临时目录，日志写那里会随进程退出被删除；
# 冻结入口会设置 IBDW_LOG_ROOT，把日志统一改写到 exe 同级的 logs/ 下。
_log_root = os.environ.get("IBDW_LOG_ROOT")
LOG_DIR = (Path(_log_root) / SCRIPT_DIR.name) if _log_root else SCRIPT_DIR / "logs"


LOG_REDACT = str(os.environ.get("IBDW_LOG_REDACT", "1")).strip().lower() not in {"0", "false", "no", "off"}
_USER_PATH = re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s\"']+")
_USER_PATH_POSIX = re.compile(r"/home/[A-Za-z0-9_.-]+")


def redact_text(text):
    """把本机日志目录替换成 <ROOT>、用户目录替换成 <USER>，日志不留绝对路径。"""
    if not LOG_REDACT:
        return text
    for variant in {str(LOG_DIR), str(LOG_DIR).replace("\\", "/")}:
        if variant:
            text = text.replace(variant, "<ROOT>")
    text = _USER_PATH.sub("<USER>", text)
    text = _USER_PATH_POSIX.sub("<USER>", text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_text(super().format(record))


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def setup_logger(task_name):
    """控制台 + logs/ 文件双写日志器。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{task_name}_{_timestamp()}.txt"
    logger = logging.getLogger(f"file_toolkit.{task_name}.{_timestamp()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = RedactingFormatter("[%(asctime)s] [%(levelname)s] %(message)s",
                                   "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info("本次运行日志文件: %s", log_file.name)
    return logger
