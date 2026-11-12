# -*- coding: utf-8 -*-
"""docx 批量内容替换工具箱子包（由原单文件 replace_toolkit.py 按原始脚本边界拆分）。

模块对照：
    config.py         公共配置常量（原「公共配置」区；测试经 config.X 覆盖）
    common.py         日志工具 + normalize_cell（short/long 共用）
    short_replace.py  【原 短替换.py】词对/正则批量替换（python-docx 引擎，快）
    long_replace.py   【原 长替换.py】Excel 规则表区间替换并插入素材 docx（Word COM 引擎，保格式）

重要约定：
    业务代码一律以 `config.X` 属性方式读取配置（晚绑定），
    保证测试可以通过猴子补丁覆盖沙箱路径。
"""
