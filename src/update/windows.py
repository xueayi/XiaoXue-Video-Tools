# -*- coding: utf-8 -*-
"""Windows 自动更新后端 (M4.2)。

流程与旧 ``src/updater.py`` 一致, 只把**暂存目录**从安装目录 ``_update``
改为 :func:`src.platform.paths.platform_paths` 的 ``cache_dir/update``
(安装目录只保留 ``_backup`` 备份):

    检查 Release -> 下载 zip 到 cache_dir/update -> SHA256 校验
    -> 解压到 cache_dir/update/new -> 生成 updater.ps1
    -> 主程序退出后 PowerShell 完成 备份 + 替换 + 重启

Windows-only 操作 (``prepare``/``launch_updater`` 等) 在其它平台会:
``prepare`` 抛 :class:`UpdateNotSupportedError` (UI 统一捕获展示);
``launch_updater`` 返回 False; ``has_pending_update`` 返回 False;
``cleanup_staging`` 空操作 —— 不抛未处理异常。
"""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional

from ..platform.paths import platform_paths
from ..platform.process import no_window_kwargs
from .checker import (
    WINDOWS_ASSET_SUFFIX,
    ReleaseInfo,
    UpdateError,
    UpdateNotSupportedError,
    download,
    ensure_free_space,
    fetch_latest,
    resolve_checksum,
    verify_sha256,
)

#: cache_dir 下的更新暂存目录名
STAGING_DIR_NAME = "update"

#: 安装目录下的旧版备份目录名 (更新成功后下次启动清理)
BACKUP_DIR = "_backup"

#: 旧版本更新暂存目录名 (历史遗留, 启动清理时顺带删除)
LEGACY_STAGING_DIR = "_update"

#: 暂存区里的安装包文件名
ZIP_NAME = "update.zip"

_NOT_SUPPORTED_MESSAGE = (
    "当前平台不支持应用内自动安装，请到 Release 页面手动下载安装包。")


def _is_windows() -> bool:
    """当前是否 Windows (单测可 monkeypatch 模拟平台)。"""
    return os.name == "nt"


def staging_dir() -> Path:
    """更新暂存目录: ``PlatformPaths.cache_dir/update`` (跨平台路径解析)。"""
    return Path(platform_paths().cache_dir) / STAGING_DIR_NAME


def ensure_disk_space(install_dir, asset_size: int) -> None:
    """磁盘空间预检: 优先检查暂存目录所在卷, 失败回退安装目录所在卷。"""
    if asset_size <= 0:
        return
    target = staging_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        base = target
    except OSError:
        base = Path(install_dir)
    ensure_free_space(base, asset_size)


# 更新器: 等主程序退出 -> 备份旧版 -> 换入新版 -> 重启。纯 ASCII, 无需编码处理。
# 全程写 安装目录/_update/updater.log (隐藏窗口排障唯一手段); 任一替换失败回滚旧版。
UPDATER_PS1 = r"""
param(
    [int]$ParentPid,
    [string]$InstallDir,
    [string]$NewDir
)
$ErrorActionPreference = "Stop"
$logDir = Join-Path $InstallDir "_update"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$log = Join-Path $logDir "updater.log"

function Log($msg) {
    Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f (Get-Date -Format s), $msg) -Encoding UTF8
}

try {
    Log "updater start (parent=$ParentPid)"

    # 1. 等待主程序退出 (最多 60s, 超时则继续尝试)
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $p = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
        if (-not $p) { break }
        Start-Sleep -Milliseconds 500
    }
    Log "parent process exited"

    Set-Location $InstallDir

    # 2. 校验新包完整性
    $newExe = Get-ChildItem -LiteralPath $NewDir -Filter "*.exe" -File |
        Select-Object -First 1
    if (-not $newExe -or -not (Test-Path (Join-Path $NewDir "_internal"))) {
        Log "invalid new package, abort"
        exit 2
    }

    # 3. 备份旧版 (exe + _internal 移动到 _backup)
    $backup = Join-Path $InstallDir "_backup"
    if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
    New-Item -ItemType Directory -Path $backup | Out-Null

    $oldExe = Get-ChildItem -Path $InstallDir -Filter "*.exe" -File |
        Where-Object { $_.DirectoryName -eq (Get-Item $InstallDir).FullName } |
        Select-Object -First 1
    try {
        Move-Item -LiteralPath $oldExe.FullName -Destination $backup -Force
        if (Test-Path (Join-Path $InstallDir "_internal")) {
            Move-Item -LiteralPath (Join-Path $InstallDir "_internal") `
                -Destination $backup -Force
        }
        Log "old version moved to backup"
    } catch {
        Log ("backup move failed (will retry inline): " + $_.Exception.Message)
    }

    # 4. 换入新版; 任一步失败立即回滚旧版
    try {
        Move-Item -LiteralPath $newExe.FullName -Destination $InstallDir -Force
        Move-Item -LiteralPath (Join-Path $NewDir "_internal") `
            -Destination $InstallDir -Force
        Log "new version installed"
    } catch {
        Log ("install failed, rolling back: " + $_.Exception.Message)
        if ($oldExe -and (Test-Path (Join-Path $backup $oldExe.Name))) {
            Move-Item -LiteralPath (Join-Path $backup $oldExe.Name) `
                -Destination $InstallDir -Force
        }
        if (Test-Path (Join-Path $backup "_internal")) {
            Move-Item -LiteralPath (Join-Path $backup "_internal") `
                -Destination $InstallDir -Force
        }
        exit 3
    }

    Remove-Item $NewDir -Recurse -Force -ErrorAction SilentlyContinue

    # 5. 重启新版本 (失败不回滚: 更新已生效, 可手动启动)
    try {
        Start-Process -FilePath (Join-Path $InstallDir $newExe.Name)
        Log "new version launched"
    } catch {
        Log ("start new version failed (update applied, start manually): " +
            $_.Exception.Message)
    }
    exit 0
} catch {
    try { Log ("fatal: " + $_.Exception.Message) } catch {}
    exit 1
}
"""

#: 兼容旧模块私有名
_UPDATER_PS1 = UPDATER_PS1


def _stage(stage_cb: Optional[Callable], message: str) -> None:
    if stage_cb is not None:
        try:
            stage_cb(message)
        except Exception:
            pass


def prepare(zip_path: str, install_dir: str, new_version: str) -> str:
    """解压新包到 cache 暂存区并生成更新器脚本, 返回 updater.ps1 路径。

    任何完整性问题抛 :class:`UpdateError`; 非 Windows 抛
    :class:`UpdateNotSupportedError` (UI 统一捕获展示)。
    """
    if not _is_windows():
        raise UpdateNotSupportedError(_NOT_SUPPORTED_MESSAGE)

    staging = staging_dir()
    new_dir = staging / "new"
    if new_dir.exists():
        shutil.rmtree(new_dir, ignore_errors=True)
    new_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(new_dir)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"安装包解压失败 (文件可能已损坏): {e}") from e

    exe_list = [f for f in os.listdir(new_dir) if f.lower().endswith(".exe")]
    if not exe_list:
        raise UpdateError("安装包内容异常: 未找到主程序")
    if not (new_dir / "_internal").is_dir():
        raise UpdateError("安装包内容异常: 缺少运行时目录")

    with open(new_dir / "version.txt", "w", encoding="utf-8") as f:
        f.write(new_version)

    ps1_path = staging / "updater.ps1"
    with open(ps1_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(UPDATER_PS1)
    return str(ps1_path)


def launch_updater(install_dir: str, parent_pid: int) -> bool:
    """以隐藏进程启动 PowerShell 更新器 (主程序随后自行退出)。

    注意: 只能用 CREATE_NO_WINDOW (via
    :func:`src.platform.process.no_window_kwargs`), 不能加 DETACHED_PROCESS ——
    PowerShell 在完全脱离控制台时会静默初始化失败直接退出,
    导致更新器什么都没做 (v2.2.0 实测踩坑)。

    Returns:
        是否成功拉起更新器; 非 Windows 平台返回 False (不抛异常)。
    """
    if not _is_windows():
        return False
    staging = staging_dir()
    ps1 = staging / "updater.ps1"
    new_dir = staging / "new"
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", str(ps1),
         "-ParentPid", str(parent_pid),
         "-InstallDir", str(install_dir),
         "-NewDir", str(new_dir)],
        close_fds=True, **no_window_kwargs())
    return True


def has_pending_update(install_dir: Optional[str] = None) -> bool:
    """是否有已解压就绪、等待替换的更新 (仅 Windows 可能为 True)。"""
    if not _is_windows():
        return False
    staging = staging_dir()
    ps1 = staging / "updater.ps1"
    new_dir = staging / "new"
    return ps1.is_file() and (new_dir / "_internal").is_dir()


def cleanup_staging(install_dir: str) -> None:
    """新版启动成功后清理备份与暂存 (幂等, 非 Windows 空操作)。

    - ``_backup``: 旧版已被成功替换, 可安全删除;
    - cache 暂存区: 仅在没有待应用更新时删除 (保留用户下载, 下次启动继续安装);
    - 旧版安装目录 ``_update``: 历史遗留布局, 无待应用更新时顺带清理。
    """
    if not _is_windows():
        return
    backup = Path(install_dir) / BACKUP_DIR
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    if has_pending_update(install_dir):
        return
    staging = staging_dir()
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    legacy = Path(install_dir) / LEGACY_STAGING_DIR
    if legacy.exists():
        shutil.rmtree(legacy, ignore_errors=True)


class WindowsUpdateBackend:
    """Windows 自动更新后端 (行为与旧 ``src/updater.py`` 一致)。"""

    name = "windows"
    supports_self_update = True
    asset_suffix = WINDOWS_ASSET_SUFFIX

    # ----------------------------------------------------------------
    # 检查 / 下载准备 / 安装
    # ----------------------------------------------------------------

    def check(self, current_version: str,
              timeout: float = 10.0) -> Optional[ReleaseInfo]:
        return fetch_latest(
            current_version,
            timeout=timeout,
            asset_suffix=self.asset_suffix,
            require_asset=True,
        )

    def download_and_prepare(
        self, release: ReleaseInfo, install_dir: str,
        progress_cb=None, check_cancel=None, stage_cb=None) -> str:
        """下载 -> 校验 -> 解压暂存, 返回 updater.ps1 路径。

        SHA256 缺失时通过 ``stage_cb`` 显式提示「已跳过校验」但不阻断升级;
        校验失败抛 UpdateError。
        """
        _stage(stage_cb, "正在下载更新包…")
        ensure_disk_space(install_dir, release.asset_size)
        zip_path = staging_dir() / ZIP_NAME
        download(release.asset_url, str(zip_path),
                 progress_cb=progress_cb, check_cancel=check_cancel)

        _stage(stage_cb, "正在校验安装包完整性…")
        expected = resolve_checksum(release)
        if expected and not verify_sha256(str(zip_path), expected):
            raise UpdateError(
                "SHA256 校验失败, 安装包可能已损坏, 请重试或到发布页手动下载")
        if not expected:
            # 旧版发行包可能没有校验和: 显式提示用户, 不静默跳过
            _stage(stage_cb,
                   "未找到安装包校验和，已跳过完整性校验（建议到发布页手动核对）")

        _stage(stage_cb, "正在准备更新文件…")
        return prepare(str(zip_path), str(install_dir), release.version)

    def install(self, install_dir: str, parent_pid: int) -> bool:
        return launch_updater(install_dir, parent_pid)

    # ----------------------------------------------------------------
    # 待应用恢复 / 清理 / Release 页面
    # ----------------------------------------------------------------

    def has_pending(self, install_dir: str) -> bool:
        return has_pending_update(install_dir)

    def cleanup(self, install_dir: str) -> None:
        cleanup_staging(install_dir)

    def release_page_url(self, release: Optional[ReleaseInfo] = None) -> str:
        from .checker import REPO_URL
        html_url = getattr(release, "html_url", "") if release is not None else ""
        return html_url or f"{REPO_URL}/releases/latest"

    def open_release_page(self, release: Optional[ReleaseInfo] = None) -> str:
        import webbrowser
        url = self.release_page_url(release)
        webbrowser.open(url)
        return url
