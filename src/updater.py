# -*- coding: utf-8 -*-
"""应用自更新模块 —— GitHub Release 整包下载 + 校验 + 外部更新器。

流程: 检查 (releases/latest) -> 下载 zip -> SHA256 校验 -> 解压到 _update/new
-> 生成 PowerShell 更新器 -> 主程序退出后由更新器完成 替换 + 重启。

安全与健壮性设计:
- 只替换 exe 与 _internal; config.ini / notify_config.json 等用户数据
  都在安装目录下且不在发行包内, 天然保留
- 更新前整目录磁盘空间预检; 下载支持断点续传与取消
- 更新器先把旧版移入 _backup 再换入新版, 移动失败自动回滚
- 新版启动成功后, 下一次启动时清理 _backup 与 _update 暂存目录
- 发行包文件名保持 ASCII (XiaoXueToolbox_*.zip); 更新器用 *.exe 通配
  定位新引导器, 因此 exe 中文名 (小雪工具箱.exe) 与旧英文名均兼容,
  exe 名不进入任何更新路径, 不触碰兼容模式的非中文路径约束
"""

import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass

import requests

REPO_URL = "https://github.com/xueayi/XiaoXue-Video-Tools"
RELEASES_LATEST_API = "https://api.github.com/repos/xueayi/XiaoXue-Video-Tools/releases/latest"

STAGING_DIR = "_update"       # 安装目录下的下载/解压暂存
BACKUP_DIR = "_backup"        # 旧版本备份 (更新成功后下次启动清理)
CHUNK_SIZE = 256 * 1024

_ORG = "XiaoXue"
_APP = "XiaoXueToolbox"


class UpdateError(Exception):
    """更新流程中的可恢复错误 (展示给用户)。"""


@dataclass
class ReleaseInfo:
    """新版本发行信息。"""
    version: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256_url: str
    notes: str = ""
    published_at: str = ""
    html_url: str = ""


# ----------------------------------------------------------------
# 版本比较
# ----------------------------------------------------------------

_VERSION_RE = re.compile(
    r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:-?(alpha|beta|rc)[.\-]?(\d+)?)?\s*$", re.I)
_PRE_RANK = {"": 3, "rc": 2, "beta": 1, "alpha": 0}


def parse_version(version: str):
    """解析版本号为可比较元组; 无法解析返回 None。

    2.1.0 -> (2, 1, 0, 3, 0)   正式版 > rc > beta > alpha
    """
    m = _VERSION_RE.match(str(version))
    if not m:
        return None
    rank = _PRE_RANK[(m.group(4) or "").lower()]
    num = int(m.group(5)) if m.group(5) else 0
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), rank, num)


def is_newer(remote: str, local: str) -> bool:
    """远端版本是否严格更新于本地; 任一版本无法解析时返回 False。"""
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    return r > l


def is_dev_version(version: str) -> bool:
    """开发版本 (git 描述失败回退的 *-dev) 不参与静默提示。"""
    return "dev" in str(version).lower()


# ----------------------------------------------------------------
# 检查更新
# ----------------------------------------------------------------

def _pick_asset(assets: list, shield: bool) -> dict:
    """按当前发行版变体挑选安装包资产。"""
    suffix = "_Shield_Windows_x64.zip" if shield else "_Windows_x64.zip"
    for asset in assets:
        name = str(asset.get("name", ""))
        if shield and name.endswith(suffix):
            return asset
        if not shield and name.endswith(suffix) and "_Shield" not in name:
            return asset
    raise UpdateError("新版本中没有找到与当前版本匹配的安装包")


def fetch_latest(current_version: str, shield: bool = False,
                 timeout: float = 10.0):
    """查询最新正式版; 有更新返回 ReleaseInfo, 已是最新返回 None。

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

    asset = _pick_asset(data.get("assets", []), shield)
    remote_version = str(data.get("tag_name", "")).lstrip("vV")
    info = ReleaseInfo(
        version=remote_version,
        asset_name=str(asset.get("name", "")),
        asset_url=str(asset.get("browser_download_url", "")),
        asset_size=int(asset.get("size", 0)),
        sha256_url=str(asset.get("browser_download_url", "")) + ".sha256",
        notes=str(data.get("body", "")),
        published_at=str(data.get("published_at", "")),
        html_url=str(data.get("html_url", REPO_URL + "/releases")),
    )
    if not is_newer(remote_version, current_version):
        return None
    return info


# ----------------------------------------------------------------
# 下载与校验
# ----------------------------------------------------------------

def ensure_disk_space(install_dir: str, asset_size: int):
    """磁盘空间预检: 需容纳 下载包 + 解压结果 + 余量。"""
    if asset_size <= 0:
        return
    usage = shutil.disk_usage(install_dir)
    need = int(asset_size * 3) + (200 << 20)
    if usage.free < need:
        raise UpdateError(
            f"磁盘空间不足: 约需 {need >> 20} MB, "
            f"当前剩余 {usage.free >> 20} MB")


def download(url: str, dest: str, progress_cb=None, check_cancel=None):
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


def sha256_of(path: str) -> str:
    import hashlib
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


def resolve_checksum(release: ReleaseInfo):
    """解析发行包校验和: 优先 Release 正文, 回退独立 .sha256 资产。"""
    if release.notes:
        found = parse_checksums_from_body(release.notes).get(release.asset_name)
        if found:
            return found
    if release.sha256_url:
        return fetch_checksum(release.sha256_url)
    return None


def fetch_checksum(url: str, timeout: float = 15.0):
    """获取发行包的 SHA256; 校验和资产不存在 (旧版发行) 返回 None。"""
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise UpdateError(f"校验和下载失败: {e}") from e
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise UpdateError(f"校验和下载失败 (HTTP {resp.status_code})")
    return resp.text.strip().split()[0] if resp.text.strip() else None


# ----------------------------------------------------------------
# 准备更新 (解压 + 生成更新器)
# ----------------------------------------------------------------

def _settings():
    from .gui_config import get_qsettings
    return get_qsettings()


def get_skip_version() -> str:
    return str(_settings().value("update/skip_version", "") or "")


def set_skip_version(version: str):
    _settings().setValue("update/skip_version", version)


# 更新器: 等主程序退出 -> 备份旧版 -> 换入新版 -> 重启。纯 ASCII, 无需编码处理
_UPDATER_PS1 = r"""
param(
    [int]$ParentPid,
    [string]$InstallDir,
    [string]$NewDir
)
$ErrorActionPreference = "Stop"

# 1. 等待主程序退出 (最多 60s, 超时则继续尝试)
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $p = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
    if (-not $p) { break }
    Start-Sleep -Milliseconds 500
}

Set-Location $InstallDir

# 2. 校验新包完整性
$newExe = Get-ChildItem -Path $NewDir -Filter "*.exe" -File |
    Select-Object -First 1
if (-not $newExe -or -not (Test-Path (Join-Path $NewDir "_internal"))) {
    exit 2
}

# 3. 备份旧版 (exe + _internal 移动到 _backup)
$backup = Join-Path $InstallDir "_backup"
if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
New-Item -ItemType Directory -Path $backup | Out-Null

$oldExe = Get-ChildItem -Path $InstallDir -Filter "*.exe" -File |
    Where-Object { $_.DirectoryName -eq (Get-Item $InstallDir).FullName } |
    Select-Object -First 1
Move-Item -LiteralPath $oldExe.FullName -Destination $backup -Force
if (Test-Path (Join-Path $InstallDir "_internal")) {
    Move-Item -LiteralPath (Join-Path $InstallDir "_internal") `
        -Destination $backup -Force
}

# 4. 换入新版; 任一步失败立即回滚
try {
    Move-Item -LiteralPath $newExe.FullName -Destination $InstallDir -Force
    Move-Item -LiteralPath (Join-Path $NewDir "_internal") `
        -Destination $InstallDir -Force
} catch {
    Move-Item -LiteralPath (Join-Path $backup $oldExe.Name) `
        -Destination $InstallDir -Force
    if (Test-Path (Join-Path $backup "_internal")) {
        Move-Item -LiteralPath (Join-Path $backup "_internal") `
            -Destination $InstallDir -Force
    }
    exit 3
}

Remove-Item $NewDir -Recurse -Force -ErrorAction SilentlyContinue

# 5. 重启新版本
Start-Process -FilePath (Join-Path $InstallDir $newExe.Name)
"""


def prepare(zip_path: str, install_dir: str, new_version: str) -> str:
    """解压新包到暂存区并生成更新器脚本, 返回 updater.ps1 路径。

    任何完整性问题抛出 UpdateError, 主程序保持可用。
    """
    staging = os.path.join(install_dir, STAGING_DIR)
    new_dir = os.path.join(staging, "new")
    if os.path.exists(new_dir):
        shutil.rmtree(new_dir, ignore_errors=True)
    os.makedirs(new_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(new_dir)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"安装包解压失败 (文件可能已损坏): {e}") from e

    exe_list = [f for f in os.listdir(new_dir) if f.lower().endswith(".exe")]
    if not exe_list:
        raise UpdateError("安装包内容异常: 未找到主程序")
    if not os.path.isdir(os.path.join(new_dir, "_internal")):
        raise UpdateError("安装包内容异常: 缺少运行时目录")

    with open(os.path.join(new_dir, "version.txt"), "w",
              encoding="utf-8") as f:
        f.write(new_version)

    ps1_path = os.path.join(staging, "updater.ps1")
    with open(ps1_path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(_UPDATER_PS1)
    return ps1_path


def launch_updater(install_dir: str, parent_pid: int):
    """以分离进程启动 PowerShell 更新器 (主程序随后自行退出)。"""
    ps1 = os.path.join(install_dir, STAGING_DIR, "updater.ps1")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", ps1,
         "-ParentPid", str(parent_pid),
         "-InstallDir", install_dir,
         "-NewDir", os.path.join(install_dir, STAGING_DIR, "new")],
        creationflags=flags, close_fds=True)


def cleanup_staging(install_dir: str):
    """新版启动成功后清理备份与暂存 (旧版确认不再需要)。"""
    for name in (BACKUP_DIR, STAGING_DIR):
        path = os.path.join(install_dir, name)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
