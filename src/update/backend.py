# -*- coding: utf-8 -*-
"""更新后端协议、平台工厂与跨平台辅助 (M4.2)。

平台矩阵:
    * Windows → :class:`src.update.windows.WindowsUpdateBackend`
      (整包下载/校验/PowerShell 替换/重启, 支持 ``has_pending`` 恢复);
    * macOS   → :class:`src.update.macos.MacUpdateBackend`
      (check-only: 只检查版本并打开 Release 页面, 不下载/不替换);
    * 其它    → :class:`CheckOnlyBackend` (同上, 通用兜底)。

UI (M4.4) 只需依赖本模块的 :class:`UpdateBackend` 协议与
:func:`get_update_backend`, 并用 ``platform_capabilities().self_update_available``
决定是否展示「立即更新/重启安装」等写盘操作; ``supports_self_update``
为 False 的后端调用写盘方法会抛 :class:`UpdateNotSupportedError`
(继承 UpdateError, UI 已统一捕获展示, 不会崩溃)。
"""

import webbrowser
from typing import Optional, Protocol, runtime_checkable

from .checker import (
    REPO_URL,
    ReleaseInfo,
    UpdateNotSupportedError,
    fetch_latest,
)

#: check-only 后端对写盘操作给出的统一提示
_NOT_SUPPORTED_MESSAGE = (
    "当前平台不支持应用内自动更新，请打开 Release 页面手动下载安装包。")


@runtime_checkable
class UpdateBackend(Protocol):
    """更新后端协议 (Windows 自动更新 / macOS·其它 check-only)。"""

    #: 后端名称 (windows / macos / check-only), 用于日志与 UI 诊断
    name: str
    #: 是否支持应用内自动安装 (仅 Windows 为 True)
    supports_self_update: bool

    def check(self, current_version: str,
              timeout: float = 10.0) -> Optional[ReleaseInfo]:
        """检查新版本; 有更新返回 ReleaseInfo, 已最新返回 None。"""

    def download_and_prepare(
        self, release: ReleaseInfo, install_dir: str,
        progress_cb=None, check_cancel=None, stage_cb=None) -> str:
        """下载 + 校验 + 解压暂存, 返回更新器脚本路径 (Windows)。"""

    def install(self, install_dir: str, parent_pid: int) -> bool:
        """拉起外部更新器 (主程序随后退出由更新器替换并重启)。"""

    def has_pending(self, install_dir: str) -> bool:
        """是否有已下载就绪、等待替换的更新 (仅 Windows 可能为 True)。"""

    def cleanup(self, install_dir: str) -> None:
        """清理旧版备份/暂存目录 (启动时调用, 安全幂等)。"""

    def release_page_url(self, release: Optional[ReleaseInfo] = None) -> str:
        """返回 Release 页面 URL (无具体版本时返回最新发行页)。"""

    def open_release_page(self, release: Optional[ReleaseInfo] = None) -> str:
        """在浏览器打开 Release 页面并返回该 URL (check-only 的「下载」入口)。"""


class CheckOnlyBackend:
    """通用 check-only 后端: 只检查更新 + 打开 Release 页面。

    用于 macOS 之外的其它非 Windows 平台, 也是 macOS 后端的基类。
    """

    name = "check-only"
    supports_self_update = False

    def check(self, current_version: str,
              timeout: float = 10.0) -> Optional[ReleaseInfo]:
        # 只关心版本信息与发行页 URL, 不要求存在本平台安装包资产
        return fetch_latest(
            current_version, timeout=timeout, require_asset=False)

    def download_and_prepare(self, release, install_dir, progress_cb=None,
                             check_cancel=None, stage_cb=None) -> str:
        raise UpdateNotSupportedError(_NOT_SUPPORTED_MESSAGE)

    def install(self, install_dir: str, parent_pid: int) -> bool:
        raise UpdateNotSupportedError(_NOT_SUPPORTED_MESSAGE)

    def has_pending(self, install_dir: str) -> bool:
        return False

    def cleanup(self, install_dir: str) -> None:
        return None

    def release_page_url(self, release: Optional[ReleaseInfo] = None) -> str:
        html_url = getattr(release, "html_url", "") if release is not None else ""
        return html_url or f"{REPO_URL}/releases/latest"

    def open_release_page(self, release: Optional[ReleaseInfo] = None) -> str:
        url = self.release_page_url(release)
        webbrowser.open(url)
        return url


def get_update_backend(platform: Optional[str] = None,
                       capabilities=None) -> UpdateBackend:
    """按平台/能力选择更新后端。

    Args:
        platform: 覆盖平台标识 (``sys.platform`` 值, 测试用)。
        capabilities: 覆盖平台能力快照 (测试用); 缺省读取
            :func:`src.platform.capabilities.platform_capabilities`。

    选择规则:
        * win32 且 ``self_update_available`` → WindowsUpdateBackend;
        * darwin → MacUpdateBackend;
        * 其它 (含 Windows 但能力不可用) → CheckOnlyBackend。
    """
    if capabilities is None:
        from ..platform.capabilities import platform_capabilities
        capabilities = platform_capabilities()
    os_name = platform or capabilities.os_name

    if os_name == "win32" and capabilities.self_update_available:
        from .windows import WindowsUpdateBackend
        return WindowsUpdateBackend()
    if os_name == "darwin":
        from .macos import MacUpdateBackend
        return MacUpdateBackend()
    return CheckOnlyBackend()


# ----------------------------------------------------------------
# 跳过版本 (QSettings; 跨平台共享)
# ----------------------------------------------------------------

def _settings():
    from ..gui_config import get_qsettings
    return get_qsettings()


def get_skip_version() -> str:
    """读取用户「跳过此版本」设置; 无设置返回空串。"""
    return str(_settings().value("update/skip_version", "") or "")


def set_skip_version(version: str) -> None:
    """记录用户「跳过此版本」。"""
    _settings().setValue("update/skip_version", version)
