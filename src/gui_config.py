# -*- coding: utf-8 -*-
"""
GUI 配置模块：包含 PyQt6 GUI 的配置常量和图标获取函数。

注: 本文件保留以兼容可能引用 get_icon_path() 的其它模块。
主窗口配置已迁移至 src/ui/main_window.py 和 src/ui/theme.py。
"""
import os

from .utils import get_base_dir, get_internal_dir

# 窗口基本配置
PROGRAM_NAME = "小雪工具箱"
PROGRAM_DESCRIPTION = "一个简单的视频压制与检测工具"

from ._version import __version__ as VERSION
DEFAULT_SIZE = (960, 720)


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
