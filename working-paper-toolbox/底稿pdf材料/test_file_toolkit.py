# -*- coding: utf-8 -*-
"""test_file_toolkit.py —— file_toolkit.py 的沙箱冒烟测试。"""

import os
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pypdf import PdfReader, PdfWriter

TOOLKIT = Path(__file__).resolve().parent / "file_toolkit.py"
TEST_ROOT = os.path.join(tempfile.gettempdir(), "opencode", "file_toolkit_test")

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, cond, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name} {detail}")


def run(*argv):
    """以子进程方式调用工具，返回退出码（控制台输出由日志器打印）。"""
    return subprocess.run(
        [sys.executable, str(TOOLKIT), *argv],
        capture_output=True, text=True, encoding="utf-8",
    ).returncode


def make_pdf(path, width=600, height=800):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    with open(path, "wb") as f:
        writer.write(f)


def main():
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    os.makedirs(TEST_ROOT)

    # ============ [1] renumber_files：预览 + 应用 + 跳过提示 ============
    print("=" * 60)
    print("[1] renumber_files")
    print("=" * 60)
    ren = Path(TEST_ROOT) / "renumber"
    ren.mkdir()
    for name in ("3 丙公司 9000万元.pdf", "1 甲公司 10000万元.pdf",
                 "10 乙公司 500万元.pdf"):
        make_pdf(ren / name)
    make_pdf(ren / "无编号说明.pdf")

    # 预览不应改名
    r = run("renumber_files", "--folder", str(ren))
    names = set(os.listdir(ren))
    check("预览退出码为 0", r == 0)
    check("预览未改动文件", "3 丙公司 9000万元.pdf" in names and "__renumber_" not in str(names))

    r = run("renumber_files", "--folder", str(ren), "--apply")
    after = sorted(os.listdir(ren))
    check("应用后按原编号顺序重排为 1/2/3",
          {"1 甲公司 10000万元.pdf", "2 丙公司 9000万元.pdf", "3 乙公司 500万元.pdf"}
          <= set(after),
          f"实际={after}")
    check("无临时残留", not any(n.endswith(".temp_rename_holder") for n in after))

    # ============ [2] pdf_merge：合并→铺平→自然排序编号 ============
    print()
    print("=" * 60)
    print("[2] pdf_merge（自然排序修复验证）")
    print("=" * 60)
    top = Path(TEST_ROOT) / "pdf_merge_top"
    (top / "2 权属证明B").mkdir(parents=True)
    (top / "10 权属证明C").mkdir(parents=True)
    make_pdf(top / "2 权属证明B" / "x.pdf")
    make_pdf(top / "10 权属证明C" / "y.pdf")
    make_pdf(top / "1 根目录独立件.pdf")

    r = run("pdf_merge", "--top", str(top), "--prefix", "2-3-6-2-", "--all")
    check("pdf_merge 退出码为 0", r == 0)
    tops = [f for f in os.listdir(top) if f.lower().endswith(".pdf")]
    check("子文件夹已铺平、无残留目录", not any((top / f).is_dir() for f in os.listdir(top)))
    expected_first = "2-3-6-2-1 根目录独立件.pdf"
    check("自然排序生效：1 < 2 < 10（字典序会把 10 排在 2 前）",
          tops[0] == expected_first and
          "2-3-6-2-2 权属证明B.pdf" in tops and
          "2-3-6-2-3 权属证明C.pdf" in tops,
          f"实际={sorted(tops)}")

    # 合并件页数应为各子文件夹 PDF 页数之和的容器（抽查第一件可读）
    try:
        PdfReader(str(top / tops[0]))
        readable = True
    except Exception:
        readable = False
    check("产出 PDF 可正常读取", readable)

    # 子文件夹内再套一层：合并必须按真实路径读取
    nested_top = Path(TEST_ROOT) / "pdf_merge_nested"
    nested_inner = nested_top / "2 权属证明B" / "inner"
    nested_inner.mkdir(parents=True)
    make_pdf(nested_inner / "scan.pdf")
    r = run("pdf_merge", "--top", str(nested_top), "--prefix", "9-9-9-", "--all")
    nested_pdfs = [f for f in os.listdir(nested_top) if f.lower().endswith(".pdf")]
    check("嵌套 PDF 合并+铺平退出码 0", r == 0)
    check("嵌套文件已合并铺平",
          any(f.endswith("权属证明B.pdf") for f in nested_pdfs),
          f"实际={nested_pdfs}")
    check("嵌套原始目录已清理", not (nested_top / "2 权属证明B").exists())

    # --flatten 在缺少合并件时应拒绝，避免删原件
    guard_top = Path(TEST_ROOT) / "pdf_merge_guard"
    guard_sub = guard_top / "3 待合并"
    guard_sub.mkdir(parents=True)
    original = guard_sub / "keep.pdf"
    make_pdf(original)
    r = run("pdf_merge", "--top", str(guard_top), "--prefix", "9-9-8-", "--flatten")
    check("缺少合并件时 flatten 退出码非 0", r != 0)
    check("缺少合并件时原始 PDF 仍在", original.exists())

    # ============ [3] flat_rename：平铺 + 原地重命名 ============
    print()
    print("=" * 60)
    print("[3] flat_rename")
    print("=" * 60)
    parent = Path(TEST_ROOT) / "flat_parent"
    d7 = parent / "9-9-7 固定资产科目核查"
    (d7 / "nested").mkdir(parents=True)
    make_pdf(d7 / "nested" / "b.pdf", width=111)
    make_pdf(d7 / "a.pdf", width=110)
    d8 = parent / "9-9-8 无形资产科目核查"
    d8.mkdir(parents=True)
    make_pdf(d8 / "c.pdf")

    spec = "9-9-7 固定资产科目核查:flat,9-9-8 无形资产科目核查"
    # 预览
    r = run("flat_rename", "--parent", str(parent), "--folders", spec)
    check("flat_rename 预览退出码 0", r == 0)
    check("预览未改动（嵌套文件仍在原子目录）", (d7 / "nested" / "b.pdf").exists())

    r = run("flat_rename", "--parent", str(parent), "--folders", spec, "--apply")
    check("apply 退出码 0", r == 0)
    check("平铺：嵌套文件移至顶级并编号",
          (d7 / "9-9-7-1 a.pdf").exists() and (d7 / "9-9-7-2 b.pdf").exists(),
          f"实际={os.listdir(d7)}")
    check("空子文件夹已删除", not (d7 / "nested").exists())
    check("原地重命名独立编号（9-9-8-1）", (d8 / "9-9-8-1 c.pdf").exists(),
          f"实际={os.listdir(d8)}")

    # ============ [4] order_rename：跨位置全局连贯编号 ============
    print()
    print("=" * 60)
    print("[4] order_rename")
    print("=" * 60)
    loc_root = Path(TEST_ROOT) / "order_root"
    loc1 = loc_root / "土地使用权证"
    loc2 = loc_root / "开发成本"
    loc1.mkdir(parents=True)
    loc2.mkdir(parents=True)
    make_pdf(loc1 / "土地证扫描.pdf")
    make_pdf(loc2 / "2 施工合同B.pdf")
    make_pdf(loc2 / "1 施工合同A.pdf")

    r = run("order_rename", "--locations", str(loc1), str(loc2),
            "--prefix", "2-3-5-6-")
    check("order_rename 预览退出码 0", r == 0)

    r = run("order_rename", "--locations", str(loc1), str(loc2),
            "--prefix", "2-3-5-6-", "--apply")
    got1 = os.listdir(loc1)
    got2 = os.listdir(loc2)
    check("位置顺序优先（loc1 编 1）", got1 == ["2-3-5-6-1 土地证扫描.pdf"],
          f"实际={got1}")
    check("loc2 内部自然排序且全局续编",
          got2 == ["2-3-5-6-2 施工合同A.pdf", "2-3-5-6-3 施工合同B.pdf"],
          f"实际={got2}")

    # ============ [5] match_excel：自定义列参数 ============
    print()
    print("=" * 60)
    print("[5] match_excel（参数化）")
    print("=" * 60)
    ht = Path(TEST_ROOT) / "ht.xlsx"
    df1 = pd.DataFrame([
        {"机构": "银行A", "单位": "甲", "余额": 100},
        {"机构": "银行B", "单位": "乙", "余额": 200},
    ])
    df2 = pd.DataFrame([
        {"序号": 1, "机构": "银行A", "单位": "甲", "余额": 100},
    ])
    with pd.ExcelWriter(ht) as w:
        df1.to_excel(w, sheet_name="Sheet1", index=False)
        df2.to_excel(w, sheet_name="Sheet2", index=False)

    out_dir = Path(TEST_ROOT) / "match_out"
    r = run("match_excel", "--excel", str(ht), "--cols", "机构,单位,余额",
            "--output-dir", str(out_dir))
    check("match_excel 退出码 0", r == 0)
    result = pd.read_excel(out_dir / "匹配结果_已添加num.xlsx", sheet_name="sheet1")
    check("num 列生成且第二行为空",
          result.loc[0, "num"] == 1 and pd.isna(result.loc[1, "num"]),
          f"实际={result['num'].tolist()}")

    print()
    print("=" * 60)
    print(f"测试完成：通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
    print(f"沙箱目录: {TEST_ROOT}")
    print("=" * 60)
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
