# -*- coding: utf-8 -*-
"""
工具函数模块：路径处理、FFmpeg 可执行文件定位等。
"""
import os
import sys
import shutil


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


def get_internal_dir() -> str:
    """
    获取 PyInstaller 打包后的 _internal 目录。
    - 打包后: _MEIPASS 或 exe 同级的 _internal 目录
    - 开发模式: 项目根目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller >= 6.0 使用 _internal 目录
        # 优先使用 _MEIPASS (onefile 模式)
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        # onedir 模式: _internal 在 exe 同级
        return os.path.join(os.path.dirname(sys.executable), '_internal')
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_ffmpeg_path() -> str:
    """
    获取 ffmpeg 可执行文件的路径。
    查找顺序：
    1. _internal/bin (PyInstaller 打包环境)
    2. 项目根目录/bin (开发环境)
    3. 系统 PATH 环境变量
    4. 回退到 'ffmpeg' (让命令执行时报错)
    """
    exe_name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    
    # 1. 检查 _internal/bin (打包环境)
    internal_path = os.path.join(get_internal_dir(), 'bin', exe_name)
    if os.path.exists(internal_path):
        return internal_path
    
    # 2. 检查项目根目录/bin (开发环境)
    base_path = os.path.join(get_base_dir(), 'bin', exe_name)
    if os.path.exists(base_path):
        return base_path
    
    # 3. 回退到系统 PATH 查找
    system_ffmpeg = shutil.which('ffmpeg')
    if system_ffmpeg:
        return system_ffmpeg
    
    # 4. 最终回退 (让后续命令调用报错，便于排查)
    return 'ffmpeg'


def get_ffprobe_path() -> str:
    """
    获取 ffprobe 可执行文件的路径。
    查找顺序：
    1. _internal/bin (PyInstaller 打包环境)
    2. 项目根目录/bin (开发环境)
    3. 系统 PATH 环境变量
    4. 回退到 'ffprobe' (让命令执行时报错)
    """
    exe_name = 'ffprobe.exe' if os.name == 'nt' else 'ffprobe'
    
    # 1. 检查 _internal/bin (打包环境)
    internal_path = os.path.join(get_internal_dir(), 'bin', exe_name)
    if os.path.exists(internal_path):
        return internal_path
    
    # 2. 检查项目根目录/bin (开发环境)
    base_path = os.path.join(get_base_dir(), 'bin', exe_name)
    if os.path.exists(base_path):
        return base_path
    
    # 3. 回退到系统 PATH 查找
    system_ffprobe = shutil.which('ffprobe')
    if system_ffprobe:
        return system_ffprobe
    
    # 4. 最终回退 (让后续命令调用报错，便于排查)
    return 'ffprobe'


def escape_path_for_ffmpeg(path: str) -> str:
    """
    对路径进行转义，以便在 FFmpeg 的 -vf subtitles 等滤镜中使用。
    Windows 路径中的反斜杠和冒号需要特殊处理。
    
    FFmpeg subtitles 滤镜需要:
    1. 反斜杠转为正斜杠
    2. 冒号转义为 \\:
    3. 单引号需要额外处理
    """
    # 替换反斜杠为正斜杠
    path = path.replace('\\', '/')
    # 转义冒号 (FFmpeg 滤镜语法要求)
    path = path.replace(':', '\\:')
    # 转义单引号
    path = path.replace("'", "'\\''")
    return path


def generate_output_path(input_path: str, encoder: str) -> str:
    """
    根据输入路径和编码器生成输出路径。
    例如: input.mp4 + libx264 -> input_libx264.mp4
    """
    base, ext = os.path.splitext(input_path)
    # 简化编码器名称
    encoder_short = encoder.replace('lib', '').replace('_', '')
    return f"{base}_{encoder_short}{ext}"


def auto_generate_output_path(input_path: str, suffix: str, extension: str = None) -> str:
    """
    通用自动输出路径生成。
    
    Args:
        input_path: 输入文件路径
        suffix: 追加的后缀 (如 "_remux")
        extension: 输出扩展名 (包含点, 如 ".mp4")。如果为 None，则沿用输入文件的扩展名。
    
    Returns:
        生成的输出路径
    """
    base, input_ext = os.path.splitext(input_path)
    if extension is None:
        extension = input_ext
    
    return f"{base}{suffix}{extension}"
