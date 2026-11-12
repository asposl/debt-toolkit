# -*- coding: utf-8 -*-
"""组A：dedup_folders —— 编号子文件夹哈希去重并复制（organize_toolkit 血缘）。"""

import hashlib
import os
import re
import shutil
from pathlib import Path

from .imaging import convert_images_in_tree


def parse_folder_number(folder_name: str) -> float:
    """
    '5' -> 5.0；'99-100' -> 99.5；'114（查不到此笔放款）' -> 114.0；无数字 -> inf
    """
    match = re.match(r"^(\d+)(?:-(\d+))?", folder_name)
    if not match:
        return float("inf")
    start = int(match.group(1))
    return start + 0.5 if match.group(2) else float(start)


def calculate_folder_fingerprint(folder_path: Path):
    """指纹 = (文件数, 排序后的 (相对路径, MD5) 元组)；层级和内容都一致才判重。"""
    files_hashes = []
    file_count = 0
    for root, _, files in os.walk(folder_path):
        for file in sorted(files):
            file_path = os.path.join(root, file)
            file_count += 1
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            rel_path = os.path.relpath(file_path, folder_path)
            files_hashes.append((rel_path, hasher.hexdigest()))
    return file_count, tuple(sorted(files_hashes))


def collect_dedup_items(source_path: Path, layout: str):
    """nested=母/子两层；single=一层。返回按编号升序的条目列表。"""
    items = []
    if layout == "nested":
        candidates = (
            sub_dir
            for mother_dir in source_path.iterdir() if mother_dir.is_dir()
            for sub_dir in mother_dir.iterdir() if sub_dir.is_dir()
        )
    else:
        candidates = (entry for entry in source_path.iterdir() if entry.is_dir())

    for sub_dir in candidates:
        if re.match(r"^\d+(-\d+)?", sub_dir.name):
            items.append({
                "path": sub_dir,
                "name": sub_dir.name,
                "sort_key": parse_folder_number(sub_dir.name),
                "mother_name": sub_dir.parent.name,
            })
    items.sort(key=lambda x: x["sort_key"])
    return items


def run_dedup(source_dir: Path, output_dir: Path, layout: str,
              convert_first: bool, logger):
    if not source_dir.exists():
        logger.error(f"源目录不存在：{source_dir}")
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)

    items = collect_dedup_items(source_dir, layout)
    if not items:
        logger.warning("未找到任何符合编号规则的子文件夹，程序结束。")
        return 1

    logger.info(f"共扫描到 {len(items)} 个符合编号规则的子文件夹，已完成编号升序排序。")

    logger.info("步骤 1/3: 正在复制子文件夹到输出目录...")
    working_dirs = []
    for item in items:
        target_folder = output_dir / item["name"]
        if target_folder.exists():
            logger.warning(f"[命名冲突] 子文件夹 [{item['name']}] 重名，采用后缀区分。")
            target_folder = output_dir / f"{item['name']}_from_{item['mother_name']}"
        shutil.rmtree(target_folder, ignore_errors=True)
        shutil.copytree(item["path"], target_folder)
        working_dirs.append({"path": target_folder, "name": item["name"]})

    if convert_first:
        logger.info("步骤 2/3: 先将各副本中的图片统一转为 PDF...")
        for entry in working_dirs:
            convert_images_in_tree(entry["path"], logger)
    else:
        logger.info("步骤 2/3: 跳过图片转换（--no-image-convert）。")

    logger.info("步骤 3/3: 开始比对全部内容并进行去重...")
    seen_fingerprints = {}
    folders_to_delete = []
    for entry in working_dirs:
        fingerprint = calculate_folder_fingerprint(entry["path"])
        if fingerprint in seen_fingerprints:
            logger.info(
                f"[发现重复] 文件夹 [{entry['name']}] 与 "
                f"[{seen_fingerprints[fingerprint]}] 内容完全相同。标记移除。"
            )
            folders_to_delete.append(entry["path"])
        else:
            seen_fingerprints[fingerprint] = entry["name"]

    removed = 0
    for folder in folders_to_delete:
        shutil.rmtree(folder, ignore_errors=True)
        removed += 1
        logger.info(f"[执行删除] 成功移除重复文件夹: [{folder.name}]，仅保留编号更小的版本。")

    logger.info("==================== 去重任务完成 ====================")
    logger.info(
        f"原始 {len(items)} 个，保留 {len(items) - removed} 个，移除重复 {removed} 个。"
        f"输出位置：{output_dir}"
    )
    return 0


def cmd_dedup_folders(args, logger):
    return run_dedup(
        Path(args.source), Path(args.output), args.layout,
        not args.no_image_convert, logger,
    )
