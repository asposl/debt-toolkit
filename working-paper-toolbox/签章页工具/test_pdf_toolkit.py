# -*- coding: utf-8 -*-
"""
test_pdf_toolkit.py —— pdf_toolkit.py 的自动化冒烟测试。

在 Temp 沙箱中构造测试数据，通过覆盖模块配置变量逐项验证
format / header / filter / insert(append+replace) / export 的核心行为，
不触碰真实项目文件夹。export 拆页清单用现成 PDF 测，全链路再走 Word COM。
"""

import io
import json
import logging
import os
import shutil
import tempfile
import sys
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLKIT_PATH = os.path.join(BASE_DIR, "pdf_toolkit.py")
if not os.path.isfile(TOOLKIT_PATH):
    BASE_DIR = os.path.dirname(BASE_DIR)  # 兼容从别处运行

sys.path.insert(0, BASE_DIR)
import pdf_toolkit as pt  # noqa: E402

from docx import Document  # noqa: E402
from docx.enum.text import WD_BREAK  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

TEST_ROOT = os.path.join(tempfile.gettempdir(), "opencode", "pdf_toolkit_test")

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


def make_docx(path, header_text=None, body_text="正文内容"):
    doc = Document()
    doc.add_paragraph(body_text)
    if header_text is not None:
        doc.sections[0].header.paragraphs[0].text = header_text
    doc.save(path)


def read_header_texts(docx_path):
    texts = []
    with zipfile.ZipFile(docx_path, "r") as z:
        for name in z.namelist():
            if name.startswith("word/header") and name.endswith(".xml"):
                data = z.read(name).decode("utf-8", errors="ignore")
                texts.append(data)
    return "".join(texts)


def make_pdf(path, page_sizes):
    writer = PdfWriter()
    for w, h in page_sizes:
        writer.add_blank_page(width=w, height=h)
    with open(path, "wb") as f:
        writer.write(f)


def _one_page_ascii_pdf(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 12 Tf 50 700 Td ({safe}) Tj ET".encode("ascii")
    chunks = [b"%PDF-1.4\n"]
    offsets = []

    def add_obj(obj_id: int, payload: bytes) -> None:
        offsets.append(sum(len(c) for c in chunks))
        chunks.append(f"{obj_id} 0 obj\n".encode("ascii") + payload + b"\nendobj\n")

    add_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add_obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    )
    add_obj(
        4,
        f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream",
    )
    add_obj(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    xref_pos = sum(len(c) for c in chunks)
    xref = [b"xref\n0 6\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    chunks.extend(xref)
    chunks.append(
        f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return b"".join(chunks)


def write_ascii_pdf(path, page_texts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    writer = PdfWriter()
    for text in page_texts:
        reader = PdfReader(io.BytesIO(_one_page_ascii_pdf(text)))
        writer.add_page(reader.pages[0])
    with open(path, "wb") as f:
        writer.write(f)


def make_docx_pages(path, pages):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = Document()
    if not pages:
        doc.save(path)
        return
    first, *rest = pages
    if doc.paragraphs:
        doc.paragraphs[0].text = first
    else:
        doc.add_paragraph(first)
    for text in rest:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.add_paragraph(text)
    doc.save(path)


def page_sizes(path):
    return [(round(float(p.mediabox.width)), round(float(p.mediabox.height)))
            for p in PdfReader(path).pages]


def main():
    # ---------- 准备沙箱 ----------
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    docx_dir = os.path.join(TEST_ROOT, "docx")
    pdf_dir = os.path.join(TEST_ROOT, "pdf")
    out_dir = os.path.join(TEST_ROOT, "out")
    log_dir = os.path.join(TEST_ROOT, "logs")
    for d in (docx_dir, pdf_dir, out_dir, log_dir):
        os.makedirs(d, exist_ok=True)

    # 覆盖模块配置：日志与产物全部进沙箱（拆分后常量位于 pt.config，业务代码晚绑定读取）
    pt.config.LOG_DIR = log_dir
    pt.config.PROJECT_TAG = "测试"

    logger = logging.getLogger("smoke_test")
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.propagate = False

    print("=" * 60)
    print("[0] 默认配置：PROJECT_ROOT 指向仓库样本且存在")
    print("=" * 60)
    default_project = pt.config.PROJECT_ROOT
    check(
        "默认 PROJECT_ROOT 存在",
        os.path.isdir(default_project),
        f"实际={default_project}",
    )
    check(
        "默认 PROJECT_ROOT 落在仓库样本 new",
        os.path.basename(os.path.normpath(default_project)) == "new",
        f"实际={default_project}",
    )
    check(
        "format/header/export/insert 根目录与 PROJECT_ROOT 一致",
        os.path.normpath(pt.config.FORMAT_INPUT_FOLDER) == os.path.normpath(default_project)
        and os.path.normpath(pt.config.HEADER_ROOT_DIR) == os.path.normpath(default_project)
        and os.path.normpath(pt.config.EXPORT_ROOT_FOLDER) == os.path.normpath(default_project)
        and os.path.normpath(pt.config.APPEND_ROOT_DIR) == os.path.normpath(default_project),
    )

    print()
    print("=" * 60)
    print("[1] header：页眉编号检查与修复")
    print("=" * 60)
    make_docx(os.path.join(docx_dir, "1-1-1 页眉错误.docx"), "尽职调查报告：9-9-9")
    make_docx(os.path.join(docx_dir, "1-1-2 页眉正确.docx"), "尽职调查报告：1-1-2")
    make_docx(os.path.join(docx_dir, "无编号文档.docx"), "随便写的页眉")

    pt.config.HEADER_ROOT_DIR = os.path.join(TEST_ROOT, "no_such_header")
    header_missing_rc = pt.cmd_header(logger)
    check("header 根目录不存在时返回 1", header_missing_rc == 1)

    pt.config.HEADER_ROOT_DIR = docx_dir
    pt.config.HEADER_DRY_RUN = False
    header_rc = pt.cmd_header(logger)
    check("header 成功时返回 0", header_rc == 0)

    fixed = read_header_texts(os.path.join(docx_dir, "1-1-1 页眉错误.docx"))
    kept = read_header_texts(os.path.join(docx_dir, "1-1-2 页眉正确.docx"))
    check("错误编号被替换为 1-1-1", "1-1-1" in fixed and "9-9-9" not in fixed)
    check("正确编号保持不变", "1-1-2" in kept)
    check("生成 header 日志文件", any(f.startswith("header_") for f in os.listdir(log_dir)))

    print()
    print("=" * 60)
    print("[2] format：docx 格式刷新")
    print("=" * 60)
    fmt_path = os.path.join(docx_dir, "2-1-1 格式测试.docx")
    doc = Document()
    doc.add_paragraph("第一节 总体情况")
    doc.add_paragraph("这是正文段落。English 123")
    doc.save(fmt_path)

    pt.config.FORMAT_INPUT_FOLDER = os.path.join(TEST_ROOT, "no_such_format")
    format_missing_rc = pt.cmd_format(logger)
    check("format 文件夹不存在时返回 1", format_missing_rc == 1)

    pt.config.FORMAT_INPUT_FOLDER = docx_dir
    pt.config.FORMAT_UPDATE_DAYS = 1
    format_rc = pt.cmd_format(logger)
    check("format 成功时返回 0", format_rc == 0)

    doc2 = Document(fmt_path)
    p0, p1 = doc2.paragraphs[0], doc2.paragraphs[1]

    def east_asia(run):
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        return None if rFonts is None else rFonts.get(qn("w:eastAsia"))

    def ascii_font(run):
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        return None if rFonts is None else rFonts.get(qn("w:ascii"))

    check("章节标题刷为黑体", east_asia(p0.runs[0]) == "黑体",
          f"实际={east_asia(p0.runs[0])}")
    check("标题西文为 Arial", ascii_font(p0.runs[0]) == "Arial")
    check("正文刷为宋体", east_asia(p1.runs[0]) == "宋体",
          f"实际={east_asia(p1.runs[0])}")
    check("行距为 1.5", float(p1.paragraph_format.line_spacing) == 1.5,
          f"实际={p1.paragraph_format.line_spacing}")

    print()
    print("=" * 60)
    print("[3] filter：过滤“索引”条目")
    print("=" * 60)
    test_json = os.path.join(out_dir, "no_company_test.json")
    items = ["1-2-3 说明.pdf", "1-2-4 目录索引.pdf", "2-2-2 备查.pdf"]
    with open(test_json, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)

    pt.config.FILTER_JSON_PATH = os.path.join(out_dir, "missing_filter.json")
    filter_missing_rc = pt.cmd_filter(logger)
    check("filter 输入不存在时返回 1", filter_missing_rc == 1)

    pt.config.FILTER_JSON_PATH = test_json
    pt.config.FILTER_KEYWORD = "索引"
    filter_rc = pt.cmd_filter(logger)
    check("filter 成功时返回 0", filter_rc == 0)

    latest_log = os.path.join(log_dir, "no_company_无索引_latest.log")
    with open(latest_log, "r", encoding="utf-8") as f:
        raw = f.read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    check("latest 清单已生成", os.path.isfile(latest_log))
    check("latest.log 只含路径（带默认页码）、不含统计块",
          lines == ["1-2-3 说明.pdf|末页", "2-2-2 备查.pdf|末页"]
          and "统计信息" not in raw,
          f"实际={lines!r}")
    check("过滤后剩余 2 条且不含“索引”",
          len(lines) == 2 and all("索引" not in l for l in lines),
          f"实际={lines}")

    noisy = os.path.join(out_dir, "legacy_with_stats.log")
    with open(noisy, "w", encoding="utf-8") as f:
        f.write("keep-a.pdf\n\n")
        f.write("=" * 60 + "\n统计信息\n" + "=" * 60 + "\n")
        f.write("JSON 总条数：3\n")
        f.write("包含“索引”的条数（已移除）：1\n")
        f.write("不包含“索引”的条数：2\n")
    loaded = pt._load_path_list(noisy)
    check("旧版带统计的 log 仍只解析出路径", loaded == ["keep-a.pdf"], f"实际={loaded}")

    from toolkit.filter_index import parse_page_entry
    path_part, page_part = parse_page_entry("a/b.pdf|12")
    check("条目解析：数字页码为第 12 页", (path_part, page_part) == ("a/b.pdf", 12))
    path_part, page_part = parse_page_entry("a/b.pdf|末页")
    check("条目解析：末页标记返回 None", (path_part, page_part) == ("a/b.pdf", None))
    path_part, page_part = parse_page_entry("a/b.pdf")
    check("条目解析：无页码视为末页", (path_part, page_part) == ("a/b.pdf", None))
    try:
        parse_page_entry("a/b.pdf|abc")
        check("条目解析：非法页码抛 ValueError", False)
    except ValueError:
        check("条目解析：非法页码抛 ValueError", True)
    try:
        parse_page_entry("a/b.pdf|0")
        check("条目解析：非正页码抛 ValueError", False)
    except ValueError:
        check("条目解析：非正页码抛 ValueError", True)

    print()
    print("=" * 60)
    print("[4] insert --mode append：追加签章页")
    print("=" * 60)
    # 目标 PDF 两页（600x800），签章 PDF 两页（100x200，尺寸可识别）
    root_a = os.path.join(pdf_dir, "append_root")
    os.makedirs(root_a, exist_ok=True)
    sub_a = os.path.join(root_a, "sub")
    os.makedirs(sub_a, exist_ok=True)
    t1 = os.path.join(sub_a, "1-1-1 文件甲.pdf")
    t2 = os.path.join(root_a, "1-1-2 文件乙.pdf")
    make_pdf(t1, [(600, 800)] * 2)
    make_pdf(t2, [(600, 800)] * 2)
    sig_append = os.path.join(out_dir, "签章页.pdf")
    make_pdf(sig_append, [(100, 200)] * 2)

    append_json = os.path.join(out_dir, "has_company.json")
    with open(append_json, "w", encoding="utf-8") as f:
        json.dump(["sub/1-1-1 文件甲.pdf", "1-1-2 文件乙.pdf"], f, ensure_ascii=False)

    pt.config.APPEND_JSON_PATH = append_json
    pt.config.APPEND_SIGNATURE_PDF_PATH = sig_append
    pt.config.APPEND_ROOT_DIR = os.path.join(TEST_ROOT, "no_such_insert")
    insert_missing_rc = pt.cmd_insert(logger, "append")
    check("insert 根目录不存在时返回 1", insert_missing_rc == 1)

    pt.config.APPEND_ROOT_DIR = root_a
    insert_rc = pt.cmd_insert(logger, "append")
    check("insert append 成功时返回 0", insert_rc == 0)

    s1 = page_sizes(t1)
    s2 = page_sizes(t2)
    check("甲由 2 页变 3 页", len(s1) == 3, f"实际={len(s1)} 页")
    check("乙由 2 页变 3 页", len(s2) == 3, f"实际={len(s2)} 页")
    check("末页来自签章 PDF（100x200）", s1[-1] == (100, 200) and s2[-1] == (100, 200),
          f"实际={s1[-1]},{s2[-1]}")
    check("原页面未被破坏（前两页 600x800）", s1[:2] == [(600, 800)] * 2)
    check("无 .tmp 残留", not any(f.endswith(".tmp")
          for _, _, fs in os.walk(root_a) for f in fs))

    print()
    print("=" * 60)
    print("[5] insert --mode replace：替换末页（含 filter 产物直连）")
    print("=" * 60)
    root_b = os.path.join(pdf_dir, "replace_root")
    os.makedirs(root_b, exist_ok=True)
    r1 = os.path.join(root_b, "2-1-1 文件丙.pdf")
    make_pdf(r1, [(600, 800)] * 3)
    sig_replace = os.path.join(out_dir, "签字合并.pdf")
    make_pdf(sig_replace, [(300, 400)])  # 1 页签字页，尺寸 300x400

    chain_json = os.path.join(out_dir, "no_company_latest.json")
    with open(chain_json, "w", encoding="utf-8") as f:
        json.dump(["2-1-1 文件丙.pdf", "2-1-9 目录索引.pdf"], f, ensure_ascii=False)
    pt.config.FILTER_JSON_PATH = chain_json
    pt.cmd_filter(logger)

    pt.config.REPLACE_LIST_PATH = latest_log
    pt.config.REPLACE_SIGNATURE_PDF_PATH = sig_replace
    pt.config.REPLACE_ROOT_DIR = root_b
    replace_rc = pt.cmd_insert(logger, "replace")
    check("insert replace 成功时返回 0", replace_rc == 0)

    sr = page_sizes(r1)
    check("总页数不变仍为 3 页", len(sr) == 3, f"实际={len(sr)} 页")
    check("末页已被签字页替换（300x400）", sr[-1] == (300, 400), f"实际={sr[-1]}")
    check("前两页保持原样（600x800）", sr[:2] == [(600, 800)] * 2)

    print()
    print("=" * 60)
    print("[6] insert --mode replace：数量不一致应拒绝执行")
    print("=" * 60)
    bad_list = os.path.join(out_dir, "bad_list.log")
    with open(bad_list, "w", encoding="utf-8") as f:
        f.write("a.pdf\nb.pdf\n")  # 2 条 vs 签字 PDF 1 页

    pt.config.REPLACE_LIST_PATH = bad_list
    before = page_sizes(r1)
    mismatch_rc = pt.cmd_insert(logger, "replace")
    check("数量不一致时 insert replace 返回 1", mismatch_rc == 1)
    check("拒绝执行后文件未被改动", page_sizes(r1) == before)

    print()
    print("=" * 60)
    print("[6.5] insert --mode replace：指定页码替换")
    print("=" * 60)
    # 3 页目标 PDF，签字 1 页；清单指定替换第 2 页（模拟签字页后有附件）
    r2 = os.path.join(root_b, "2-1-2 文件指定页.pdf")
    make_pdf(r2, [(600, 800), (600, 800), (600, 800)])
    page_list = os.path.join(out_dir, "page_list.log")
    with open(page_list, "w", encoding="utf-8") as f:
        f.write("2-1-2 文件指定页.pdf|2\n")

    pt.config.REPLACE_LIST_PATH = page_list
    pt.config.REPLACE_SIGNATURE_PDF_PATH = sig_replace
    pt.config.REPLACE_ROOT_DIR = root_b
    page_rc = pt.cmd_insert(logger, "replace")
    sp = page_sizes(r2)
    check("指定页码替换成功时返回 0", page_rc == 0)
    check("总页数不变仍为 3 页", len(sp) == 3, f"实际={len(sp)} 页")
    check("第 2 页被替换为签字页（300x400）", sp[1] == (300, 400), f"实际={sp[1]}")
    check("第 1、3 页保持原样", sp[0] == (600, 800) and sp[2] == (600, 800))

    # 越界页码：该条失败但返回码为 1，文件不被改动
    over_list = os.path.join(out_dir, "over_page_list.log")
    with open(over_list, "w", encoding="utf-8") as f:
        f.write("2-1-2 文件指定页.pdf|9\n")
    pt.config.REPLACE_LIST_PATH = over_list
    before_over = page_sizes(r2)
    over_rc = pt.cmd_insert(logger, "replace")
    check("越界页码返回 1", over_rc == 1)
    check("越界页码不改动文件", page_sizes(r2) == before_over)

    # 非法格式：动手前整体拒绝执行
    bad_fmt_list = os.path.join(out_dir, "bad_fmt_list.log")
    with open(bad_fmt_list, "w", encoding="utf-8") as f:
        f.write("2-1-2 文件指定页.pdf|abc\n")
    pt.config.REPLACE_LIST_PATH = bad_fmt_list
    before_bad = page_sizes(r2)
    bad_fmt_rc = pt.cmd_insert(logger, "replace")
    check("非法页码格式整体拒绝执行", bad_fmt_rc == 1)
    check("拒绝后文件未被改动", page_sizes(r2) == before_bad)

    print()
    print("=" * 60)
    print("[7] 纯函数：页眉编号提取 / PDF 复用判断 / 混用斜杠路径")
    print("=" * 60)
    from toolkit.header_fix import extract_number_from_filename, extract_number_from_header_text
    from toolkit.export_sign import (
        auto_shorten_long_paths,
        can_reuse_recent_pdf,
        extract_serial_name,
        natural_sort_key,
        split_and_catalog_pdfs,
    )

    check("文件名提取 4-1-1", extract_number_from_filename("4-1-1 发行人关于.docx") == "4-1-1")
    check("无编号文件名返回 None", extract_number_from_filename("无编号文档.docx") is None)
    check("页眉忽略中文前缀", extract_number_from_header_text("尽职调查报告：9-9-9") == "9-9-9")
    check("页眉无连字符编号不提取", extract_number_from_header_text("尽职调查报告：9") is None)

    docx_p = os.path.join(out_dir, "reuse.docx")
    pdf_p = os.path.join(out_dir, "reuse.pdf")
    make_docx(docx_p)
    make_pdf(pdf_p, [(100, 100)])
    now = os.path.getmtime(pdf_p)
    os.utime(docx_p, (now - 100, now - 100))
    os.utime(pdf_p, (now, now))
    check("新 PDF 且不旧于 docx 时可复用", can_reuse_recent_pdf(docx_p, pdf_p, max_age_days=1))
    os.utime(docx_p, (now + 50, now + 50))
    check("docx 比 PDF 新则强制重导", not can_reuse_recent_pdf(docx_p, pdf_p, max_age_days=1))
    check("max_age_days=0 关闭复用", not can_reuse_recent_pdf(docx_p, pdf_p, max_age_days=0))

    original = pt.config.EXPORT_RECENT_PDF_MAX_AGE_DAYS
    pt.config.EXPORT_RECENT_PDF_MAX_AGE_DAYS = 0
    os.utime(docx_p, (now - 100, now - 100))
    os.utime(pdf_p, (now, now))
    check(
        "默认参数晚绑定读取 config（覆盖为 0 后不可复用）",
        not can_reuse_recent_pdf(docx_p, pdf_p),
    )
    pt.config.EXPORT_RECENT_PDF_MAX_AGE_DAYS = original

    shorten_dir = os.path.join(out_dir, "shorten")
    os.makedirs(shorten_dir, exist_ok=True)
    upper_docx = os.path.join(shorten_dir, "UPPER.DOCX")
    make_docx(upper_docx)
    saved_limit = pt.config.EXPORT_PATH_LENGTH_LIMIT
    pt.config.EXPORT_PATH_LENGTH_LIMIT = 1
    renamed = auto_shorten_long_paths(shorten_dir)
    pt.config.EXPORT_PATH_LENGTH_LIMIT = saved_limit
    check(
        "路径阈值晚绑定且大写 .DOCX 也会被缩短",
        len(renamed) == 1 and renamed[0][0] == "UPPER.DOCX" and not os.path.isfile(upper_docx),
        f"实际={renamed} 残留={os.listdir(shorten_dir)}",
    )
    check("extract_serial_name 保留开头序号", extract_serial_name("2-3-6-1 很长的名字.docx", 9) == "2-3-6-1.docx")
    check("extract_serial_name 无序号回退", extract_serial_name("说明.docx", 3) == "doc_3.docx")
    sort_names = ["第十章/a.pdf", "第九章/a.pdf", "10 x.pdf", "2 x.pdf"]
    sorted_names = sorted(sort_names, key=natural_sort_key)
    check(
        "export 自然排序：2<第九章(9)<10=第十章",
        sorted_names == ["2 x.pdf", "第九章/a.pdf", "10 x.pdf", "第十章/a.pdf"],
        f"实际={sorted_names}",
    )

    print()
    print("=" * 60)
    print("[8] insert append：清单混用斜杠 + 单页 PDF replace")
    print("=" * 60)
    root_c = os.path.join(pdf_dir, "slash_root")
    os.makedirs(root_c, exist_ok=True)
    sub_c = os.path.join(root_c, "sub")
    os.makedirs(sub_c, exist_ok=True)
    t3 = os.path.join(sub_c, "3-1-1 混斜杠.pdf")
    make_pdf(t3, [(600, 800)])
    sig_slash = os.path.join(out_dir, "签章页_slash.pdf")
    make_pdf(sig_slash, [(111, 222)])
    slash_json = os.path.join(out_dir, "slash.json")
    with open(slash_json, "w", encoding="utf-8") as f:
        json.dump(["sub/3-1-1 混斜杠.pdf"], f, ensure_ascii=False)
    pt.config.APPEND_JSON_PATH = slash_json
    pt.config.APPEND_SIGNATURE_PDF_PATH = sig_slash
    pt.config.APPEND_ROOT_DIR = root_c
    pt.cmd_insert(logger, "append")
    s3 = page_sizes(t3)
    check("正斜杠相对路径仍能追加", len(s3) == 2 and s3[-1] == (111, 222), f"实际={s3}")

    root_d = os.path.join(pdf_dir, "onepage_root")
    os.makedirs(root_d, exist_ok=True)
    r_one = os.path.join(root_d, "only.pdf")
    make_pdf(r_one, [(600, 800)])
    sig_one = os.path.join(out_dir, "签字一页.pdf")
    make_pdf(sig_one, [(333, 444)])
    one_list = os.path.join(out_dir, "one.log")
    with open(one_list, "w", encoding="utf-8") as f:
        f.write("only.pdf\n")
    pt.config.REPLACE_LIST_PATH = one_list
    pt.config.REPLACE_SIGNATURE_PDF_PATH = sig_one
    pt.config.REPLACE_ROOT_DIR = root_d
    pt.cmd_insert(logger, "replace")
    so = page_sizes(r_one)
    check("单页 PDF 替换后仍为 1 页", len(so) == 1, f"实际={so}")
    check("单页内容来自签字 PDF", so == [(333, 444)], f"实际={so}")

    print()
    print("=" * 60)
    print("[9] export 阶段二：拆末页 / 单页跳过 / JSON 固定名副本")
    print("=" * 60)
    from toolkit.export_sign import split_and_catalog_pdfs

    split_root = os.path.join(pdf_dir, "split_root")
    os.makedirs(os.path.join(split_root, "第九章"), exist_ok=True)
    hit_pdf = os.path.join(split_root, "第九章", "9-1 有公司.pdf")
    skip_pdf = os.path.join(split_root, "单页有公司.pdf")
    keep_pdf = os.path.join(split_root, "2 无公司.pdf")
    later_pdf = os.path.join(split_root, "10 无公司.pdf")
    write_ascii_pdf(hit_pdf, ["BODY", "ACMECO SIGNATURE"])
    write_ascii_pdf(skip_pdf, ["ACMECO ONLY"])
    write_ascii_pdf(keep_pdf, ["NOKEYWORD"])
    write_ascii_pdf(later_pdf, ["STILLNONE"])
    extracted = "".join(p.extract_text() or "" for p in PdfReader(hit_pdf).pages)
    check("ASCII PDF 可抽出关键字", "ACMECO" in extracted.replace(" ", ""), f"实际={extracted!r}")

    pt.config.EXPORT_MERGED_PDF_NAME = "签章页.pdf"
    catalog = split_and_catalog_pdfs(
        split_root,
        [hit_pdf, skip_pdf, keep_pdf, later_pdf],
        "ACMECO",
    )
    check(
        "多页命中公司名列入 has_company",
        catalog["has_company_list"] == ["第九章/9-1 有公司.pdf"],
        f"实际={catalog['has_company_list']}",
    )
    check(
        "未命中列入 no_company，且 2 在 10 前",
        catalog["no_company_list"] == ["2 无公司.pdf", "10 无公司.pdf"],
        f"实际={catalog['no_company_list']}",
    )
    check("单页命中公司名不进任何清单", "单页有公司.pdf" not in catalog["has_company_list"] + catalog["no_company_list"])
    check("命中文件被拆掉末页", len(PdfReader(hit_pdf).pages) == 1)
    check("未命中文件页数不变", len(PdfReader(keep_pdf).pages) == 1 and len(PdfReader(later_pdf).pages) == 1)
    merged_path = os.path.join(split_root, "签章页.pdf")
    check("生成签章页.pdf 且含 1 页", catalog["merged_pdf_path"] == merged_path and len(PdfReader(merged_path).pages) == 1)
    latest_has = os.path.join(log_dir, "has_company_latest.json")
    latest_no = os.path.join(log_dir, "no_company_latest.json")
    with open(latest_has, encoding="utf-8") as f:
        has_latest = json.load(f)
    with open(latest_no, encoding="utf-8") as f:
        no_latest = json.load(f)
    check("has_company_latest.json 与清单一致", has_latest == catalog["has_company_list"])
    check("no_company_latest.json 与清单一致", no_latest == catalog["no_company_list"])

    print()
    print("=" * 60)
    print("[10] export 全链路（Word COM）+ filter/insert 直连")
    print("=" * 60)
    pt.config.EXPORT_ROOT_FOLDER = os.path.join(TEST_ROOT, "no_such_export")
    export_missing_rc = pt.cmd_export(logger)
    check("export 根目录不存在时返回 1", export_missing_rc == 1)

    export_root = os.path.join(pdf_dir, "export_com")
    os.makedirs(os.path.join(export_root, "第九章"), exist_ok=True)
    company_docx = os.path.join(export_root, "第九章", "9-1 有公司.docx")
    plain_docx = os.path.join(export_root, "2 无公司.docx")
    make_docx_pages(company_docx, ["第一页正文", "TestCompanyKeyword"])
    make_docx_pages(plain_docx, ["普通正文没有关键字"])
    pt.config.EXPORT_ROOT_FOLDER = export_root
    pt.config.EXPORT_COMPANY_KEYWORD = "TestCompanyKeyword"
    pt.config.EXPORT_MERGED_PDF_NAME = "签章页.pdf"
    pt.config.EXPORT_RECENT_PDF_MAX_AGE_DAYS = 1
    try:
        export_rc = pt.cmd_export(logger)
        check("export 成功时返回 0", export_rc == 0)
        company_pdf = os.path.splitext(company_docx)[0] + ".pdf"
        plain_pdf = os.path.splitext(plain_docx)[0] + ".pdf"
        check("Word 已导出两个 PDF", os.path.isfile(company_pdf) and os.path.isfile(plain_pdf))
        check("含关键字的 2 页 PDF 被拆成 1 页", len(PdfReader(company_pdf).pages) == 1, f"实际={len(PdfReader(company_pdf).pages)}")
        check("不含关键字的 PDF 保持 1 页", len(PdfReader(plain_pdf).pages) == 1)
        merged_export = os.path.join(export_root, "签章页.pdf")
        check("项目根写出签章页.pdf", os.path.isfile(merged_export) and len(PdfReader(merged_export).pages) == 1)
        with open(os.path.join(log_dir, "has_company_latest.json"), encoding="utf-8") as f:
            has_com = json.load(f)
        with open(os.path.join(log_dir, "no_company_latest.json"), encoding="utf-8") as f:
            no_com = json.load(f)
        check("COM 导出 has_company 含相对路径", any("9-1 有公司.pdf" in item for item in has_com), f"实际={has_com}")
        check("COM 导出 no_company 含无关键字文件", any("2 无公司.pdf" in item for item in no_com), f"实际={no_com}")

        first_has_json = os.path.join(out_dir, "first_has_company.json")
        shutil.copy2(os.path.join(log_dir, "has_company_latest.json"), first_has_json)
        first_no_json = os.path.join(out_dir, "first_no_company.json")
        shutil.copy2(os.path.join(log_dir, "no_company_latest.json"), first_no_json)

        mtime_before = os.path.getmtime(company_pdf)
        reuse_rc = pt.cmd_export(logger)
        check("第二次 export 复用仍返回 0", reuse_rc == 0)
        check("复用时已拆页 PDF 不会被 Word 覆盖回 2 页", len(PdfReader(company_pdf).pages) == 1)
        check("复用时拆页 PDF mtime 不刷新", os.path.getmtime(company_pdf) == mtime_before)
        with open(os.path.join(log_dir, "has_company_latest.json"), encoding="utf-8") as f:
            has_after_reuse = json.load(f)
        check(
            "复用已拆页 PDF 后 has_company 变空（末页关键字已拆走）",
            has_after_reuse == [],
            f"实际={has_after_reuse}",
        )

        pt.config.FILTER_JSON_PATH = first_no_json
        pt.config.FILTER_KEYWORD = "索引"
        filter_com_rc = pt.cmd_filter(logger)
        check("第一次 export 的 no_company 可直接给 filter", filter_com_rc == 0)

        pt.config.APPEND_JSON_PATH = first_has_json
        pt.config.APPEND_SIGNATURE_PDF_PATH = merged_export
        pt.config.APPEND_ROOT_DIR = export_root
        insert_com_rc = pt.cmd_insert(logger, "append")
        check("第一次 export 的签章页可直接给 insert append", insert_com_rc == 0)
        check("insert 把拆出的末页追加回去", len(PdfReader(company_pdf).pages) == 2)
    except Exception as exc:
        check(f"export COM 全链路异常: {exc}", False)

    print()
    print("=" * 60)
    print(f"测试完成：通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
    print(f"沙箱目录: {TEST_ROOT}")
    print("=" * 60)
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
