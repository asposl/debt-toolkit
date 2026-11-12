"""目标 URL 与页面交互参数构造。"""
from urllib.parse import quote

from .subject_utils import subject_text


def format_target_url(config, subject):
    query_mode = config.get("query_mode", "name")
    values = {
        "company": quote(subject_text(subject, query_mode), safe=""),
        "name": quote(subject_text(subject, "name"), safe=""),
        "id_card": quote(subject_text(subject, "id_card"), safe=""),
        "keyword": quote(subject_text(subject, "name_id"), safe=""),
        "raw": quote(subject_text(subject, "raw"), safe=""),
    }
    url = config["url"]
    if "{" not in url:
        # 纯前缀模式（无占位符）：仅对无交互动作的纯导航型配置（自定义网站）
        # 在末尾拼接关键词；带 action/post_action 的网站靠页面内交互填表，URL 原样使用
        if config.get("action") is None and config.get("post_action") is None:
            url = url + quote(subject_text(subject, query_mode), safe="")
    else:
        url = url.format(**values)
    # www/域名/站名开头时自动补齐 scheme，避免被当作相对路径
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def action_argument(config, subject):
    if config.get("action_arg") == "item":
        return subject
    return subject_text(subject, config.get("action_query_mode", config.get("query_mode", "name")))
