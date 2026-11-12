# -*- coding: utf-8 -*-
"""债承 PDF/docx 处理工具箱子包（由原单文件 pdf_toolkit.py 按原始脚本边界拆分）。

模块对照：
    config.py         公共配置常量（原「公共配置」区；测试经 config.X 覆盖）
    logutil.py        日志工具（_timestamp/_ensure_log_dir/_resolve_input/_log_path/setup_logger）
    format_word.py    【原 宋体Arial.py】format —— 批量刷新 docx 格式（python-docx）
    header_fix.py     【原 页眉检查.py】header —— 检查并修复 docx 页眉编号（OOXML 整块平移）
    export_sign.py    【原 输出签章页.py】export —— Word→PDF 导出、拆末页合并签章页
    filter_index.py   【原 check_sign.py】filter + 清单读取工具（供 insert 共用）
    insert_pages.py   【原 插入签章页.py + 插入签字页.py】insert append/replace

重要约定：
    1. 业务代码一律以 `config.X` 属性方式读取配置（晚绑定），保证测试可覆盖沙箱路径。
    2. Word/OOXML/COM 相关逻辑各自整体保留在单一模块内，不做内部拆分。
"""
