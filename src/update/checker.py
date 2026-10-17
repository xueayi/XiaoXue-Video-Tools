# -*- coding: utf-8 -*-
"""GitHub Release 检查 + 安装包下载 / SHA256 校验 (跨平台网络层, M4.2)。

职责:
    * 查询 releases/latest, 组装 :class:`ReleaseInfo`;
    * 按平台资产后缀挑选安装包 (Windows 标准版 ``_Windows_x64.zip``);
    * 流式下载 (断点续传/取消) 与 SHA256 校验和解析
      (优先 Release 正文内嵌校验和, 回退独立 .sha256 资产)。

本模块不含任何平台替换/安装逻辑: Windows 的整包替换在
:mod:`src.update.windows`, macOS 首版只在 :mod:`src.update.macos` 做检查。
"""

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests

from .version import is_newer

REPO_URL = "https://github.com/xueayi/XiaoXue-Video-Tools"
RELEASES_LATEST_API = (
    "https://api.github.com/repos/xueayi/XiaoXue-Video-Tools/releases/latest")

#: 流式下载块大小
CHUNK_SIZE = 256 * 1024

#: Windows 标准版安装包资产后缀 (Shield 版资产为 _Shield_Windows_x64.zip,
#: 当前发行流程只发布标准版, 保持与旧版一致)
WINDOWS_ASSET_SUFFIX = "_Windows_x64.zip"

#: macOS 资产后缀 (M4.2 仅预留, 首版 check-only 不下载)
MACOS_ASSET_SUFFIX = "_macOS_arm64.zip"

_ORG = "XiaoXue"
_APP = "XiaoXueToolbox"


class UpdateError(Exception):
    """更新流程中的可恢复错误 (展示给用户)。"""


class UpdateNotSupportedError(UpdateError):
    """当前平台不支持该更新操作 (例如 macOS 的自动替换)。

    继承 UpdateError: UI 的 Worker 已统一捕获 UpdateError 并展示友好文案,
    因此非 Windows 平台调用 Windows 专有流程时不会崩溃。
    """


@dataclass
class ReleaseInfo:
    """新版本发行信息。

    资产字段 (asset_*) 在只检查不下载的场景 (macOS check-only /
    发行页无当前平台资产) 下可能为空字符串, 调用方不应假设一定有包可下。
    """

    version: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256_url: str
    notes: str = ""
    published_at: str = ""
    html_url: str = ""


# ----------------------------------------------------------------
# Release 检查
# ----------------------------------------------------------------

def find_asset(assets: list, suffix: str = WINDOWS_ASSET_SUFFIX) -> Optional[dict]:
    """从发行资产中挑选匹配后缀的安装包; 找不到返回 None。"""
    for asset in assets or []:
        name = str(asset.get("name", ""))
        if name.endswith(suffix):
            return asset
    return None


def _pick_asset(assets: list, suffix: str = WINDOWS_ASSET_SUFFIX) -> dict:
    """挑选安装包资产; 找不到时抛 UpdateError (Windows 下载流程使用)。"""
    asset = find_asset(assets, suffix)
    if asset is None:
        raise UpdateError("新版本中没有找到与当前版本匹配的安装包")
    return asset


def fetch_latest(
    current_version: str,
    timeout: float = 10.0,
    *,
    asset_suffix: str = WINDOWS_ASSET_SUFFIX,
    require_asset: bool = True,
):
    """查询最新正式版; 有更新返回 ReleaseInfo, 已是最新返回 None。

    Args:
        current_version: 本地版本号。
        timeout: 网络超时秒数。
        asset_suffix: 当前平台安装包资产后缀。
        require_asset: 没有匹配资产时是否报错。Windows 下载流程为 True;
            macOS check-only 为 False (只关心版本信息/发行页 URL)。

    网络/接口异常抛出 UpdateError (由调用方展示)。
    """
    try:
        resp = requests.get(
            RELEASES_LATEST_API, timeout=timeout,
            headers={"Accept": "application/vnd.github+json"})
    except requests.RequestException as e:
        raise UpdateError(f"无法连接更新服务器: {e}") from e

    if resp.status_code != 200:
        raise UpdateError(f"更新服务器返回异常 (HTTP {resp.status_code})")
    try:
        data = resp.json()
    except ValueError as e:
        raise UpdateError(f"更新服务器响应解析失败: {e}") from e

    assets = data.get("assets", [])
    asset = find_asset(assets, asset_suffix)
    if asset is None and require_asset:
        raise UpdateError("新版本中没有找到与当前版本匹配的安装包")
    asset = asset or {}

    remote_version = str(data.get("tag_name", "")).lstrip("vV")
    info = ReleaseInfo(
        version=remote_version,
        asset_name=str(asset.get("name", "")),
        asset_url=str(asset.get("browser_download_url", "")),
        asset_size=int(asset.get("size", 0)),
        sha256_url=str(asset.get("browser_download_url", "")) + ".sha256"
        if asset.get("browser_download_url") else "",
        notes=str(data.get("body", "")),
        published_at=str(data.get("published_at", "")),
        html_url=str(data.get("html_url", REPO_URL + "/releases")),
    )
    if not is_newer(remote_version, current_version):
        return None
    return info


# ----------------------------------------------------------------
# 下载
# ----------------------------------------------------------------

def ensure_free_space(directory, asset_size: int) -> None:
    """磁盘空间预检: 需容纳 下载包 + 解压结果 + 余量。

    目录不存在时尝试创建; 无法使用该目录时跳过检查 (由真正写入时报错)。
    """
    if asset_size <= 0:
        return
    import shutil

    try:
        os.makedirs(str(directory), exist_ok=True)
        usage = shutil.disk_usage(str(directory))
    except OSError:
        return
    need = int(asset_size * 3) + (200 << 20)
    if usage.free < need:
        raise UpdateError(
            f"磁盘空间不足: 约需 {need >> 20} MB, "
            f"当前剩余 {usage.free >> 20} MB")


def download(url: str, dest: str, progress_cb=None, check_cancel=None) -> None:
    """流式下载 (支持断点续传 .part 与取消)。

    progress_cb(已下载字节, 总字节或 0)
    check_cancel() 返回 True 时抛出 UpdateError("已取消"), .part 保留供续传。
    """
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part_path = dest + ".part"
    headers = {}
    resume_from = 0
    if os.path.exists(part_path):
        resume_from = os.path.getsize(part_path)
        headers["Range"] = f"bytes={resume_from}-"

    try:
        resp = requests.get(url, headers=headers, stream=True,
                            timeout=(10, 60))
    except requests.RequestException as e:
        raise UpdateError(f"下载请求失败: {e}") from e

    if resp.status_code != 200 and resp.status_code != 206:
        raise UpdateError(f"下载失败 (HTTP {resp.status_code})")
    if resume_from and resp.status_code != 206:
        resume_from = 0  # 服务器不支持续传, 从头下载

    try:
        total = int(resp.headers.get("Content-Length", 0)) + resume_from
    except (TypeError, ValueError):
        total = 0

    done = resume_from
    mode = "ab" if resume_from else "wb"
    try:
        with open(part_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if check_cancel is not None and check_cancel():
                    raise UpdateError("已取消")
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb is not None:
                        progress_cb(done, total)
    except requests.RequestException as e:
        raise UpdateError(f"下载中断 (已保留进度, 可重试续传): {e}") from e

    os.replace(part_path, dest)


# ----------------------------------------------------------------
# SHA256 校验和
# ----------------------------------------------------------------

def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: str, expected: str) -> bool:
    return sha256_of(path).lower() == str(expected).strip().lower()


def parse_checksums_from_body(body: str) -> dict:
    """从 Release 正文的「### SHA256 校验和」段解析 {文件名: 哈希}。

    CI 在发版后把校验和嵌入正文 (替代独立 .sha256 资产, 保持发行页整洁)。
    """
    result = {}
    in_section = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped == "### SHA256 校验和":
            in_section = True
            continue
        if in_section:
            if stripped.startswith("### ") or stripped.startswith("## "):
                break
            parts = stripped.split()
            if (len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0])
                    and not stripped.startswith("`")):
                result[parts[1].strip("`")] = parts[0].lower()
    return result


def fetch_checksum(url: str, timeout: float = 15.0):
    """获取发行包的 SHA256; 校验和资产不存在 (旧版发行) 返回 None。"""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise UpdateError(f"校验和下载失败: {e}") from e
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise UpdateError(f"校验和下载失败 (HTTP {resp.status_code})")
    return resp.text.strip().split()[0] if resp.text.strip() else None


def resolve_checksum(release: ReleaseInfo, fetch=None):
    """解析发行包校验和: 优先 Release 正文, 回退独立 .sha256 资产。

    Args:
        release: 发行信息。
        fetch: 校验和获取函数, 缺省用本模块 :func:`fetch_checksum`。
            兼容门面 ``src.updater`` 会传入自己的 ``fetch_checksum``, 使旧
            代码/测试对 ``src.updater.fetch_checksum`` 的 monkeypatch 依然生效。

    Returns:
        校验和字符串; None 表示该发行没有可用校验和 (旧版发行),
        由调用方显式提示, 不得静默跳过。
    """
    if release.notes:
        found = parse_checksums_from_body(release.notes).get(release.asset_name)
        if found:
            return found
    if release.sha256_url:
        return (fetch or fetch_checksum)(release.sha256_url)
    return None
