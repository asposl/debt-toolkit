# 文件路径: GUI/modules/scraper/output_layout.py
"""输出目录布局：每次运行独立目录，主体用序号占位，真实名称不落到路径上。

布局约定
    <base_output>/run_YYYYmmdd-HHMMSS/subj_001/<站点>.png

- 目录里只出现「run_时间戳」和「subj_序号」，不出现被查询主体名称。
- 序号按 companies 列表顺序分配，写入端（batch_runner/workflows）与核验端
  （run_state.verify_run）都用同一份顺序，因此无需共享状态即可对上。
- 序号→主体的映射只在显式开启时（环境变量 IBDW_WRITE_MANIFEST=1）写成
  manifest.json；默认不落盘，避免把主体名重新写回磁盘。
"""

import json
import os
from datetime import datetime

RUN_DIR_PREFIX = "run_"
SUBJECT_DIR_TEMPLATE = "subj_{index:03d}"
MANIFEST_NAME = "manifest.json"

ENV_WRITE_MANIFEST = "IBDW_WRITE_MANIFEST"
ENV_DEMO_MODE = "IBDW_DEMO_MODE"

DEMO_SUBJECT_TEMPLATE = "示例主体{index:03d}"


def run_dir_name(now=None):
    """运行目录名，例如 run_20261112-2130 。"""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{RUN_DIR_PREFIX}{stamp}"


def new_run_dir(base_output, now=None):
    return os.path.join(base_output, run_dir_name(now))


def subject_dir_name(index):
    """主体子目录名：subj_001 起（index 为 0 基）。"""
    return SUBJECT_DIR_TEMPLATE.format(index=index + 1)


def subject_dir(run_dir, index):
    return os.path.join(run_dir, subject_dir_name(index))


def env_flag(name):
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def demo_mode():
    return env_flag(ENV_DEMO_MODE)


def manifest_enabled():
    return env_flag(ENV_WRITE_MANIFEST)


def build_manifest(run_dir, companies, demo=None):
    """构造序号↔主体映射；脱敏模式下只写示例名。"""
    demo = demo_mode() if demo is None else demo
    items = []
    for index, comp in enumerate(companies):
        if isinstance(comp, dict):
            name = str(comp.get("name") or "").strip()
            id_card = str(comp.get("id_card") or "").strip()
            raw = str(comp.get("raw") or "").strip()
        else:
            name, id_card, raw = str(comp or "").strip(), "", str(comp or "").strip()
        items.append({
            "index": index + 1,
            "folder": subject_dir_name(index),
            "name": DEMO_SUBJECT_TEMPLATE.format(index=index + 1) if demo else (name or raw),
            "id_card": "" if demo else id_card,
        })
    return {
        "run_dir": os.path.basename(run_dir),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "demo_mode": bool(demo),
        "subjects": items,
    }


def write_manifest(run_dir, companies, demo=None):
    """写 manifest.json（默认不调用）。返回路径或 None。"""
    try:
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, MANIFEST_NAME)
        data = build_manifest(run_dir, companies, demo=demo)
        with open(path, "w", encoding="utf-8") as fobj:
            json.dump(data, fobj, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None
