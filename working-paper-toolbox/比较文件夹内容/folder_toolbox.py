"""docx 文件夹工具箱：比较、合并、提取打印，三合一入口。

用法（不传路径时使用 toolbox/common.py 中的默认常量）:
    python folder_toolbox.py compare [old_folder] [new_folder] [--json]
    python folder_toolbox.py merge   [old_folder] [new_folder]
    python folder_toolbox.py extract [source_folder] [output_folder] [--no-prefix] [--clear-output]

所有日志统一输出到脚本同级的 logs/ 文件夹，命名格式:
    {功能}_{项目名}_{YYYYMMDD_HHMM}.log

模块结构（由原单文件按原始脚本边界拆分，函数体逐行保真）:
    toolbox/common.py      共享常量与工具函数
    toolbox/compare.py     【原 compare.py】哈希比较两个文件夹
    toolbox/merge_file.py  【原 merge_file.py】用 new 中同名 docx 覆盖 old
    toolbox/extract.py     【原 提取打印文件.py】平铺提取 Word 用于批量打印
"""

from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---- 对外兼容导出：测试与旧用法仍从 folder_toolbox 导入这些名字 ----
from toolbox.common import (  # noqa: F401
    ADD_ORDER_PREFIX,
    CLEAR_OUTPUT,
    DEFAULT_NEW_FOLDER,
    DEFAULT_OLD_FOLDER,
    DEFAULT_OUTPUT_FOLDER,
    DEFAULT_SOURCE_FOLDER,
    EXTENSIONS,
    LOGS_DIR,
    SCRIPT_DIR,
    file_sha256,
    is_temp_office_file,
    make_log_path,
    normalize_relative_path,
    project_label_from,
    validate_folder,
    write_log,
)
from toolbox.compare import (  # noqa: F401
    build_compare_report,
    collect_docx_hashes,
    compare_docx_folders,
)
from toolbox.extract import (  # noqa: F401
    ExtractResult,
    WordFile,
    build_extract_report,
    clear_output_files,
    collect_word_files,
    extract_word_files,
    natural_sort_key,
)
from toolbox.merge_file import (  # noqa: F401
    DocxFile,
    MergeResult,
    build_merge_report,
    collect_docx_by_name,
    duplicate_report,
    format_pair,
    replace_docx_files,
)

from toolbox.compare import run_compare
from toolbox.extract import run_extract
from toolbox.merge_file import run_merge


# ==================== 命令行解析 ====================


def _add_two_folder_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "old_folder",
        nargs="?",
        default=None,
        help="旧文件夹；不传时使用 toolbox/common.py 中的 DEFAULT_OLD_FOLDER。",
    )
    parser.add_argument(
        "new_folder",
        nargs="?",
        default=None,
        help="新文件夹；不传时使用 toolbox/common.py 中的 DEFAULT_NEW_FOLDER。",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="日志输出路径；不传时自动写入 logs/ 并按 功能_项目名_时间戳 命名。",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="docx 文件夹工具箱：compare 比较差异 / merge 用新版覆盖旧版 / extract 平铺提取打印。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser(
        "compare",
        help="递归比较两个母文件夹中的 docx 文件，按相对路径和 SHA-256 哈希找出差异。",
    )
    _add_two_folder_args(compare_parser)
    compare_parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果，便于其他程序继续处理。",
    )
    compare_parser.set_defaults(func=run_compare)

    merge_parser = subparsers.add_parser(
        "merge",
        help="递归比较两个母文件夹中的 docx 文件，并用 new 中的最新版覆盖 old。",
    )
    _add_two_folder_args(merge_parser)
    merge_parser.set_defaults(func=run_merge)

    extract_parser = subparsers.add_parser(
        "extract",
        help="把多级文件夹中的 doc / docx 平铺复制到一个文件夹，方便批量打印。",
    )
    extract_parser.add_argument(
        "source_folder",
        nargs="?",
        default=None,
        help="多级源文件夹；不传时使用 toolbox/common.py 中的 DEFAULT_SOURCE_FOLDER。",
    )
    extract_parser.add_argument(
        "output_folder",
        nargs="?",
        default=None,
        help="平铺输出文件夹；不传时使用 toolbox/common.py 中的 DEFAULT_OUTPUT_FOLDER。",
    )
    extract_parser.add_argument(
        "--no-prefix",
        action="store_true",
        help="不添加打印序号前缀，尽量保留原文件名。",
    )
    extract_parser.add_argument(
        "--clear-output",
        action="store_true",
        help="运行前清空输出文件夹中的 doc / docx。",
    )
    extract_parser.add_argument(
        "--project-tag",
        default=None,
        help="项目标识：传了就把文件名尾部的 `--26某项目02` 这类后缀剥掉，避免产物名带项目代号。",
    )
    extract_parser.add_argument(
        "--log",
        default=None,
        help="日志输出路径；不传时自动写入 logs/ 并按 功能_项目名_时间戳 命名。",
    )
    extract_parser.add_argument(
        "--test",
        action="store_true",
        help="生成测试用例并自检，不使用顶部路径。",
    )
    extract_parser.set_defaults(func=run_extract)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = args.func(args)
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
