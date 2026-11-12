"""【原 compare.py】compare：按相对路径与 SHA-256 哈希比较两个文件夹中的 docx。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .common import (
    DEFAULT_NEW_FOLDER,
    DEFAULT_OLD_FOLDER,
    file_sha256,
    is_temp_office_file,
    make_log_path,
    normalize_relative_path,
    project_label_from,
    validate_folder,
    write_log,
)


# ==================== compare：哈希比较两个文件夹 ====================


def collect_docx_hashes(root: Path) -> dict[str, str]:
    validate_folder(root, "目标")

    hashes: dict[str, str] = {}
    for path in root.rglob("*.docx"):
        if not path.is_file() or is_temp_office_file(path):
            continue
        relative_path = normalize_relative_path(path.relative_to(root))
        hashes[relative_path] = file_sha256(path)
    return hashes


def _paths_by_name(paths: set[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for relative in paths:
        grouped[Path(relative).name].append(relative)
    return {name: sorted(items) for name, items in grouped.items()}


def _same_name_different_path_entries(old_paths: set[str], new_paths: set[str]) -> list[str]:
    """同名但相对路径不同，或同一侧出现多次。不重复计入仅一侧存在的单路径文件。"""
    old_by_name = _paths_by_name(old_paths)
    new_by_name = _paths_by_name(new_paths)
    entries = []
    for name in sorted(set(old_by_name) | set(new_by_name)):
        old_list = old_by_name.get(name, [])
        new_list = new_by_name.get(name, [])
        old_dup = len(old_list) > 1
        new_dup = len(new_list) > 1
        relocated = bool(old_list) and bool(new_list) and set(old_list) != set(new_list)
        if not (old_dup or new_dup or relocated):
            continue
        parts = [name]
        if old_list:
            parts.append(f"old: {'；'.join(old_list)}")
        if new_list:
            parts.append(f"new: {'；'.join(new_list)}")
        entries.append(" | ".join(parts))
    return entries


def compare_docx_folders(old_root: Path, new_root: Path) -> dict[str, list[str]]:
    old_hashes = collect_docx_hashes(old_root)
    new_hashes = collect_docx_hashes(new_root)

    old_paths = set(old_hashes)
    new_paths = set(new_hashes)
    common_paths = old_paths & new_paths

    return {
        "added_in_new": sorted(new_paths - old_paths),
        "removed_from_new": sorted(old_paths - new_paths),
        "changed_content": sorted(
            path for path in common_paths if old_hashes[path] != new_hashes[path]
        ),
        "same_name_different_path": _same_name_different_path_entries(old_paths, new_paths),
    }


def build_compare_report(result: dict[str, list[str]], old_root: Path, new_root: Path) -> str:
    labels = {
        "added_in_new": "new 中新增的 docx",
        "removed_from_new": "new 中缺少的 docx",
        "changed_content": "路径相同但内容不同的 docx",
        "same_name_different_path": "同名但相对路径不同（或一侧重名）",
    }

    lines = [
        "docx 文件夹哈希比较结果",
        f"old 文件夹: {old_root}",
        f"new 文件夹: {new_root}",
        "",
    ]
    diff_total = (
        len(result.get("added_in_new", []))
        + len(result.get("removed_from_new", []))
        + len(result.get("changed_content", []))
    )
    total = diff_total
    lines.append(f"共发现 {total} 个不同的 docx 文件。")

    for key, label in labels.items():
        paths = result[key]
        lines.append("")
        lines.append(f"[{label}] {len(paths)} 个")
        for path in paths:
            lines.append(path)

    return "\n".join(lines) + "\n"


# ==================== 执行入口 ====================


def run_compare(args: argparse.Namespace) -> None:
    old_root = Path(args.old_folder) if args.old_folder else DEFAULT_OLD_FOLDER
    new_root = Path(args.new_folder) if args.new_folder else DEFAULT_NEW_FOLDER
    log_path = Path(args.log) if args.log else make_log_path("compare", project_label_from(new_root))

    result = compare_docx_folders(old_root, new_root)

    report = (
        json.dumps(result, ensure_ascii=False, indent=2)
        if args.json
        else build_compare_report(result, old_root, new_root)
    )
    write_log(log_path, report)
    print(f"比较完成，结果已写入: {log_path}")
