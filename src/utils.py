# -*- coding: utf-8 -*-
"""
工具函数模块：路径处理、FFmpeg 可执行文件定位等。
"""
import os
import sys


def get_base_dir() -> str:
    """
    获取应用程序根目录。
    - 如果是打包后的 exe，返回 exe 所在目录。
    - 如果是脚本运行，返回脚本所在目录。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的路径
        return os.path.dirname(sys.executable)
    else:
        # 脚本开发模式
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_ffmpeg_path() -> str:
    """获取 ffmpeg.exe 的绝对路径。"""
    return os.path.join(get_base_dir(), 'bin', 'ffmpeg.exe')


def get_ffprobe_path() -> str:
    """获取 ffprobe.exe 的绝对路径。"""
    return os.path.join(get_base_dir(), 'bin', 'ffprobe.exe')


def escape_path_for_ffmpeg(path: str) -> str:
    """
    对路径进行转义，以便在 FFmpeg 的 -vf subtitles 等滤镜中使用。
    Windows 路径中的反斜杠和冒号需要特殊处理。
    """
    # 替换反斜杠为正斜杠，再转义冒号
    path = path.replace('\\', '/')
    path = path.replace(':', r'\\:')
    return path
