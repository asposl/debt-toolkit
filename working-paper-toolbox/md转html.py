# -*- coding: utf-8 -*-
"""把 Markdown 使用手册转成带侧边导航的单文件 HTML。

用法：
    python md转html.py <手册.md> [输出.html]

特性（针对本项目手册定制）：
    1. `> !!!` 包裹的连续引用行 → 红色高危警示框（每行为一段）；
    2. `⚠️` 开头的段落 → 黄色注意框；
    3. 普通引用 → 灰色提示框；
    4. 表格横向可滚动；ASCII 界面图代码块用等宽深色底；
    5. 自动生成 h2 章节导航 + 滚动高亮 + 回到顶部。
"""
from __future__ import annotations

import os
import re
import sys

import markdown

# ---------- 预处理 ----------

_FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_HTML_TAG_RE = re.compile(
    r"</?(?:a|b|i|em|strong|code|br|p|div|span|table|thead|tbody|tr|td|th|"
    r"ul|ol|li|h[1-6]|img|hr|blockquote|pre)\b[^>]*>", re.I)


def escape_bare_lt(text: str) -> str:
    """转义裸尖括号（如 logs\\<模块名>\\），但保留行内代码、围栏代码块与合法标签。"""
    holder: list[str] = []

    def keep(match: re.Match) -> str:
        holder.append(match.group(0))
        return f"\x00{len(holder) - 1}\x00"

    text = _FENCE_RE.sub(keep, text)
    text = _INLINE_CODE_RE.sub(keep, text)
    text = _HTML_TAG_RE.sub(keep, text)
    text = text.replace("<", "&lt;")
    for i, saved in enumerate(holder):
        text = text.replace(f"\x00{i}\x00", saved)
    return text


def extract_danger_blocks(text: str) -> str:
    """把 `> !!! … > !!!` 块转成 <div class="danger">。"""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("> !!!"):
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("> !!!"):
                matched = re.match(r"^\s*>\s?(.*)$", lines[i])
                if matched and matched.group(1).strip():
                    body.append(matched.group(1).strip())
                i += 1
            i += 1
            if body:
                out += ["", '<div class="danger">'] + [f"<p>{b}</p>" for b in body] + ["</div>", ""]
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def split_title(text: str) -> tuple[str, str, str]:
    """拆出 (h1 标题, 首段引用副标题, 正文 markdown)。"""
    lines = text.splitlines()
    title, subtitle, rest = "使用手册", "", []
    i = 0
    while i < len(lines) and not lines[i].startswith("# "):
        i += 1
    if i < len(lines):
        title = lines[i][2:].strip()
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(">"):
        buf = []
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            buf.append(lines[i].lstrip()[1:].strip())
            i += 1
        subtitle = " ".join(buf)
    rest = lines[i:]
    return title, subtitle, "\n".join(rest)


# ---------- 转换 ----------

def convert(md_text: str) -> tuple[str, str, list[tuple[str, str]]]:
    md_text = extract_danger_blocks(md_text)
    md_text = escape_bare_lt(md_text)
    title, subtitle, body_md = split_title(md_text)

    html = markdown.markdown(
        body_md, extensions=["tables", "fenced_code", "sane_lists"])
    # 副标题去掉 markdown 生成的 <p> 包裹，避免嵌进 hero 的 <p> 里
    sub_html = ""
    if subtitle:
        sub_html = markdown.markdown(subtitle).strip()
        if sub_html.startswith("<p>") and sub_html.endswith("</p>"):
            sub_html = sub_html[3:-4]

    # ⚠️ 段落 → 注意框
    html = re.sub(r"<p>⚠️\s*(.*?)</p>",
                  lambda m: f'<div class="warn"><p>{m.group(1)}</p></div>',
                  html, flags=re.S)
    # 表格横向滚动容器
    html = html.replace("<table>", '<div class="table-wrap"><table>')
    html = html.replace("</table>", "</table></div>")

    # h2 编号 + 目录
    toc: list[tuple[str, str]] = []

    def _h2(match: re.Match) -> str:
        anchor = f"sec-{len(toc) + 1}"
        plain = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        toc.append((anchor, plain))
        return f'<h2 id="{anchor}">{match.group(1)}</h2>'

    html = re.sub(r"<h2>(.*?)</h2>", _h2, html, flags=re.S)
    return html, sub_html, toc


# ---------- 模板 ----------

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  --blue:#2f6fed; --blue-dark:#1d4fb8; --ink:#16233c; --text:#33405c;
  --muted:#7a8599; --line:#e4e8f0; --bg:#f3f5f9; --card:#ffffff;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:"Microsoft YaHei UI","PingFang SC","Hiragino Sans GB",system-ui,sans-serif;
  font-size:15px;line-height:1.85;-webkit-font-smoothing:antialiased;}
a{color:var(--blue);text-decoration:none;}
a:hover{text-decoration:underline;}

/* ---- 侧边目录 ---- */
aside{position:fixed;left:0;top:0;bottom:0;width:252px;background:var(--card);
  border-right:1px solid var(--line);overflow-y:auto;padding:22px 0 40px;}
.brand{padding:0 22px 16px;font-size:16px;font-weight:600;color:var(--ink);
  border-bottom:1px solid var(--line);margin-bottom:12px;letter-spacing:.3px;}
aside nav a{display:block;padding:7px 22px;font-size:13.5px;color:#5d6b85;
  border-left:3px solid transparent;line-height:1.5;}
aside nav a:hover{background:#f0f4fb;color:var(--blue);text-decoration:none;}
aside nav a.active{color:var(--blue);border-left-color:var(--blue);
  background:#eef3fd;font-weight:600;}

/* ---- 正文 ---- */
main{margin-left:252px;padding:0 0 80px;}
.hero{background:var(--card);border-bottom:1px solid var(--line);
  padding:38px 56px 30px;}
.hero h1{margin:0 0 10px;font-size:27px;font-weight:600;color:var(--ink);letter-spacing:.5px;}
.hero .sub{margin:0;font-size:14px;color:var(--muted);line-height:1.8;}
.body{padding:8px 56px 0;max-width:1080px;}

h2{font-size:20px;font-weight:600;color:var(--ink);margin:42px 0 16px;
  padding-bottom:9px;border-bottom:1px solid var(--line);scroll-margin-top:20px;}
h2:first-child{margin-top:28px;}
h3{font-size:16.5px;font-weight:600;color:#2456b3;margin:28px 0 12px;}
p{margin:12px 0;}
strong{color:var(--ink);font-weight:600;}
ul,ol{padding-left:24px;margin:12px 0;}
li{margin:6px 0;}

code{background:#eef1f6;color:#c0344d;padding:2px 6px;border-radius:4px;
  font-family:Consolas,"Courier New",monospace;font-size:13px;}
pre{background:#10151d;color:#c9d4e3;padding:16px 18px;border-radius:10px;
  overflow-x:auto;line-height:1.55;margin:16px 0;}
pre code{background:none;color:inherit;padding:0;font-size:12.5px;}

.table-wrap{overflow-x:auto;margin:16px 0;border:1px solid var(--line);
  border-radius:10px;background:var(--card);}
table{border-collapse:collapse;width:100%;font-size:14px;}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--line);
  vertical-align:top;line-height:1.7;}
th{background:#f7f9fc;color:var(--ink);font-weight:600;white-space:nowrap;}
tbody tr:last-child td{border-bottom:none;}
tbody tr:hover{background:#fafbfe;}

blockquote{margin:16px 0;padding:12px 18px;background:#f7f9fc;
  border-left:3px solid #b9c6dd;border-radius:0 8px 8px 0;color:#4a5670;}
blockquote p{margin:4px 0;}

.danger,.warn{position:relative;margin:18px 0;padding:14px 20px 14px 78px;border-radius:8px;}
.danger{background:#fef2f2;border:1px solid #f8c9c9;border-left:4px solid #dc2626;}
.danger::before{content:"高危";position:absolute;left:20px;top:15px;
  background:#dc2626;color:#fff;font-size:12px;padding:1px 8px;border-radius:4px;}
.danger p{margin:6px 0;color:#8f1d1d;font-weight:600;}
.warn{background:#fffbeb;border:1px solid #f6e0a8;border-left:4px solid #e8a317;}
.warn::before{content:"注意";position:absolute;left:20px;top:13px;
  background:#e8a317;color:#fff;font-size:12px;padding:1px 8px;border-radius:4px;}
.warn p{margin:4px 0;color:#7a5206;}

hr{border:none;border-top:1px solid var(--line);margin:38px 0;}

footer{margin:56px 56px 0;padding-top:20px;border-top:1px solid var(--line);
  color:var(--muted);font-size:13px;}

#totop{position:fixed;right:26px;bottom:30px;width:40px;height:40px;
  border:none;border-radius:50%;background:var(--blue);color:#fff;font-size:18px;
  cursor:pointer;opacity:0;pointer-events:none;transition:opacity .2s;}
#totop.show{opacity:.85;pointer-events:auto;}
#totop:hover{opacity:1;}

@media (max-width:980px){
  aside{position:static;width:auto;border-right:none;border-bottom:1px solid var(--line);}
  main{margin-left:0;}
  .hero{padding:28px 24px 22px;}
  .body,footer{padding-left:24px;padding-right:24px;}
  footer{margin-left:0;margin-right:0;}
}
@media print{
  aside,#totop{display:none;}
  main{margin-left:0;}
  body{background:#fff;}
  h2{page-break-after:avoid;}
  .danger,.warn,.table-wrap,pre{page-break-inside:avoid;}
}
</style>
</head>
<body>
<aside>
  <div class="brand">__TITLE__</div>
  <nav id="toc">__TOC__</nav>
</aside>
<main>
  <header class="hero">
    <h1>__TITLE__</h1>
    <p class="sub">__SUB__</p>
  </header>
  <div class="body">
__BODY__
  </div>
  <footer>__TITLE__ · 由 Markdown 自动生成</footer>
</main>
<button id="totop" title="回到顶部">&uarr;</button>
<script>
(function(){
  var links = Array.prototype.slice.call(document.querySelectorAll('#toc a'));
  var heads = links.map(function(a){ return document.getElementById(a.getAttribute('href').slice(1)); });
  var btn = document.getElementById('totop');
  function onScroll(){
    var y = window.scrollY + 120, cur = 0;
    heads.forEach(function(h, i){ if (h && h.offsetTop <= y) cur = i; });
    links.forEach(function(a, i){ a.classList.toggle('active', i === cur); });
    var active = links[cur];
    if (active) {
      var nav = document.getElementById('toc');
      var top = active.offsetTop - nav.clientHeight / 2;
      nav.scrollTop = Math.max(0, top);
    }
    btn.classList.toggle('show', window.scrollY > 400);
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  window.addEventListener('resize', onScroll);
  btn.addEventListener('click', function(){ window.scrollTo({top:0, behavior:'smooth'}); });
  onScroll();
})();
</script>
</body>
</html>
"""


def build_html(md_text: str, title: str) -> str:
    body, subtitle, toc = convert(md_text)
    toc_html = "\n".join(
        f'    <a href="#{anchor}">{text}</a>' for anchor, text in toc)
    return (TEMPLATE
            .replace("__BODY__", body)
            .replace("__TOC__", toc_html)
            .replace("__TITLE__", title)
            .replace("__SUB__", subtitle))


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else "使用手册.md"
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".html"
    with open(src, encoding="utf-8") as fh:
        md_text = fh.read()

    title = "使用手册"
    first = next((ln for ln in md_text.splitlines() if ln.startswith("# ")), None)
    if first:
        title = first[2:].strip()

    html = build_html(md_text, title)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"[OK] {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
