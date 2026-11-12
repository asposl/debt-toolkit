# -*- coding: utf-8 -*-
"""组A：match_excel —— 台账六字段匹配，给 Sheet1 加 num 列（organize_toolkit 血缘）。"""

from pathlib import Path

import pandas as pd

DEFAULT_MATCH_COLS = ["贷款机构", "借款单位", "余额", "借款日", "到期日", "利率"]
_BLANK_TOKENS = frozenset({"", "nan", "none", "<na>", "nat"})


def _normalize_match_col(series: pd.Series) -> pd.Series:
    """匹配用文本：去空白、整数值浮点去 .0、真正的空值保持 NA（避免 'nan' 互配）。

    必须先转成文本再解析数字，避免 datetime 列被 to_numeric 收成时间戳整数。
    """
    as_text = series.astype("string").str.strip()
    numeric = pd.to_numeric(as_text, errors="coerce")
    is_whole = numeric.notna() & (numeric == numeric.round())
    whole_text = numeric.round().astype("Int64").astype("string")
    result = as_text.mask(is_whole, whole_text)
    invalid = result.isna() | result.str.lower().isin(_BLANK_TOKENS)
    return result.mask(invalid)


def _non_matching_na_key(frame: pd.DataFrame, cols: list[str], prefix: str) -> pd.Series:
    """拼匹配键；任一带 NA 的行用唯一哨兵，避免 pandas 3 merge 把空值互配。"""
    parts = frame.loc[:, cols].astype("string")
    blocked = parts.isna().any(axis=1)
    filled = parts.fillna("")
    key = filled[cols[0]]
    for col in cols[1:]:
        key = key + "\x1f" + filled[col]
    unique = prefix + pd.Series(range(len(frame)), index=frame.index).astype("string")
    return key.mask(blocked, unique)


def cmd_match_excel(args, logger):
    excel_path = Path(args.excel)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not excel_path.exists():
        logger.error(f"找不到 Excel 文件：{excel_path}")
        return 1

    cols = [c.strip() for c in args.cols.split(",")] if args.cols else list(DEFAULT_MATCH_COLS)

    try:
        df1 = pd.read_excel(excel_path, sheet_name=args.sheet1)
        df2 = pd.read_excel(excel_path, sheet_name=args.sheet2)
    except Exception as e:
        logger.error(f"读取 Excel 失败: {e}")
        return 1

    missing = [c for c in cols + ["序号"] if c not in df2.columns]
    if missing:
        logger.error(f"Sheet2 缺少匹配所需列: {missing}（当前列：{list(df2.columns)}）")
        return 1
    missing = [c for c in cols if c not in df1.columns]
    if missing:
        logger.error(f"Sheet1 缺少匹配所需列: {missing}（当前列：{list(df1.columns)}）")
        return 1

    # 标准化处理：去空白、整数值统一成无小数文本；空值保持 NA，避免双方 "nan" 误匹配
    for col in cols:
        df1[col] = _normalize_match_col(df1[col])
        df2[col] = _normalize_match_col(df2[col])

    # 步骤 A：以 Sheet2 的序号为基准，给 Sheet1 加上 num 列。
    # 空值行用唯一键，pandas 3 默认会把 NA 键互配。
    df1_key = _non_matching_na_key(df1, cols, "L#")
    df2_key = _non_matching_na_key(df2, cols, "R#")
    result_sheet1 = (
        df1.assign(_match_key=df1_key)
        .merge(
            df2.assign(_match_key=df2_key, num=df2["序号"])[["_match_key", "num"]],
            on="_match_key",
            how="left",
        )
        .drop(columns="_match_key")
    )

    result_xlsx = output_dir / "匹配结果_已添加num.xlsx"
    with pd.ExcelWriter(result_xlsx) as writer:
        result_sheet1.to_excel(writer, sheet_name="sheet1", index=False)
    logger.info(f"[已生成] {result_xlsx}")

    # 步骤 B：找出 Sheet2 中有、但 Sheet1 中没有的数据（反向关联打标记）
    not_matched_df2 = (
        df2.assign(_match_key=df2_key)
        .merge(
            df1.assign(_match_key=df1_key, in_sheet1=True)[["_match_key", "in_sheet1"]],
            on="_match_key",
            how="left",
        )
        .drop(columns="_match_key")
    )
    not_matched_csv_df = (
        not_matched_df2[not_matched_df2["in_sheet1"].isna()]
        .drop(columns=["in_sheet1"])
    )

    unmatched_csv = output_dir / "sheet2特有_未匹配数据.csv"
    not_matched_csv_df.to_csv(unmatched_csv, index=False, encoding="utf-8-sig")
    logger.info(f"[已生成] {unmatched_csv}")

    matched_count = int(result_sheet1["num"].notna().sum())
    logger.info(
        f"匹配完成：Sheet1 共 {len(df1)} 行，成功关联 num 列 {matched_count} 行；"
        f"Sheet2 特有（未匹配）{len(not_matched_csv_df)} 行。"
    )
    return 0
