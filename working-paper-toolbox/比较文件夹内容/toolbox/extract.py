"""【原 提取打印文件.py】extract：平铺提取 Word 文件用于批量打印。"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .common import (
    ADD_ORDER_PREFIX,
    CLEAR_OUTPUT,
    DEFAULT_OUTPUT_FOLDER,
    DEFAULT_SOURCE_FOLDER,
    EXTENSIONS,
    ensure_writable,
    is_temp_office_file,
    make_log_path,
    normalize_relative_path,
    default_project_tag,
    project_label_from,
    safe_unlink,
    strip_project_suffix,
    validate_folder,
    write_log,
)


# ==================== extract：平铺提取 Word 文件用于批量打印 ====================

_CHINESE_NUM_MAP = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
    "十五": 15,
    "十六": 16,
    "十七": 17,
    "十八": 18,
    "十九": 19,
    "二十": 20,
}
_CHINESE_NUM_SORTED = sorted(_CHINESE_NUM_MAP, key=len, reverse=True)
_CHINESE_ORDINAL_PATTERN = re.compile(r"第(" + "|".join(_CHINESE_NUM_SORTED) + r")")


@dataclass(frozen=True)
class WordFile:
    path: Path
    relative_path: str
    name: str


@dataclass
class ExtractResult:
    copied: list[str] = field(default_factory=list)
    skipped_temp: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)
    clear_failed: list[str] = field(default_factory=list)


def natural_sort_key(value: str) -> list[int | str]:
    """让 9-2 排在 9-10 前面，并把「第九章」转成数字参与排序。"""

    def replace_chinese(match: re.Match[str]) -> str:
        number = _CHINESE_NUM_MAP.get(match.group(1))
        if number is None:
            return match.group(0)
        return f"{number:05d}"

    converted = _CHINESE_ORDINAL_PATTERN.sub(replace_chinese, str(value))
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", converted)
    ]


def collect_word_files(root: Path, extensions: set[str]) -> tuple[list[WordFile], list[str]]:
    """按资源管理器习惯收集：每层先按自然序处理文件，再进入子文件夹。"""
    validate_folder(root, "源")

    collected: list[WordFile] = []
    skipped_temp: list[str] = []

    def walk(current: Path) -> None:
        try:
            entries = list(current.iterdir())
        except OSError:
            return

        entries.sort(key=lambda item: natural_sort_key(item.name))
        files = [item for item in entries if item.is_file()]
        dirs = [item for item in entries if item.is_dir()]

        for path in files:
            if path.suffix.lower() not in extensions:
                continue
            relative_path = normalize_relative_path(path.relative_to(root))
            if is_temp_office_file(path):
                skipped_temp.append(relative_path)
                continue
            collected.append(
                WordFile(path=path, relative_path=relative_path, name=path.name)
            )

        for path in dirs:
            walk(path)

    walk(root)
    return collected, skipped_temp


def uniquify_destination(output_dir: Path, filename: str) -> Path:
    destination = output_dir / filename
    if not destination.exists():
        return destination

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while True:
        candidate = output_dir / f"{stem}__{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def clear_output_files(
    output_dir: Path,
    extensions: set[str],
    failed: list[str] | None = None,
) -> list[str]:
    """清空输出文件夹中的旧提取文件。

    只读文件先解除只读再删；仍删不掉（被 PDF 阅读器等占用、或没有权限）时
    记入 failed 并继续，避免单个文件导致整个任务中断。
    """
    if not output_dir.exists():
        return []

    cleared: list[str] = []
    for path in output_dir.iterdir():
        if path.is_file() and path.suffix.lower() in extensions:
            try:
                safe_unlink(path)
            except OSError as exc:
                if failed is not None:
                    failed.append(f"{path.name} | {exc}")
                continue
            cleared.append(path.name)
    return cleared


def extract_word_files(
    source_root: Path,
    output_root: Path,
    extensions: set[str] | None = None,
    add_order_prefix: bool = True,
    clear_output: bool = False,
    project_tag: str = "",
) -> ExtractResult:
    extensions = {item.lower() for item in (extensions or EXTENSIONS)}
    files, skipped_temp = collect_word_files(source_root, extensions)

    output_root.mkdir(parents=True, exist_ok=True)

    result = ExtractResult(skipped_temp=skipped_temp)
    if clear_output:
        result.cleared = clear_output_files(output_root, extensions, result.clear_failed)

    width = max(3, len(str(len(files)))) if files else 3

    for index, item in enumerate(files, start=1):
        filename = strip_project_suffix(item.name, project_tag)
        if add_order_prefix:
            filename = f"{index:0{width}d}_{filename}"

        destination = uniquify_destination(output_root, filename)
        if destination.name != filename:
            result.renamed.append(f"{item.relative_path} -> {destination.name}")

        try:
            shutil.copy2(item.path, destination)
            ensure_writable(destination)  # 源文件可能是只读的，避免下轮清空删不掉
            result.copied.append(f"{item.relative_path} -> {destination.name}")
        except OSError as exc:
            result.failed.append(f"{item.relative_path} -> {destination.name} | {exc}")

    return result


def build_extract_report(
    result: ExtractResult,
    source_root: Path,
    output_root: Path,
    extensions: set[str],
    add_order_prefix: bool,
    clear_output: bool,
) -> str:
    lines = [
        "Word 文件平铺提取结果",
        f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"源文件夹: {source_root}",
        f"输出文件夹: {output_root}",
        f"扩展名: {', '.join(sorted(extensions))}",
        f"序号前缀: {'开启' if add_order_prefix else '关闭'}",
        f"清空输出: {'是' if clear_output else '否'}",
        "",
        "汇总:",
        f"已复制: {len(result.copied)} 个",
        f"因重名改名: {len(result.renamed)} 个",
        f"跳过临时文件: {len(result.skipped_temp)} 个",
        f"清空旧输出: {len(result.cleared)} 个",
        f"清空失败: {len(result.clear_failed)} 个",
        f"复制失败: {len(result.failed)} 个",
    ]

    sections = [
        ("已复制", result.copied),
        ("因重名改名", result.renamed),
        ("跳过的 Word 临时文件", result.skipped_temp),
        ("清空的旧输出", result.cleared),
        ("清空失败（文件被占用或无权限，请关闭后重试）", result.clear_failed),
        ("复制失败", result.failed),
    ]
    for label, items in sections:
        lines.append("")
        lines.append(f"[{label}] {len(items)} 个")
        lines.extend(items)

    return "\n".join(lines) + "\n"


# ==================== 执行入口 ====================


def run_extract(args: argparse.Namespace) -> None:
    if args.test:
        from test_提取打印文件 import run_all_tests

        run_all_tests()
        return

    source_root = Path(args.source_folder) if args.source_folder else DEFAULT_SOURCE_FOLDER
    output_root = Path(args.output_folder) if args.output_folder else DEFAULT_OUTPUT_FOLDER
    log_path = Path(args.log) if args.log else make_log_path("extract", project_label_from(source_root))
    add_order_prefix = False if args.no_prefix else ADD_ORDER_PREFIX
    clear_output = True if args.clear_output else CLEAR_OUTPUT
    project_tag = getattr(args, "project_tag", None) or default_project_tag()

    result = extract_word_files(
        source_root=source_root,
        output_root=output_root,
        extensions=EXTENSIONS,
        add_order_prefix=add_order_prefix,
        clear_output=clear_output,
        project_tag=project_tag,
    )
    report = build_extract_report(
        result=result,
        source_root=source_root,
        output_root=output_root,
        extensions=EXTENSIONS,
        add_order_prefix=add_order_prefix,
        clear_output=clear_output,
    )
    print(report, end="")
    write_log(log_path, report)
    print(f"日志已写入: {log_path}")
