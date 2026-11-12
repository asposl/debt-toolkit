# 文件路径: run_state.py
# 运行结果核验与持久化（纯函数集合，供 GUI 重跑闭环使用）。
# 判定原则：任务结束(DONE)后，逐对(公司×站点)检查预期截图是否在本轮新生成。
# 不侵入 modules/scraper；状态持久化到 <base_output>/_ibdw_state.json。

import json
import os
import time

from modules.scraper.output_layout import subject_dir
from modules.scraper.subject_utils import anonymize_key, safe_path_name

STATE_FILENAME = "_ibdw_state.json"
STATE_VERSION = 2

STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"

# mtime 比较余量（秒）：容忍文件系统时间戳精度与起跑计时误差
MTIME_SKEW = 2.0


# ============================ 路径与配置解析 ============================

def resolve_save_as(site_key, site_cfg):
    """截图文件名主体 = 配置 save_as，缺省为站点 key（与 batch_runner 一致）。"""
    return str((site_cfg or {}).get("save_as") or site_key)


def is_unknown_site(site_cfg):
    """整批/单对象工作流类站点产出命名不可预测 → 无法自动核验。"""
    cfg = site_cfg or {}
    return bool(cfg.get("workflow") or cfg.get("batch_workflow"))


def subject_folder(subject):
    """兼容旧接口：主体文件夹名（即将废弃，仅历史状态迁移时使用）。"""
    name = str(subject.get("name") or "").strip()
    id_card = str(subject.get("id_card") or "").strip()
    raw = str(subject.get("raw") or "").strip()
    return safe_path_name(name or id_card or raw)


def company_key(subject):
    """主体匿名键（审计缩写，不含名称）。"""
    if isinstance(subject, dict):
        return anonymize_key(subject.get("name"), subject.get("id_card"))
    return anonymize_key(subject)


def expected_png_path(run_dir, index, site_key, site_cfg):
    """复刻 batch_runner+capture 的产出路径：<run_xxx>/subj_NNN/<save_as>.png"""
    fname = safe_path_name(resolve_save_as(site_key, site_cfg))
    return os.path.join(subject_dir(run_dir, index), f"{fname}.png")


# ============================ 任务快照与核验 ============================

def build_task(companies, selected_sites, run_dir, started_at=None):
    """开跑前快照本轮任务范围（公司×站点笛卡尔积）、运行目录与起始时间戳。"""
    return {
        "started_at": started_at if started_at is not None else time.time(),
        "run_dir": run_dir,
        "companies": [
            {"key": company_key(c), "index": idx}
            for idx, c in enumerate(companies)
        ],
        "sites": list(selected_sites),
    }


def verify_run(task, merged_config, now=None):
    """DONE 后核验：返回 {results, counts}。

    - ok      预期 png 存在、非空且 mtime >= 本轮开始时间（留余量）
    - fail    其余情况（缺图 / 旧图 / 空文件）
    - unknown 工作流类站点（batch_workflow / workflow），不参与自动判定
    """
    now = now if now is not None else time.time()
    results = {}
    counts = {STATUS_OK: 0, STATUS_FAIL: 0, STATUS_UNKNOWN: 0}
    run_dir = task.get("run_dir") or ""

    for comp in task["companies"]:
        per_site = {}
        for site_key in task["sites"]:
            cfg = (merged_config or {}).get(site_key)
            if is_unknown_site(cfg):
                status = STATUS_UNKNOWN
            else:
                path = expected_png_path(run_dir, comp["index"], site_key, cfg)
                try:
                    fresh = (
                        os.path.isfile(path)
                        and os.path.getsize(path) > 0
                        and os.path.getmtime(path) >= task["started_at"] - MTIME_SKEW
                    )
                except OSError:
                    fresh = False
                status = STATUS_OK if fresh else STATUS_FAIL
            per_site[site_key] = status
            counts[status] += 1
        results[comp.get("key")] = per_site

    return {"results": results, "counts": counts}


def failed_sites_for(results, company_keys):
    """给定公司范围内失败站点的并集（供【仅选上次失败】使用）。"""
    keys = set(company_keys)
    failed = set()
    for comp_key, per_site in (results or {}).items():
        if comp_key in keys:
            failed.update(s for s, st in (per_site or {}).items() if st == STATUS_FAIL)
    return failed


# ============================ 状态持久化 ============================

def state_path(base_output):
    return os.path.join(base_output, STATE_FILENAME)


def empty_state():
    return {"version": STATE_VERSION, "last_run": None, "results": {}}


def load_state(base_output):
    """读取状态文件；损坏/缺失时静默降级为空白结构，绝不抛出。"""
    try:
        with open(state_path(base_output), "r", encoding="utf-8") as fobj:
            data = json.load(fobj)
        if isinstance(data, dict) and isinstance(data.get("results"), dict):
            data.setdefault("version", STATE_VERSION)
            data.setdefault("last_run", None)
            return data
    except Exception:
        pass
    return empty_state()


def merge_results(state, verdict_results, summary):
    """把本轮判定合并进历史状态：本轮覆盖同键，未涉及的历史条目保留。"""
    all_results = state.setdefault("results", {})
    for comp_key, per_site in (verdict_results or {}).items():
        row = all_results.setdefault(comp_key, {})
        row.update(per_site)
    state["last_run"] = summary
    return state


def save_state(base_output, state):
    """原子写入（临时文件 + replace）；失败返回 False 不抛出。"""
    tmp_path = None
    try:
        os.makedirs(base_output, exist_ok=True)
        tmp_path = state_path(base_output) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fobj:
            json.dump(state, fobj, ensure_ascii=False, indent=2)
        os.replace(tmp_path, state_path(base_output))
        return True
    except Exception:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def clear_state(base_output):
    """删除状态文件（不存在视为成功）；返回是否成功。"""
    try:
        path = state_path(base_output)
        if os.path.isfile(path):
            os.remove(path)
        return True
    except Exception:
        return False
