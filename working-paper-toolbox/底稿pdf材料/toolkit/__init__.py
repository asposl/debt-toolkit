# -*- coding: utf-8 -*-
"""债承文件整理工具箱子包（由原单文件 file_toolkit.py 按原始脚本边界拆分）。

模块对照：
    logutil.py       日志工具
    numbering.py     编号内核：收集 -> 排序 -> 赋前缀编号 -> 两阶段重命名 -> 核验
    imaging.py       图片转 PDF（convert.ipynb 血缘，dedup 与 convert_images 共用）
    dedup.py         【organize_toolkit·dedup_folders】编号子文件夹哈希去重并复制
    ledger_match.py  【organize_toolkit·match_excel】台账六字段匹配加 num 列
    ledger_merge.py  【organize_toolkit·merge_pdfs】按 num 定位文件夹按特征优先级合并
    working_paper.py 【会计科目底稿整理.py 整体】pdf_merge / flat_rename / order_rename
    renumber.py      【有息负债-担保重命名.ipynb 单元1】重新连贯编号

约定：所有涉及改名的命令默认【预览模式】；两阶段临时名协议原样保留，
三套实现（内核版/renumber 时间戳版/flat 单步版）不做合并。
"""
