# -*- coding: utf-8 -*-
"""【原 输出签章页.py】export —— Word→PDF 全量导出、按公司名拆末页合并签章页、生成清单。

本文件为原始脚本的整块平移：四阶段流程（缩路径改名 → Word COM 全量导出 →
拆末页合并 → 清单/日志输出）保持完整，不做内部拆分。
pywincom/pypdf 仅在本模块导入（export 是唯一需要 pywin32 的子命令）。

产物契约（供下游 filter / insert 免改配置直连）：
    logs/has_company_latest.json、logs/no_company_latest.json 固定名副本
"""

import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import pythoncom
from pypdf import PdfReader, PdfWriter
from win32com.client import DispatchEx

from . import config
from .logutil import _log_path

# 中文数字到阿拉伯数字的映射表（一~二十）
_CHINESE_NUM_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
}

# 按长度降序排列的中文数字列表，用于优先匹配"十一"等双字节数字
_CHINESE_NUM_SORTED = sorted(_CHINESE_NUM_MAP.keys(), key=len, reverse=True)


def _replace_chinese_ordinals(s):
    """
    将字符串中的中文序号模式（如"第一章"、"第三章"、"第七节"等）
    替换为零填充的数字序号，以便自然排序能正确比较。
    例如："第一章$xxx" -> "00001章$xxx"
    """
    def _replacer(m):
        cn_num = m.group(1)
        if cn_num in _CHINESE_NUM_MAP:
            return f"{_CHINESE_NUM_MAP[cn_num]:05d}"
        return m.group(0)

    pattern = r'第(' + '|'.join(_CHINESE_NUM_SORTED) + r')'
    return re.sub(pattern, _replacer, s)


def natural_sort_key(s):
    """
    自然排序核心算法：
    1. 先将中文序号（如"第一章"）转换为数字序号
    2. 再将字符串中的阿拉伯数字转化为整数进行比较
    """
    s_converted = _replace_chinese_ordinals(s)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s_converted)]


def can_reuse_recent_pdf(docx_path, pdf_path, max_age_days=None):
    """判断现有 PDF 是否足够新，可以跳过 Word 重复导出。"""
    if max_age_days is None:
        max_age_days = config.EXPORT_RECENT_PDF_MAX_AGE_DAYS
    if max_age_days is None or max_age_days <= 0:
        return False

    try:
        if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) <= 0:
            return False

        pdf_mtime = os.path.getmtime(pdf_path)
        docx_mtime = os.path.getmtime(docx_path)
    except OSError:
        return False

    max_age_seconds = max_age_days * 24 * 60 * 60
    pdf_age_seconds = max(0, time.time() - pdf_mtime)

    # PDF 必须在有效期内，并且不能比源 Word 更旧。
    return pdf_age_seconds <= max_age_seconds and pdf_mtime >= docx_mtime


def extract_serial_name(filename, fallback_index):
    """
    从文件名中提取开头的序号前缀（如 "2-3-6-1"），生成短名：序号.docx
    若没有开头数字，则回退为 doc_<序号>.docx
    """
    m = re.match(r'^(\d+(?:-\d+)*)', filename)
    if m:
        serial = m.group(1)
        return f"{serial}.docx"
    return f"doc_{fallback_index}.docx"


def auto_shorten_long_paths(root_folder, limit=None):
    """
    阶段零：遍历目录，仅对全路径长度超过 limit 的 .docx 文件就地改名（只保留序号）。
    其余文件名保持不变。返回被缩短的文件改名清单。
    """
    if limit is None:
        limit = config.EXPORT_PATH_LENGTH_LIMIT
    shortened_count = 0
    renamed_files = []  # 记录 [原名, 新名] 的改名清单
    fallback_idx = 0
    for root, dirs, files in os.walk(root_folder):
        for filename in files:
            if not filename.lower().endswith('.docx') or filename.startswith('~$'):
                continue
            docx_path = os.path.abspath(os.path.join(root, filename))
            if len(docx_path) <= limit:
                continue
            # 超限：生成短名，防冲突
            fallback_idx += 1
            short_name = extract_serial_name(filename, fallback_idx)
            short_path = os.path.join(root, short_name)
            counter = 2
            while os.path.exists(short_path):
                name_base, name_ext = os.path.splitext(short_name)
                short_path = os.path.join(root, f"{name_base}_{counter}{name_ext}")
                counter += 1
            try:
                os.rename(docx_path, short_path)
                shortened_count += 1
                renamed_files.append((filename, os.path.basename(short_path)))
                print(f"✂️ [路径过长改名] {filename} -> {os.path.basename(short_path)}")
            except Exception as e:
                print(f"❌ 改名失败 {filename}: {e}")
    print(f"📢 阶段零完成：共缩短 {shortened_count} 个超长路径文件。\n")
    return renamed_files


def split_and_catalog_pdfs(root_folder, generated_pdfs, company_keyword):
    """阶段二+三：自然排序、按末尾关键字拆签章页、写 JSON 清单。

    不启动 Word，便于用现成 PDF 做沙箱测试。返回 has/no 清单与签章页路径。
    """
    pdf_paths = list(generated_pdfs)
    pdf_paths.sort(key=lambda x: natural_sort_key(os.path.relpath(x, root_folder)))

    has_company_list = []
    no_company_list = []
    single_page_list = []   # 末尾含公司名但仅 1 页：无法拆分，原样保留（不计入上面两表）
    failed_list = []        # 读取/解析失败：同样不计入上面两表
    global_merged_writer = PdfWriter()

    print("\n📢 阶段二：对生成文件进行自然排序，并开始进行文本识别...")

    for pdf_path in pdf_paths:
        rel_pdf_path = os.path.relpath(pdf_path, root_folder).replace("\\", "/")
        filename = os.path.basename(pdf_path)

        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() or ""

            cleaned_text = full_text.rstrip()
            tail_chars = cleaned_text[-150:]
            tail_stripped = re.sub(r'\s+', '', tail_chars)

            if company_keyword in tail_stripped:
                if total_pages > 1:
                    last_page = reader.pages[total_pages - 1]
                    global_merged_writer.add_page(last_page)

                    local_writer = PdfWriter()
                    for page_num in range(total_pages - 1):
                        local_writer.add_page(reader.pages[page_num])
                    with open(pdf_path, "wb") as f:
                        local_writer.write(f)
                    print(
                        f"  ✂️ {filename} -> [拆出末页] 末尾存在‘{company_keyword}’，"
                        f"已拆出末页并入签章页（{total_pages}页 -> {total_pages-1}页）"
                    )
                else:
                    print(f"  ⏭️ {filename} -> [跳过] 末尾有‘{company_keyword}’但文件仅 1 页，已跳过")
                    single_page_list.append(rel_pdf_path)
                    continue

                has_company_list.append(rel_pdf_path)
            else:
                no_company_list.append(rel_pdf_path)
                print(f"  ✅ {filename} -> [直接输出] 末尾未检测到‘{company_keyword}’，保持原样")

        except Exception as e:
            print(f"  ❌ 处理 PDF 失败 {filename}: {e}")
            failed_list.append(rel_pdf_path)

    print("\n⚖️ 阶段三：正在输出最终文件及 JSON 日志...")

    merged_pdf_path = None
    if len(global_merged_writer.pages) > 0:
        merged_pdf_path = os.path.join(root_folder, config.EXPORT_MERGED_PDF_NAME)
        with open(merged_pdf_path, "wb") as f:
            global_merged_writer.write(f)
        print(f"💾 签章页合并完成！输出至: {merged_pdf_path}")
    else:
        print(f"ℹ️ 没有发现任何含有‘{company_keyword}’的文件，未生成签章页 PDF。")

    json_has_path = _log_path("has_company", ".json")
    json_no_path = _log_path("no_company", ".json")

    with open(json_has_path, 'w', encoding='utf-8') as f:
        json.dump(has_company_list, f, ensure_ascii=False, indent=4)

    with open(json_no_path, 'w', encoding='utf-8') as f:
        json.dump(no_company_list, f, ensure_ascii=False, indent=4)

    json_has_latest = os.path.join(config.LOG_DIR, "has_company_latest.json")
    json_no_latest = os.path.join(config.LOG_DIR, "no_company_latest.json")
    for src, dst in ((json_has_path, json_has_latest), (json_no_path, json_no_latest)):
        with open(src, "r", encoding='utf-8') as f_in, open(dst, "w", encoding="utf-8") as f_out:
            f_out.write(f_in.read())

    print(f"\n🎉 拆页合并任务完成！")
    print(f"0️⃣ 参与拆分的 PDF 总数: {len(pdf_paths)} 个")
    print(f"1️⃣ 含‘{company_keyword}’（已拆出末页并入签章页）: {len(has_company_list)} 个 -> {json_has_path}")
    print(f"2️⃣ 未含‘{company_keyword}’（原样直接输出）: {len(no_company_list)} 个 -> {json_no_path}")
    if single_page_list:
        print(f"3️⃣ 含‘{company_keyword}’但仅 1 页（末页即签章页，无法拆分，原样保留）: "
              f"{len(single_page_list)} 个")
    if failed_list:
        print(f"4️⃣ 读取/解析失败（未计入任何清单）: {len(failed_list)} 个")
    accounted = (len(has_company_list) + len(no_company_list)
                 + len(single_page_list) + len(failed_list))
    print(f"✅ 对账: {len(has_company_list)}(拆) + {len(no_company_list)}(未拆) "
          f"+ {len(single_page_list)}(单页跳过) + {len(failed_list)}(失败) "
          f"= {accounted} / 总数 {len(pdf_paths)}")

    return {
        "has_company_list": has_company_list,
        "no_company_list": no_company_list,
        "single_page_list": single_page_list,
        "failed_list": failed_list,
        "merged_pdf_path": merged_pdf_path,
        "json_has_path": json_has_path,
        "json_no_path": json_no_path,
        "sorted_pdfs": pdf_paths,
    }


def cmd_export(logger):
    """Word→PDF 全量导出、按公司名拆末页合并签章页、生成 has/no_company 清单。"""
    root_folder = config.EXPORT_ROOT_FOLDER
    company_keyword = config.EXPORT_COMPANY_KEYWORD

    if not os.path.exists(root_folder):
        logger.error(f"找不到指定的根文件夹：{root_folder}")
        return 1

    # 阶段零：自动缩短超长路径的 docx 文件名（仅保留序号）
    print("📢 阶段零：检测并缩短超长路径的文件名...")
    logger.info("阶段零：检测并缩短超长路径的文件名")

    initial_docx_files = []
    for root, dirs, files in os.walk(root_folder):
        for filename in files:
            if filename.lower().endswith('.docx') and not filename.startswith('~$'):
                initial_docx_files.append(filename)
    print(f"📂 最初读取到的 docx 文件数量: {len(initial_docx_files)}")
    # 同步写日志：只看日志文件时也能判断规模（界面输出不会落在日志文件里）
    logger.info(f"最初读取到的 docx 文件数量: {len(initial_docx_files)}")

    renamed_files = auto_shorten_long_paths(root_folder)
    if renamed_files:
        for old_name, new_name in renamed_files:
            logger.info(f"[路径过长改名] {old_name} -> {new_name}")
    logger.info(f"阶段零完成：共缩短 {len(renamed_files)} 个超长路径文件")

    generated_pdfs = []

    # 阶段一：让 Word 进行 100% 安全的全量 PDF 导出
    print("📢 阶段一：启动 Word 引擎进行全量高保真 PDF 导出...")
    logger.info("阶段一：启动 Word 引擎进行全量高保真 PDF 导出")
    pythoncom.CoInitialize()
    word_app = None
    wd_export_format_pdf = 17
    wd_export_all_document = 0

    try:
        word_app = DispatchEx("Word.Application")
        word_app.Visible = False
        word_app.DisplayAlerts = 0
        word_app.Options.PrintBackground = False  # 同步打印，确保文件生成完整

        exported = reused = 0
        for root, dirs, files in os.walk(root_folder):
            for filename in files:
                if filename.lower().endswith('.docx') and not filename.startswith('~$'):
                    docx_path = os.path.abspath(os.path.join(root, filename))
                    pdf_path = os.path.splitext(docx_path)[0] + ".pdf"

                    if can_reuse_recent_pdf(docx_path, pdf_path):
                        pdf_age_hours = max(
                            0,
                            (time.time() - os.path.getmtime(pdf_path)) / 3600,
                        )
                        reused += 1
                        print(f"♻️ 复用最近 PDF（{pdf_age_hours:.1f} 小时前生成）: {filename}")
                        # 逐个文件进度写入日志：Word 导出很慢，否则日志会长时间
                        # 停在「阶段一」一行，看起来像卡死，也定位不到卡在哪个文件
                        logger.info(f"复用最近 PDF（{pdf_age_hours:.1f} 小时前）: {filename}")
                        generated_pdfs.append(pdf_path)
                        continue

                    exported += 1
                    print(f"📄 正在全量导出 [{exported}/{len(initial_docx_files)}]: {filename}")
                    logger.info(f"正在导出 [{exported}/{len(initial_docx_files)}]: {filename}")
                    doc = word_app.Documents.Open(docx_path, ReadOnly=True)
                    doc.ExportAsFixedFormat(
                        pdf_path, wd_export_format_pdf, False, 0, wd_export_all_document
                    )
                    doc.Close(False)
                    logger.info(f"  已导出: {os.path.basename(pdf_path)}")

                    generated_pdfs.append(pdf_path)
        logger.info(f"阶段一完成：新导出 {exported} 个、复用旧 PDF {reused} 个")
    except Exception as e:
        logger.error(f"Word 导出阶段发生错误: {e}")
        print(f"❌ Word 导出阶段发生错误: {e}")
        return 1
    finally:
        if word_app is not None:
            try:
                word_app.Quit()
            except Exception:
                pass
            print("🔒 Word 后台引擎已安全关闭。")
            logger.info("Word 后台引擎已关闭")
        pythoncom.CoUninitialize()

    catalog = split_and_catalog_pdfs(root_folder, generated_pdfs, company_keyword)
    has_company_list = catalog["has_company_list"]
    no_company_list = catalog["no_company_list"]
    single_page_list = catalog["single_page_list"]
    failed_list = catalog["failed_list"]
    logger.info(
        f"has_company 清单（{len(has_company_list)} 条）-> {catalog['json_has_path']}"
    )
    logger.info(
        f"no_company 清单（{len(no_company_list)} 条）-> {catalog['json_no_path']}"
    )
    logger.info(
        f"对账: 拆出末页 {len(has_company_list)} + 未拆 {len(no_company_list)}"
        f" + 单页跳过 {len(single_page_list)} + 失败 {len(failed_list)}"
        f" = 参与拆分总数 {len(generated_pdfs)}"
    )

    # 阶段四：写入全流程处理日志（logs/ 目录）
    log_file = _log_path("processing_log")
    with open(log_file, 'w', encoding='utf-8') as log:
        log.write("=" * 60 + "\n")
        log.write("全流程处理日志\n")
        log.write("=" * 60 + "\n\n")

        log.write(f"【1】最初读取的 docx 文件（共 {len(initial_docx_files)} 个）:\n")
        for name in initial_docx_files:
            log.write(f"  - {name}\n")
        log.write("\n")

        log.write(f"【2】被修改名称的 docx 文件（共 {len(renamed_files)} 个）:\n")
        for old_name, new_name in renamed_files:
            log.write(f"  - {old_name} -> {new_name}\n")
        log.write("\n")

        log.write(f"【3】被拆出末页并入签章页的文件（共 {len(has_company_list)} 个）:\n")
        for path in has_company_list:
            log.write(f"  - {path}\n")
        log.write("\n")

        log.write(f"【4】未被拆出末页的文件（共 {len(no_company_list)} 个）:\n")
        for path in no_company_list:
            log.write(f"  - {path}\n")
        log.write("\n")

        log.write(f"【5】末页即签章页、仅 1 页无法拆分的文件（共 {len(single_page_list)} 个，"
                  "原样保留，不参与⑤追加/⑥替换）:\n")
        for path in single_page_list:
            log.write(f"  - {path}\n")
        log.write("\n")

        log.write(f"【6】读取/解析失败的文件（共 {len(failed_list)} 个，未计入任何清单）:\n")
        for path in failed_list:
            log.write(f"  - {path}\n")
        log.write("\n" + "=" * 60 + "\n")

    logger.info(f"详细日志已输出至: {log_file}")
    print(f"📝 详细日志已输出至: {log_file}")
    return 0
