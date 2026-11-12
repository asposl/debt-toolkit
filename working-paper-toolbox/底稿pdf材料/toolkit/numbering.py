# -*- coding: utf-8 -*-
"""编号内核（原 file_toolkit.py「公共：编号内核」区，逐行保真）。

收集 -> 排序 -> 赋前缀编号 -> 冲突检查 -> 两阶段临时名重命名 -> 连贯性核验。
被 working_paper.py（组B）与 renumber.py（组C）共享。

注意：两阶段重命名另有 renumber 时间戳变体；flatten 已并入本函数（move=True）。
"""

import os
import re
from pathlib import Path


def leading_num(name):
    """返回名称开头的数字（int）；无前缀数字返回 None。"""
    m = re.match(r"^(\d+)", name)
    return int(m.group(1)) if m else None


def natural_sort_key(name):
    """自然排序：带数字前缀的按数字升序在前，无前缀的按名称排在后面。"""
    n = leading_num(name)
    return (n is None, n if n is not None else 0, name)


def clean_pdf_name(name):
    """删除文件名开头数字及紧随的空格/横线；扩展名统一小写 .pdf。"""
    base = os.path.splitext(name)[0]
    return re.sub(r"^\d+[\s\-]*", "", base) + ".pdf"


def list_top_level_pdfs(folder: Path):
    """仅顶级目录下的 PDF 文件名列表（自然排序，保证 2 在 10 前）。"""
    names = [f.name for f in folder.iterdir()
             if f.is_file() and f.name.lower().endswith(".pdf")]
    names.sort(key=natural_sort_key)
    return names


def collect_tree_pdfs(folder: Path):
    """递归收集 PDF，子目录与文件均按自然排序（2 在 10 前）。"""
    result = []
    for root, dirs, files in os.walk(folder):
        dirs.sort(key=natural_sort_key)
        files.sort(key=natural_sort_key)
        for f in files:
            if f.lower().endswith(".pdf"):
                result.append((Path(root), f))
    return result


def collect_pdf_items(locations, flatten_flags=None, sort_mode="natural"):
    """
    编号内核第一步：从多个位置收集 PDF。

    locations      : [Path, ...]，处理顺序即给定顺序
    flatten_flags  : {位置索引: bool}；True=该位置递归收集子目录中的 PDF 并标记移动，
                     False/缺省=仅取该位置顶级文件
    sort_mode      : natural=自然排序；tree/given=按目录树（即给定）顺序
    返回 [{dir, name, path, move}, ...]，move 表示该文件需要移到其所在位置的顶级。
    """
    flatten_flags = flatten_flags or {}
    items = []
    for idx, loc in enumerate(locations):
        do_flatten = bool(flatten_flags.get(idx))
        if do_flatten:
            found = collect_tree_pdfs(loc)
        else:
            found = [(loc, f) for f in list_top_level_pdfs(loc)]
        for src_dir, name in found:
            items.append({
                "dir": src_dir,
                "name": name,
                "path": src_dir / name,
                "top": loc,
                "move": do_flatten and src_dir != loc,
            })

    if sort_mode == "natural":
        items.sort(key=lambda x: natural_sort_key(x["name"]))
    # tree/given：位置顺序保持给定，每个位置内部已是自然排序
    return items


def assign_numbers(items, prefix, start=1, clean=True):
    """编号内核第二步：为收集结果生成 `prefix-N 名称.pdf` 新名计划。"""
    plan = []
    for i, item in enumerate(items, start=start):
        base = clean_pdf_name(item["name"]) if clean else item["name"]
        plan.append({
            **item,
            "new_name": f"{prefix}{i} {base}",
            "num": i,
        })
    return plan


def check_new_name_conflicts(plan):
    """冲突检查：新文件名在计划内重复，返回错误信息列表。"""
    seen = {}
    errors = []
    for item in plan:
        key = (str(item.get("target_dir") or item["dir"]), item["new_name"])
        if key in seen:
            errors.append(f"新文件名重复 → {item['new_name']}（于 {key[0]}）")
        seen[key] = True
    return errors


def remove_empty_subfolders(top: Path, logger):
    """自底向上删除 top 下所有空子文件夹，返回删除数量。"""
    removed = 0
    for root, dirs, files in os.walk(top, topdown=False):
        if str(root) == str(top):
            continue
        try:
            os.rmdir(root)
            logger.info(f"  已删除空文件夹: {os.path.relpath(root, top)}")
            removed += 1
        except OSError:
            logger.info(f"  跳过（非空）: {os.path.relpath(root, top)}")
    return removed


RENAME_TEMP_SUFFIX = ".temp_rename_holder"


def _rollback_temp_to_original(temp_items, logger) -> None:
    """把仍是临时名的文件改回原名。"""
    for item in reversed(temp_items):
        temp_path = item.get("temp_path")
        if temp_path is None:
            continue
        try:
            if Path(temp_path).exists():
                os.rename(temp_path, item["path"])
                logger.info(f"  已回滚: {Path(temp_path).name} -> {item['name']}")
        except OSError as rollback_exc:
            logger.error(f"  回滚失败: {temp_path} -> {item['name']}: {rollback_exc}")


def apply_plan_two_phase(plan, logger) -> bool:
    """
    两阶段原地重命名（防中间态冲突）：
    第一阶段全部改为临时名，第二阶段恢复为最终名。
    plan 项需含 dir/name/new_name；move=True 时第二阶段直接移动到 top。
    任一阶段失败会尽量回滚到原名，并返回 False。
    """
    logger.info("第一阶段（重命名为临时文件）...")
    temp_items = []
    try:
        for item in plan:
            old_path = item["path"]
            temp_path = item["dir"] / f"{item['new_name']}{RENAME_TEMP_SUFFIX}"
            os.rename(old_path, temp_path)
            temp_items.append({**item, "temp_path": temp_path})
    except OSError as exc:
        logger.error(f"第一阶段失败，正在回滚：{exc}")
        _rollback_temp_to_original(temp_items, logger)
        return False

    logger.info("第二阶段（应用最终文件名）...")
    finalized: list[tuple[dict, Path]] = []
    try:
        for item in temp_items:
            if item.get("move"):
                final_path = item["top"] / item["new_name"]
            else:
                final_path = item["dir"] / item["new_name"]
            os.rename(item["temp_path"], final_path)
            finalized.append((item, final_path))
            tag = "移动+" if item.get("move") and item["dir"] != final_path.parent else ""
            logger.info(f"已{tag}重命名: {item['name']} -> {final_path.name}")
    except OSError as exc:
        logger.error(f"第二阶段失败，正在回滚：{exc}")
        for item, final_path in reversed(finalized):
            try:
                os.rename(final_path, item["temp_path"])
            except OSError as rollback_exc:
                logger.error(
                    f"  回滚失败: {final_path.name} -> {item['temp_path'].name}: {rollback_exc}"
                )
        _rollback_temp_to_original(temp_items, logger)
        return False
    return True


def verify_numbering(folder: Path, prefix: str, logger):
    """核验某目录下以 prefix 开头的编号是否从 1 连贯。"""
    nums = []
    total = 0
    for f in list_top_level_pdfs(folder):
        m = re.match(rf"^{re.escape(prefix)}(\d+) ", f)
        if m:
            nums.append(int(m.group(1)))
        if f.lower().endswith(".pdf"):
            total += 1
    nums.sort()
    ok = nums == list(range(1, len(nums) + 1))
    logger.info(
        f"{folder.name}: 共 {total} 个 PDF，编号 "
        f"{('1-' + str(len(nums))) if nums else '无'}，连贯 {ok}"
    )
    return ok
