# -*- coding: utf-8 -*-
"""平台抽象层 (M4.1)。

三个子模块:

* :mod:`src.platform.paths` —— ``PlatformPaths`` 资源/用户可写目录分离与
  回退链 (Windows 默认 portable, 不可写逐级回退用户目录/临时目录);
* :mod:`src.platform.capabilities` —— ``PlatformCapabilities`` 平台能力聚合
  (平台判定 / ffmpeg 路径 / M3 能力快照 / AviSynth / 自更新 / VideoToolbox);
* :mod:`src.platform.process` —— 子进程平台参数 (``CREATE_NO_WINDOW``)。

注意: ``capabilities`` 依赖 ``src.utils``, 而 ``src.utils`` 又会导入
``src.platform.paths``; 为避免循环导入, capabilities 的导出使用模块级
``__getattr__`` 懒加载。
"""

from .paths import (
    APP_DIR_NAME,
    PlatformPaths,
    detect as detect_platform_paths,
    ensure_dir,
    platform_paths,
    reset_platform_paths,
    resolve_install_dir,
    resolve_log_dir,
    resolve_resource_dir,
    resolve_temp_dir,
    resolve_user_cache_dir,
    resolve_user_config_dir,
    resolve_user_data_dir,
    resolve_user_log_dir,
)
from .process import CREATE_NO_WINDOW, no_window_kwargs

#: capabilities 子模块按需懒加载: 公开名 -> 子模块属性名
_CAPABILITIES_EXPORTS = {
    "PlatformCapabilities": "PlatformCapabilities",
    "VIDEOTOOLBOX_ENCODERS": "VIDEOTOOLBOX_ENCODERS",
    "detect_capabilities": "detect",
    "platform_capabilities": "platform_capabilities",
    "reset_platform_capabilities": "reset_platform_capabilities",
    "reset_capabilities": "reset_platform_capabilities",
}

__all__ = [
    "APP_DIR_NAME",
    "CREATE_NO_WINDOW",
    "PlatformPaths",
    "detect_capabilities",
    "detect_platform_paths",
    "ensure_dir",
    "no_window_kwargs",
    "platform_capabilities",
    "platform_paths",
    "reset_capabilities",
    "reset_platform_capabilities",
    "reset_platform_paths",
    "resolve_install_dir",
    "resolve_log_dir",
    "resolve_resource_dir",
    "resolve_temp_dir",
    "resolve_user_cache_dir",
    "resolve_user_config_dir",
    "resolve_user_data_dir",
    "resolve_user_log_dir",
]


def __getattr__(name: str):
    """按需导入 capabilities 导出, 打破 utils <-> platform 的循环导入。"""
    target = _CAPABILITIES_EXPORTS.get(name)
    if target is not None:
        from . import capabilities

        value = getattr(capabilities, target)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_CAPABILITIES_EXPORTS))
