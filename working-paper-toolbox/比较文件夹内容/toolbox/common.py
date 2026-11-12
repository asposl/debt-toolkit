"""共享常量与工具函数（原 folder_toolbox.py 公共配置区 + 共享工具函数区）。

注意：LOGS_DIR 锚定到包的上一级目录（即入口脚本所在目录），
保证日志仍然生成在「脚本同级 logs/」。打包运行时入口脚本在 _MEIPASS 临时目录，
此时由冻结入口注入 IBDW_LOG_ROOT，日志改写到 exe 同级的 logs/<模块名>/。
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from datetime import datetime
from pathlib import Path


# ==================== 默认参数（在 VSCode 中改这里后直接运行） ====================

SCRIPT_DIR = Path(__file__).resolve().parents[1]
# 打包运行时脚本位于 _MEIPASS 临时目录，日志写那里会随进程退出被删掉。
# 冻结入口会设置 IBDW_LOG_ROOT，把日志统一改写到 exe 同级的 logs/ 下。
_log_root = os.environ.get("IBDW_LOG_ROOT")
LOGS_DIR = (Path(_log_root) / SCRIPT_DIR.name) if _log_root else SCRIPT_DIR / "logs"

# compare / merge：被更新的旧文件夹 与 最新版来源文件夹
# 默认指向本工具目录下的样本 old/new（F5 可直接跑）；正式项目改成底稿根目录。
# 注意：merge 会按文件名覆盖 old，不要把正式底稿当 old 又不传命令行参数。
DEFAULT_OLD_FOLDER = SCRIPT_DIR / "old"
DEFAULT_NEW_FOLDER = SCRIPT_DIR / "new"

# extract：多级源文件夹 与 平铺输出文件夹（输出写到工具目录，不依赖 F:）
DEFAULT_SOURCE_FOLDER = SCRIPT_DIR / "new"
DEFAULT_OUTPUT_FOLDER = SCRIPT_DIR / "打印文件"

# extract 可选项
EXTENSIONS = {".doc", ".docx"}
ADD_ORDER_PREFIX = True   # True：按原目录顺序加 001_ 前缀；False：重名时自动加 __2
CLEAR_OUTPUT = False      # True：运行前清空输出文件夹中的 Word 文件

# ==============================================================================

CHUNK_SIZE = 1024 * 1024
_LOG_UNSAFE_PATTERN = re.compile(r'[\\/:*?"<>|$]')


# ==================== 共享工具函数 ====================


def file_sha256(path: Path) -> str:
    """Calculate a SHA-256 hash without loading the whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_relative_path(path: Path) -> str:
    return path.as_posix()


def validate_folder(root: Path, label: str) -> None:
    if not root.exists():
        raise FileNotFoundError(f"{label} 文件夹不存在: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"{label} 不是文件夹: {root}")


def is_temp_office_file(path: Path) -> bool:
    return path.name.startswith("~$")


def ensure_writable(path: Path) -> None:
    """清掉文件的只读属性。

    从光盘/网盘/下载目录复制出来的文件常带只读位（copy2 会连权限一起复制），
    下一轮「清空输出」时 unlink 会抛 WinError 5，因此复制后先解除只读。
    """
    try:
        mode = path.stat().st_mode
        if not mode & stat.S_IWRITE:
            path.chmod(mode | stat.S_IWRITE)
    except OSError:
        pass


def safe_unlink(path: Path) -> None:
    """删除文件：只读文件先解除只读再删；仍失败（被占用/无权限）则抛回 OSError。

    调用方应捕获 OSError 并记录，而不是让整个任务中断。
    """
    try:
        path.unlink()
        return
    except PermissionError:
        ensure_writable(path)
    path.unlink()


def make_log_path(action: str, project_label: str = "") -> Path:
    """生成 logs/{功能}_{时间戳}.log 形式的日志路径。

    项目名不进文件名（文件夹名里常带项目代号/主体名，一旦落进文件名就等于把
    项目信息写到了明面上）；日志正文仍会记录源目录，需要追溯时看正文即可。
    仅在显式设置环境变量 IBDW_LOG_LABEL=1 时才把项目名拼回文件名。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    keep_label = str(os.environ.get("IBDW_LOG_LABEL", "")).strip().lower() in {"1", "true", "yes", "on"}
    safe = _LOG_UNSAFE_PATTERN.sub("_", project_label or "").strip("_")[:40]
    stem = f"{action}_{safe}_{timestamp}" if (keep_label and safe) else f"{action}_{timestamp}"
    base = LOGS_DIR / stem
    log_path = base.with_suffix(".log")
    index = 2
    while log_path.exists():
        log_path = base.with_name(f"{base.name}_{index}.log")
        index += 1
    return log_path


def project_label_from(folder: Path) -> str:
    """取文件夹名作为项目名，便于在日志文件名中识别这次操作针对哪个项目。"""
    return folder.name or str(folder)


def write_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(text, encoding="utf-8-sig")


# ==================== 输出命名脱敏 ====================

PROJECT_TAG_ENV = "IBDW_PROJECT_TAG"


def default_project_tag() -> str:
    """项目标识默认取环境变量 IBDW_PROJECT_TAG；为空表示不做剥离。"""
    return str(os.environ.get(PROJECT_TAG_ENV, "") or "").strip()


def strip_project_suffix(filename: str, tag: str = "") -> str:
    """去掉文件名末尾的项目标识，例如 `xxx--26示例02.docx` → `xxx.docx`。

    只在明确传入 tag（或环境变量 IBDW_PROJECT_TAG）时生效，避免误伤正常文件名。
    """
    tag = str(tag or "").strip()
    if not tag:
        return filename
    stem, _, ext = filename.rpartition(".")
    if not stem:
        return filename
    pattern = re.compile(rf"[-_—]{{1,2}}[^-_—\s]{{0,6}}{re.escape(tag)}\d*$")
    stripped = pattern.sub("", stem).strip()
    return f"{stripped}{('.' + ext) if ext else ''}" if stripped else filename
