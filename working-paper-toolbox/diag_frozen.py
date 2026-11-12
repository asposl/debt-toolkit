# -*- coding: utf-8 -*-
"""diag_frozen.py —— 逐项验证 exe 的各内部模式（全部为只读/预览/临时目录操作）。

覆盖：
  A. --run-script  比较文件夹内容/folder_toolbox.py compare   （纯标准库）
  B. --run-script  底稿pdf材料/file_toolkit.py renumber_files （预览，不落盘）
  C. --gui-runner  sign/header dry-run                        （toolkit 包 + pypdf）
  D. --gui-runner  replace/short 输出到独立目录                （python-docx + openpyxl）
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "dist" / "底稿工具箱GUI.exe"

if not EXE.is_file():
    sys.exit(f"[失败] 未找到 {EXE}")

tmp = Path(tempfile.mkdtemp(prefix="ibdw_diag_"))


def run(label, argv, cwd, timeout=90):
    print(f"\n===== {label} =====", flush=True)
    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if out:
            for line in out.splitlines()[:30]:
                print("   ", line)
        else:
            print("    [无任何输出]")
        print(f"    >>> 退出码 = {proc.returncode}")
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print(f"    [异常] {exc}")
        return False


results = {}

# ---- A. folder_toolbox compare（纯标准库 CLI）----
old = tmp / "old"; new = tmp / "new"
old.mkdir(); new.mkdir()
(old / "a.docx").write_bytes(b"v1")
(new / "a.docx").write_bytes(b"v2")
results["A folder_toolbox compare"] = run(
    "A: --run-script folder_toolbox.py compare",
    [str(EXE), "--run-script", str(ROOT / "比较文件夹内容" / "folder_toolbox.py"),
     "compare", str(old), str(new)],
    ROOT / "比较文件夹内容")

# ---- B. file_toolkit renumber_files 预览（pypdf/PIL 路径）----
ft_dir = tmp / "编号文件夹"
ft_dir.mkdir()
(ft_dir / "旧文件.pdf").write_bytes(b"%PDF-1.4\n")
results["B file_toolkit renumber preview"] = run(
    "B: --run-script file_toolkit.py renumber_files（预览）",
    [str(EXE), "--run-script", str(ROOT / "底稿pdf材料" / "file_toolkit.py"),
     "renumber_files", "--folder", str(ft_dir), "--start", "1"],
    ROOT / "底稿pdf材料")

# ---- C. sign/header dry-run（toolkit 包 + pypdf）----
sign_root = tmp / "签章页项目"
(sign_root / "01 底稿").mkdir(parents=True)
results["C sign header dry-run"] = run(
    "C: --gui-runner sign/header（dry-run）",
    [str(EXE), "--gui-runner", json.dumps({
        "task": "sign",
        "params": {"cmd": "header", "root": str(sign_root), "tag": "测试",
                   "keyword": "测试公司", "dry_run": True,
                   "update_days": 100, "pdf_reuse_days": 1},
    }, ensure_ascii=False)],
    ROOT)

# ---- D. replace/short（python-docx + openpyxl，输出到独立目录）----
from docx import Document  # noqa: E402

rep_src = tmp / "待替换"
rep_src.mkdir()
doc = Document()
doc.add_paragraph("长期借款合计")
doc.save(str(rep_src / "底稿一.docx"))
rep_out = tmp / "替换结果"
rules = ROOT / "替换规则表.xlsx"
if rules.is_file():
    results["D replace short"] = run(
        "D: --gui-runner replace/short",
        [str(EXE), "--gui-runner", json.dumps({
            "task": "replace",
            "params": {"cmd": "short", "rules_xlsx": str(rules),
                       "source": str(rep_src), "final": str(rep_out)},
        }, ensure_ascii=False)],
    ROOT)
else:
    print("\n[D] 跳过：未找到 替换规则表.xlsx")

print("\n========== 汇总 ==========")
for k, ok in results.items():
    print(f"{'✅' if ok else '❌'} {k}")
