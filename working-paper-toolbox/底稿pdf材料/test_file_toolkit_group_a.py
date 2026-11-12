# -*- coding: utf-8 -*-
"""file_toolkit 组A + 编号内核的沙箱测试。

覆盖现有 test_file_toolkit.py 未测的 dedup_folders / convert_images / merge_pdfs，
以及 numbering / ledger_merge / dedup 纯函数。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

import pandas as pd
from PIL import Image
from pypdf import PdfReader, PdfWriter

TOOLKIT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLKIT_DIR))

from toolkit import numbering  # noqa: E402
from toolkit.dedup import (  # noqa: E402
    calculate_folder_fingerprint,
    parse_folder_number,
    run_dedup,
)
from toolkit.imaging import convert_images_in_tree  # noqa: E402
from toolkit.ledger_match import _normalize_match_col  # noqa: E402
from toolkit.ledger_merge import (  # noqa: E402
    format_xuhao,
    get_folder_by_num,
    leading_folder_nums,
    match_priority,
    parse_num_range,
)
from toolkit.working_paper import parse_folder_spec  # noqa: E402

TOOLKIT = TOOLKIT_DIR / "file_toolkit.py"
TEST_ROOT = Path(tempfile.gettempdir()) / "opencode" / "file_toolkit_group_a_test"

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


def make_logger() -> logging.Logger:
    logger = logging.getLogger(f"group_a.{PASS_COUNT + FAIL_COUNT}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def run(*argv: str) -> int:
    return subprocess.run(
        [sys.executable, str(TOOLKIT), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).returncode


def make_pdf(path: Path, width: int = 600, height: int = 800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    with path.open("wb") as fh:
        writer.write(fh)


def make_png(path: Path, color: tuple[int, int, int] = (255, 0, 0)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color).save(path)


def test_numbering_kernel() -> None:
    print("=" * 60)
    print("[1] numbering 内核：自然排序 / 清洗 / 收集 / 冲突检查")
    print("=" * 60)
    names = ["10 权属C.pdf", "2 权属B.pdf", "说明.pdf", "1 根.pdf"]
    ordered = sorted(names, key=numbering.natural_sort_key)
    check(
        "自然排序：有数字前缀按数值，无前缀垫后",
        ordered == ["1 根.pdf", "2 权属B.pdf", "10 权属C.pdf", "说明.pdf"],
        f"实际={ordered}",
    )
    check("leading_num 解析整数", numbering.leading_num("10 权属C.pdf") == 10)
    check("leading_num 无前缀返回 None", numbering.leading_num("说明.pdf") is None)
    check("clean_pdf_name 去前缀数字和横线", numbering.clean_pdf_name("12-权属.pdf") == "权属.pdf")
    check("clean_pdf_name 去前缀空格", numbering.clean_pdf_name("3 合同.pdf") == "合同.pdf")

    spec = parse_folder_spec("2-3-5-7 固定资产科目核查:flat, 2-3-5-8 无形资产科目核查,")
    check(
        "parse_folder_spec 识别 :flat 与默认 keep",
        spec == [("2-3-5-7 固定资产科目核查", True), ("2-3-5-8 无形资产科目核查", False)],
        f"实际={spec}",
    )

    plan = [
        {"dir": Path("a"), "new_name": "1 x.pdf"},
        {"dir": Path("a"), "new_name": "1 x.pdf"},
        {"dir": Path("b"), "new_name": "1 x.pdf"},
    ]
    errors = numbering.check_new_name_conflicts(plan)
    check("同目录新名重复报冲突", len(errors) == 1, f"实际={errors}")
    check("不同目录允许同名", numbering.check_new_name_conflicts([
        {"dir": Path("a"), "new_name": "1 x.pdf"},
        {"dir": Path("b"), "new_name": "1 x.pdf"},
    ]) == [])


def test_collect_and_assign(tmp: Path) -> None:
    loc = tmp / "collect"
    nested = loc / "inner"
    nested.mkdir(parents=True)
    make_pdf(loc / "2 b.pdf")
    make_pdf(loc / "10 a.pdf")
    make_pdf(nested / "scan.pdf")

    top_only = numbering.collect_pdf_items([loc], sort_mode="natural")
    check("非 flatten 只收集顶级", {item["name"] for item in top_only} == {"2 b.pdf", "10 a.pdf"})
    check("natural 模式下 2 在 10 前", [item["name"] for item in top_only][:2] == ["2 b.pdf", "10 a.pdf"])

    flattened = numbering.collect_pdf_items([loc], flatten_flags={0: True}, sort_mode="natural")
    names = [item["name"] for item in flattened]
    check("flatten 递归收到子目录 PDF", "scan.pdf" in names, f"实际={names}")
    nested_item = next(item for item in flattened if item["name"] == "scan.pdf")
    check("子目录文件标记 move=True", nested_item["move"] is True)

    tree_root = tmp / "tree_order"
    (tree_root / "10 later").mkdir(parents=True)
    (tree_root / "2 earlier").mkdir()
    make_pdf(tree_root / "10 later" / "a.pdf")
    make_pdf(tree_root / "2 earlier" / "z.pdf")
    given_items = numbering.collect_pdf_items(
        [tree_root], flatten_flags={0: True}, sort_mode="given"
    )
    given_names = [item["name"] for item in given_items]
    check(
        "树收集按子目录自然序（2 在 10 前，不按文件名字典序）",
        given_names == ["z.pdf", "a.pdf"],
        f"实际={given_names}",
    )

    plan = numbering.assign_numbers(flattened, "9-9-", start=1)
    check("assign_numbers 从 start 连续编号", [item["num"] for item in plan] == [1, 2, 3])
    check("新名格式为 前缀N 清洗名.pdf", plan[0]["new_name"].startswith("9-9-1 "))


def test_two_phase_rollback(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[1b] 两阶段重命名失败时回滚到原名")
    print("=" * 60)
    logger = make_logger()
    folder = tmp / "phase1"
    folder.mkdir(parents=True)
    make_pdf(folder / "a.pdf")
    make_pdf(folder / "b.pdf")
    plan = [
        {
            "dir": folder,
            "name": "a.pdf",
            "path": folder / "a.pdf",
            "top": folder,
            "move": False,
            "new_name": "1 a.pdf",
        },
        {
            "dir": folder,
            "name": "b.pdf",
            "path": folder / "b.pdf",
            "top": folder,
            "move": False,
            "new_name": "2 b.pdf",
        },
    ]
    blocker = folder / f"2 b.pdf{numbering.RENAME_TEMP_SUFFIX}"
    blocker.mkdir()
    ok = numbering.apply_plan_two_phase(plan, logger)
    names = sorted(p.name for p in folder.iterdir() if p.is_file())
    check("第一阶段失败返回 False", ok is False)
    check("第一阶段失败后原文件仍在", names == ["a.pdf", "b.pdf"], f"实际={names}")
    check(
        "无临时名残留文件",
        not any(p.name.endswith(numbering.RENAME_TEMP_SUFFIX) and p.is_file() for p in folder.iterdir()),
    )

    folder2 = tmp / "phase2"
    folder2.mkdir()
    make_pdf(folder2 / "a.pdf")
    make_pdf(folder2 / "b.pdf")
    plan2 = [
        {
            "dir": folder2,
            "name": "a.pdf",
            "path": folder2 / "a.pdf",
            "top": folder2,
            "move": False,
            "new_name": "1 a.pdf",
        },
        {
            "dir": folder2,
            "name": "b.pdf",
            "path": folder2 / "b.pdf",
            "top": folder2,
            "move": False,
            "new_name": "2 b.pdf",
        },
    ]
    (folder2 / "2 b.pdf").mkdir()
    ok2 = numbering.apply_plan_two_phase(plan2, logger)
    files2 = sorted(p.name for p in folder2.iterdir() if p.is_file())
    check("第二阶段失败返回 False", ok2 is False)
    check("第二阶段失败后回滚到原名", files2 == ["a.pdf", "b.pdf"], f"实际={files2}")
    check("第二阶段冲突目录仍在", (folder2 / "2 b.pdf").is_dir())


def test_ledger_merge_helpers(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[2] ledger_merge 纯函数：num 范围 / 特征优先级 / 文件夹定位")
    print("=" * 60)
    check("parse_num_range 单数字", parse_num_range("5") == [5])
    check("parse_num_range 浮点整数 5.0", parse_num_range("5.0") == [5])
    check("parse_num_range 范围 3-6", parse_num_range("3-6") == [3, 4, 5, 6])
    check("parse_num_range 空/nan 返回空", parse_num_range("nan") == [] and parse_num_range("") == [])
    check("format_xuhao 去掉 .0", format_xuhao(7.0) == "7")
    check("format_xuhao 保留非整数", format_xuhao(7.5) == "7.5")

    features = ["流动资金贷款合同", "借款合同", "贷款合同", "借据"]
    check("更具体特征优先于短特征", match_priority("流动资金贷款合同.pdf", features) == 0)
    check("未命中返回 inf", match_priority("扫描件.pdf", features) == float("inf"))

    root = tmp / "folders"
    (root / "5 银行A").mkdir(parents=True)
    (root / "99-100 范围").mkdir()
    (root / "114（查不到此笔放款）").mkdir()
    path, name = get_folder_by_num(root, 5)
    check("按单号定位文件夹", name is not None and name.startswith("5"), f"实际={name}")
    path, name = get_folder_by_num(root, 100)
    check("范围文件夹 99-100 覆盖 100", name is not None and name.startswith("99-100"), f"实际={name}")
    path, name = get_folder_by_num(root, 114)
    check("中文后缀编号仍能定位", name is not None and name.startswith("114"), f"实际={name}")
    path, name = get_folder_by_num(root, 7)
    check("不存在的编号返回 None", path is None and name is None)

    check("leading 单号", leading_folder_nums("5 银行A") == [5])
    check("leading 范围 99-100", leading_folder_nums("99-100 范围") == list(range(99, 101)))
    check(
        "多段索引 2-3-5-7 不拆成范围 2-3",
        leading_folder_nums("2-3-5-7 固定资产科目核查") == [],
    )
    (root / "2-3-5-7 固定资产科目核查").mkdir()
    path, name = get_folder_by_num(root, 2)
    check(
        "get_folder_by_num 不把 2-3-5-7 误当成编号 2",
        path is None and name is None,
        f"实际={name}",
    )
    path, name = get_folder_by_num(root, 3)
    check("get_folder_by_num 也不把 2-3-5-7 当成编号 3", path is None and name is None)


def test_dedup_helpers() -> None:
    print()
    print("=" * 60)
    print("[3] dedup 编号解析")
    print("=" * 60)
    check("纯数字 -> 5.0", parse_folder_number("5 银行A") == 5.0)
    check("范围 99-100 -> 99.5", parse_folder_number("99-100") == 99.5)
    check("中文后缀取前导数字", parse_folder_number("114（查不到此笔放款）") == 114.0)
    check("无数字 -> inf", parse_folder_number("其他资料") == float("inf"))
    check("范围排在起号之后", parse_folder_number("99") < parse_folder_number("99-100") < parse_folder_number("100"))


def test_convert_images(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[4] convert_images：转 PDF 并删原图 / 新 PDF 则直接删图")
    print("=" * 60)
    target = tmp / "images"
    make_png(target / "scan.png")
    make_png(target / "nested" / "photo.jpg", (0, 255, 0))
    rgba = Image.new("RGBA", (8, 8), (0, 0, 255, 128))
    rgba_path = target / "alpha.png"
    rgba_path.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(rgba_path)

    logger = make_logger()
    success, fail = convert_images_in_tree(target, logger)
    pdfs = list(target.rglob("*.pdf"))
    images = [p for p in target.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".jfif"}]
    check("三张图都转换成功", success == 3 and fail == 0, f"success={success} fail={fail}")
    check("原图已删除", images == [], f"残留={images}")
    check("生成 3 个 PDF", len(pdfs) == 3, f"实际={[p.name for p in pdfs]}")
    check("产出 PDF 可读", all(len(PdfReader(p).pages) == 1 for p in pdfs))

    newer_pdf = target / "already.pdf"
    make_pdf(newer_pdf)
    stale = target / "already.png"
    make_png(stale)
    os.utime(newer_pdf, (newer_pdf.stat().st_mtime + 10, newer_pdf.stat().st_mtime + 10))
    success, fail = convert_images_in_tree(target, logger)
    check("已有更新 PDF 时直接删旧图", not stale.exists() and newer_pdf.exists())

    r = run("convert_images", "--target", str(tmp / "missing_dir"))
    check("目录不存在时 CLI 退出码非 0", r != 0)


def test_dedup_folders(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[5] dedup_folders：保留编号更小的重复副本，源目录不动")
    print("=" * 60)
    source = tmp / "dedup_src"
    output = tmp / "dedup_out"
    make_pdf(source / "1 甲" / "合同.pdf", width=100)
    make_pdf(source / "2 乙" / "合同.pdf", width=100)  # 与 1 内容相同
    make_pdf(source / "3 丙" / "合同.pdf", width=200)  # 不同
    make_pdf(source / "99-100 范围" / "合同.pdf", width=300)
    write_note = source / "其他资料" / "readme.txt"
    write_note.parent.mkdir(parents=True, exist_ok=True)
    write_note.write_text("skip", encoding="utf-8")

    logger = make_logger()
    code = run_dedup(source, output, "single", convert_first=False, logger=logger)
    kept = sorted(p.name for p in output.iterdir() if p.is_dir())
    check("run_dedup 退出码 0", code == 0)
    check(
        "重复的 2 被去掉，保留 1/3/99-100",
        kept == ["1 甲", "3 丙", "99-100 范围"],
        f"实际={kept}",
    )
    check("源目录原样保留（含重复文件夹）", (source / "2 乙" / "合同.pdf").exists())
    check("无编号文件夹不进入输出", "其他资料" not in kept)
    fp1 = calculate_folder_fingerprint(source / "1 甲")
    fp2 = calculate_folder_fingerprint(source / "2 乙")
    check("内容相同的文件夹指纹相等", fp1 == fp2)

    nested_src = tmp / "dedup_nested_src"
    make_pdf(nested_src / "母A" / "5 子" / "a.pdf", width=111)
    make_pdf(nested_src / "母B" / "6 子" / "a.pdf", width=222)
    nested_out = tmp / "dedup_nested_out"
    code = run_dedup(nested_src, nested_out, "nested", convert_first=False, logger=logger)
    nested_kept = sorted(p.name for p in nested_out.iterdir() if p.is_dir())
    check("nested 布局扫描母/子两层", code == 0 and nested_kept == ["5 子", "6 子"], f"实际={nested_kept}")

    r = run("dedup_folders", "--source", str(tmp / "no_such"), "--output", str(tmp / "x"), "--no-image-convert")
    check("源目录不存在时 CLI 退出码非 0", r != 0)


def test_merge_pdfs(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[6] merge_pdfs：特征排序合并 / 未匹配特征放弃 / 范围编号")
    print("=" * 60)
    folders = tmp / "loan_folders"
    make_pdf(folders / "1" / "借据.pdf", width=101)
    make_pdf(folders / "1" / "借款合同.pdf", width=102)
    make_pdf(folders / "2" / "扫描件无特征.pdf", width=103)
    make_pdf(folders / "3-6" / "保证合同.pdf", width=104)
    unused = folders / "9 未使用"
    unused.mkdir(parents=True)
    make_pdf(unused / "借据.pdf", width=105)

    excel = tmp / "匹配结果_已添加num.xlsx"
    df = pd.DataFrame([
        {"num": 1, "序号": 7.0, "核算科目": "短期借款", "贷款机构": "银行A",
         "借款单位": "甲公司", "余额": 100000},
        {"num": 2, "序号": 8, "核算科目": "短期借款", "贷款机构": "银行B",
         "借款单位": "乙公司", "余额": 200000},
        {"num": "3-6", "序号": 9, "核算科目": "长期借款", "贷款机构": "银行C",
         "借款单位": "丙公司", "余额": 300000},
        {"num": 99, "序号": 10, "核算科目": "短期借款", "贷款机构": "银行D",
         "借款单位": "丁公司", "余额": 400000},
    ])
    df.to_excel(excel, sheet_name="sheet1", index=False)

    out = tmp / "merged"
    r = run(
        "merge_pdfs",
        "--excel", str(excel),
        "--folders", str(folders),
        "--output", str(out),
    )
    check("merge_pdfs 退出码 0（跳过不算失败）", r == 0)
    produced = sorted(p.name for p in out.iterdir() if p.suffix.lower() == ".pdf")
    check("成功合并 2 份（1 与 3-6），跳过无特征与找不到的编号", len(produced) == 2, f"实际={produced}")

    hit = next(p for p in out.iterdir() if "银行A" in p.name)
    pages = [(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in PdfReader(hit).pages]
    check("合同类排在借据前（102 宽在 101 宽前）", pages == [(102, 800), (101, 800)], f"实际={pages}")
    check("输出文件名不含非法字符且含万元", "万元.pdf" in hit.name and ":" not in hit.name)

    # 自定义特征表：只认「扫描件无特征」，让文件夹 2 也能合并
    feat = tmp / "features.json"
    feat.write_text(json.dumps(["扫描件无特征"], ensure_ascii=False), encoding="utf-8")
    out2 = tmp / "merged_custom"
    r = run(
        "merge_pdfs",
        "--excel", str(excel),
        "--folders", str(folders),
        "--output", str(out2),
        "--features", str(feat),
    )
    custom = list(out2.glob("*.pdf"))
    check("自定义特征表后文件夹 2 可合并", r == 0 and any("银行B" in p.name for p in custom), f"实际={[p.name for p in custom]}")

    all_skip_excel = tmp / "all_skip.xlsx"
    pd.DataFrame([
        {"num": 99, "序号": 1, "核算科目": "短期借款", "贷款机构": "银行Z",
         "借款单位": "戊公司", "余额": 1},
        {"num": 2, "序号": 2, "核算科目": "短期借款", "贷款机构": "银行B",
         "借款单位": "乙公司", "余额": 2},
    ]).to_excel(all_skip_excel, sheet_name="sheet1", index=False)
    r = run(
        "merge_pdfs",
        "--excel", str(all_skip_excel),
        "--folders", str(folders),
        "--output", str(tmp / "merged_all_skip"),
    )
    check("全部跳过时 merge_pdfs 退出码非 0", r != 0)


def test_match_excel_errors(tmp: Path) -> None:
    print()
    print("=" * 60)
    print("[7] match_excel：缺列报错 + Sheet2 特有行导出")
    print("=" * 60)
    tmp.mkdir(parents=True, exist_ok=True)
    ht = tmp / "ht.xlsx"
    df1 = pd.DataFrame([{"机构": "银行A", "单位": "甲", "余额": 100}])
    df2 = pd.DataFrame([
        {"序号": 1, "机构": "银行A", "单位": "甲", "余额": 100},
        {"序号": 2, "机构": "银行C", "单位": "丙", "余额": 300},
    ])
    with pd.ExcelWriter(ht) as writer:
        df1.to_excel(writer, sheet_name="Sheet1", index=False)
        df2.to_excel(writer, sheet_name="Sheet2", index=False)

    out = tmp / "match_ok"
    r = run("match_excel", "--excel", str(ht), "--cols", "机构,单位,余额", "--output-dir", str(out))
    check("正常匹配退出码 0", r == 0)
    unmatched = pd.read_csv(out / "sheet2特有_未匹配数据.csv")
    check("Sheet2 特有行导出 1 条", len(unmatched) == 1 and unmatched.loc[0, "机构"] == "银行C", f"实际={unmatched.to_dict()}")

    r = run("match_excel", "--excel", str(ht), "--cols", "贷款机构,余额", "--output-dir", str(tmp / "match_bad"))
    check("缺列时退出码非 0", r != 0)

    r = run("match_excel", "--excel", str(tmp / "missing.xlsx"), "--output-dir", str(tmp / "x"))
    check("Excel 不存在时退出码非 0", r != 0)

    normalized = _normalize_match_col(pd.Series([100.0, None, "  银行A  ", float("nan"), "nan"]))
    check("整数值浮点去 .0", normalized.iloc[0] == "100", f"实际={normalized.iloc[0]!r}")
    check("真正的空值保持 NA", pd.isna(normalized.iloc[1]) and pd.isna(normalized.iloc[3]))
    check("去空白保留文本", normalized.iloc[2] == "银行A")
    check("字符串 nan 不当成匹配键", pd.isna(normalized.iloc[4]))
    date_norm = _normalize_match_col(pd.Series(pd.to_datetime(["2024-01-01"])))
    check(
        "日期列不会被收成时间戳整数",
        "2024-01-01" in str(date_norm.iloc[0]) and not str(date_norm.iloc[0]).isdigit(),
        f"实际={date_norm.iloc[0]!r}",
    )

    na_xlsx = tmp / "na.xlsx"
    df1_na = pd.DataFrame([
        {"机构": "银行A", "单位": None, "余额": 100.0},
        {"机构": "银行B", "单位": "乙", "余额": 200.0},
    ])
    df2_na = pd.DataFrame([
        {"序号": 1, "机构": "银行A", "单位": None, "余额": 100},
        {"序号": 2, "机构": "银行B", "单位": "乙", "余额": 200},
    ])
    with pd.ExcelWriter(na_xlsx) as writer:
        df1_na.to_excel(writer, sheet_name="Sheet1", index=False)
        df2_na.to_excel(writer, sheet_name="Sheet2", index=False)
    out_na = tmp / "match_na"
    r = run("match_excel", "--excel", str(na_xlsx), "--cols", "机构,单位,余额", "--output-dir", str(out_na))
    result_na = pd.read_excel(out_na / "匹配结果_已添加num.xlsx", sheet_name="sheet1")
    check("双方 NA 不因变成 nan 字符串而误匹配", r == 0 and pd.isna(result_na.loc[0, "num"]), f"实际={result_na['num'].tolist()}")
    check("非空行仍按 200.0==200 匹配", result_na.loc[1, "num"] == 2, f"实际={result_na['num'].tolist()}")


def main() -> None:
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    TEST_ROOT.mkdir(parents=True)

    test_numbering_kernel()
    test_collect_and_assign(TEST_ROOT / "collect_case")
    test_two_phase_rollback(TEST_ROOT / "rollback_case")
    test_ledger_merge_helpers(TEST_ROOT / "ledger_case")
    test_dedup_helpers()
    test_convert_images(TEST_ROOT / "img_case")
    test_dedup_folders(TEST_ROOT / "dedup_case")
    test_merge_pdfs(TEST_ROOT / "merge_case")
    test_match_excel_errors(TEST_ROOT / "match_case")

    print()
    print("=" * 60)
    print(f"测试完成：通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
    print(f"沙箱目录: {TEST_ROOT}")
    print("=" * 60)
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
