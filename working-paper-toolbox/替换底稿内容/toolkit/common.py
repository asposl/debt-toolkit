# -*- coding: utf-8 -*-
"""日志工具与 Excel 单元格清洗（short / long 共用）。

原 replace_toolkit.py 的 _timestamp/_ensure_log_dir/setup_logger/normalize_cell。
LOG_DIR 经 config 属性读取（晚绑定），测试可覆盖。
"""

import datetime
import logging
import os

from . import config


def _timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def _ensure_log_dir():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    return config.LOG_DIR


def setup_logger(task_name):
    """控制台 + logs/ 文件双写日志器。"""
    _ensure_log_dir()
    log_file = os.path.join(config.LOG_DIR, f"{task_name}_{_timestamp()}.txt")
    logger = logging.getLogger(f"replace_toolkit.{task_name}.{_timestamp()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info(f"本次运行日志文件: {log_file}")
    return logger


def normalize_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text
