# -*- coding: utf-8 -*-
"""folder_toolbox：compare / merge 自动化测试（extract 仍由 test_提取打印文件.py 覆盖）。

README 原先写明 compare 与 merge 无自动化测试。本文件在临时目录构造
old/new 样本树，验证相对路径哈希比较、按文件名覆盖、重名冲突跳过等契约。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from folder_toolbox import (
    DEFAULT_NEW_FOLDER,
    DEFAULT_OLD_FOLDER,
    DEFAULT_OUTPUT_FOLDER,
    DEFAULT_SOURCE_FOLDER,
    EXTENSIONS,
    SCRIPT_DIR,
    build_compare_report,
    compare_docx_folders,
    extract_word_files,
    file_sha256,
    is_temp_office_file,
    normalize_relative_path,
    replace_docx_files,
)


PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name} {detail}")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_text(path: Path, content: str) -> None:
    write_bytes(path, content.encode("utf-8"))


def test_common_helpers() -> None:
    print("=" * 60)
    print("[1] common：路径规范化 / 临时文件识别 / SHA-256")
    print("=" * 60)
    check(
        "相对路径统一为正斜杠",
        normalize_relative_path(Path("a") / "b" / "c.docx") == "a/b/c.docx",
    )
    check("Office 锁定文件被识别", is_temp_office_file(Path("dir/~$草稿.docx")))
    check("普通 docx 不是临时文件", not is_temp_office_file(Path("说明.docx")))

    with tempfile.TemporaryDirectory(prefix="sha_") as tmp:
        a = Path(tmp) / "a.docx"
        b = Path(tmp) / "b.docx"
        write_text(a, "same")
        write_text(b, "same")
        check("相同内容哈希一致", file_sha256(a) == file_sha256(b))
        write_text(b, "other")
        check("不同内容哈希不同", file_sha256(a) != file_sha256(b))


def test_compare() -> None:
    print()
    print("=" * 60)
    print("[2] compare：相对路径 + SHA-256 三份差异清单")
    print("=" * 60)
    with tempfile.TemporaryDirectory(prefix="compare_") as tmp:
        old = Path(tmp) / "old"
        new = Path(tmp) / "new"

        write_text(old / "第九章/说明.docx", "v1")
        write_text(new / "第九章/说明.docx", "v2")  # 同路径内容变
        write_text(old / "第九章/未改.docx", "keep")
        write_text(new / "第九章/未改.docx", "keep")  # 同路径同内容
        write_text(old / "第九章/仅旧.docx", "only-old")  # new 缺少
        write_text(new / "第十章/新增.docx", "only-new")  # new 新增
        write_text(old / "第九章/~$锁定.docx", "temp-old")
        write_text(new / "第九章/~$锁定.docx", "temp-new-different")
        write_text(old / "第九章/同名不同路径.docx", "a")
        write_text(new / "第十章/同名不同路径.docx", "b")  # 相对路径不同，不算 changed

        result = compare_docx_folders(old, new)
        check(
            "new 中新增按相对路径列出",
            result["added_in_new"] == ["第十章/同名不同路径.docx", "第十章/新增.docx"],
            f"实际={result['added_in_new']}",
        )
        check(
            "new 中缺少按相对路径列出",
            result["removed_from_new"] == ["第九章/仅旧.docx", "第九章/同名不同路径.docx"],
            f"实际={result['removed_from_new']}",
        )
        check(
            "同路径内容变化计入 changed_content",
            result["changed_content"] == ["第九章/说明.docx"],
            f"实际={result['changed_content']}",
        )
        check(
            "同路径同内容不出现在任何差异清单",
            all("未改.docx" not in paths for paths in result.values()),
        )
        check(
            "临时锁定文件被跳过",
            all("~$锁定.docx" not in paths for paths in result.values()),
        )
        check(
            "同名不同路径单独列出，不并入 changed_content",
            len(result["same_name_different_path"]) == 1
            and "同名不同路径.docx" in result["same_name_different_path"][0]
            and "第九章" in result["same_name_different_path"][0]
            and "第十章" in result["same_name_different_path"][0],
            f"实际={result['same_name_different_path']}",
        )

        report = build_compare_report(result, old, new)
        check("文本报告含三类标签", "new 中新增的 docx" in report and "路径相同但内容不同的 docx" in report)
        check("文本报告含同名不同路径标签", "同名但相对路径不同" in report)
        check("文本报告统计总数正确", "共发现 5 个不同的 docx 文件" in report, f"实际片段={report[:200]!r}")

        as_json = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(as_json)
        check(
            "结果可 JSON 序列化且键完整",
            set(parsed) == {
                "added_in_new",
                "removed_from_new",
                "changed_content",
                "same_name_different_path",
            },
        )


def test_compare_same_name_one_side_duplicate() -> None:
    print()
    print("=" * 60)
    print("[2b] compare：同一侧出现多次同名")
    print("=" * 60)
    with tempfile.TemporaryDirectory(prefix="compare_dup_") as tmp:
        old = Path(tmp) / "old"
        new = Path(tmp) / "new"
        write_text(old / "冲突A/重名.docx", "a")
        write_text(old / "冲突B/重名.docx", "b")
        write_text(new / "唯一/说明.docx", "c")

        result = compare_docx_folders(old, new)
        check(
            "old 一侧重名记入 same_name_different_path",
            len(result["same_name_different_path"]) == 1
            and "重名.docx" in result["same_name_different_path"][0]
            and "冲突A" in result["same_name_different_path"][0]
            and "冲突B" in result["same_name_different_path"][0],
            f"实际={result['same_name_different_path']}",
        )
        check(
            "一侧重名仍按相对路径出现在 removed_from_new",
            result["removed_from_new"] == ["冲突A/重名.docx", "冲突B/重名.docx"],
            f"实际={result['removed_from_new']}",
        )


def test_default_sample_trees() -> None:
    print()
    print("=" * 60)
    print("[2c] 默认配置：样本 old/new 只读冒烟（不改样本、不写默认打印文件）")
    print("=" * 60)
    check("DEFAULT_OLD_FOLDER 存在", DEFAULT_OLD_FOLDER.is_dir(), f"实际={DEFAULT_OLD_FOLDER}")
    check("DEFAULT_NEW_FOLDER 存在", DEFAULT_NEW_FOLDER.is_dir(), f"实际={DEFAULT_NEW_FOLDER}")
    check("DEFAULT_SOURCE_FOLDER 默认就是 new", DEFAULT_SOURCE_FOLDER.resolve() == DEFAULT_NEW_FOLDER.resolve())
    check(
        "extract 默认输出在工具目录下，不依赖 F:",
        DEFAULT_OUTPUT_FOLDER.parent.resolve() == SCRIPT_DIR.resolve(),
        f"实际={DEFAULT_OUTPUT_FOLDER}",
    )

    result = compare_docx_folders(DEFAULT_OLD_FOLDER, DEFAULT_NEW_FOLDER)
    check(
        "默认 old/new 可比较且含四份清单",
        set(result) == {
            "added_in_new",
            "removed_from_new",
            "changed_content",
            "same_name_different_path",
        },
        f"实际键={set(result)}",
    )

    with tempfile.TemporaryDirectory(prefix="extract_default_") as tmp:
        output = Path(tmp) / "打印文件"
        extracted = extract_word_files(
            source_root=DEFAULT_NEW_FOLDER,
            output_root=output,
            extensions=EXTENSIONS,
            add_order_prefix=True,
            clear_output=True,
        )
        names = [p.name for p in output.iterdir() if p.is_file()]
        check("默认 new 至少能抽出 1 个 Word", len(extracted.copied) >= 1 and len(names) >= 1, f"实际={names}")
        sample_docx = next(DEFAULT_NEW_FOLDER.rglob("*.docx"), None)
        check("extract 不改样本源文件", sample_docx is not None and sample_docx.is_file())


def test_merge() -> None:
    print()
    print("=" * 60)
    print("[3] merge：按文件名覆盖 + 六类结果")
    print("=" * 60)
    with tempfile.TemporaryDirectory(prefix="merge_") as tmp:
        old = Path(tmp) / "old"
        new = Path(tmp) / "new"

        write_text(old / "第九章/说明.docx", "old-v1")
        write_text(new / "第九章/说明.docx", "new-v2")  # 被修改
        write_text(old / "第九章/未改.docx", "same")
        write_text(new / "第九章/未改.docx", "same")  # 内容相同
        write_text(old / "第九章/仅旧.docx", "only-old")  # old 独有
        write_text(new / "第十章/新增.docx", "only-new")  # 新增到 old
        write_text(old / "冲突A/重名.docx", "old-a")
        write_text(old / "冲突B/重名.docx", "old-b")  # old 重名冲突
        write_text(new / "冲突A/重名.docx", "new-dup")
        write_text(new / "一侧多份/单侧.docx", "n1")
        write_text(new / "一侧多份2/单侧.docx", "n2")  # new 重名，old 无此名
        write_text(old / "第九章/~$锁定.docx", "temp")
        write_text(new / "第九章/~$锁定.docx", "temp-new")

        result = replace_docx_files(old, new)

        check("内容不同的同名文件被覆盖", (old / "第九章/说明.docx").read_text(encoding="utf-8") == "new-v2")
        check("被修改清单 1 条", len(result.modified) == 1, f"实际={result.modified}")
        check("内容相同不覆盖且计入 unchanged", len(result.unchanged_same) == 1)
        check("old 独有计入 missing_new", result.missing_new == ["第九章/仅旧.docx"], f"实际={result.missing_new}")
        check("new 独有复制到 old 对应相对路径", (old / "第十章/新增.docx").exists())
        check("新增清单 1 条", len(result.added) == 1, f"实际={result.added}")
        check(
            "old 侧重名冲突跳过且不改文件",
            any("重名.docx" in item and "old" in item for item in result.duplicate_conflicts)
            and (old / "冲突A/重名.docx").read_text(encoding="utf-8") == "old-a",
            f"实际={result.duplicate_conflicts}",
        )
        check(
            "new 侧重名冲突跳过",
            any("单侧.docx" in item and "new" in item for item in result.duplicate_conflicts),
            f"实际={result.duplicate_conflicts}",
        )
        check("临时锁定文件不参与 merge", all("~$锁定" not in item for item in (
            result.modified + result.added + result.unchanged_same + result.missing_new
        )))
        check("复制失败为空（沙箱可写）", result.failed == [])
        check("仅旧文件仍在 old 中", (old / "第九章/仅旧.docx").exists())


def test_merge_same_name_different_relative_path() -> None:
    print()
    print("=" * 60)
    print("[4] merge：仅按文件名匹配（相对路径可以不同）")
    print("=" * 60)
    with tempfile.TemporaryDirectory(prefix="merge_name_") as tmp:
        old = Path(tmp) / "old"
        new = Path(tmp) / "new"
        write_text(old / "第九章/调查.docx", "old")
        write_text(new / "附录/调查.docx", "new")

        result = replace_docx_files(old, new)
        check("同名不同路径仍覆盖 old 原位", (old / "第九章/调查.docx").read_text(encoding="utf-8") == "new")
        check("不会在 old 里按 new 的相对路径再复制一份", not (old / "附录/调查.docx").exists())
        check("计入被修改而非新增", len(result.modified) == 1 and len(result.added) == 0)


def run_all_tests() -> None:
    test_common_helpers()
    test_compare()
    test_compare_same_name_one_side_duplicate()
    test_default_sample_trees()
    test_merge()
    test_merge_same_name_different_relative_path()


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as exc:
        print(f"测试异常: {exc}")
        sys.exit(1)
    print()
    print("=" * 60)
    print(f"测试完成：通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
    print("=" * 60)
    sys.exit(1 if FAIL_COUNT else 0)
