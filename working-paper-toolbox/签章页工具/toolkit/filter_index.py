# -*- coding: utf-8 -*-
"""【原 check_sign.py】filter —— 过滤 no_company JSON 中含关键字的条目。

同时提供清单读取与条目解析工具：
  _is_inventory_noise_line / _load_path_list —— 读清单（旧版 latest.log 可能
  夹带统计块，读清单时必须跳过）；
  parse_page_entry —— 把「路径|页码」条目拆成 (路径, 页码)，供 insert
  replace 支持指定页码替换；无页码部分视为替换末页。
"""

import json
import os

from . import config
from .logutil import _log_path, _resolve_input


def cmd_filter(logger):
    """从 no_company JSON 过滤掉含关键字的条目，生成无索引清单（logs/ 目录）。"""
    json_path = _resolve_input(config.FILTER_JSON_PATH)

    if not os.path.exists(json_path):
        logger.error(f"找不到输入文件：{json_path}")
        return 1

    with open(json_path, 'r', encoding='utf-8') as f:
        items = json.load(f)

    logger.info(f"读取 JSON 文件，共 {len(items)} 条。")

    filtered_items = [item for item in items if config.FILTER_KEYWORD not in item]
    removed_count = len(items) - len(filtered_items)

    logger.info(f"包含“{config.FILTER_KEYWORD}”的条目：{removed_count} 条（已移除）")
    logger.info(f"不包含“{config.FILTER_KEYWORD}”的条目：{len(filtered_items)} 条")

    out_path = _log_path("no_company_无索引", ".log")
    with open(out_path, "w", encoding="utf-8") as log:
        for item in filtered_items:
            # 默认替换末页；例外文件由人工把「末页」改成具体页码（如 `xxx.pdf|12`）
            log.write(f"{item}|{LAST_PAGE_MARK}\n")

    logger.info(f"过滤结果已输出至：{out_path}")

    # 固定名副本：供后续 insert --mode replace 直接引用，免去每次改配置
    latest_path = os.path.join(config.LOG_DIR, "no_company_无索引_latest.log")
    with open(out_path, "r", encoding="utf-8") as f_in, open(latest_path, "w", encoding="utf-8") as f_out:
        f_out.write(f_in.read())
    logger.info(f"固定名副本（供 insert --mode replace 使用）：{latest_path}")
    return 0


def _is_inventory_noise_line(line):
    """旧版 latest.log 可能夹带统计块，insert 读清单时必须跳过。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("=") or stripped == "统计信息":
        return True
    if stripped.startswith(("JSON 总条数", "包含", "不包含")):
        return True
    return False


def _load_path_list(list_path):
    """按扩展名读取清单：.json 用 json.load，其余按每行一条读取。"""
    if list_path.lower().endswith(".json"):
        with open(list_path, "r", encoding="utf-8") as f:
            return [item.strip() for item in json.load(f) if str(item).strip()]
    with open(list_path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not _is_inventory_noise_line(line)
        ]


# 清单条目的默认页码标记（替换末页）
LAST_PAGE_MARK = "末页"


def parse_page_entry(entry):
    """把清单条目拆成 (相对路径, 目标页码)，页码为 None 表示替换末页。

    合法格式：`路径`、`路径|末页`、`路径|数字`（数字为 1 起算的替换页码）。
    按最后一个 `|` 分割（Windows 文件名不允许含 `|`，无歧义）。
    页码非法时抛 ValueError，由调用方决定拒绝策略。
    """
    if "|" not in entry:
        return entry, None
    path_part, _, page_part = entry.rpartition("|")
    page_part = page_part.strip()
    if not page_part or page_part == LAST_PAGE_MARK:
        return path_part, None
    try:
        page = int(page_part)
    except ValueError:
        raise ValueError(f"无法识别的页码“{page_part}”")
    if page <= 0:
        raise ValueError(f"页码必须为正整数，实际“{page_part}”")
    return path_part, page
