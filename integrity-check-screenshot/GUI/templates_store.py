# 文件路径: templates_store.py
# 核查模板的持久化与名单行解析（纯函数集合）。
# 行格式：`[编号]<空白分隔>名称 [证件号]`；编号仅当行首 token 形如 `数字-数字`
# （如 1-3-1-3-1、3-1-1-4-1）时识别。全角括号备注、18位统一社会信用代码均安全。

import json
import os
import re
from datetime import datetime

from modules.scraper.subject_utils import ID_PATTERN, normalize_subject

TEMPLATES_FILENAME = "check_templates.json"

# 编号：以数字开头、后接若干「-数字」段；避免把普通整数序号误判为层级编号
CODE_PATTERN = re.compile(r"^\d+(?:-\d+)+$")


def split_code(line):
    """拆分行首编号。返回 (code 或 None, 剩余文本)。"""
    line = str(line or "").strip()
    parts = line.split(None, 1)
    if parts and CODE_PATTERN.match(parts[0]):
        return parts[0], parts[1].strip() if len(parts) > 1 else ""
    return None, line


def parse_subject_line(line):
    """解析单行名单 → {raw, name, id_card, code}；空行返回 None。"""
    code, rest = split_code(line)
    if not rest:
        return None
    norm = normalize_subject(rest)   # 复用爬虫侧解析：ID 提取/大小写/分隔符清洗
    return {
        "raw": rest,
        "name": norm["name"],
        "id_card": norm["id_card"],
        "code": code or "",
    }


def parse_roster(text):
    """多行名单文本 → 条目列表（自动跳过空行）。"""
    entries = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        entry = parse_subject_line(line)
        if entry:
            entries.append(entry)
    return entries


def serialize_roster(entries):
    """条目列表 → 多行文本（可回填编辑框，往返无损）。"""
    lines = []
    for e in entries or []:
        code = str(e.get("code") or "").strip()
        raw = str(e.get("raw") or "").strip()
        lines.append(f"{code} {raw}" if code else raw)
    return "\n".join(lines)


def to_subjects(entries):
    """模板条目 → 核查页 companies_data 结构（含去重键 key 与 code）。"""
    subjects = []
    for e in entries or []:
        name = str(e.get("name") or "")
        id_card = str(e.get("id_card") or "")
        raw = str(e.get("raw") or "").strip()
        subjects.append({
            "name": name,
            "id_card": id_card,
            "raw": raw,
            "key": f"{name}|{id_card}",
            "code": str(e.get("code") or ""),
        })
    return subjects


# ============================ 文件读写 ============================

def templates_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATES_FILENAME)


def load_templates():
    """读取模板列表；缺失/损坏时静默返回空列表，绝不抛出。"""
    try:
        with open(templates_path(), "r", encoding="utf-8") as fobj:
            data = json.load(fobj)
        if isinstance(data, list):
            return [t for t in data if isinstance(t, dict) and t.get("name")]
    except Exception:
        pass
    return []


def save_templates(templates):
    """原子写入模板列表；失败抛出由调用方提示。"""
    path = templates_path()
    tmp = path + ".tmp"
    payload = []
    for t in templates:
        payload.append({
            "name": str(t.get("name") or "").strip(),
            "updated_at": t.get("updated_at") or "",
            "companies": [
                {"raw": c.get("raw", ""), "name": c.get("name", ""),
                 "id_card": c.get("id_card", ""), "code": c.get("code", "")}
                for c in (t.get("companies") or [])
            ],
        })
    with open(tmp, "w", encoding="utf-8") as fobj:
        json.dump(payload, fobj, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")
