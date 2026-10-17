# -*- coding: utf-8 -*-
"""更新包 (M4.2): Windows 自动更新 + macOS/其它 check-only。

模块划分:
    * :mod:`~src.update.version`   —— 版本解析/比较 (纯函数)
    * :mod:`~src.update.checker`   —— GitHub Release 检查 + 下载 + SHA256 校验
    * :mod:`~src.update.backend`   —— ``UpdateBackend`` 协议 + 平台工厂 + 跳过版本
    * :mod:`~src.update.windows`   —— Windows 整包自动更新 (PowerShell 替换)
    * :mod:`~src.update.macos`     —— macOS check-only (只提示 + 打开 Release 页)

旧模块 :mod:`src.updater` 保留为兼容门面, 现有 UI/测试的导入路径不变。
"""

from .version import is_dev_version, is_newer, parse_version
from .checker import (
    CHUNK_SIZE,
    MACOS_ASSET_SUFFIX,
    RELEASES_LATEST_API,
    REPO_URL,
    WINDOWS_ASSET_SUFFIX,
    ReleaseInfo,
    UpdateError,
    UpdateNotSupportedError,
    _pick_asset,
    download,
    ensure_free_space,
    fetch_checksum,
    fetch_latest,
    find_asset,
    parse_checksums_from_body,
    resolve_checksum,
    sha256_of,
    verify_sha256,
)
from .backend import (
    CheckOnlyBackend,
    UpdateBackend,
    get_skip_version,
    get_update_backend,
    set_skip_version,
)
from .macos import (
    MacUpdateBackend,
    open_release_page,
    release_page_url,
)
from .windows import (
    BACKUP_DIR,
    LEGACY_STAGING_DIR,
    STAGING_DIR_NAME,
    UPDATER_PS1,
    ZIP_NAME,
    WindowsUpdateBackend,
    cleanup_staging,
    ensure_disk_space,
    has_pending_update,
    launch_updater,
    prepare,
    staging_dir,
)

__all__ = [
    "BACKUP_DIR",
    "CHUNK_SIZE",
    "CheckOnlyBackend",
    "LEGACY_STAGING_DIR",
    "MACOS_ASSET_SUFFIX",
    "MacUpdateBackend",
    "RELEASES_LATEST_API",
    "REPO_URL",
    "ReleaseInfo",
    "STAGING_DIR_NAME",
    "UPDATER_PS1",
    "UpdateBackend",
    "UpdateError",
    "UpdateNotSupportedError",
    "WINDOWS_ASSET_SUFFIX",
    "WindowsUpdateBackend",
    "ZIP_NAME",
    "_pick_asset",
    "cleanup_staging",
    "download",
    "ensure_disk_space",
    "ensure_free_space",
    "fetch_checksum",
    "fetch_latest",
    "find_asset",
    "get_skip_version",
    "get_update_backend",
    "has_pending_update",
    "is_dev_version",
    "is_newer",
    "launch_updater",
    "open_release_page",
    "parse_checksums_from_body",
    "parse_version",
    "prepare",
    "release_page_url",
    "resolve_checksum",
    "set_skip_version",
    "sha256_of",
    "staging_dir",
    "verify_sha256",
]
