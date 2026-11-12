# -*- coding: utf-8 -*-
"""gui_runner.py —— GUI 子进程任务执行器。

由 底稿工具箱GUI.py 以独立子进程调用：
    python gui_runner.py "<JSON 任务描述>"

为什么要经过本中转脚本：
  1. 各模块的实现包存在同名冲突（多个 toolkit/toolbox），
     在独立子进程中运行可彻底隔离 sys.modules；
  2. 签章页工具 / 替换底稿内容的路径写在各自 toolkit/config.py 里，
     本脚本按 GUI 传入的参数覆写 config 后再调用原命令函数，
     不改动任何原有代码；
  3. Word COM 等重资源操作崩溃时不会拖垮 GUI 主进程。

任务描述格式：{"task": "sign|replace|dirgen", "params": {...}}
所有输出走 stdout/stderr（utf-8），由 GUI 捕获展示。
"""

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))


def _apply_log_root(cfg, module_name: str) -> None:
    """打包运行时把模块日志目录从 _MEIPASS 重定向到 exe 同级 logs/<模块名>。

    各模块的 LOG_DIR 都是晚绑定读取（config.LOG_DIR），在导入业务模块前覆写即可生效。
    """
    root = os.environ.get("IBDW_LOG_ROOT")
    if root:
        cfg.LOG_DIR = os.path.join(root, module_name)


# =====================================================================
# 签章页工具（pdf_toolkit）：format / header / export / filter / insert
# =====================================================================
def _run_sign(p):
    base = os.path.join(ROOT, "签章页工具")
    sys.path.insert(0, base)

    from toolkit import config as cfg  # noqa: E402

    _apply_log_root(cfg, "签章页工具")

    if p.get("tag"):
        cfg.PROJECT_TAG = p["tag"]

    root = p["root"]
    cfg.PROJECT_ROOT = root
    # config 中派生路径在导入时赋值，这里逐项同步覆写
    cfg.FORMAT_INPUT_FOLDER = root
    cfg.HEADER_ROOT_DIR = root
    cfg.EXPORT_ROOT_FOLDER = root
    cfg.APPEND_ROOT_DIR = root
    cfg.REPLACE_ROOT_DIR = root
    cfg.APPEND_SIGNATURE_PDF_PATH = os.path.join(root, cfg.EXPORT_MERGED_PDF_NAME)
    cfg.REPLACE_SIGNATURE_PDF_PATH = os.path.join(root, "签字合并.pdf")

    if p.get("keyword"):
        cfg.EXPORT_COMPANY_KEYWORD = p["keyword"]
    if p.get("dry_run") is not None:
        cfg.HEADER_DRY_RUN = bool(p["dry_run"])
    if p.get("update_days") is not None:
        cfg.FORMAT_UPDATE_DAYS = int(p["update_days"])
    if p.get("pdf_reuse_days") is not None:
        cfg.EXPORT_RECENT_PDF_MAX_AGE_DAYS = int(p["pdf_reuse_days"])

    # ---- ④-⑥ 手动路径覆写（GUI 留空时为 None，走上方默认派生值）----
    cmd = p["cmd"]
    steps_root = p.get("steps_root")
    if cmd == "filter":
        # ④ 只读取 JSON 清单并输出到 logs/，与项目根目录无关
        if p.get("filter_json"):
            cfg.FILTER_JSON_PATH = p["filter_json"]
    elif cmd == "insert_append":
        if steps_root:
            cfg.APPEND_ROOT_DIR = steps_root
            # 「清单与路径」页指定了根目录时，默认签章页.pdf 也应从该根目录取，
            # 而不是沿用标准流程根目录（手动路径仍优先）
            cfg.APPEND_SIGNATURE_PDF_PATH = os.path.join(
                steps_root, cfg.EXPORT_MERGED_PDF_NAME)
        if p.get("append_json"):
            cfg.APPEND_JSON_PATH = p["append_json"]
        if p.get("append_pdf"):
            cfg.APPEND_SIGNATURE_PDF_PATH = p["append_pdf"]
    elif cmd == "insert_replace":
        if steps_root:
            cfg.REPLACE_ROOT_DIR = steps_root
            # 同上：默认签字合并.pdf 跟随「清单与路径」页的根目录（手动路径仍优先）
            cfg.REPLACE_SIGNATURE_PDF_PATH = os.path.join(steps_root, "签字合并.pdf")
        if p.get("replace_list"):
            cfg.REPLACE_LIST_PATH = p["replace_list"]
        if p.get("replace_pdf"):
            cfg.REPLACE_SIGNATURE_PDF_PATH = p["replace_pdf"]

    from toolkit.export_sign import cmd_export  # noqa: E402
    from toolkit.filter_index import cmd_filter  # noqa: E402
    from toolkit.format_word import cmd_format  # noqa: E402
    from toolkit.header_fix import cmd_header  # noqa: E402
    from toolkit.insert_pages import cmd_insert  # noqa: E402
    from toolkit.logutil import setup_logger  # noqa: E402

    cmd = p["cmd"]
    dispatch = {
        "format": lambda lg: cmd_format(lg),
        "header": lambda lg: cmd_header(lg),
        "export": lambda lg: cmd_export(lg),
        "filter": lambda lg: cmd_filter(lg),
        "insert_append": lambda lg: cmd_insert(lg, "append"),
        "insert_replace": lambda lg: cmd_insert(lg, "replace"),
    }
    logger = setup_logger(cmd)
    code = dispatch[cmd](logger)
    return code if isinstance(code, int) else 0


# =====================================================================
# 替换底稿内容（replace_toolkit）：short / long
# =====================================================================
def _run_replace(p):
    base = os.path.join(ROOT, "替换底稿内容")
    sys.path.insert(0, base)

    from toolkit import config as cfg  # noqa: E402

    _apply_log_root(cfg, "替换底稿内容")

    if p.get("rules_xlsx"):
        cfg.SHORT_RULES_XLSX = Path(p["rules_xlsx"])
        cfg.RULES_XLSX = Path(p["rules_xlsx"])
    if p.get("source"):
        cfg.SOURCE_FOLDER = p["source"]
        cfg.TARGET_DOCX_DIR = Path(p["source"])
    final = p.get("final") or p.get("source")
    if final:
        cfg.FINAL_FOLDER = final
    if p.get("insert_dir"):
        cfg.INSERT_DOCX_DIR = Path(p["insert_dir"])
    if p.get("overwrite") is not None:
        cfg.OVERWRITE_ORIGINAL = bool(p["overwrite"])
    if p.get("output_dir"):
        cfg.OUTPUT_DIR = Path(p["output_dir"])

    from toolkit.common import setup_logger  # noqa: E402

    cmd = p["cmd"]  # short / long
    logger = setup_logger(cmd)
    if cmd == "short":
        from toolkit.short_replace import cmd_short  # noqa: E402

        code = cmd_short(logger)
    else:
        from toolkit.long_replace import cmd_long  # noqa: E402

        code = cmd_long(logger)
    return code if isinstance(code, int) else 0


# =====================================================================
# 多级文件夹生成目录（输出文件目录.py）
# =====================================================================
def _run_dirgen(p):
    base = os.path.join(ROOT, "多级文件夹生成目录")
    sys.path.insert(0, base)

    import importlib  # noqa: E402

    m = importlib.import_module("输出文件目录")

    target = p.get("target")
    excel = p.get("excel")
    word = p.get("word")

    if target and excel:
        m.export_directory_to_excel(target, excel)
    elif excel:
        raise ValueError("生成 Excel 目录需要同时填写「目标文件夹」")
    if word:
        if not excel or not os.path.exists(excel):
            raise ValueError(f"生成 Word 目录前需要先生成有效的 Excel 目录：{excel}")
        m.export_excel_to_word_directory(excel, word)
    return 0


# =====================================================================
# 初始化底稿文件（初始化底稿文件.py：字体/行距刷新 + 追加/汇总签章页）
# =====================================================================
def _run_init(p):
    base = os.path.join(ROOT, "签章页工具")
    src = os.path.join(base, "初始化底稿文件.py")

    with open(src, encoding="utf-8") as fh:
        source = fh.read()

    # 该脚本在模块顶层会按硬编码默认路径 os.makedirs，
    # 先临时屏蔽 makedirs，避免 import 副作用；随后覆写配置再调用 main()
    real_makedirs = os.makedirs
    os.makedirs = lambda *a, **k: None
    try:
        namespace = {"__name__": "init_sign_pages", "__file__": src}
        exec(compile(source, src, "exec"), namespace)
    finally:
        os.makedirs = real_makedirs

    root = p["root"]
    namespace["INPUT_FOLDER"] = root
    namespace["OUTPUT_FOLDER"] = root
    namespace["SEPARATE_FOLDER"] = p.get("separate") or root
    if p.get("issuer"):
        namespace["issuer"] = p["issuer"]
    if p.get("project_team"):
        namespace["project_team"] = p["project_team"]
    if p.get("date"):
        namespace["date"] = p["date"]
    if p.get("sign_name"):
        namespace["sign_name"] = p["sign_name"]

    namespace["main"]()
    return 0


# =====================================================================
# 入口
# =====================================================================
TASKS = {
    "sign": _run_sign,
    "replace": _run_replace,
    "dirgen": _run_dirgen,
    "init": _run_init,
}


def main():
    if len(sys.argv) < 2:
        print("用法: python gui_runner.py '<JSON>'")
        return 2
    spec = json.loads(sys.argv[1])
    handler = TASKS.get(spec.get("task"))
    if handler is None:
        print(f"未知任务类型: {spec.get('task')}")
        return 2
    try:
        code = handler(spec.get("params", {}))
    except SystemExit as exc:  # 下游脚本可能直接 sys.exit
        code = exc.code if isinstance(exc.code, int) else 0
    return code


if __name__ == "__main__":
    sys.exit(main())
