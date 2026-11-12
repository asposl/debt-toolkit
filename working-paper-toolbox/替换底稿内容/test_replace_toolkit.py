# -*- coding: utf-8 -*-
"""
test_replace_toolkit.py —— replace_toolkit.py 的沙箱冒烟测试。
在 Temp 中构造规则表副本与 docx 样本，验证 short（词表外置）与 long（Word COM）两条链路。
"""

import os
import shutil
import tempfile
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import replace_toolkit as rt  # noqa: E402

from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

TEST_ROOT = os.path.join(tempfile.gettempdir(), "opencode", "replace_toolkit_test")

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


def make_docx(path, paragraphs=None):
    doc = Document()
    for text in (paragraphs or ["正文"]):
        doc.add_paragraph(text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc.save(path)


def _set_landscape(section) -> None:
    section.orientation = WD_ORIENT.LANDSCAPE
    width, height = section.page_width, section.page_height
    if width < height:
        section.page_width = height
        section.page_height = width


def _is_landscape(section) -> bool:
    return section.page_width > section.page_height


def make_landscape_docx(path, paragraphs=None):
    """双节素材：第一节占位 + 第二节横向，才能走到 long 的节隔离路径。"""
    doc = Document()
    if doc.paragraphs:
        doc.paragraphs[0].text = "横版节前占位"
    else:
        doc.add_paragraph("横版节前占位")
    landscape_section = doc.add_section()
    _set_landscape(landscape_section)
    texts = paragraphs or ["横版素材"]
    for text in texts:
        doc.add_paragraph(text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc.save(path)


def docx_text(path):
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(p.text for p in cell.paragraphs)
    return "\n".join(parts)


def main():
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    src_dir = os.path.join(TEST_ROOT, "src")
    out_dir = os.path.join(TEST_ROOT, "out")
    log_dir = os.path.join(TEST_ROOT, "logs")
    for d in (src_dir, out_dir, log_dir):
        os.makedirs(d, exist_ok=True)

    default_source = rt.config.SOURCE_FOLDER
    default_rules = rt.config.SHORT_RULES_XLSX
    check("默认 SOURCE_FOLDER 存在（仓库样本）", os.path.isdir(default_source), default_source)
    check("默认规则表存在", os.path.isfile(default_rules), str(default_rules))

    # 覆盖模块配置：全部指向沙箱（拆分后常量位于 rt.config，业务代码晚绑定读取）
    rt.config.LOG_DIR = log_dir
    rules_xlsx = os.path.join(TEST_ROOT, "替换规则表.xlsx")
    rt.config.SHORT_RULES_XLSX = rules_xlsx
    rt.config.SOURCE_FOLDER = src_dir
    rt.config.FINAL_FOLDER = src_dir  # 原地替换
    rt.config.RULES_XLSX = __import__("pathlib").Path(rules_xlsx)
    rt.config.TARGET_DOCX_DIR = __import__("pathlib").Path(src_dir)
    rt.config.INSERT_DOCX_DIR = __import__("pathlib").Path(out_dir)
    rt.config.OVERWRITE_ORIGINAL = True

    logger = rt.setup_logger("test")

    # ---------- 准备规则表 ----------
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "填写说明"
    ws_long = wb.create_sheet("长替换")
    ws_long.append(["起始关键字", "结束关键字", "替换素材文件名"])  # 表头占第 1 行
    ws_short = wb.create_sheet("短替换")
    ws_short.append(["查找词", "替换词"])
    ws_short.append(["本募集说明书签署日", "本文件出具日"])                      # 普通词对
    ws_short.append([r"regex:2026年6月[\s\u00A0\u3000]*日", "2026年6月30日"])   # 正则
    ws_short.append([" obsolete词 ", ""])                                        # 空格清洗+删除
    ws_long.delete_rows(2, ws_long.max_row)                                     # 清掉原示例规则
    wb.save(rules_xlsx)
    wb.close()

    # ---------- 准备 docx 样本 ----------
    hit_path = os.path.join(src_dir, "sub", "命中文档.docx")
    os.makedirs(os.path.dirname(hit_path), exist_ok=True)
    doc = Document()
    doc.add_paragraph("自本募集说明书签署日起，费用由发行人承担。")
    doc.add_paragraph("签署日期是 2026年6月　日，请核对。")   # 全角空格，走 regex
    doc.add_paragraph("这一段含 obsolete词 需要清理。")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].text = "表格里也提到本募集说明书签署日。"
    doc.sections[0].header.paragraphs[0].text = "页眉：本募集说明书签署日"
    doc.save(hit_path)

    miss_path = os.path.join(src_dir, "未命中文档.docx")
    make_docx(miss_path, ["这段没有任何目标词汇。"])

    print("=" * 60)
    print("[1] short：词表外置替换")
    print("=" * 60)
    short_rc = rt.cmd_short(logger)
    check("short 成功时返回 0", short_rc == 0)

    text_after = docx_text(hit_path)
    check("普通词对已替换（正文）", "本文件出具日" in text_after and "本募集说明书签署日" not in text_after)
    check("正则规则已替换（全角空格日期）", "2026年6月30日" in text_after)
    check("空替换词=删除生效", "obsolete词" not in text_after and "需要清理" in text_after)
    check("表格内文字已替换", "表格里也提到本文件出具日" in text_after)
    check("页眉文字已替换", any(
        "本文件出具日" in p.text for s in Document(hit_path).sections for p in s.header.paragraphs
    ))
    check("未命中文档保持原样", "这段没有任何目标词汇。" in docx_text(miss_path))
    check("short 日志落盘", any(f.startswith("test_") for f in os.listdir(log_dir)))

    print()
    print("=" * 60)
    print("[2] short 异常路径：工作表不存在应报错退出")
    print("=" * 60)
    rt.config.SHORT_RULES_SHEET = "不存在的工作表"
    before = docx_text(hit_path)
    missing_sheet_rc = rt.cmd_short(logger)
    check("工作表不存在时 short 返回 1", missing_sheet_rc == 1)
    check("报错后文件未被改动", docx_text(hit_path) == before)
    rt.config.SHORT_RULES_SHEET = "短替换"

    saved_source = rt.config.SOURCE_FOLDER
    rt.config.SOURCE_FOLDER = os.path.join(TEST_ROOT, "no_such_source")
    missing_src_rc = rt.cmd_short(logger)
    check("源目录不存在时 short 返回 1", missing_src_rc == 1)
    rt.config.SOURCE_FOLDER = saved_source

    print()
    print("=" * 60)
    print("[3] long：规则表区间替换 + 插入素材（Word COM）")
    print("=" * 60)
    # 目标文档：起始/结束关键字之间为旧内容
    target_path = os.path.join(src_dir, "区间文档.docx")
    make_docx(target_path, [
        "开头说明。",
        "【起始标记】",
        "这里是要被换掉的旧内容旧内容。",
        "【结束标记】",
        "结尾说明。",
    ])
    # 素材文档：新内容
    insert_path = os.path.join(out_dir, "新内容素材.docx")
    make_docx(insert_path, ["这是插入的新内容。"])

    wb2 = load_workbook(rules_xlsx)
    ws1 = wb2["长替换"]
    ws1.append(["【起始标记】", "【结束标记】", insert_path])
    # 把「短替换」挪到最前，模拟 Excel 打开时活动表不是「长替换」
    wb2.move_sheet("短替换", offset=-wb2.sheetnames.index("短替换"))
    check("活动表已被换成「短替换」（回归：long 不得误读）",
          wb2.sheetnames[0] == "短替换" and wb2.active.title == "短替换",
          f"实际 sheetnames={wb2.sheetnames}, active={wb2.active.title}")
    wb2.save(rules_xlsx)
    wb2.close()

    saved_target = rt.config.TARGET_DOCX_DIR
    rt.config.TARGET_DOCX_DIR = __import__("pathlib").Path(os.path.join(TEST_ROOT, "no_such_long"))
    long_missing_rc = rt.cmd_long(logger)
    check("被替换文件夹不存在时 long 返回 1", long_missing_rc == 1)
    rt.config.TARGET_DOCX_DIR = saved_target

    try:
        rt.cmd_long(logger)
        text_long = docx_text(target_path)
        check("旧内容被移除", "旧内容旧内容" not in text_long)
        check("素材新内容已插入", "这是插入的新内容。" in text_long)
        check("起止标记一并被替换（REPLACE_BOUNDARY_TEXT=True）",
              "【起始标记】" not in text_long and "【结束标记】" not in text_long,
              f"实际文本={text_long!r}")
        check("前后文保留", "开头说明。" in text_long and "结尾说明。" in text_long)
        check("long 日志落盘", any(f.startswith("long_") or f.startswith("test_")
              for f in os.listdir(log_dir)))
    except Exception as exc:
        check(f"long 执行异常: {exc}", False)

    print()
    print("=" * 60)
    print("[3b] long：横版素材插入后目标前后文仍为纵向")
    print("=" * 60)
    land_target = os.path.join(src_dir, "横版插入目标.docx")
    make_docx(land_target, [
        "开头说明保持纵向。",
        "【横版起始】",
        "旧的纵向内容。",
        "【横版结束】",
        "结尾说明保持纵向。",
    ])
    land_insert = os.path.join(out_dir, "横版素材.docx")
    make_landscape_docx(land_insert, ["这是横版插入内容。"])
    wb_land = load_workbook(rules_xlsx)
    wb_land["长替换"].append(["【横版起始】", "【横版结束】", land_insert])
    wb_land.save(rules_xlsx)
    wb_land.close()
    try:
        land_rc = rt.cmd_long(logger)
        check("横版插入 long 返回 0", land_rc == 0)
        land_after = Document(land_target)
        land_text = docx_text(land_target)
        check("横版素材文字已插入", "这是横版插入内容。" in land_text)
        check("前后文仍在", "开头说明保持纵向。" in land_text and "结尾说明保持纵向。" in land_text)
        sizes = [(s.page_width, s.page_height, s.orientation) for s in land_after.sections]
        first, last = land_after.sections[0], land_after.sections[-1]
        check(
            "首节仍为纵向（前后文页面设置未被素材污染）",
            not _is_landscape(first),
            f"实际sections={sizes}",
        )
        check(
            "末节仍为纵向（前后文页面设置未被素材污染）",
            not _is_landscape(last),
            f"实际sections={sizes}",
        )
        check(
            "插入后存在横向节（多节素材的方向切换被保留）",
            any(_is_landscape(s) for s in land_after.sections),
            f"实际sections={sizes}",
        )
    except Exception as exc:
        check(f"long 横版插入异常: {exc}", False)

    print()
    print("=" * 60)
    print("[4] 纯函数与边缘路径")
    print("=" * 60)
    check("normalize_cell 空值", rt.normalize_cell(None) == "")
    check("normalize_cell 清洗 nan", rt.normalize_cell("  nan  ") == "")
    check("normalize_cell 去首尾空格", rt.normalize_cell("  词  ") == "词")

    footer_path = os.path.join(src_dir, "页脚文档.docx")
    doc_f = Document()
    doc_f.add_paragraph("页脚将单独命中。")
    doc_f.sections[0].footer.paragraphs[0].text = "页脚：本文件出具日待替换"
    # 再写入一个尚未被 short 处理过的查找词
    doc_f.paragraphs[0].text = "正文无目标。"
    doc_f.sections[0].footer.paragraphs[0].text = "页脚：本募集说明书签署日"
    doc_f.save(footer_path)
    rt.cmd_short(logger)
    footers = [
        p.text
        for s in Document(footer_path).sections
        for p in s.footer.paragraphs
    ]
    check("页脚文字已替换", any("本文件出具日" in t for t in footers), f"实际={footers}")

    upper_dir = os.path.join(src_dir, "case")
    os.makedirs(upper_dir, exist_ok=True)
    upper_path = os.path.join(upper_dir, "UPPER.DOCX")
    make_docx(upper_path, ["本募集说明书签署日应当被替换。"])
    rt.cmd_short(logger)
    check(
        "大写 .DOCX 扩展名也应被 short 处理",
        "本文件出具日" in docx_text(upper_path),
        f"实际={docx_text(upper_path)!r}",
    )

    from toolkit.short_replace import load_short_rules
    from toolkit.long_replace import (
        MAX_WORD_FIND_TEXT_LENGTH,
        load_rules,
        resolve_insert_path,
        split_word_find_text,
    )

    long_find = "甲" * (MAX_WORD_FIND_TEXT_LENGTH + 80)
    chunks = split_word_find_text(long_find)
    check("超长关键字会切成多段", len(chunks) >= 2, f"实际段数={len(chunks)}")
    check("每段不超过 Word Find 上限", all(len(c) <= MAX_WORD_FIND_TEXT_LENGTH for c in chunks))
    check("切分后拼接还原", "".join(chunks) == long_find)
    check("换行转成 Word ^p", "^p" in "".join(split_word_find_text("第一行\n第二行")))

    wb3 = load_workbook(rules_xlsx)
    ws_short = wb3["短替换"]
    ws_short.append(["regex:", "无效"])
    ws_short.append(["", "空查找"])
    ws_long = wb3["长替换"]
    ws_long.append(["只有起始", "", ""])
    wb3.save(rules_xlsx)
    wb3.close()
    short_rules = load_short_rules(rules_xlsx, "短替换")
    check("空正则前缀 regex: 被跳过", "regex:" not in short_rules)
    long_rules = load_rules(rt.config.RULES_XLSX)
    check("缺列的长替换规则被跳过", all(rule.start_text != "只有起始" for rule in long_rules))

    rel = resolve_insert_path("新内容素材")
    check(
        "素材路径省略后缀时自动补 .docx",
        rel.name == "新内容素材.docx",
        f"实际={rel}",
    )

    from make_rules_template import main as make_template_main
    existed = os.path.join(TEST_ROOT, "已存在规则表.xlsx")
    with open(existed, "wb") as f:
        f.write(b"keep")
    old_argv = sys.argv
    try:
        sys.argv = ["make_rules_template.py", existed]
        rc = make_template_main()
    finally:
        sys.argv = old_argv
    check("模板已存在时不覆盖并返回 1", rc == 1)
    check("已存在文件内容未被改写", open(existed, "rb").read() == b"keep")

    fresh = os.path.join(TEST_ROOT, "新规则表.xlsx")
    try:
        sys.argv = ["make_rules_template.py", fresh]
        rc = make_template_main()
    finally:
        sys.argv = old_argv
    check("新路径可生成模板", rc == 0 and os.path.isfile(fresh))
    wb_new = load_workbook(fresh)
    check(
        "模板含三张工作表",
        set(wb_new.sheetnames) == {"填写说明", "短替换", "长替换"},
        f"实际={wb_new.sheetnames}",
    )
    wb_new.close()

    print()
    print("=" * 60)
    print(f"测试完成：通过 {PASS_COUNT} 项，失败 {FAIL_COUNT} 项")
    print(f"沙箱目录: {TEST_ROOT}")
    print("=" * 60)
    sys.exit(1 if FAIL_COUNT else 0)


if __name__ == "__main__":
    main()
