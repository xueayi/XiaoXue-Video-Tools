# -*- coding: utf-8 -*-
"""应用自更新 —— 兼容门面 (M4.2)。

实现已拆分到 :mod:`src.update` 包, 本模块只保留**旧对外 API** (现有
``src/ui`` 与测试无需修改):

    * 版本比较:    parse_version / is_newer / is_dev_version
    * Release 检查: fetch_latest / ReleaseInfo / REPO_URL
    * 下载与校验:  download / sha256_of / verify_sha256 / resolve_checksum /
                   fetch_checksum / parse_checksums_from_body
    * Windows 安装: prepare / launch_updater / has_pending_update /
                   cleanup_staging / ensure_disk_space
    * 跳过版本:    get_skip_version / set_skip_version

平台差异:
    * ``STAGING_DIR`` 现在指向 :func:`src.update.windows.staging_dir`
      (即 ``PlatformPaths.cache_dir/update``, 绝对路径), 旧 UI 里
      ``os.path.join(install_dir, STAGING_DIR, "update.zip")`` 依然可用,
      且下载/解压暂存自动落到用户可写 cache 目录;
    * Windows 专有符号在 macOS/其它平台优雅降级: ``launch_updater`` 返回
      False、``has_pending_update`` 返回 False、``cleanup_staging`` 空操作;
      ``prepare`` 抛 :class:`UpdateError` 子类 (UI 统一捕获并展示友好文案)。

新代码 (M4.4 起) 请直接使用 :mod:`src.update` 的
``get_update_backend()`` 与 ``PlatformCapabilities.self_update_available``。
"""

import subprocess  # noqa: F401 - 既有 monkeypatch 入口 (src.updater.subprocess.Popen)

import requests  # noqa: F401 - 保留为既有 monkeypatch 入口 (src.updater.requests)

from .update import (
    BACKUP_DIR,
    CHUNK_SIZE,
    RELEASES_LATEST_API,
    REPO_URL,
    ReleaseInfo,
    UpdateError,
    UpdateNotSupportedError,
    _pick_asset as _pick_asset_impl,
    download as _download,
    ensure_disk_space as _ensure_disk_space,
    fetch_checksum as _fetch_checksum,
    fetch_latest as _fetch_latest,
    get_skip_version as _get_skip_version,
    is_dev_version,
    is_newer,
    parse_checksums_from_body as _parse_checksums_from_body,
    parse_version,
    resolve_checksum as _resolve_checksum,
    set_skip_version as _set_skip_version,
    sha256_of as _sha256_of,
    verify_sha256 as _verify_sha256,
)
from .update import windows as _windows

#: 旧常量: 更新器脚本 (私有, 保留兼容)
_BACKUP_DIR = BACKUP_DIR

#: 旧组织/应用名 (未使用, 保留兼容)
_ORG = "XiaoXue"
_APP = "XiaoXueToolbox"


# ----------------------------------------------------------------
# 版本 / Release 检查 (委托 src.update)
# ----------------------------------------------------------------

def fetch_latest(current_version: str, timeout: float = 10.0):
    """查询最新正式版 (按当前平台选择后端; Windows 要求匹配安装包资产)。"""
    from .update.backend import get_update_backend

    return get_update_backend().check(current_version, timeout=timeout)


def _pick_asset(assets: list) -> dict:
    """旧接口: 挑选标准版 Windows 安装包 (兼容保留)。"""
    return _pick_asset_impl(assets)


# ----------------------------------------------------------------
# 下载与校验 (委托 src.update.checker)
# ----------------------------------------------------------------

def download(url: str, dest: str, progress_cb=None, check_cancel=None) -> None:
    """流式下载安装包 (断点续传/取消)。"""
    return _download(url, dest, progress_cb=progress_cb,
                     check_cancel=check_cancel)


def sha256_of(path: str) -> str:
    """计算文件 SHA256。"""
    return _sha256_of(path)


def verify_sha256(path: str, expected: str) -> bool:
    """校验文件 SHA256。"""
    return _verify_sha256(path, expected)


def parse_checksums_from_body(body: str) -> dict:
    """解析 Release 正文内嵌的 SHA256 校验和表。"""
    return _parse_checksums_from_body(body)


def resolve_checksum(release: ReleaseInfo):
    """统一校验和解析入口 (正文优先, 回退 .sha256 资产)。

    显式把本模块的 ``fetch_checksum`` 传给实现: 旧代码/测试对
    ``src.updater.fetch_checksum`` 的 monkeypatch 继续生效。
    """
    return _resolve_checksum(release, fetch=fetch_checksum)


def fetch_checksum(url: str, timeout: float = 15.0):
    """下载独立 .sha256 资产 (不存在返回 None)。"""
    return _fetch_checksum(url, timeout=timeout)


# ----------------------------------------------------------------
# Windows 安装流程 (非 Windows 优雅降级)
# ----------------------------------------------------------------

def ensure_disk_space(install_dir: str, asset_size: int) -> None:
    """磁盘空间预检 (检查更新暂存目录所在卷)。"""
    return _ensure_disk_space(install_dir, asset_size)


def prepare(zip_path: str, install_dir: str, new_version: str) -> str:
    """解压安装包到暂存区并生成 PowerShell 更新器, 返回 ps1 路径。"""
    return _windows.prepare(zip_path, install_dir, new_version)


def launch_updater(install_dir: str, parent_pid: int) -> bool:
    """拉起外部更新器; 非 Windows 返回 False (不抛异常)。"""
    return _windows.launch_updater(install_dir, parent_pid)


def has_pending_update(install_dir: str) -> bool:
    """是否有等待替换的更新 (仅 Windows 可能为 True)。"""
    return _windows.has_pending_update(install_dir)


def cleanup_staging(install_dir: str) -> None:
    """清理旧版备份/暂存 (启动时调用, 非 Windows 空操作)。"""
    return _windows.cleanup_staging(install_dir)


# ----------------------------------------------------------------
# 跳过版本 (委托 src.update.backend)
# ----------------------------------------------------------------

def get_skip_version() -> str:
    """读取「跳过此版本」设置。"""
    return _get_skip_version()


def set_skip_version(version: str) -> None:
    """写入「跳过此版本」设置。"""
    return _set_skip_version(version)


# ----------------------------------------------------------------
# 动态兼容属性
# ----------------------------------------------------------------

def __getattr__(name: str):
    """动态提供旧模块私有/常量属性 (PEP 562)。

    ``STAGING_DIR`` 需要按当前 ``PlatformPaths.cache_dir`` 计算, 因此不能
    在 import 时固化为相对名; 旧 UI 用 ``os.path.join(install_dir,
    STAGING_DIR, ...)`` 拼接绝对路径时节下仍可用。
    """
    if name == "STAGING_DIR":
        return str(_windows.staging_dir())
    if name == "_UPDATER_PS1":
        return _windows.UPDATER_PS1
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | {"STAGING_DIR", "_UPDATER_PS1"})
