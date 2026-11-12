# -*- coding: utf-8 -*-
"""打包产物验证脚本：
1. 检查 dist/底稿工具箱GUI.exe 是否存在及大小；
2. 以 --gui-runner 内部模式跑一次「目录生成」任务，验证：
   - 数据文件(gui_runner.py、输出文件目录.py)能否在 _MEIPASS 中定位；
   - 子进程 stdout 能否被父进程捕获（windowed 模式关键验证点）；
   - 第三方库(openpyxl/pandas/docx)在冻结环境中可用。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "dist" / "底稿工具箱GUI.exe"

if not EXE.is_file():
    sys.exit(f"[失败] 未找到 {EXE}")

size_mb = EXE.stat().st_size / 1024 / 1024
print(f"[1] exe 存在：{EXE.name}  大小 {size_mb:.1f} MB")

# 准备一个小的多级目录树作为 dirgen 输入
tmp = Path(tempfile.mkdtemp(prefix="ibdw_exe_test_"))
target = tmp / "测试底稿"
(target / "第一章" / "1-1 底稿").mkdir(parents=True)
(target / "第二章" / "2-1 备查集").mkdir(parents=True)
(target / "第一章" / "1-1 底稿" / "a.docx").write_bytes(b"placeholder")
excel_out = tmp / "【测试底稿】目录.xlsx"

spec = json.dumps({
    "task": "dirgen",
    "params": {"target": str(target), "excel": str(excel_out), "word": None},
}, ensure_ascii=False)

print("[2] 运行 --gui-runner dirgen 任务 …")
proc = subprocess.run(
    [str(EXE), "--gui-runner", spec],
    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    errors="replace", timeout=180,
)
out = (proc.stdout or "") + (proc.stderr or "")
if out.strip():
    print("    —— 子进程输出（已成功捕获）——")
    for line in out.splitlines()[:20]:
        print("   ", line)
else:
    print("    [警告] 子进程无任何 stdout 输出（windowed 管道可能未接通）")

print(f"[3] 退出码 = {proc.returncode}")
if excel_out.is_file():
    print(f"[4] Excel 目录已生成：{excel_out.name} "
          f"({excel_out.stat().st_size} 字节) ✅")
    ok = True
else:
    print("[4] Excel 目录未生成 ❌")
    ok = False

print("\n结论：", "通过" if (ok and proc.returncode == 0 and out.strip()) else "存在问题，见上方日志")
