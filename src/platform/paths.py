# -*- coding: utf-8 -*-
"""平台路径解析 (M4.1)。

目标: 把「打包资源目录」和「用户可写目录」彻底分开, 并为 macOS 等
非 Windows 平台准备好用户目录语义。

约定:
    * ``resource_dir``: 随程序分发的只读资源 (bin/ image/ icon);
      打包后是 ``sys._MEIPASS`` / ``_internal``, 开发时是仓库根;
    * ``install_dir``: 可执行文件所在目录 (便携版自更新/备份仍用它);
    * ``config_dir`` / ``data_dir`` / ``cache_dir`` / ``log_dir``:
      用户可写目录; **绝不**指向 ``resource_dir`` 内的只读区域;
    * ``temp_dir``: 进程级临时目录。

Windows 默认 Portable 模式: 以上可写目录都放在 ``install_dir`` 旁
(配置/日志布局与旧版本一致); 目录不可写时逐级回退::

    portable(install_dir) -> 用户目录(%APPDATA%/%LOCALAPPDATA%) -> 临时目录

非 Windows 直接使用用户目录 (优先 Qt ``QStandardPaths``, 无 Qt 时按
XDG / macOS 约定用环境变量回退), 不做 portable。

本模块的所有目录解析/创建都**绝不抛出**: ``mkdir`` 或写探测失败时继续
尝试下一级候选, 最终兜底到临时目录。
"""

import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

#: 用户目录统一使用 ASCII 应用名 (跨平台稳定, 不随 exe 中文名变化)
APP_DIR_NAME = "XiaoXueToolbox"

#: 目录可写性探测用的临时文件名
_WRITE_PROBE_NAME = ".xiaoxue_write_test"

_paths_lock = threading.Lock()
_paths: Optional["PlatformPaths"] = None


# ----------------------------------------------------------------
# 平台 / 基础目录判定 (均为可 monkeypatch 的小函数, 便于单测)
# ----------------------------------------------------------------

def _is_windows() -> bool:
    """当前是否 Windows (单测可 monkeypatch 本函数模拟平台)。"""
    return os.name == "nt"


def _is_macos() -> bool:
    """当前是否 macOS。"""
    return sys.platform == "darwin"


def _repo_root() -> Path:
    """开发模式仓库根目录 (src/platform/paths.py 上两级)。"""
    return Path(__file__).resolve().parents[2]


def resolve_install_dir() -> Path:
    """可执行文件所在目录; 开发模式为仓库根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return _repo_root()


def resolve_resource_dir() -> Path:
    """只读打包资源目录; 打包后为 ``_MEIPASS`` / ``_internal``。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return resolve_install_dir() / "_internal"
    return _repo_root()


# ----------------------------------------------------------------
# 用户目录: 优先 Qt QStandardPaths, 回退环境变量 / 系统约定
# ----------------------------------------------------------------

def _qt_writable_location(location_name: str) -> Optional[Path]:
    """读取 Qt 标准目录并归一为 ``<base>/XiaoXueToolbox``。

    Qt 在未设置 applicationName 时可能把可执行文件名 (含开发期的
    ``python``) 拼进路径, 这里统一替换为 ASCII 应用名, 保证目录稳定。
    Qt 不可用时返回 None。
    """
    try:
        from PyQt6.QtCore import QStandardPaths
        location = getattr(QStandardPaths.StandardLocation, location_name)
        raw = QStandardPaths.writableLocation(location)
    except Exception:
        return None
    if not raw:
        return None
    try:
        path = Path(raw)
        if path.name == APP_DIR_NAME:
            return path
        return path.parent / APP_DIR_NAME
    except (OSError, ValueError):
        return None


def _windows_base_env(var: str) -> Path:
    """Windows 用户基础目录: 环境变量缺失时按系统盘默认约定回退。"""
    value = os.environ.get(var)
    if value:
        return Path(value)
    home = Path.home()
    if var == "APPDATA":
        return home / "AppData" / "Roaming"
    return home / "AppData" / "Local"


def _darwin_base(kind: str) -> Path:
    sub = {
        "config": "Preferences",
        "data": "Application Support",
        "cache": "Caches",
        "log": "Logs",
    }[kind]
    return Path.home() / "Library" / sub


def _xdg_base(kind: str) -> Path:
    home = Path.home()
    if kind == "config":
        return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    if kind == "data":
        return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache")


def _fallback_user_dir(kind: str) -> Path:
    """无 Qt / Qt 失败时, 按各平台约定拼出用户目录。"""
    if _is_windows():
        base = _windows_base_env("APPDATA" if kind in ("config", "data")
                                 else "LOCALAPPDATA")
        if kind in ("config", "data"):
            return base / APP_DIR_NAME
        sub = "Cache" if kind == "cache" else "Logs"
        return base / APP_DIR_NAME / sub
    if _is_macos():
        base = _darwin_base(kind)
        if kind in ("config", "data"):
            return base / APP_DIR_NAME
        return base / APP_DIR_NAME
    base = _xdg_base(kind)
    if kind == "cache":
        return base / APP_DIR_NAME
    if kind == "log":
        return base / APP_DIR_NAME / "logs"
    return base / APP_DIR_NAME


def resolve_user_config_dir() -> Path:
    """用户配置目录 (QSettings/config.ini 所在)。"""
    qt = _qt_writable_location("AppConfigLocation")
    return qt if qt is not None else _fallback_user_dir("config")


def resolve_user_data_dir() -> Path:
    """用户数据目录 (报告/默认输出等)。"""
    qt = _qt_writable_location("AppDataLocation")
    return qt if qt is not None else _fallback_user_dir("data")


def resolve_user_cache_dir() -> Path:
    """用户缓存目录。

    Windows 上按 %LOCALAPPDATA%\\XiaoXueToolbox\\Cache 布局, 其它平台用
    Qt CacheLocation / XDG cache。
    """
    if _is_windows():
        base = _qt_writable_location("AppLocalDataLocation")
        if base is None:
            return _fallback_user_dir("cache")
        return base / "Cache"
    qt = _qt_writable_location("CacheLocation")
    return qt if qt is not None else _fallback_user_dir("cache")


def resolve_user_log_dir() -> Path:
    """用户日志目录。

    Windows 上按 %LOCALAPPDATA%\\XiaoXueToolbox\\Logs 布局; macOS 用
    ~/Library/Logs/XiaoXueToolbox; 其它平台用数据目录下的 logs/。
    """
    if _is_windows():
        base = _qt_writable_location("AppLocalDataLocation")
        if base is None:
            return _fallback_user_dir("log")
        return base / "Logs"
    if _is_macos():
        return Path.home() / "Library" / "Logs" / APP_DIR_NAME
    qt = _qt_writable_location("GenericDataLocation")
    base = qt / "logs" if qt is not None else _fallback_user_dir("log")
    return base


def resolve_temp_dir() -> Path:
    """进程级临时目录 (Qt TempLocation / 系统临时目录 + 应用子目录)。"""
    qt = _qt_writable_location("TempLocation")
    if qt is not None:
        return qt
    return Path(tempfile.gettempdir()) / APP_DIR_NAME


# ----------------------------------------------------------------
# 目录可写性判定与链式回退
# ----------------------------------------------------------------

def ensure_dir(path: Path) -> bool:
    """尝试创建目录并做一次写探测; 成功返回 True, 任何异常返回 False。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / _WRITE_PROBE_NAME
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except (OSError, ValueError):
        return False


def _first_available(candidates: Sequence[Path]) -> Path:
    """按顺序返回第一个可创建/可写的目录; 全部失败时返回最后一个候选。

    绝不抛出: 最后一个候选即使不可写也返回, 由调用方在真正写入时兜底。
    """
    last = candidates[-1]
    for candidate in candidates:
        try:
            if ensure_dir(candidate):
                return candidate
        except Exception:  # pragma: no cover - ensure_dir 已兜底, 双保险
            continue
    return last


def _dir_writable(path: Path) -> bool:
    """轻量可写判定 (不创建目录/不写文件, 供 get_log_dir 等只读场景)。"""
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


# ----------------------------------------------------------------
# PlatformPaths
# ----------------------------------------------------------------

@dataclass(frozen=True)
class PlatformPaths:
    """一次路径解析的不可变结果。

    Attributes:
        resource_dir: 只读资源目录 (bin/ image/ icon), 永不可写。
        install_dir: 可执行文件所在目录; Windows portable 自更新使用。
        config_dir: 配置目录 (config.ini)。
        data_dir: 用户数据目录。
        cache_dir: 缓存目录 (能力探测缓存 / 更新暂存等)。
        log_dir: 日志目录。
        temp_dir: 进程级临时目录。
    """

    resource_dir: Path
    install_dir: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path
    temp_dir: Path

    @property
    def portable(self) -> bool:
        """是否 Windows 便携模式 (配置直接落在安装目录)。"""
        return self.config_dir == self.install_dir

    def as_dict(self) -> dict:
        """路径字典 (日志/诊断用)。"""
        return {
            "resource_dir": str(self.resource_dir),
            "install_dir": str(self.install_dir),
            "config_dir": str(self.config_dir),
            "data_dir": str(self.data_dir),
            "cache_dir": str(self.cache_dir),
            "log_dir": str(self.log_dir),
            "temp_dir": str(self.temp_dir),
            "portable": self.portable,
        }


def _candidates(*items: Optional[Path]) -> list:
    """过滤 None 候选 (单级解析失败不影响整条回退链)。"""
    return [item for item in items if item is not None]


def _safe(fn) -> Optional[Path]:
    """调用目录解析函数; 异常时返回 None (由回退链继续)。"""
    try:
        return Path(fn())
    except Exception:
        return None


def _migrate_legacy_config(paths: "PlatformPaths") -> None:
    """把安装目录下的旧 config.ini 复制到新的用户配置目录。

    copy-not-move: 源文件保留, 老版本回退运行仍可读到配置;
    新位置已有配置时不覆盖。
    """
    try:
        if paths.config_dir == paths.install_dir:
            return
        legacy = paths.install_dir / "config.ini"
        target = paths.config_dir / "config.ini"
        if not legacy.is_file() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
    except (OSError, ValueError):
        pass


def _detect_impl() -> "PlatformPaths":
    install_dir = resolve_install_dir()
    resource_dir = resolve_resource_dir()

    temp_candidates = _candidates(
        _safe(resolve_temp_dir),
        Path(tempfile.gettempdir()) / APP_DIR_NAME,
    )
    temp_dir = _first_available(temp_candidates)

    if _is_windows():
        config_candidates = _candidates(
            install_dir,
            _safe(resolve_user_config_dir),
            temp_dir / "config",
        )
        data_candidates = _candidates(
            install_dir,
            _safe(resolve_user_data_dir),
            temp_dir / "data",
        )
        cache_candidates = _candidates(
            install_dir / "_cache",
            _safe(resolve_user_cache_dir),
            temp_dir / "cache",
        )
        log_candidates = _candidates(
            install_dir,
            _safe(resolve_user_log_dir),
            temp_dir / "logs",
        )
    else:
        # 非 Windows 不做 portable: 资源只读, 用户数据一律进用户目录
        config_candidates = _candidates(
            _safe(resolve_user_config_dir), temp_dir / "config")
        data_candidates = _candidates(
            _safe(resolve_user_data_dir), temp_dir / "data")
        cache_candidates = _candidates(
            _safe(resolve_user_cache_dir), temp_dir / "cache")
        log_candidates = _candidates(
            _safe(resolve_user_log_dir), temp_dir / "logs")

    paths = PlatformPaths(
        resource_dir=resource_dir,
        install_dir=install_dir,
        config_dir=_first_available(config_candidates),
        data_dir=_first_available(data_candidates),
        cache_dir=_first_available(cache_candidates),
        log_dir=_first_available(log_candidates),
        temp_dir=temp_dir,
    )
    _migrate_legacy_config(paths)
    return paths


def _fallback_paths() -> "PlatformPaths":
    """最终兜底: 任何解析/创建异常都退化为临时目录布局, 不抛出。"""
    install_dir = _safe(resolve_install_dir) or _repo_root()
    resource_dir = _safe(resolve_resource_dir) or install_dir
    temp_dir = _safe(resolve_temp_dir) or (
        Path(tempfile.gettempdir()) / APP_DIR_NAME)
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError):
        pass
    return PlatformPaths(
        resource_dir=resource_dir,
        install_dir=install_dir,
        config_dir=temp_dir / "config",
        data_dir=temp_dir / "data",
        cache_dir=temp_dir / "cache",
        log_dir=temp_dir / "logs",
        temp_dir=temp_dir,
    )


def detect() -> "PlatformPaths":
    """解析一套平台路径 (带完整回退链); 绝不抛出。"""
    try:
        return _detect_impl()
    except Exception:
        return _fallback_paths()


def platform_paths() -> "PlatformPaths":
    """进程级路径单例 (多个模块共享同一套目录)。"""
    global _paths
    with _paths_lock:
        if _paths is None:
            _paths = detect()
        return _paths


def reset_platform_paths() -> None:
    """清空单例 (测试 / 运行环境变化后重新解析)。"""
    global _paths
    with _paths_lock:
        _paths = None


# ----------------------------------------------------------------
# 单文件类便捷函数 (日志等只需要单一目录时使用)
# ----------------------------------------------------------------

def resolve_log_dir() -> Path:
    """日志目录 (不创建/不写探测, 供启动早期调用)。

    Windows 便携布局下沿用 ``install_dir`` 保持现有日志位置; 安装目录
    不可写时回退用户日志目录。其它平台直接使用用户日志目录。
    """
    if _is_windows():
        install_dir = resolve_install_dir()
        if _dir_writable(install_dir):
            return install_dir
        return resolve_user_log_dir()
    return resolve_user_log_dir()
