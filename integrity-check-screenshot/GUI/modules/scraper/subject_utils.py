"""核查对象解析与安全命名工具。"""
import hashlib
import re


# 引入 dp 版配置
ID_PATTERN = re.compile(
    r"(?<![0-9A-Za-z])(?:\d{17}[\dXx]|\d{15}|[0-9A-Za-z]{18})(?![0-9A-Za-z])"
)


def anonymize_key(name, id_card=""):
    """主体匿名键：状态文件、核验结果都用它，避免把真实名称写进 json。"""
    raw = f"{str(name or '').strip()}|{str(id_card or '').strip().upper()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]



def safe_path_name(value):
    value = str(value or "").strip()
    value = re.sub(r'[<>:"/\\|?*\r\n\t]+', "_", value)
    value = value.strip(" .")
    return value or "未命名"


def normalize_subject(subject):
    if isinstance(subject, dict):
        name = str(subject.get("name") or "").strip()
        id_card = str(subject.get("id_card") or "").strip().upper()
        raw = str(subject.get("raw") or f"{name} {id_card}").strip()
    else:
        raw = str(subject or "").strip()
        match = ID_PATTERN.search(raw)
        id_card = match.group(0).upper() if match else ""
        if match:
            name = f"{raw[:match.start()]} {raw[match.end():]}"
            name = re.sub(r"[\s,，;；:：|/\\]+", " ", name).strip()
        else:
            name = raw

    display_name = name or id_card or raw or "未命名"
    return {
        "name": name,
        "id_card": id_card,
        "raw": raw,
        "display_name": display_name,
        "folder_name": display_name,
    }


def subject_text(subject, mode="name"):
    name = subject.get("name", "")
    id_card = subject.get("id_card", "")
    raw = subject.get("raw", "")

    if mode in ("name_id", "keyword"):
        return f"{name} {id_card}".strip() or raw
    if mode in ("id", "id_card"):
        return id_card
    if mode == "raw":
        return raw
    return name or raw or id_card
