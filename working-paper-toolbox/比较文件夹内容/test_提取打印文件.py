from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from folder_toolbox import (
    EXTENSIONS,
    extract_word_files,
    natural_sort_key,
)


def write_dummy(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_sample_tree(root: Path) -> dict[str, str]:
    """
    生成一套覆盖常见打印场景的多级测试目录。

    结构：
    第九章$发行存在的主要风险/
      old.docx
      9-1$说明文件/
        9-1-1 说明文件.docx
        ~$临时锁定.docx          # 应跳过
        无关说明.txt             # 应忽略
      9-2$重大事项调查/
        9-10$后置编号/
          后置文件.doc
        9-2-1$违法违规/
          9-2-1核查记录.docx
        9-2-2$仲裁诉讼/
          9-2-2-1$调查分析/
            调查分析.docx
            同名文件.docx
          9-2-2-2$咨询记录/
            咨询记录.doc
            同名文件.docx        # 与上一层重名
    第十章$其他/
      附件.pdf                   # 应忽略
      补充说明.DOCX              # 大写扩展名
    """
    files = {
        "第九章$发行存在的主要风险/old.docx": "old",
        "第九章$发行存在的主要风险/9-1$说明文件/9-1-1 说明文件.docx": "memo",
        "第九章$发行存在的主要风险/9-1$说明文件/~$临时锁定.docx": "temp",
        "第九章$发行存在的主要风险/9-1$说明文件/无关说明.txt": "ignore-txt",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-10$后置编号/后置文件.doc": "later",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-2-1$违法违规/9-2-1核查记录.docx": "illegal",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-2-2$仲裁诉讼/9-2-2-1$调查分析/调查分析.docx": "analysis",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-2-2$仲裁诉讼/9-2-2-1$调查分析/同名文件.docx": "dup-a",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-2-2$仲裁诉讼/9-2-2-2$咨询记录/咨询记录.doc": "consult",
        "第九章$发行存在的主要风险/9-2$重大事项调查/9-2-2$仲裁诉讼/9-2-2-2$咨询记录/同名文件.docx": "dup-b",
        "第十章$其他/附件.pdf": "ignore-pdf",
        "第十章$其他/补充说明.DOCX": "extra",
    }
    for relative, content in files.items():
        write_dummy(root / relative, content)
    return files


def output_names(output_dir: Path) -> list[str]:
    return sorted(path.name for path in output_dir.iterdir() if path.is_file())


def test_natural_sort() -> None:
    names = [
        "第九章/9-10/后置.docx",
        "第九章/9-2/前面.docx",
        "第十章/补充.docx",
    ]
    ordered = sorted(names, key=natural_sort_key)
    assert_true(
        ordered == [
            "第九章/9-2/前面.docx",
            "第九章/9-10/后置.docx",
            "第十章/补充.docx",
        ],
        f"自然排序错误: {ordered}",
    )


def test_extract_with_prefix(source: Path, output: Path) -> None:
    result = extract_word_files(
        source_root=source,
        output_root=output,
        extensions=EXTENSIONS,
        add_order_prefix=True,
        clear_output=True,
    )

    names = output_names(output)
    assert_true(len(result.copied) == 9, f"应复制 9 个 Word 文件，实际 {len(result.copied)}")
    assert_true(len(result.skipped_temp) == 1, f"应跳过 1 个临时文件，实际 {len(result.skipped_temp)}")
    assert_true(len(names) == 9, f"输出目录应只有 9 个文件，实际 {names}")
    assert_true(all(name[:4].rstrip("_").isdigit() for name in names), f"未全部加序号前缀: {names}")
    assert_true(
        not any(name.startswith("~$") or name.endswith(".txt") or name.endswith(".pdf") for name in names),
        f"输出中混入了非目标文件: {names}",
    )

    # 9-2 必须排在 9-10 前面；「第九章」必须排在「第十章」前面
    assert_true(names[0].endswith("old.docx"), f"第一个文件应为 old.docx: {names}")
    assert_true(any(name.endswith("后置文件.doc") for name in names), f"缺少 .doc 文件: {names}")
    later_index = next(i for i, name in enumerate(names) if name.endswith("后置文件.doc"))
    earlier_index = next(i for i, name in enumerate(names) if "9-2-1核查记录" in name)
    extra_index = next(i for i, name in enumerate(names) if "补充说明" in name)
    assert_true(earlier_index < later_index, f"9-2 应排在 9-10 前: {names}")
    assert_true(extra_index == len(names) - 1, f"第十章应排在最后: {names}")


def test_extract_without_prefix_handles_duplicates(source: Path, output: Path) -> None:
    result = extract_word_files(
        source_root=source,
        output_root=output,
        extensions=EXTENSIONS,
        add_order_prefix=False,
        clear_output=True,
    )

    names = set(output_names(output))
    assert_true("同名文件.docx" in names, "应保留第一个同名文件原名")
    assert_true("同名文件__2.docx" in names, "第二个同名文件应自动改名为 同名文件__2.docx")
    assert_true(len(result.renamed) == 1, f"应记录 1 次重名改名，实际 {result.renamed}")
    assert_true(len(names) == 9, f"无前缀模式也应输出 9 个文件: {sorted(names)}")


def test_clear_output_only_removes_word_files(source: Path, output: Path) -> None:
    write_dummy(output / "旧打印稿.docx", "old-output")
    write_dummy(output / "保留清单.txt", "keep-me")

    result = extract_word_files(
        source_root=source,
        output_root=output,
        extensions=EXTENSIONS,
        add_order_prefix=True,
        clear_output=True,
    )

    names = set(output_names(output))
    assert_true("旧打印稿.docx" not in names, "清空输出后不应残留旧 Word 文件")
    assert_true("保留清单.txt" in names, "清空输出时不应删除非 Word 文件")
    assert_true("旧打印稿.docx" in result.cleared, f"应记录被清空的旧文件: {result.cleared}")


def test_real_old_folder_if_present() -> None:
    real_source = Path(__file__).resolve().parent / "old"
    if not real_source.exists():
        print("跳过真实目录抽检：未找到 old 文件夹")
        return

    with tempfile.TemporaryDirectory(prefix="extract_print_real_") as tmp:
        output = Path(tmp) / "out"
        result = extract_word_files(
            source_root=real_source,
            output_root=output,
            extensions=EXTENSIONS,
            add_order_prefix=True,
            clear_output=True,
        )
        names = output_names(output)
        assert_true(len(result.copied) == len(names), "真实目录复制数与输出文件数不一致")
        assert_true(len(names) >= 1, "真实 old 文件夹中应至少提取到 1 个 Word 文件")
        print(f"真实目录抽检通过: 从 old 提取 {len(names)} 个文件")


def run_all_tests() -> None:
    print("开始生成测试用例并自检...")
    test_natural_sort()

    with tempfile.TemporaryDirectory(prefix="extract_print_") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "source"
        output = tmp_path / "output"
        build_sample_tree(source)

        test_extract_with_prefix(source, output / "with_prefix")
        test_extract_without_prefix_handles_duplicates(source, output / "no_prefix")
        test_clear_output_only_removes_word_files(source, output / "clear")

    test_real_old_folder_if_present()
    print("全部测试通过。")


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as exc:
        print(f"测试失败: {exc}")
        sys.exit(1)
