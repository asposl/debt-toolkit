"""【原 merge_file.py】merge：用 new 中同名 docx 覆盖 old 中的旧版。"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
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


# ==================== merge：用 new 中同名 docx 覆盖 old ====================


@dataclass(frozen=True)
class DocxFile:
    name: str
    path: Path
    relative_path: str


@dataclass
class MergeResult:
    modified: list[str]
    added: list[str]
    unchanged_same: list[str]
    missing_new: list[str]
    duplicate_conflicts: list[str]
    failed: list[str]


def collect_docx_by_name(root: Path) -> dict[str, list[DocxFile]]:
    validate_folder(root, "目标")

    files_by_name: dict[str, list[DocxFile]] = defaultdict(list)
    for path in root.rglob("*.docx"):
        if not path.is_file() or is_temp_office_file(path):
            continue
        files_by_name[path.name].append(
            DocxFile(
                name=path.name,
                path=path,
                relative_path=normalize_relative_path(path.relative_to(root)),
            )
        )
    return dict(files_by_name)


def duplicate_report(name: str, label: str, files: list[DocxFile]) -> str:
    paths = "；".join(file.relative_path for file in sorted(files, key=lambda item: item.relative_path))
    return f"{name} | {label} 中出现 {len(files)} 次: {paths}"


def format_pair(old_file: DocxFile, new_file: DocxFile) -> str:
    return f"{old_file.relative_path} <= {new_file.relative_path}"


def replace_docx_files(old_root: Path, new_root: Path) -> MergeResult:
    validate_folder(old_root, "old")
    validate_folder(new_root, "new")

    old_files = collect_docx_by_name(old_root)
    new_files = collect_docx_by_name(new_root)
    all_names = sorted(set(old_files) | set(new_files))

    result = MergeResult(
        modified=[],
        added=[],
        unchanged_same=[],
        missing_new=[],
        duplicate_conflicts=[],
        failed=[],
    )

    for name in all_names:
        old_matches = old_files.get(name, [])
        new_matches = new_files.get(name, [])

        if len(old_matches) > 1:
            result.duplicate_conflicts.append(duplicate_report(name, "old", old_matches))
            continue
        if len(new_matches) > 1:
            result.duplicate_conflicts.append(duplicate_report(name, "new", new_matches))
            continue

        if old_matches and not new_matches:
            result.missing_new.append(old_matches[0].relative_path)
            continue

        if new_matches and not old_matches:
            new_file = new_matches[0]
            destination = old_root / new_file.relative_path
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(new_file.path, destination)
                result.added.append(f"{normalize_relative_path(destination.relative_to(old_root))} <= {new_file.relative_path}")
            except OSError as exc:
                result.failed.append(
                    f"{new_file.relative_path} -> {normalize_relative_path(destination.relative_to(old_root))} | {exc}"
                )
            continue

        old_file = old_matches[0]
        new_file = new_matches[0]
        try:
            if file_sha256(old_file.path) == file_sha256(new_file.path):
                result.unchanged_same.append(format_pair(old_file, new_file))
                continue

            shutil.copy2(new_file.path, old_file.path)
            result.modified.append(format_pair(old_file, new_file))
        except OSError as exc:
            result.failed.append(f"{format_pair(old_file, new_file)} | {exc}")

    return result


def build_merge_report(result: MergeResult, old_root: Path, new_root: Path) -> str:
    sections = [
        ("被修改的文件", result.modified),
        ("新增到 old 的文件", result.added),
        ("未被修改的文件 - 内容相同", result.unchanged_same),
        ("未被修改的文件 - old 中存在但 new 中未找到同名新版", result.missing_new),
        ("未被修改的文件 - 重名冲突，已跳过", result.duplicate_conflicts),
        ("未被修改的文件 - 复制失败", result.failed),
    ]

    lines = [
        "docx 文件夹替换结果",
        f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"old 文件夹（被更新）: {old_root}",
        f"new 文件夹（最新版来源）: {new_root}",
        "匹配规则: 文件名相同",
        "备份策略: 不备份",
        "",
        "汇总:",
        f"被修改: {len(result.modified)} 个",
        f"新增: {len(result.added)} 个",
        f"未修改-内容相同: {len(result.unchanged_same)} 个",
        f"未修改-未找到新版: {len(result.missing_new)} 个",
        f"未修改-重名冲突: {len(result.duplicate_conflicts)} 个",
        f"未修改-复制失败: {len(result.failed)} 个",
    ]

    for label, items in sections:
        lines.append("")
        lines.append(f"[{label}] {len(items)} 个")
        for item in items:
            lines.append(item)

    return "\n".join(lines) + "\n"


# ==================== 执行入口 ====================


def run_merge(args: argparse.Namespace) -> None:
    old_root = Path(args.old_folder) if args.old_folder else DEFAULT_OLD_FOLDER
    new_root = Path(args.new_folder) if args.new_folder else DEFAULT_NEW_FOLDER
    log_path = Path(args.log) if args.log else make_log_path("merge", project_label_from(new_root))

    result = replace_docx_files(old_root, new_root)
    write_log(log_path, build_merge_report(result, old_root, new_root))

    changed_count = len(result.modified) + len(result.added)
    skipped_count = (
        len(result.unchanged_same)
        + len(result.missing_new)
        + len(result.duplicate_conflicts)
        + len(result.failed)
    )
    print(f"替换完成，修改/新增 {changed_count} 个，未修改 {skipped_count} 个。")
    print(f"日志已写入: {log_path}")
