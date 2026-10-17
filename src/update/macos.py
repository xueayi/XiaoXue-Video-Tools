# -*- coding: utf-8 -*-
"""macOS 更新后端 (M4.2, check-only)。

首版不做应用内自动替换 (需要签名/公证/Apple Silicon 实机验证), 只支持:
检查 GitHub Release → 提示新版本 → 打开 Release 页面手动下载。

因此 ``download_and_prepare`` / ``install`` 一律抛
:class:`UpdateNotSupportedError` (继承 UpdateError, UI 统一捕获展示),
``has_pending`` 恒 False, ``cleanup`` 为空操作; M4.4 的 UI 应通过
``platform_capabilities().self_update_available`` 隐藏写盘入口。
"""

import webbrowser
from typing import Optional

from .backend import CheckOnlyBackend
from .checker import (
    MACOS_ASSET_SUFFIX,
    REPO_URL,
    ReleaseInfo,
    UpdateNotSupportedError,
    fetch_latest,
)

_MACOS_NOT_SUPPORTED_MESSAGE = (
    "macOS 版暂不支持应用内自动更新，请打开 Release 页面下载安装包。")


def release_page_url(release: Optional[ReleaseInfo] = None) -> str:
    """返回 Release 页面 URL; 没有具体发行信息时返回最新发行页。"""
    html_url = getattr(release, "html_url", "") if release is not None else ""
    return html_url or f"{REPO_URL}/releases/latest"


def open_release_page(release: Optional[ReleaseInfo] = None) -> str:
    """在浏览器打开 Release 页面并返回 URL。"""
    url = release_page_url(release)
    webbrowser.open(url)
    return url


class MacUpdateBackend(CheckOnlyBackend):
    """macOS check-only 更新后端。"""

    name = "macos"
    supports_self_update = False
    #: 未来 macOS 自动更新使用的资产后缀 (首版不下载, 仅记录约定)
    asset_suffix = MACOS_ASSET_SUFFIX

    def check(self, current_version: str,
              timeout: float = 10.0) -> Optional[ReleaseInfo]:
        return fetch_latest(
            current_version,
            timeout=timeout,
            asset_suffix=self.asset_suffix,
            require_asset=False,
        )

    def download_and_prepare(self, release, install_dir, progress_cb=None,
                             check_cancel=None, stage_cb=None) -> str:
        raise UpdateNotSupportedError(_MACOS_NOT_SUPPORTED_MESSAGE)

    def install(self, install_dir: str, parent_pid: int) -> bool:
        raise UpdateNotSupportedError(_MACOS_NOT_SUPPORTED_MESSAGE)

    def has_pending(self, install_dir: str) -> bool:
        return False

    def cleanup(self, install_dir: str) -> None:
        return None

    def release_page_url(self, release: Optional[ReleaseInfo] = None) -> str:
        return release_page_url(release)

    def open_release_page(self, release: Optional[ReleaseInfo] = None) -> str:
        return open_release_page(release)
