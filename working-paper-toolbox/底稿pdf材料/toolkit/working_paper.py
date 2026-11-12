# -*- coding: utf-8 -*-
"""组B：财务底稿整理（【会计科目底稿整理.py】整体，保持预览/--apply 安全设计）。

    pdf_merge    （原 merge_2362.py / merge 子命令）子文件夹合并→铺平→连贯编号
    flat_rename  （原 rename_57_58_59.py / r5789 子命令）多个文件夹各自平铺/原地重命名
    order_rename （原 rename_pdfs.py / r56 子命令）多固定位置跨目录全局连贯编号

编号计划与执行统一走 toolkit/numbering.py 内核。
"""

import os
import re
import shutil
from pathlib import Path

from .numbering import (
    apply_plan_two_phase,
    assign_numbers,
    check_new_name_conflicts,
    collect_pdf_items,
    collect_tree_pdfs,
    list_top_level_pdfs,
    natural_sort_key,
    remove_empty_subfolders,
    verify_numbering,
)


# =====================================================================
# 组B：pdf_merge —— 子文件夹合并 -> 铺平 -> 连贯编号（原 merge）
# =====================================================================
def cmd_pdf_merge(args, logger):
    import pypdf

    top = Path(args.top)
    prefix = args.prefix
    if not top.is_dir():
        logger.error(f"目标文件夹不存在 → {top}")
        return 1

    do_merge = args.merge or args.all
    do_flatten = args.flatten or args.all
    subs = sorted([d.name for d in top.iterdir() if d.is_dir()])

    # ---------- 预览 ----------
    def print_plan():
        total_pdfs = 0
        merge_names = []
        for i, sub in enumerate(subs, 1):
            sub_dir = top / sub
            pdfs = [p for _, p in collect_tree_pdfs(sub_dir)
                    if p != f"{sub}.pdf"]
            total_pdfs += len(pdfs)
            merge_names.append(f"{sub}.pdf")
            logger.info(f"[{i:>2}] 子文件夹: {sub}（含 {len(pdfs)} 个PDF → {sub}.pdf）")
        root_pdfs = list_top_level_pdfs(top)
        logger.info(f"子文件夹合并件合计 {len(subs)} 个，涉及原 PDF {total_pdfs} 个；"
                    f"根目录独立保留 {len(root_pdfs)} 个。")
        final_names = merge_names + root_pdfs
        final_sorted = sorted(final_names, key=natural_sort_key)
        logger.info(f"铺平重命名计划：{len(final_sorted)} 个PDF → 编号 {prefix}1 ~ {prefix}{len(final_sorted)}（自然排序）")

    if not do_merge and not do_flatten:
        logger.info("========== 预览：合并 + 铺平计划 ==========")
        print_plan()
        logger.info("预览模式：未修改任何文件。加 --merge 执行合并；--flatten 铺平重命名；--all 一步完成。")
        return 0

    # ---------- 阶段一：合并 ----------
    if do_merge:
        logger.info("========== 阶段一：合并 ==========")
        results = []
        for i, sub in enumerate(subs, 1):
            sub_dir = top / sub
            pdf_entries = [
                (src_dir, name)
                for src_dir, name in collect_tree_pdfs(sub_dir)
                if name != f"{sub}.pdf"
            ]
            if not pdf_entries:
                logger.info(f"[{i:>2}] {sub}: 无PDF，跳过")
                continue
            logger.info(f"[{i:>2}] {sub}: 合并 {len(pdf_entries)} 个PDF ...")
            try:
                writer = pypdf.PdfWriter()
                for src_dir, pdf_name in pdf_entries:
                    writer.append(str(src_dir / pdf_name))
                out_path = sub_dir / f"{sub}.pdf"
                with open(out_path, "wb") as f:
                    writer.write(f)
                pages = len(writer.pages)
                writer.close()
                logger.info(f"      完成 → {out_path.name}（{pages} 页）")
                results.append(sub)
            except Exception as e:
                logger.error(f"      失败: {e}")
                return 1
        logger.info(f"合并完成：{len(results)} 个合并件。请人工核对后再执行铺平（--flatten）。")
        if not do_flatten:
            return 0

    # ---------- 阶段二：铺平+编号 ----------
    logger.info("========== 阶段二：铺平+重命名 ==========")
    subs = sorted([d.name for d in top.iterdir() if d.is_dir()])
    missing_merges = []
    for sub in subs:
        sub_dir = top / sub
        merge_path = sub_dir / f"{sub}.pdf"
        others = [
            name for _, name in collect_tree_pdfs(sub_dir) if name != f"{sub}.pdf"
        ]
        if others and not merge_path.exists():
            missing_merges.append(sub)
    if missing_merges:
        logger.error(
            "以下子文件夹缺少合并件，已拒绝铺平以免删除原始 PDF："
            f"{missing_merges}。请先加 --merge 完成合并并核对。"
        )
        return 1
    for sub in subs:
        sub_dir = top / sub
        merge_name = f"{sub}.pdf"
        removed = 0
        for src_dir, name in collect_tree_pdfs(sub_dir):
            if name != merge_name:
                os.remove(src_dir / name)
                removed += 1
        if removed:
            logger.info(f"  {sub}: 已清理原始 PDF {removed} 个")
    for sub in subs:
        merge_path = top / sub / f"{sub}.pdf"
        dst = top / f"{sub}.pdf"
        if merge_path.exists():
            shutil.move(str(merge_path), str(dst))
            logger.info(f"  {sub}.pdf → 顶级")
    removed_dirs = remove_empty_subfolders(top, logger)
    logger.info(f"共删除 {removed_dirs} 个空子文件夹。")

    # 编号：改用统一编号内核的自然排序（修复原字典序把 10 排在 2 前的问题）
    items = [{"dir": top, "name": n, "path": top / n,
              "top": top, "move": False}
             for n in list_top_level_pdfs(top)]
    items.sort(key=lambda x: natural_sort_key(x["name"]))
    plan = assign_numbers(items, prefix)
    conflicts = check_new_name_conflicts(plan)
    if conflicts:
        for msg in conflicts:
            logger.error(msg)
        return 1

    logger.info("铺平重命名计划：")
    for item in plan:
        logger.info(f"  [{item['num']:>2}] {item['name']} → {item['new_name']}")

    if not apply_plan_two_phase(plan, logger):
        return 1

    logger.info("===== 核验 =====")
    ok = verify_numbering(top, prefix, logger)
    return 0 if ok else 1


# =====================================================================
# 组B：flat_rename —— 多个文件夹各自平铺/原地重命名（原 r5789）
# =====================================================================
def parse_folder_spec(spec: str):
    """
    解析 --folders 参数："目录名[:flat],..."（逗号分隔）。
    :flat 表示该目录递归收集并平铺到顶级；缺省仅处理顶级文件。
    """
    entries = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part and part.rsplit(":", 1)[1].strip().lower() in ("flat", "keep"):
            name, mode = part.rsplit(":", 1)
            entries.append((name.strip(), mode.strip().lower() == "flat"))
        else:
            entries.append((part, False))
    return entries


def run_flat_rename(parent: Path, folder_spec, apply: bool, logger):
    groups = []  # [(prefix, top, flatten)]
    for dirname, flatten in folder_spec:
        top = parent / dirname
        if not top.is_dir():
            logger.error(f"目标文件夹不存在 → {top}")
            return 1
        base_prefix = dirname.split()[0] if " " in dirname else dirname
        prefix = base_prefix if base_prefix.endswith("-") else base_prefix + "-"
        groups.append((prefix, top, flatten))

    plans = {}
    for prefix, top, flatten in groups:
        locations = [top]
        flags = {0: flatten}
        items = collect_pdf_items(locations, flatten_flags=flags, sort_mode="natural")
        plan = assign_numbers(items, prefix)
        # 平铺时目标位置为顶级
        for item in plan:
            item["target_dir"] = top
        plans[prefix] = (top, flatten, plan)

    # 冲突检查：新名不得重复、不得与顶级现有文件重名（源自身除外）
    for prefix, (top, flatten, plan) in plans.items():
        seen = set()
        existing = set(os.listdir(top))
        for item in plan:
            if item["new_name"] in seen:
                logger.error(f"错误：新文件名重复 → {item['new_name']}（于 {top}）")
                return 1
            seen.add(item["new_name"])
            if item["new_name"] in existing and \
                    str(top / item["new_name"]) != str(item["path"]):
                logger.error(f"错误：目标已存在 → {top / item['new_name']}")
                return 1

    # 预览输出
    total = sum(len(p) for _, (_, _, p) in plans.items())
    logger.info(f"共 {total} 个 PDF 文件。")
    for prefix, (top, flatten, plan) in plans.items():
        mode = "（平铺+重命名）" if flatten else "（原地重命名）"
        logger.info(f"===== {prefix} {top.name} {mode} =====")
        for item in plan:
            rel = os.path.relpath(item["dir"], top) if item["dir"] != top else "（顶级）"
            logger.info(f"  位置: {rel}")
            logger.info(f"  旧: {item['name']}")
            logger.info(f"  新: {item['new_name']}")

    if not apply:
        logger.info("预览模式：未修改任何文件。确认无误后加 --apply 执行。")
        return 0

    # 执行（flatten 也走两阶段：move=True 的项第二阶段移到顶级）
    logger.info("开始执行……")
    for prefix, top, flatten, plan in [(p, t, f, pl) for p, (t, f, pl) in plans.items()]:
        if not apply_plan_two_phase(plan, logger):
            return 1

    logger.info("清理空子文件夹……")
    removed_total = 0
    for prefix, top, flatten in groups:
        if flatten:
            removed_total += remove_empty_subfolders(top, logger)
    if removed_total == 0:
        logger.info("（无空子文件夹可删除）")

    logger.info("===== 核验 =====")
    all_ok = True
    for prefix, top, flatten in groups:
        all_ok = verify_numbering(top, prefix, logger) and all_ok
    return 0 if all_ok else 1


# =====================================================================
# 组B：order_rename —— 多个固定位置的 PDF 跨位置全局连贯编号（原 r56）
# =====================================================================
def run_order_rename(locations, prefix: str, apply: bool, logger):
    resolved = []
    for loc in locations:
        p = Path(loc)
        if not p.is_dir():
            logger.error(f"位置不存在 → {p}")
            return 1
        resolved.append(p)

    items = collect_pdf_items(resolved, sort_mode="given")  # 位置顺序即编号顺序；位置内自然排序
    plan = assign_numbers(items, prefix)

    if not plan:
        logger.error("未找到任何 PDF 文件，退出。")
        return 1

    new_names = set()
    for item in plan:
        if item["new_name"] in new_names:
            logger.error(f"错误：新文件名重复 → {item['new_name']}")
            return 1
        new_names.add(item["new_name"])

    cur_label = None
    logger.info(f"共 {len(plan)} 个 PDF 文件，编号 1-{len(plan)}。")
    for item in plan:
        if item["dir"] != cur_label:
            cur_label = item["dir"]
            logger.info(f"===== 目标文件夹: {cur_label} =====")
        logger.info(f"  旧: {item['name']}")
        logger.info(f"  新: {item['new_name']}")

    # 冲突检查：新名不得与所在目录现有文件重名（源自身除外）
    for item in plan:
        target_path = item["dir"] / item["new_name"]
        if target_path.exists() and str(target_path) != str(item["path"]):
            logger.error(f"错误：目标已存在 → {target_path}")
            return 1

    if not apply:
        logger.info("预览模式：未修改任何文件。确认无误后加 --apply 执行。")
        return 0

    logger.info("开始重命名……")
    if not apply_plan_two_phase(plan, logger):
        return 1

    logger.info("===== 核验 =====")
    nums = sorted(item["num"] for item in plan)
    ok = nums == list(range(1, len(plan) + 1))
    logger.info(f"编号 1-{len(plan)} 连贯：{ok}")
    return 0 if ok else 1
