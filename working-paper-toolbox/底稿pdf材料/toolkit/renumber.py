# -*- coding: utf-8 -*-
"""组C：renumber_files —— 已有"N 名称.pdf"的文件夹重新连贯编号。

源自 有息负债-担保重命名.ipynb 单元1 的通用化封装。
注意：本模块的两阶段临时名带时间戳成分（与 numbering.apply_plan_two_phase
语义不同），为保留原行为而独立实现，不做合并。
"""

import os
import re
from pathlib import Path

from .logutil import _timestamp
from .numbering import RENAME_TEMP_SUFFIX, list_top_level_pdfs


def run_renumber(folder: Path, pattern_str: str, start: int, apply: bool, logger):
    if not folder.is_dir():
        logger.error(f"文件夹不存在：{folder}")
        return 1

    pattern = re.compile(pattern_str)
    matched = []
    skipped = []
    for filename in list_top_level_pdfs(folder):
        m = pattern.match(filename)
        if m:
            matched.append({
                "old_num": int(m.group(1)),
                "rest": m.group(2),
                "name": filename,
                "path": folder / filename,
            })
        else:
            skipped.append(filename)

    if not matched:
        logger.warning("没有找到符合条件的文件。")
        return 1

    matched.sort(key=lambda x: x["old_num"])

    if skipped:
        logger.warning(
            f"【提示】有 {len(skipped)} 个 PDF 未匹配编号模式将被跳过、不参与重排：{skipped}"
        )

    # 计划：按原编号顺序重新编为 start..start+n-1
    temp_items = []
    for index, item in enumerate(matched, start=start):
        temp_items.append({
            "dir": folder,
            "name": item["name"],
            "old_num": item["old_num"],
            "new_name": f"{index} {item['rest']}",
            "path": item["path"],
        })

    end_num = start + len(temp_items) - 1
    logger.info(f"共匹配 {len(temp_items)} 个文件，将按原编号顺序重排为 {start}-{end_num}。")
    for item in temp_items:
        mark = "" if item["name"] != item["new_name"] else "（不变）"
        logger.info(f"  {item['old_num']:>4} -> {item['new_name']} {mark}")

    if not apply:
        logger.info("预览模式：未修改任何文件。确认无误后加 --apply 执行。")
        return 0

    # 两阶段临时名重命名（防中间态冲突），临时名带时间戳成分避免与既有文件撞名
    logger.info("第一阶段（重命名为临时文件）...")
    stamp = _timestamp().replace("_", "")
    temp_renames = []
    try:
        for idx, item in enumerate(temp_items, 1):
            temp_path = folder / f"__renumber_{stamp}_{idx}{RENAME_TEMP_SUFFIX}"
            os.rename(item["path"], temp_path)
            temp_renames.append((temp_path, item))
    except OSError as exc:
        logger.error(f"第一阶段失败，正在回滚：{exc}")
        for temp_path, item in reversed(temp_renames):
            try:
                os.rename(temp_path, item["path"])
            except OSError as rollback_exc:
                logger.error(f"  回滚失败: {temp_path.name} -> {item['name']}: {rollback_exc}")
        return 1

    logger.info("第二阶段（应用最终文件名）...")
    finalized = []
    try:
        for temp_path, item in temp_renames:
            final_path = folder / item["new_name"]
            os.rename(temp_path, final_path)
            finalized.append((item, final_path, temp_path))
            logger.info(f"已重命名: {item['name']} -> {item['new_name']}")
    except OSError as exc:
        logger.error(f"第二阶段失败，正在回滚：{exc}")
        for item, final_path, temp_path in reversed(finalized):
            try:
                os.rename(final_path, temp_path)
            except OSError as rollback_exc:
                logger.error(f"  回滚失败: {final_path.name} -> {temp_path.name}: {rollback_exc}")
        for temp_path, item in reversed(temp_renames):
            if temp_path.exists():
                try:
                    os.rename(temp_path, item["path"])
                except OSError as rollback_exc:
                    logger.error(f"  回滚失败: {temp_path.name} -> {item['name']}: {rollback_exc}")
        return 1

    logger.info(f"所有文件重命名完成！共 {len(temp_renames)} 个。")
    return 0
