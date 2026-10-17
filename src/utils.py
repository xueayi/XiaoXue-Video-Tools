# -*- coding: utf-8 -*-
"""工具函数模块：路径处理、FFmpeg 可执行文件定位等。

M4.1 起:
    * 安装目录 / 只读资源目录分别由 :mod:`src.platform.paths` 提供
      (``install_dir`` / ``resource_dir``), 不再在这里重复 sys 判定;
    * ffmpeg/ffprobe 查找顺序 = 资源目录/安装目录 bin → 环境变量/配置
      → 系统 PATH; 不假设 ``.exe`` 后缀 (Windows 上带/不带后缀都尝试),
      内置与配置路径做 isfile + X_OK 校验; PATH 交给 ``shutil.which``。
"""
import configparser
import os
import shutil

from .platform.paths import (
    resolve_install_dir,
    resolve_resource_dir,
    resolve_user_config_dir,
)

#: 环境变量覆盖: 名称为 (专用, 通用) 两组, 前者优先
_ENV_OVERRIDES = {
    "ffmpeg": ("XIAOXUE_FFMPEG", "FFMPEG"),
    "ffprobe": ("XIAOXUE_FFPROBE", "FFPROBE"),
}


def get_base_dir() -> str:
    """获取应用程序安装目录 (exe 所在目录 / 开发模式仓库根)。

    兼容旧接口; 语义等同 ``PlatformPaths.install_dir``。
    """
    return str(resolve_install_dir())


def get_internal_dir() -> str:
    """获取只读资源目录 (``_MEIPASS`` / ``_internal`` / 开发模式仓库根)。

    兼容旧接口; 语义等同 ``PlatformPaths.resource_dir``。
    """
    return str(resolve_resource_dir())


# ----------------------------------------------------------------
# ffmpeg / ffprobe 解析
# ----------------------------------------------------------------

def _executable_names(stem: str):
    """候选可执行文件名: Windows 同时尝试带/不带 ``.exe``。"""
    if os.name == "nt":
        return (stem + ".exe", stem)
    return (stem,)


def _is_executable_file(path: str) -> bool:
    """内置/配置路径校验: 必须是文件且可执行 (Windows 上 X_OK 恒真)。"""
    try:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    except (OSError, ValueError):
        return False


def _find_bundled(stem: str):
    """步骤 1: 只读资源目录/bin 与安装目录/bin (便携覆盖) 查找。"""
    for directory in (get_internal_dir(), get_base_dir()):
        for name in _executable_names(stem):
            candidate = os.path.join(directory, "bin", name)
            if _is_executable_file(candidate):
                return candidate
    return None


def _read_config_override(stem: str):
    """从 config.ini 读取覆盖路径 (不依赖 Qt, 不产生目录副作用)。

    兼容两种键: ``[<stem>] path=...`` 与 ``[paths] <stem>=...``。
    """
    candidates = []
    try:
        candidates.append(resolve_install_dir() / "config.ini")
        candidates.append(resolve_user_config_dir() / "config.ini")
    except Exception:
        return None
    parser = configparser.ConfigParser()
    for config_path in candidates:
        try:
            if not config_path.is_file():
                continue
            parser.read(config_path, encoding="utf-8")
        except (OSError, ValueError, configparser.Error):
            continue
        values = []
        if parser.has_section(stem):
            values.append(parser.get(stem, "path", fallback=""))
        if parser.has_section("paths"):
            values.append(parser.get("paths", stem, fallback=""))
        for value in values:
            value = str(value or "").strip()
            if value and _is_executable_file(value):
                return value
    return None


def _find_configured(stem: str):
    """步骤 2: 环境变量与 config.ini 覆盖。"""
    for env_name in _ENV_OVERRIDES[stem]:
        value = os.environ.get(env_name, "").strip()
        if value and _is_executable_file(value):
            return value
    return _read_config_override(stem)


def _find_on_path(stem: str):
    """步骤 3: 系统 PATH (``shutil.which`` 自带可执行校验)。"""
    for name in _executable_names(stem):
        found = shutil.which(name)
        if found:
            return found
    return None


def _resolve_executable(stem: str) -> str:
    """按 内置 -> 配置 -> PATH 顺序解析; 最终回退裸名便于报错定位。"""
    for finder in (_find_bundled, _find_configured, _find_on_path):
        found = finder(stem)
        if found:
            return found
    return stem


def get_ffmpeg_path() -> str:
    """获取 ffmpeg 可执行文件路径。

    查找顺序: 资源目录/bin → 环境变量/配置 → 系统 PATH → ``"ffmpeg"``。
    """
    return _resolve_executable("ffmpeg")


def get_ffprobe_path() -> str:
    """获取 ffprobe 可执行文件路径 (顺序同 :func:`get_ffmpeg_path`)。"""
    return _resolve_executable("ffprobe")


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


def generate_output_path(input_path: str, encoder: str, output_ext: str = None) -> str:
    """
    根据输入路径和编码器生成输出路径。
    例如: input.mp4 + libx264 -> input_libx264.mp4

    Args:
        output_ext: 可选的输出扩展名 (如 ".mkv")，为空则保持输入扩展名。
    """
    base, ext = os.path.splitext(input_path)
    if output_ext:
        ext = output_ext if output_ext.startswith('.') else '.' + output_ext
    encoder_short = encoder.replace('lib', '').replace('_', '')
    return f"{base}_{encoder_short}{ext}"


def auto_generate_output_path(input_path: str, suffix: str, extension: str = None) -> str:
    """通用自动输出路径生成。
    
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
