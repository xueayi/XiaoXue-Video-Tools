# -*- coding: utf-8 -*-
"""
GUI 配置模块：包含 PyQt6 GUI 的配置常量和图标获取函数。

注: 本文件保留以兼容可能引用 get_icon_path() 的其它模块。
主窗口配置已迁移至 src/ui/main_window.py 和 src/ui/theme.py。

M4.1 起 config.ini 位置由 :class:`src.platform.paths.PlatformPaths` 决定:
Windows 便携布局仍放在安装目录 (与旧版本一致); 安装目录不可写时回退
用户配置目录 (并把旧 config.ini 复制过去, copy-not-move)。
"""
import os
import sys
import tempfile
from pathlib import Path

from .platform.paths import APP_DIR_NAME, platform_paths
from .utils import get_base_dir, get_internal_dir

# 窗口基本配置
PROGRAM_NAME = "小雪工具箱"
PROGRAM_DESCRIPTION = "一个简单的视频压制与检测工具"

from ._version import __version__ as VERSION
DEFAULT_SIZE = (960, 720)

_warned_config_fallback = False


def _fallback_config_path() -> str:
    """平台路径解析失败时的最终兜底: 系统临时目录下的 config.ini。"""
    return os.path.join(tempfile.gettempdir(), APP_DIR_NAME, "config.ini")


def _warn_config_fallback(message: str):
    """配置降级警告只打印一次。"""
    global _warned_config_fallback
    if _warned_config_fallback:
        return
    _warned_config_fallback = True
    try:
        print(message, file=sys.stderr or sys.stdout)
    except Exception:
        pass


def get_config_path() -> str:
    """返回 config.ini 的完整路径 (不创建 QSettings; 供诊断/测试复用)。"""
    try:
        config_dir = Path(platform_paths().config_dir)
    except Exception:
        config_dir = None
    if config_dir is None:
        fallback = _fallback_config_path()
        _warn_config_fallback(
            f"[配置] 平台路径解析失败, 已回退临时目录: {fallback}")
        return fallback
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError):
        _warn_config_fallback(
            f"[配置] 配置目录不可写, 已回退临时目录: {_fallback_config_path()}")
        return _fallback_config_path()
    return str(config_dir / "config.ini")


def get_qsettings():
    """统一的 QSettings 入口: 便携式 config.ini (exe / 用户配置目录)。

    注意: 必须用「文件路径」构造 QSettings。双参 (org, app) 构造器
    在 Windows 上永远走注册表 (NativeFormat), setDefaultFormat 对它无效。

    QSettings 构造失败 (极端只读环境) 时降级到临时目录, 不让启动崩溃。
    """
    from PyQt6.QtCore import QSettings
    try:
        path = get_config_path()
        return QSettings(path, QSettings.Format.IniFormat)
    except Exception:
        fallback = _fallback_config_path()
        _warn_config_fallback(
            f"[配置] QSettings 初始化失败, 已回退临时目录: {fallback}")
        try:
            os.makedirs(os.path.dirname(fallback), exist_ok=True)
        except (OSError, ValueError):
            pass
        return QSettings(fallback, QSettings.Format.IniFormat)


def get_icon_path():
    """
    获取图标路径 (可选)。

    Returns:
        图标文件的绝对路径，如果未找到则返回 None
    """
    base = get_base_dir()
    internal = get_internal_dir()

    icon_internal = os.path.join(internal, "icon.ico")
    if os.path.exists(icon_internal):
        return icon_internal

    icon_base = os.path.join(base, "icon.ico")
    if os.path.exists(icon_base):
        return icon_base

    return None
