# -*- coding: utf-8 -*-
"""组A：merge_pdfs —— 按 num 编号定位文件夹并按特征优先级合并（organize_toolkit 血缘）。

数据管道关系：读取 match_excel 输出的「匹配结果_已添加num.xlsx」。
"""

import json
import os
import re
from pathlib import Path

import pandas as pd
from pypdf import PdfWriter

DEFAULT_FEATURES_PRIORITY = [
    # 1. 合同类顺序
    "流动资金贷款合同", "最高额借款合同", "借款合同", "贷款合同", "流贷", "固贷", "借字", "委贷协议",
    # 2. 担保类顺序
    "最高额保证合同", "保证合同", "连带责任保证书", "委保合同", "委托保证合同", "反担保合同", "保字",
    # 3. 决议类顺序
    "股东", "董事", "决议", "股决", "董决",
    # 4. 借据类
    "借据",
]


def parse_num_range(num_str):
    """解析 num 列的编号，支持 '3-6' 范围或单个数字（含 '5.0' 形式）。"""
    num_str = str(num_str).strip()
    if not num_str or num_str == "nan":
        return []
    match_range = re.match(r"^(\d+)-(\d+)$", num_str)
    if match_range:
        start, end = map(int, match_range.groups())
        return list(range(start, end + 1))
    match_single = re.match(r"^(\d+)(\.0)?$", num_str)
    if match_single:
        return [int(match_single.group(1))]
    return []


# 只认名称开头的编号：'5 …' / '99-100 …'。
# '2-3-5-7 固定资产' 这种多段索引不是有息负债范围，不能拆成 2-3 去误匹配。
_LEADING_RANGE = re.compile(r"^(\d+)-(\d+)(?=[^\d-]|$)")
_LEADING_SINGLE = re.compile(r"^(\d+)(?=[^\d-]|$)")


def leading_folder_nums(folder_name: str) -> list[int]:
    """返回文件夹名开头编号覆盖的整数列表；无法识别则空列表。"""
    range_match = _LEADING_RANGE.match(folder_name)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))
    single = _LEADING_SINGLE.match(folder_name)
    if single:
        return [int(single.group(1))]
    return []


def get_folder_by_num(base_dir: Path, target_num: int):
    """在根目录下寻找名称开头编号等于（或范围覆盖）target_num 的文件夹。"""
    for folder_name in os.listdir(base_dir):
        folder_path = base_dir / folder_name
        if not folder_path.is_dir():
            continue
        if target_num in leading_folder_nums(folder_name):
            return folder_path, folder_name
    return None, None


def match_priority(filename: str, features_list):
    """返回文件名命中的特征在优先级列表中的索引；未命中返回无穷大。"""
    for index, feature in enumerate(features_list):
        if feature in filename:
            return index
    return float("inf")


def format_xuhao(xuhao) -> str:
    """序号规范化：Excel 读出的 7.0 这类整数值浮点转成 '7'。"""
    if isinstance(xuhao, float) and xuhao.is_integer():
        return str(int(xuhao))
    return str(xuhao)


def load_features(path: str | None):
    """--features 指定 JSON 文件时读取自定义特征表，否则用内置默认值。"""
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_FEATURES_PRIORITY


def cmd_merge_pdfs(args, logger):
    excel_path = Path(args.excel)
    source_folders_dir = Path(args.folders)
    output_dir = Path(args.output)
    features = load_features(args.features)

    if not excel_path.exists():
        logger.error(f"找不到 Excel 结果表：{excel_path}")
        return 1
    if not source_folders_dir.exists():
        logger.error(f"找不到文件夹根目录：{source_folders_dir}")
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_excel(excel_path, sheet_name=args.sheet)
    except Exception as e:
        logger.error(f"读取 Excel 失败: {e}")
        return 1

    all_physical_folders = {
        f for f in os.listdir(source_folders_dir)
        if (source_folders_dir / f).is_dir()
    }
    used_physical_folders = set()
    merged_count = skipped_count = 0

    for idx, row in df.iterrows():
        num_val = row.get("num")
        xuhao = row.get("序号")
        subject = row.get("核算科目", "")
        bank = row.get("贷款机构", "")
        company = row.get("借款单位", "")
        balance = row.get("余额", 0)

        try:
            balance_wan = float(balance) / 10000
        except (TypeError, ValueError):
            balance_wan = 0.0

        output_filename = (
            f"{format_xuhao(xuhao)} {subject} {bank} {company} {balance_wan:.2f}万元.pdf"
        )
        output_filename = re.sub(r'[\\/:*?"<>|]', "_", output_filename)

        nums_to_check = parse_num_range(num_val)
        if not nums_to_check:
            continue

        folder_path, folder_name = None, None
        for n in nums_to_check:
            folder_path, folder_name = get_folder_by_num(source_folders_dir, n)
            if folder_path:
                break

        if not folder_path:
            logger.error(
                f"Excel 第 {idx + 2} 行: num列编号 [{num_val}] 在本地找不到对应的实体文件夹"
            )
            skipped_count += 1
            continue

        used_physical_folders.add(folder_name)

        all_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
        if not all_files:
            logger.error(f"文件夹 [{folder_name}] (对应编号:{num_val}) 内没有任何 PDF 文件")
            skipped_count += 1
            continue

        matched_files_with_priority = []
        unmatched_files = []
        for fname in all_files:
            priority = match_priority(fname, features)
            if priority != float("inf"):
                matched_files_with_priority.append((priority, fname))
            else:
                unmatched_files.append(fname)

        # 文件夹中的文件没有全部匹配到特征时放弃合并，避免漏件
        if unmatched_files:
            logger.error(
                f"文件夹 [{folder_name}] 放弃合并！原因：部分文件未匹配到指定特征。"
                f"未用到文件: {unmatched_files}"
            )
            skipped_count += 1
            continue

        # 稳定排序：同特征 PDF 保持原有读入顺序
        matched_files_with_priority.sort(key=lambda x: x[0])
        sorted_files = [x[1] for x in matched_files_with_priority]

        try:
            writer = PdfWriter()
            for fname in sorted_files:
                writer.append(str(folder_path / fname))
            target_pdf_path = output_dir / output_filename
            with open(target_pdf_path, "wb") as f_out:
                writer.write(f_out)
            merged_count += 1
            logger.info(f"成功合并文件夹 [{folder_name}] -> 生成文件 [{output_filename}]")
        except Exception as e:
            logger.error(f"文件夹 [{folder_name}] 在执行 PDF 合并写入时发生错误: {e}")
            skipped_count += 1

    unused_folders = all_physical_folders - used_physical_folders
    if unused_folders:
        logger.warning(
            f"【从未使用的文件夹提示】以下本地物理文件夹在 Excel 中未被关联或使用: "
            f"{sorted(unused_folders)}"
        )

    logger.info("==================== 合并任务完成 ====================")
    logger.info(f"成功合并 {merged_count} 份，跳过 {skipped_count} 份。输出位置：{output_dir}")
    if merged_count == 0 and skipped_count > 0:
        logger.error("没有任何文件成功合并。")
        return 1
    return 0
