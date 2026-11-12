# -*- coding: utf-8 -*-
"""【原 页眉检查.py】header —— 检查并修复 docx 页眉编号。

本文件为原始脚本的整块平移，Word/OOXML 逻辑保持完整、不做内部拆分：
    - XML 命名空间注册与保留序列化（ElementTree 进程级前缀注册表）
    - 页眉文本节点操作与跨 run 区间替换
    - OPC 包结构辅助（rels/content-types/安全重写 zip）
    - check_and_fix_headers 总调度（含闭包状态机）
零第三方依赖（纯标准库），不依赖 Word COM。
"""

import datetime
import io
import os
import posixpath
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from . import config
from .logutil import _log_path

HEADER_NUMBER_PATTERN = re.compile(r"(\d+(?:-\d+)+)")
HEADER_PART_PATTERN = re.compile(r"^word/header\d+\.xml$")
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_NS = "http://www.w3.org/XML/1998/namespace"
TEXT_TAG = f"{{{W_NS}}}t"
HEADER_TAG = f"{{{W_NS}}}hdr"
PARAGRAPH_TAG = f"{{{W_NS}}}p"
RUN_TAG = f"{{{W_NS}}}r"
SECTPR_TAG = f"{{{W_NS}}}sectPr"
HEADER_REFERENCE_TAG = f"{{{W_NS}}}headerReference"
TITLEPG_TAG = f"{{{W_NS}}}titlePg"
W_TYPE_ATTR = f"{{{W_NS}}}type"
R_ID_ATTR = f"{{{R_NS}}}id"
XML_SPACE_ATTR = f"{{{XML_NS}}}space"
MC_IGNORABLE_ATTR = f"{{{MC_NS}}}Ignorable"
DOCUMENT_PART = "word/document.xml"
DOCUMENT_RELS_PART = "word/_rels/document.xml.rels"
CONTENT_TYPES_PART = "[Content_Types].xml"
HEADER_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
)
HEADER_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
)

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)


def extract_number_from_filename(filename):
    """
    从文件名中提取开头的编号，如 '4-1-1 发行人关于...' -> '4-1-1'
    支持格式: 数字-数字-数字 或 数字-数字-数字-数字 等
    """
    match = re.match(r"^\s*(\d+(?:-\d+)*)", filename)
    if match:
        return match.group(1)
    return None


def extract_number_from_header_text(text):
    """从页眉文本中提取编号，忽略中文前缀如 '尽职调查报告：'。"""
    match = HEADER_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def is_header_part(zip_name):
    return HEADER_PART_PATTERN.match(zip_name) is not None


def register_xml_namespaces(xml_bytes):
    """保留 docx XML 中已有的命名空间前缀，避免写回后 Word 难以识别。"""
    seen = set()
    for _, namespace in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = namespace
        if not uri or prefix in seen or prefix in {"xml", "xmlns"}:
            continue
        seen.add(prefix)
        ET.register_namespace(prefix, uri)


def get_root_namespace_declarations(xml_bytes):
    """读取 XML 根节点上声明的命名空间，返回 {prefix: uri}。"""
    namespaces = {}
    for event, item in ET.iterparse(
        io.BytesIO(xml_bytes),
        events=("start-ns", "start"),
    ):
        if event == "start":
            break
        prefix, uri = item
        namespaces[prefix or ""] = uri
    return namespaces


def add_root_namespace_declarations(xml_bytes, declarations):
    """把给定的具名命名空间声明安全地补到 XML 根节点。"""
    if not declarations:
        return xml_bytes

    existing_namespaces = get_root_namespace_declarations(xml_bytes)
    missing_declarations = []
    for prefix, uri in declarations.items():
        if not prefix or prefix == "xml":
            continue
        existing_uri = existing_namespaces.get(prefix)
        if existing_uri is not None:
            if existing_uri != uri:
                raise ValueError(
                    f"命名空间前缀冲突: {prefix}={existing_uri!r}, 原值={uri!r}"
                )
            continue
        missing_declarations.append(
            f" xmlns:{prefix}={quoteattr(uri)}".encode("utf-8")
        )

    if not missing_declarations:
        return xml_bytes

    declaration_end = xml_bytes.find(b"?>")
    search_from = declaration_end + 2 if declaration_end >= 0 else 0
    root_start = xml_bytes.find(b"<", search_from)
    root_tag_end = xml_bytes.find(b">", root_start + 1)
    if root_start < 0 or root_tag_end < 0:
        raise ValueError("XML 缺少有效根节点")

    # 兼容空根节点的 ``<root />`` 写法：命名空间声明必须插在斜杠前。
    insert_at = root_tag_end
    cursor = root_tag_end - 1
    while cursor > root_start and xml_bytes[cursor : cursor + 1].isspace():
        cursor -= 1
    if xml_bytes[cursor : cursor + 1] == b"/":
        insert_at = cursor

    return (
        xml_bytes[:insert_at]
        + b"".join(missing_declarations)
        + xml_bytes[insert_at:]
    )


def find_missing_ignorable_prefixes(xml_bytes):
    """找出 mc:Ignorable 引用了、但根节点没有声明的命名空间前缀。"""
    root = parse_xml(xml_bytes)
    required_prefixes = set()
    for element in root.iter():
        value = element.attrib.get(MC_IGNORABLE_ATTR, "")
        required_prefixes.update(prefix for prefix in value.split() if prefix)

    root_namespaces = get_root_namespace_declarations(xml_bytes)
    return sorted(required_prefixes - set(root_namespaces))


def serialize_xml_preserving_namespaces(root, original_xml_bytes=None):
    """
    序列化 XML，并保留原根节点上的命名空间声明。

    ElementTree 会删除只出现在 mc:Ignorable、Requires 等属性值中的
    xmlns 声明，导致 Word 将 docx 判断为损坏。这里在写回前重新注册当前
    XML 的前缀，并把序列化过程中丢失的非默认命名空间声明补回根节点。
    """
    original_namespaces = {}
    if original_xml_bytes is not None:
        original_namespaces = get_root_namespace_declarations(original_xml_bytes)
        register_xml_namespaces(original_xml_bytes)

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not original_namespaces:
        return xml_bytes

    declarations_to_restore = {
        prefix: uri
        for prefix, uri in original_namespaces.items()
        if prefix and prefix != "xml"
    }
    xml_bytes = add_root_namespace_declarations(xml_bytes, declarations_to_restore)

    final_namespaces = get_root_namespace_declarations(xml_bytes)
    lost_prefixes = [
        prefix
        for prefix, uri in original_namespaces.items()
        if prefix
        and prefix != "xml"
        and final_namespaces.get(prefix) != uri
    ]
    if lost_prefixes:
        raise ValueError(f"XML 写回时丢失命名空间: {', '.join(lost_prefixes)}")

    return xml_bytes


def parse_xml(xml_bytes):
    register_xml_namespaces(xml_bytes)
    return ET.fromstring(xml_bytes)


def get_text_nodes(root):
    return [node for node in root.iter(TEXT_TAG)]


def get_header_text(text_nodes):
    return "".join(node.text or "" for node in text_nodes).strip()


def set_node_text(node, text):
    node.text = text
    if text.startswith(" ") or text.endswith(" "):
        node.set(XML_SPACE_ATTR, "preserve")


def replace_span_in_text_nodes(text_nodes, start, end, replacement):
    """在多个 w:t 节点组成的连续文本中替换指定区间。"""
    spans = []
    pos = 0
    for node in text_nodes:
        text = node.text or ""
        next_pos = pos + len(text)
        spans.append((node, text, pos, next_pos))
        pos = next_pos

    first_index = None
    last_index = None
    for index, (_, text, span_start, span_end) in enumerate(spans):
        if text and span_end > start and first_index is None:
            first_index = index
        if text and span_start < end:
            last_index = index

    if first_index is None or last_index is None:
        return False

    first_node, first_text, first_start, _ = spans[first_index]
    last_node, last_text, last_start, _ = spans[last_index]
    local_start = start - first_start
    local_end = end - last_start

    if first_index == last_index:
        set_node_text(
            first_node,
            first_text[:local_start] + replacement + first_text[local_end:],
        )
        return True

    set_node_text(
        first_node,
        first_text[:local_start] + replacement + last_text[local_end:],
    )
    for index in range(first_index + 1, last_index + 1):
        set_node_text(spans[index][0], "")
    return True


def inspect_header_xml(xml_bytes):
    """返回页眉文本和其中第一个编号；没有编号时 number 为 None。"""
    root = parse_xml(xml_bytes)
    text_nodes = get_text_nodes(root)
    header_text = get_header_text(text_nodes)
    match = HEADER_NUMBER_PATTERN.search(header_text)
    if not match:
        return header_text, None
    return header_text, match.group(1)


def check_header_xml(xml_bytes, expected_number):
    """
    检查单个 header XML。
    返回: (header_text, old_number, new_xml_bytes, changed)
    """
    root = parse_xml(xml_bytes)
    text_nodes = get_text_nodes(root)
    header_text = get_header_text(text_nodes)
    if not header_text:
        return header_text, None, xml_bytes, False

    match = HEADER_NUMBER_PATTERN.search(header_text)
    if not match:
        return header_text, None, xml_bytes, False

    header_number = match.group(1)
    if header_number == expected_number:
        return header_text, header_number, xml_bytes, False

    replaced = replace_span_in_text_nodes(
        text_nodes,
        match.start(1),
        match.end(1),
        expected_number,
    )
    if not replaced:
        return header_text, header_number, xml_bytes, False

    new_xml_bytes = serialize_xml_preserving_namespaces(root, xml_bytes)
    return header_text, header_number, new_xml_bytes, True


def create_simple_header_xml(expected_number):
    root = ET.Element(HEADER_TAG)
    paragraph = ET.SubElement(root, PARAGRAPH_TAG)
    run = ET.SubElement(paragraph, RUN_TAG)
    text = ET.SubElement(run, TEXT_TAG)
    text.text = expected_number
    return serialize_xml_preserving_namespaces(root)


def add_number_to_header_xml(xml_bytes, expected_number):
    """
    在没有编号的页眉 XML 里补入编号。
    如果页眉没有任何文本节点，则创建一个最小页眉。
    """
    root = parse_xml(xml_bytes)
    text_nodes = get_text_nodes(root)
    if not text_nodes:
        return create_simple_header_xml(expected_number)

    target_node = None
    for node in reversed(text_nodes):
        if (node.text or "").strip():
            target_node = node
            break
    if target_node is None:
        target_node = text_nodes[-1]

    current_text = target_node.text or ""
    if current_text and not current_text.endswith(("：", ":", " ", "\t", "\n")):
        current_text += "："
    set_node_text(target_node, current_text + expected_number)
    return serialize_xml_preserving_namespaces(root, xml_bytes)


def normalize_document_target(target):
    if not target:
        return None

    target = target.replace("\\", "/")
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join("word", target))


def header_rels_part(header_part):
    dirname, filename = posixpath.split(header_part)
    return posixpath.join(dirname, "_rels", f"{filename}.rels")


def copy_related_header_rels(source_part, target_part, zip_names, changed_parts, docx_zip):
    source_rels = header_rels_part(source_part)
    if source_rels not in zip_names and source_rels not in changed_parts:
        return

    target_rels = header_rels_part(target_part)
    if source_rels in changed_parts:
        changed_parts[target_rels] = changed_parts[source_rels]
    else:
        changed_parts[target_rels] = docx_zip.read(source_rels)


def next_header_part_name(zip_names, changed_parts):
    max_index = 0
    all_names = set(zip_names) | set(changed_parts)
    for name in all_names:
        match = re.match(r"^word/header(\d+)\.xml$", name)
        if match:
            max_index = max(max_index, int(match.group(1)))

    next_index = max_index + 1
    while f"word/header{next_index}.xml" in all_names:
        next_index += 1
    return f"word/header{next_index}.xml"


def next_relationship_id(rels_root):
    max_index = 0
    used_ids = set()
    for relationship in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        relationship_id = relationship.attrib.get("Id")
        if not relationship_id:
            continue
        used_ids.add(relationship_id)
        match = re.match(r"rId(\d+)$", relationship_id)
        if match:
            max_index = max(max_index, int(match.group(1)))

    next_index = max_index + 1
    while f"rId{next_index}" in used_ids:
        next_index += 1
    return f"rId{next_index}"


def add_content_type_override(content_types_root, part_name, content_type):
    normalized_part_name = f"/{part_name}"
    for override in content_types_root.findall(f"{{{CT_NS}}}Override"):
        if override.attrib.get("PartName") == normalized_part_name:
            return False

    override = ET.SubElement(content_types_root, f"{{{CT_NS}}}Override")
    override.set("PartName", normalized_part_name)
    override.set("ContentType", content_type)
    return True


def insert_header_reference(sectPr, header_reference):
    insert_index = 0
    while insert_index < len(sectPr) and sectPr[insert_index].tag == HEADER_REFERENCE_TAG:
        insert_index += 1
    sectPr.insert(insert_index, header_reference)


def rewrite_docx(docx_path, changed_parts):
    """
    用临时文件重写 docx，避免中途失败时破坏原文件。
    changed_parts: {zip_name: bytes}
    """
    target_dir = os.path.dirname(docx_path) or "."
    fd, temp_path = tempfile.mkstemp(
        prefix="~$header_fix_",
        suffix=".docx",
        dir=target_dir,
    )
    os.close(fd)

    try:
        written_names = set()
        with zipfile.ZipFile(docx_path, "r") as src_zip:
            with zipfile.ZipFile(temp_path, "w") as dst_zip:
                for item in src_zip.infolist():
                    data = changed_parts.get(item.filename)
                    if data is None:
                        data = src_zip.read(item.filename)
                    dst_zip.writestr(item, data)
                    written_names.add(item.filename)

                for filename, data in changed_parts.items():
                    if filename not in written_names:
                        dst_zip.writestr(filename, data)
        os.replace(temp_path, docx_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def check_and_fix_headers(filepath, expected_number, dry_run=False):
    """
    检查并修复 docx 中的页眉编号。
    不依赖 Word COM，避免 RPC 服务器不可用问题。
    返回: (needs_fix: bool, changed: bool, has_error: bool, details: list[str])
    """
    details = []
    changed_parts = {}
    needs_fix = False
    has_error = False
    abs_path = os.path.abspath(filepath)

    try:
        with zipfile.ZipFile(abs_path, "r") as docx_zip:
            zip_items = docx_zip.infolist()
            zip_names = {item.filename for item in zip_items}
            xml_part_bytes = {
                item.filename: docx_zip.read(item.filename)
                for item in zip_items
                if item.filename.lower().endswith((".xml", ".rels"))
            }

            # 兼容修复旧版本脚本已经造成的损坏：从同一 docx 的其他 XML
            # 部件收集前缀映射，并补回 mc:Ignorable 引用但未声明的前缀。
            namespace_catalog = {}
            for xml_bytes in xml_part_bytes.values():
                for _, namespace in ET.iterparse(
                    io.BytesIO(xml_bytes),
                    events=("start-ns",),
                ):
                    prefix, uri = namespace
                    if prefix and uri:
                        namespace_catalog.setdefault(prefix, uri)

            for part_name, xml_bytes in list(xml_part_bytes.items()):
                missing_prefixes = find_missing_ignorable_prefixes(xml_bytes)
                if not missing_prefixes:
                    continue

                unresolved_prefixes = [
                    prefix
                    for prefix in missing_prefixes
                    if prefix not in namespace_catalog
                ]
                if unresolved_prefixes:
                    raise ValueError(
                        f"{part_name} 缺少命名空间且无法从当前 docx 恢复: "
                        f"{', '.join(unresolved_prefixes)}"
                    )

                declarations = {
                    prefix: namespace_catalog[prefix]
                    for prefix in missing_prefixes
                }
                repaired_xml = add_root_namespace_declarations(
                    xml_bytes,
                    declarations,
                )
                remaining_prefixes = find_missing_ignorable_prefixes(repaired_xml)
                if remaining_prefixes:
                    raise ValueError(
                        f"{part_name} 命名空间修复后仍缺少: "
                        f"{', '.join(remaining_prefixes)}"
                    )

                needs_fix = True
                xml_part_bytes[part_name] = repaired_xml
                details.append(
                    f"  [缺失命名空间] {part_name}: 已准备恢复 "
                    f"{', '.join(missing_prefixes)}"
                )
                if not dry_run:
                    changed_parts[part_name] = repaired_xml
                    details.append(
                        f"  [已修改] {part_name}: 已恢复缺失的命名空间声明"
                    )

            header_parts = [
                item.filename for item in zip_items if is_header_part(item.filename)
            ]
            header_bytes = {part: xml_part_bytes[part] for part in header_parts}
            header_info = {}

            def remember_header(part, xml_bytes):
                header_bytes[part] = xml_bytes
                header_info.pop(part, None)

            for header_part in header_parts:
                try:
                    header_text, header_number, new_xml_bytes, changed = check_header_xml(
                        header_bytes[header_part],
                        expected_number,
                    )
                except Exception as exc:
                    has_error = True
                    details.append(f"  [错误] {header_part}: 读取或解析页眉失败：{exc}")
                    continue

                if not changed:
                    continue

                needs_fix = True
                remember_header(header_part, new_xml_bytes)
                details.append(
                    f"  [不一致] {header_part}: 页眉编号='{header_number}', "
                    f"期望='{expected_number}', 原文本='{header_text}'"
                )

                if not dry_run:
                    changed_parts[header_part] = new_xml_bytes
                    details.append(f"  [已修改] {header_part}: 已替换为 '{expected_number}'")

            def get_header_info(header_part):
                if header_part not in header_bytes:
                    return "", None
                if header_part not in header_info:
                    header_info[header_part] = inspect_header_xml(header_bytes[header_part])
                return header_info[header_part]

            def find_numbered_source(preferred_parts=(), fallback_source=None):
                for part in preferred_parts:
                    if part and part in header_bytes and get_header_info(part)[1] == expected_number:
                        return part
                if (
                    fallback_source
                    and fallback_source in header_bytes
                    and get_header_info(fallback_source)[1] == expected_number
                ):
                    return fallback_source
                for part in header_parts:
                    if get_header_info(part)[1] == expected_number:
                        return part
                return None

            def fill_missing_header(header_part, source_part, location):
                nonlocal needs_fix, has_error

                if not header_part or header_part not in header_bytes:
                    return

                header_text, header_number = get_header_info(header_part)
                if header_number:
                    return

                needs_fix = True
                if source_part and source_part != header_part:
                    details.append(
                        f"  [缺失] {location}: {header_part} 页眉无编号，"
                        f"使用 {source_part} 补齐为 '{expected_number}'，原文本='{header_text}'"
                    )
                    new_xml_bytes = header_bytes[source_part]
                    remember_header(header_part, new_xml_bytes)

                    if not dry_run:
                        changed_parts[header_part] = new_xml_bytes
                        copy_related_header_rels(
                            source_part,
                            header_part,
                            zip_names,
                            changed_parts,
                            docx_zip,
                        )
                        details.append(
                            f"  [已修改] {header_part}: 已复制 {source_part} 的页眉内容"
                        )
                    return

                try:
                    new_xml_bytes = add_number_to_header_xml(
                        header_bytes[header_part],
                        expected_number,
                    )
                except Exception as exc:
                    has_error = True
                    details.append(f"  [错误] {location}: 补入编号失败：{exc}")
                    return

                details.append(
                    f"  [缺失] {location}: {header_part} 页眉无编号，"
                    f"已准备补入 '{expected_number}'，原文本='{header_text}'"
                )
                remember_header(header_part, new_xml_bytes)

                if not dry_run:
                    changed_parts[header_part] = new_xml_bytes
                    details.append(f"  [已修改] {header_part}: 已补入 '{expected_number}'")

            if DOCUMENT_PART in zip_names and DOCUMENT_RELS_PART in zip_names:
                document_xml = xml_part_bytes[DOCUMENT_PART]
                rels_xml = xml_part_bytes[DOCUMENT_RELS_PART]
                document_root = parse_xml(document_xml)
                rels_root = parse_xml(rels_xml)
                content_types_root = None
                content_types_xml = None
                if CONTENT_TYPES_PART in zip_names:
                    content_types_xml = xml_part_bytes[CONTENT_TYPES_PART]
                    content_types_root = parse_xml(content_types_xml)

                rid_to_target = {}
                for relationship in rels_root.findall(f"{{{REL_NS}}}Relationship"):
                    relationship_id = relationship.attrib.get("Id")
                    target = relationship.attrib.get("Target")
                    if relationship_id:
                        rid_to_target[relationship_id] = target

                document_changed = False
                rels_changed = False
                content_types_changed = False
                previous_source_part = None

                for section_idx, sectPr in enumerate(document_root.iter(SECTPR_TAG), 1):
                    refs = {}
                    for header_reference in sectPr.findall(HEADER_REFERENCE_TAG):
                        header_type = header_reference.attrib.get(W_TYPE_ATTR, "default")
                        rid = header_reference.attrib.get(R_ID_ATTR)
                        header_part = normalize_document_target(rid_to_target.get(rid))
                        refs[header_type] = {
                            "element": header_reference,
                            "rid": rid,
                            "part": header_part,
                        }

                    section_parts = [
                        ref["part"] for ref in refs.values() if ref.get("part") in header_bytes
                    ]
                    section_source = find_numbered_source(
                        section_parts,
                        fallback_source=previous_source_part,
                    )

                    for header_type, header_name in (
                        ("default", "默认页眉"),
                        ("even", "偶数页页眉"),
                        ("first", "首页页眉"),
                    ):
                        if header_type not in refs:
                            continue

                        header_part = refs[header_type]["part"]
                        preferred_parts = [
                            part for part in section_parts if part and part != header_part
                        ]
                        source_part = find_numbered_source(
                            preferred_parts,
                            fallback_source=section_source or previous_source_part,
                        )
                        fill_missing_header(
                            header_part,
                            source_part,
                            f"Section {section_idx} {header_name}",
                        )

                    section_source = find_numbered_source(
                        section_parts,
                        fallback_source=section_source or previous_source_part,
                    )
                    if section_source:
                        previous_source_part = section_source

                    has_default_header = "default" in refs
                    has_first_header = "first" in refs
                    title_page_enabled = sectPr.find(TITLEPG_TAG) is not None
                    if has_default_header or not (has_first_header or title_page_enabled):
                        continue

                    source_part = find_numbered_source(
                        section_parts,
                        fallback_source=previous_source_part,
                    )
                    if not source_part:
                        continue

                    needs_fix = True
                    details.append(
                        f"  [缺失] Section {section_idx} 默认页眉: 未设置默认页眉，"
                        f"将使用 {source_part} 新建默认页眉 '{expected_number}'"
                    )

                    if dry_run:
                        continue

                    new_part = next_header_part_name(zip_names, changed_parts)
                    new_rid = next_relationship_id(rels_root)
                    changed_parts[new_part] = header_bytes[source_part]
                    remember_header(new_part, header_bytes[source_part])
                    header_parts.append(new_part)
                    zip_names.add(new_part)
                    copy_related_header_rels(
                        source_part,
                        new_part,
                        zip_names,
                        changed_parts,
                        docx_zip,
                    )

                    relationship = ET.SubElement(
                        rels_root,
                        f"{{{REL_NS}}}Relationship",
                    )
                    relationship.set("Id", new_rid)
                    relationship.set("Type", HEADER_REL_TYPE)
                    relationship.set("Target", posixpath.basename(new_part))
                    rels_changed = True

                    header_reference = ET.Element(HEADER_REFERENCE_TAG)
                    header_reference.set(W_TYPE_ATTR, "default")
                    header_reference.set(R_ID_ATTR, new_rid)
                    insert_header_reference(sectPr, header_reference)
                    document_changed = True

                    if content_types_root is not None:
                        content_types_changed = (
                            add_content_type_override(
                                content_types_root,
                                new_part,
                                HEADER_CONTENT_TYPE,
                            )
                            or content_types_changed
                        )

                    details.append(
                        f"  [已修改] Section {section_idx}: 已新增 {new_part} 并设为默认页眉"
                    )

                if not dry_run:
                    if document_changed:
                        changed_parts[DOCUMENT_PART] = serialize_xml_preserving_namespaces(
                            document_root,
                            document_xml,
                        )
                    if rels_changed:
                        changed_parts[DOCUMENT_RELS_PART] = serialize_xml_preserving_namespaces(
                            rels_root,
                            rels_xml,
                        )
                    if content_types_changed and content_types_root is not None:
                        changed_parts[CONTENT_TYPES_PART] = serialize_xml_preserving_namespaces(
                            content_types_root,
                            content_types_xml,
                        )

        if changed_parts:
            rewrite_docx(abs_path, changed_parts)

    except zipfile.BadZipFile:
        has_error = True
        details.append("  [错误] 不是有效的 docx 文件或文件已损坏")
    except PermissionError as exc:
        has_error = True
        details.append(f"  [错误] 文件被占用或无权限访问：{exc}")
    except Exception as exc:
        has_error = True
        details.append(f"  [错误] {exc}")

    return needs_fix, bool(changed_parts), has_error, details


def collect_docx_files(root_dir):
    docx_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(".docx") and not filename.startswith("~$"):
                docx_files.append(os.path.join(dirpath, filename))
    return docx_files


def cmd_header(logger):
    """扫描多级文件夹中的所有 docx 文件，检查并修复页眉编号。"""
    root_dir = config.HEADER_ROOT_DIR
    dry_run = config.HEADER_DRY_RUN
    if not os.path.isdir(root_dir):
        logger.error(f"HEADER_ROOT_DIR 不存在或不是文件夹: {root_dir}")
        return 1

    log_lines = []
    log_lines.append("=" * 80)
    log_lines.append("页眉编号检查与修改日志")
    log_lines.append(f"扫描目录: {os.path.abspath(root_dir)}")
    log_lines.append(f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_lines.append(f"模式: {'仅检查（不修改）' if dry_run else '检查并修改'}")
    log_lines.append("=" * 80)
    log_lines.append("")

    total_files = 0
    fixed_files = 0
    need_fix_files = 0
    error_files = 0
    skipped_files = 0

    docx_files = collect_docx_files(root_dir)
    log_lines.append(f"共找到 {len(docx_files)} 个 docx 文件")
    log_lines.append("")
    logger.info(f"共找到 {len(docx_files)} 个 docx 文件")

    for filepath in docx_files:
        total_files += 1
        filename = os.path.basename(filepath)
        expected_number = extract_number_from_filename(filename)

        if expected_number is None:
            log_lines.append(f"[跳过] {filename}")
            log_lines.append(f"  路径: {filepath}")
            log_lines.append("  原因: 无法从文件名提取编号")
            log_lines.append("")
            skipped_files += 1
            continue

        needs_fix, changed, has_error, details = check_and_fix_headers(
            filepath,
            expected_number,
            dry_run,
        )

        if has_error:
            status = "错误"
            error_files += 1
        elif changed:
            status = "修改"
            fixed_files += 1
        elif needs_fix:
            status = "待修改"
            need_fix_files += 1
        else:
            status = "检查"

        if details:
            log_lines.append(f"[{status}] {filename}")
            log_lines.append(f"  路径: {filepath}")
            log_lines.append(f"  期望编号: {expected_number}")
            for detail in details:
                log_lines.append(detail)
            log_lines.append("")

    log_lines.append("")
    log_lines.append("=" * 80)
    log_lines.append("汇总统计")
    log_lines.append("=" * 80)
    log_lines.append(f"扫描文件总数: {total_files}")
    if dry_run:
        log_lines.append(f"发现需修改的文件数: {need_fix_files}")
    else:
        log_lines.append(f"已修改的文件数: {fixed_files}")
    log_lines.append(f"跳过的文件数: {skipped_files}")
    log_lines.append(f"错误的文件数: {error_files}")
    log_lines.append("=" * 80)

    log_text = "\n".join(log_lines)
    print(log_text)

    log_file = _log_path("header")
    with open(log_file, "w", encoding="utf-8") as log_file_handle:
        log_file_handle.write(log_text)
    logger.info(f"日志已保存到: {log_file}")
    return 1 if error_files else 0
