# -*- coding: utf-8 -*-
"""
make_rules_template.py —— 生成「替换规则表.xlsx」模板。

用法：
    python make_rules_template.py [输出路径]

不传参数时生成到工具包根目录（即 toolkit/config.py 中 RULES_XLSX 指向的位置）。
已存在的同名文件不会被覆盖（请先手工改名或删除）。

生成的结构：
    Sheet1「填写说明」—— 纯说明文字，程序不读取
    Sheet2「短替换」  —— short 子命令使用：第1列=查找词(regex:前缀=正则)，第2列=替换词(留空=删除)
    Sheet3「长替换」  —— long 子命令使用：第1列=起始关键字，第2列=结束关键字，第3列=素材docx文件名
"""

import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(os.path.dirname(SCRIPT_DIR), "替换规则表.xlsx")

HEADER_FONT = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")


def _write_sheet(ws, headers, widths, notes=None):
    for col, (header, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = HEADER_FONT
        ws.column_dimensions[get_column_letter(col)].width = width
    if notes:
        note_row = ws.max_row + 2
        for line in notes:
            cell = ws.cell(row=note_row, column=1, value=line)
            cell.alignment = WRAP
            note_row += 1


def build_workbook():
    wb = Workbook()

    # ---- Sheet1：填写说明（程序不读取）----
    ws = wb.active
    ws.title = "填写说明"
    ws.column_dimensions["A"].width = 110
    lines = [
        "替换规则表 · 填写说明",
        "",
        "本工作簿供 replace_toolkit.py 使用：short 子命令读「短替换」表，long 子命令读「长替换」表。",
        "本「填写说明」表程序不读取，可随意编辑。",
        "",
        "通用要求：",
        "  · 所有规则从第 2 行开始填写，第 1 行是表头（程序自动跳过）。",
        "  · 单元格首尾空格会被自动清除。",
        "  · 路径等全局配置在 替换底稿内容/toolkit/config.py 中修改。",
        "",
        "「短替换」表（词对/正则批量替换，python-docx 引擎，快）：",
        "  · 第 1 列 = 查找词：不能为空；以 regex: 开头时按正则表达式处理。",
        "  · 第 2 列 = 替换词：留空表示删除查找词。",
        "  · 查写词恰好只写 regex:（空前缀）的行会被跳过并在日志提示。",
        "  · 查找词重复时，靠后的行覆盖靠前的行。",
        "  · 替换范围：正文段落、表格、页眉页脚。（注意：整段文本会写入第一个 run，段内局部格式不保留）",
        "",
        "「长替换」表（区间定位+插入素材，Word COM 引擎，保格式）：",
        "  · 第 1 列 = 起始关键字（前缀）。",
        "  · 第 2 列 = 结束关键字（后缀），可以与起始关键字相同。",
        "  · 第 3 列 = 替换素材 docx 文件名：可写纯文件名（自动到素材目录查找）、",
        "    相对路径或绝对路径；省略 .docx 后缀时自动补试。",
        "  · 三列全空跳过；缺任意一列则该行跳过并在日志提示 [规则跳过]。",
        "  · 执行时会反复查找「起始…结束」区间并插入素材直到找完；",
        "    当前配置 REPLACE_BOUNDARY_TEXT=True，起止关键字本身也会一并被替换掉。",
    ]
    for row_idx, line in enumerate(lines, start=1):
        cell = ws.cell(row=row_idx, column=1, value=line)
        cell.alignment = WRAP
    ws.cell(row=1, column=1).font = Font(bold=True, size=14)

    # ---- Sheet2：短替换 ----
    ws_short = wb.create_sheet("短替换")
    _write_sheet(
        ws_short,
        ["查找词", "替换词"],
        [50, 50],
        notes=[
            "示例（正式使用前请删除本行说明与下方示例行）：",
            "  普通词对：查找词=本募集说明书签署日，替换词=本文件出具日",
            "  正则：查找词=regex:2026年6月[\\s]*日，替换词=2026年6月30日",
            "  删除：查找词=obsolete词，替换词=（留空）",
        ],
    )

    # ---- Sheet3：长替换 ----
    ws_long = wb.create_sheet("长替换")
    _write_sheet(
        ws_long,
        ["起始关键字", "结束关键字", "替换素材文件名"],
        [40, 40, 50],
        notes=[
            "示例（正式使用前请删除本行说明与下方示例行）：",
            "  起始关键字=【起始标记】，结束关键字=【结束标记】，素材=新内容.docx",
            "  效果：两个标记及其之间的内容整体替换为素材文档内容。",
        ],
    )

    return wb


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    if os.path.exists(output):
        print(f"[取消] 目标文件已存在，未覆盖：{output}")
        print("如需重新生成，请先删除或改名现有文件。")
        return 1

    wb = build_workbook()
    wb.save(output)
    wb.close()
    print(f"[完成] 已生成规则表模板：{output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
