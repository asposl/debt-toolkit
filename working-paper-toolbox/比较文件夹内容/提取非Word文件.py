"""提取非 Word 文件：把多级文件夹中修改时间早于截止时间的非 doc / docx 文件平铺复制出来并编号。

仿照 toolbox/extract.py（原 提取打印文件.py）的结构编写。

用法:
    python 提取非Word文件.py [source_folder] [output_folder] [--before "2026-08-01 12:00"]
                             [--skip 名称1,名称2 ...] [--no-prefix] [--clear-output]
                             [--dry-run] [--log 日志路径]

不传路径时使用顶部默认常量；截止时间不传时使用 CUTOFF_TIME 常量；
跳过文件夹不传时使用 SKIP_FOLDER_NAMES 常量（命中文件夹及其所有子文件夹整体跳过）。
--dry-run 模拟运行：只扫描并把「将要复制」的文件清单写入 log，不创建/清空输出文件夹、不复制任何文件。
所有日志统一输出到脚本同级的 logs/ 文件夹，命名格式:
    非Word_{项目名}_{YYYYMMDD_HHMM}.log
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent

# ---- 复用工具箱的公共函数（日志、校验、临时文件识别等）----
from toolbox.common import (  # noqa: E402
    ensure_writable,
    is_temp_office_file,
    make_log_path,
    normalize_relative_path,
    default_project_tag,
    project_label_from,
    strip_project_suffix,
    safe_unlink,
    validate_folder,
    write_log,
)
from toolbox.extract import natural_sort_key, uniquify_destination  # noqa: E402


# ==================== 默认参数（在 VSCode 中改这里后直接运行） ====================

DEFAULT_SOURCE_FOLDER = SCRIPT_DIR                      # 多级源文件夹
DEFAULT_OUTPUT_FOLDER = SCRIPT_DIR / "非Word文件"        # 平铺输出文件夹

CUTOFF_TIME = "2026-08-24 00:00"   # 只提取修改时间早于该时刻的文件，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM

EXCLUDED_EXTENSIONS = {".doc", ".docx"}   # 要排除（不提取）的扩展名
SKIP_FOLDER_NAMES: set[str] = set()       # 跳过的文件夹名（含其所有子文件夹），支持通配符，如 {"附件", "历史底稿*"}
ADD_ORDER_PREFIX = True                   # True：按原目录顺序加 001_ 前缀；False：重名时自动加 __2
CLEAR_OUTPUT = False                      # True：运行前清空输出文件夹中的非 Word 文件
DRY_RUN = False                           # True：模拟运行，只把将复制的文件清单写入 log，不动任何文件

# ==============================================================================


def parse_cutoff(value: str) -> datetime:
    """解析截止时间，支持 YYYY-MM-DD、YYYY-MM-DD HH:MM、YYYY-MM-DD HH:MM:SS。"""
    value = value.strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法识别的时间格式: {value}（支持 YYYY-MM-DD [HH:MM[:SS]]）")


@dataclass(frozen=True)
class OtherFile:
    path: Path
    relative_path: str
    name: str
    modified_at: datetime


@dataclass
class ExtractResult:
    copied: list[str] = field(default_factory=list)
    skipped_temp: list[str] = field(default_factory=list)
    skipped_newer: list[str] = field(default_factory=list)
    skipped_folders: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)
    clear_failed: list[str] = field(default_factory=list)
    dry_run: bool = False


def is_skipped_folder(name: str, skip_folders: set[str]) -> bool:
    """文件夹名精确命中或通配符（* ? []）命中即跳过。"""
    return any(fnmatch.fnmatch(name, pattern) for pattern in skip_folders)


def collect_other_files(
    root: Path,
    excluded_extensions: set[str],
    cutoff: datetime,
    skip_folders: set[str] | None = None,
) -> tuple[list[OtherFile], list[str], list[str], list[str]]:
    """按资源管理器习惯收集非目标扩展名、且修改时间早于截止时间的文件。

    命中 skip_folders 的文件夹及其所有子文件夹整体跳过。
    返回: (符合条件的文件列表, 跳过的 Office 临时文件, 因时间不符跳过的文件, 跳过的文件夹)
    """
    validate_folder(root, "源")

    collected: list[OtherFile] = []
    skipped_temp: list[str] = []
    skipped_newer: list[str] = []
    skipped_dir_log: list[str] = []

    def walk(current: Path) -> None:
        try:
            entries = list(current.iterdir())
        except OSError:
            return

        entries.sort(key=lambda item: natural_sort_key(item.name))
        files = [item for item in entries if item.is_file()]
        dirs = [item for item in entries if item.is_dir()]

        for path in files:
            if path.suffix.lower() in excluded_extensions:
                continue
            relative_path = normalize_relative_path(path.relative_to(root))
            if is_temp_office_file(path):
                skipped_temp.append(relative_path)
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime)
            if modified_at >= cutoff:
                skipped_newer.append(f"{relative_path} | 修改于 {modified_at.strftime('%Y-%m-%d %H:%M:%S')}")
                continue
            collected.append(
                OtherFile(path=path, relative_path=relative_path, name=path.name, modified_at=modified_at)
            )

        for path in dirs:
            if is_skipped_folder(path.name, skip_folders or set()):
                skipped_dir_log.append(normalize_relative_path(path.relative_to(root)))
                continue
            walk(path)

    walk(root)
    return collected, skipped_temp, skipped_newer, skipped_dir_log


def clear_output_files(
    output_dir: Path,
    excluded_extensions: set[str],
    failed: list[str] | None = None,
) -> list[str]:
    """清空输出文件夹中上一轮提取的非 Word 文件（保留 doc / docx 与其他内容）。

    只读文件先解除只读再删；仍删不掉（被 PDF 阅读器等占用、或没有权限）时
    记入 failed 并继续，避免单个文件导致整个任务中断。
    """
    if not output_dir.exists():
        return []

    cleared: list[str] = []
    for path in output_dir.iterdir():
        if path.is_file() and path.suffix.lower() not in excluded_extensions:
            try:
                safe_unlink(path)
            except OSError as exc:
                if failed is not None:
                    failed.append(f"{path.name} | {exc}")
                continue
            cleared.append(path.name)
    return cleared


def preview_clear_output_files(
    output_dir: Path,
    excluded_extensions: set[str],
    failed: list[str] | None = None,
) -> list[str]:
    """模拟运行版清空：只列出会被清掉的非 Word 文件名，不实际删除。"""
    if not output_dir.exists():
        return []

    return [
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() not in excluded_extensions
    ]


def extract_other_files(
    source_root: Path,
    output_root: Path,
    cutoff: datetime,
    excluded_extensions: set[str] | None = None,
    skip_folders: set[str] | None = None,
    add_order_prefix: bool = True,
    clear_output: bool = False,
    dry_run: bool = False,
    project_tag: str = "",
) -> ExtractResult:
    excluded_extensions = {item.lower() for item in (excluded_extensions or EXCLUDED_EXTENSIONS)}
    files, skipped_temp, skipped_newer, skipped_folders_log = collect_other_files(
        source_root, excluded_extensions, cutoff, skip_folders
    )

    # 模拟运行不创建输出文件夹；重名判断仍按现有输出目录内容计算（只读）
    if not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)

    result = ExtractResult(
        skipped_temp=skipped_temp,
        skipped_newer=skipped_newer,
        skipped_folders=skipped_folders_log,
        dry_run=dry_run,
    )
    clear_func = preview_clear_output_files if dry_run else clear_output_files
    if clear_output:
        result.cleared = clear_func(output_root, excluded_extensions, result.clear_failed)

    width = max(3, len(str(len(files)))) if files else 3

    for index, item in enumerate(files, start=1):
        filename = strip_project_suffix(item.name, project_tag)
        if add_order_prefix:
            filename = f"{index:0{width}d}_{filename}"

        destination = uniquify_destination(output_root, filename)
        if destination.name != filename:
            result.renamed.append(f"{item.relative_path} -> {destination.name}")

        stamp = item.modified_at.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{item.relative_path} -> {destination.name} | 修改于 {stamp}"
        if dry_run:
            # 模拟运行：只记录将复制清单，不写盘，因此不会有复制失败
            result.copied.append(entry)
        else:
            try:
                shutil.copy2(item.path, destination)
                ensure_writable(destination)  # 源文件可能是只读的，避免下轮清空删不掉
                result.copied.append(entry)
            except OSError as exc:
                result.failed.append(f"{item.relative_path} -> {destination.name} | {exc}")

    return result


def build_extract_report(
    result: ExtractResult,
    source_root: Path,
    output_root: Path,
    cutoff: datetime,
    excluded_extensions: set[str],
    skip_folders: set[str],
    add_order_prefix: bool,
    clear_output: bool,
) -> str:
    lines = [
        "非 Word 文件平铺提取结果",
        f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"源文件夹: {source_root}",
        f"输出文件夹: {output_root}",
        f"时间截止: 仅提取修改时间早于 {cutoff.strftime('%Y-%m-%d %H:%M:%S')} 的文件",
        f"排除扩展名: {', '.join(sorted(excluded_extensions))}",
        f"跳过文件夹: {', '.join(sorted(skip_folders)) if skip_folders else '无'}",
        f"序号前缀: {'开启' if add_order_prefix else '关闭'}",
        f"清空输出: {'是' if clear_output else '否'}",
    ]
    if result.dry_run:
        lines.insert(2, "运行模式: 模拟运行（仅记录将复制的文件清单，未创建/清空输出文件夹，未复制任何文件）")
    copied_label = "将复制（模拟）" if result.dry_run else "已复制"
    cleared_label = "将被清空的旧输出（模拟）" if result.dry_run else "清空的旧输出"
    lines += [
        "",
        "汇总:",
        f"{copied_label}: {len(result.copied)} 个",
        f"因重名改名: {len(result.renamed)} 个",
        f"因晚于截止时间跳过: {len(result.skipped_newer)} 个",
        f"跳过文件夹: {len(result.skipped_folders)} 个（含其子文件夹）",
        f"跳过 Office 临时文件: {len(result.skipped_temp)} 个",
        f"{cleared_label}: {len(result.cleared)} 个",
        f"清空失败: {len(result.clear_failed)} 个",
        f"复制失败: {len(result.failed)} 个",
    ]

    sections = [
        (copied_label, result.copied),
        ("因重名改名", result.renamed),
        ("因晚于截止时间跳过", result.skipped_newer),
        ("跳过的文件夹", result.skipped_folders),
        ("跳过的 Office 临时文件", result.skipped_temp),
        (cleared_label, result.cleared),
        ("清空失败（文件被占用或无权限，请关闭后重试）", result.clear_failed),
        ("复制失败", result.failed),
    ]
    for label, items in sections:
        lines.append("")
        lines.append(f"[{label}] {len(items)} 个")
        lines.extend(items)

    return "\n".join(lines) + "\n"


# ==================== 执行入口 ====================


def run(args: argparse.Namespace) -> None:
    source_root = Path(args.source_folder) if args.source_folder else DEFAULT_SOURCE_FOLDER
    output_root = Path(args.output_folder) if args.output_folder else DEFAULT_OUTPUT_FOLDER
    cutoff_raw = args.before if args.before else CUTOFF_TIME
    cutoff = parse_cutoff(cutoff_raw)
    skip_folders = set(SKIP_FOLDER_NAMES)
    for item in args.skip or []:
        skip_folders.update(part.strip() for part in item.split(",") if part.strip())
    log_path = Path(args.log) if args.log else make_log_path("非Word", project_label_from(source_root))
    add_order_prefix = False if args.no_prefix else ADD_ORDER_PREFIX
    clear_output = True if args.clear_output else CLEAR_OUTPUT
    dry_run = True if args.dry_run else DRY_RUN

    result = extract_other_files(
        source_root=source_root,
        output_root=output_root,
        cutoff=cutoff,
        excluded_extensions=EXCLUDED_EXTENSIONS,
        skip_folders=skip_folders,
        add_order_prefix=add_order_prefix,
        clear_output=clear_output,
        dry_run=dry_run,
        project_tag=getattr(args, "project_tag", None) or default_project_tag(),
    )
    report = build_extract_report(
        result=result,
        source_root=source_root,
        output_root=output_root,
        cutoff=cutoff,
        excluded_extensions=EXCLUDED_EXTENSIONS,
        skip_folders=skip_folders,
        add_order_prefix=add_order_prefix,
        clear_output=clear_output,
    )
    print(report, end="")
    write_log(log_path, report)
    print(f"日志已写入: {log_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="平铺提取多级文件夹中修改时间早于截止时间的非 doc / docx 文件并编号。",
    )
    parser.add_argument("source_folder", nargs="?", default=None, help="多级源文件夹；不传时使用顶部 DEFAULT_SOURCE_FOLDER。")
    parser.add_argument("output_folder", nargs="?", default=None, help="平铺输出文件夹；不传时使用顶部 DEFAULT_OUTPUT_FOLDER。")
    parser.add_argument("--before", default=None, help='截止时间，如 "2026-08-01" 或 "2026-08-01 12:30"；不传时使用顶部 CUTOFF_TIME。')
    parser.add_argument(
        "--skip",
        action="append",
        default=None,
        metavar="名称[,名称...]",
        help="跳过的文件夹名（含其所有子文件夹），可逗号分隔或多次使用，支持通配符；与顶部 SKIP_FOLDER_NAMES 合并。",
    )
    parser.add_argument("--no-prefix", action="store_true", help="不添加序号前缀，重名时自动加 __2 后缀。")
    parser.add_argument("--clear-output", action="store_true", help="运行前清空输出文件夹中的非 Word 文件。")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行：只扫描并把将复制的文件清单写入 log，不创建/清空输出文件夹、不复制任何文件。",
    )
    parser.add_argument(
        "--project-tag",
        default=None,
        help="项目标识：传了就把文件名尾部的 `--26某项目02` 这类后缀剥掉，避免产物名带项目代号。",
    )
    parser.add_argument("--log", default=None, help="日志输出路径；不传时自动写入 logs/ 并按 功能_项目名_时间戳 命名。")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
