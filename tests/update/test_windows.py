# -*- coding: utf-8 -*-
"""Windows 自动更新后端测试 (M4.2)。

迁移映射 (自 tests/test_updater.py, 断言强度不变):
    * test_ensure_disk_space_zero_size_skips / insufficient / ok
    * test_prepare_ok / ps1_parses_in_powershell / ps1_hardened /
      removes_stale_new_dir / bad_zip / missing_exe / missing_internal
    * test_launch_updater (keep DETACHED_PROCESS 回归)
    * test_cleanup_staging / test_has_pending_update /
      test_cleanup_staging_keeps_pending_download
新增: 暂存目录使用 PlatformPaths.cache_dir、checksum 接线、缺失校验和提示、
no_window_kwargs 接线、非 Windows 优雅降级、门面委托、后端方法。
"""

import os
import subprocess
import zipfile

import pytest

import src.update.windows as windows
from src.update.checker import ReleaseInfo, UpdateError, UpdateNotSupportedError


@pytest.fixture(autouse=True)
def _as_windows(monkeypatch):
    """本文件覆盖 Windows 流程: 平台判定固定为 Windows (真机断言另见 skip)。"""
    monkeypatch.setattr(windows, "_is_windows", lambda: True)


def make_update_zip(tmp_path, name="update.zip", with_exe=True,
                    with_internal=True):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        if with_exe:
            zf.writestr("小雪工具箱.exe", "MZWLOADER")
        if with_internal:
            zf.writestr("_internal/run.py", "print('hi')")
    return str(path)


def _release(**overrides):
    data = dict(
        version="2.2.0",
        asset_name="XiaoXueToolbox_v2.2.0_Windows_x64.zip",
        asset_url="https://dl/x.zip",
        asset_size=10,
        sha256_url="https://dl/x.zip.sha256",
        notes="",
        html_url="https://github.com/xueayi/XiaoXue-Video-Tools/releases/tag/v2.2.0",
    )
    data.update(overrides)
    return ReleaseInfo(**data)


# ----------------------------------------------------------------
# 磁盘空间
# ----------------------------------------------------------------

def test_ensure_disk_space_zero_size_skips(cache_paths, tmp_path):
    windows.ensure_disk_space(str(tmp_path), 0)  # 不检查, 不抛


def test_ensure_disk_space_insufficient(cache_paths, tmp_path):
    with pytest.raises(UpdateError, match="磁盘空间不足"):
        windows.ensure_disk_space(str(tmp_path), 1 << 60)


def test_ensure_disk_space_ok(cache_paths, tmp_path):
    windows.ensure_disk_space(str(tmp_path), 1024)


# ----------------------------------------------------------------
# prepare (解压 + 生成 PowerShell 更新器)
# ----------------------------------------------------------------

def test_staging_dir_uses_platform_cache_dir(cache_paths, tmp_path):
    assert windows.staging_dir() == cache_paths / windows.STAGING_DIR_NAME
    # 安装目录下不再创建旧 _update 暂存
    assert not (tmp_path / windows.LEGACY_STAGING_DIR).exists()


def test_prepare_ok(cache_paths, tmp_path):
    zip_path = make_update_zip(tmp_path)
    ps1 = windows.prepare(zip_path, str(tmp_path), "2.2.0")

    assert os.path.exists(ps1)
    assert ps1.endswith(os.path.join(
        windows.STAGING_DIR_NAME, "updater.ps1"))
    assert str(cache_paths) in ps1  # 暂存落在 cache_dir
    raw = open(ps1, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM, PowerShell 5.1 兼容
    assert b"param(" in raw
    new_dir = cache_paths / windows.STAGING_DIR_NAME / "new"
    assert (new_dir / "version.txt").read_text(encoding="utf-8") == "2.2.0"
    assert (new_dir / "_internal" / "run.py").exists()


def test_prepare_ps1_parses_in_powershell(cache_paths, tmp_path):
    """回归: 嵌入的更新器脚本必须能通过 PowerShell 语法解析
    (v2.2.1 曾因字符串续行语法错误导致更新器静默失效)。"""
    if os.name != "nt":
        pytest.skip("仅 Windows")
    zip_path = make_update_zip(tmp_path)
    ps1 = windows.prepare(zip_path, str(tmp_path), "2.2.1")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         '$e = $null; '
         '[void][System.Management.Automation.Language.Parser]::ParseFile('
         f"'{ps1}', [ref]$null, [ref]$e); "
         'if ($e -and $e.Count -gt 0) { $e | ForEach-Object { '
         'Write-Output $_.Message }; exit 1 }'],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_prepare_ps1_hardened(cache_paths, tmp_path):
    """更新器脚本必须带日志与回滚 (隐藏窗口下排障唯一手段)。"""
    zip_path = make_update_zip(tmp_path)
    ps1 = windows.prepare(zip_path, str(tmp_path), "2.2.1")
    content = open(ps1, encoding="utf-8-sig").read()
    assert "updater.log" in content
    assert content.count("catch") >= 3  # 备份/安装/整体三层兜底
    assert "rolling back" in content
    assert "start manually" in content  # 重启失败不回滚, 提示手动启动


def test_prepare_removes_stale_new_dir(cache_paths, tmp_path):
    stale = cache_paths / windows.STAGING_DIR_NAME / "new"
    stale.mkdir(parents=True)
    (stale / "junk.txt").write_text("x")
    zip_path = make_update_zip(tmp_path)
    windows.prepare(zip_path, str(tmp_path), "2.2.0")
    assert not (stale / "junk.txt").exists()


def test_prepare_bad_zip(cache_paths, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(UpdateError, match="解压失败"):
        windows.prepare(str(bad), str(tmp_path), "2.2.0")


def test_prepare_missing_exe(cache_paths, tmp_path):
    zip_path = make_update_zip(tmp_path, with_exe=False)
    with pytest.raises(UpdateError, match="未找到主程序"):
        windows.prepare(zip_path, str(tmp_path), "2.2.0")


def test_prepare_missing_internal(cache_paths, tmp_path):
    zip_path = make_update_zip(tmp_path, with_internal=False)
    with pytest.raises(UpdateError, match="运行时目录"):
        windows.prepare(zip_path, str(tmp_path), "2.2.0")


def test_prepare_non_windows_raises_supported_error(cache_paths, tmp_path,
                                                    monkeypatch):
    monkeypatch.setattr(windows, "_is_windows", lambda: False)
    with pytest.raises(UpdateNotSupportedError) as exc:
        windows.prepare(make_update_zip(tmp_path), str(tmp_path), "2.2.0")
    assert isinstance(exc.value, UpdateError)  # UI 可统一捕获


# ----------------------------------------------------------------
# launch_updater
# ----------------------------------------------------------------

def test_launch_updater(cache_paths, monkeypatch, tmp_path):
    """回归: 不能带 DETACHED_PROCESS (PowerShell 会静默失败, v2.2.0 踩坑)。"""
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(windows.subprocess, "Popen", fake_popen)

    assert windows.launch_updater(str(tmp_path), 12345) is True

    args = captured["args"]
    assert args[0] == "powershell"
    assert "-File" in args
    ps1 = str(cache_paths / windows.STAGING_DIR_NAME / "updater.ps1")
    assert ps1 in args
    assert "12345" in args
    if os.name == "nt":
        flags = captured["kwargs"].get("creationflags")
        assert flags == subprocess.CREATE_NO_WINDOW
        assert not flags & subprocess.DETACHED_PROCESS


def test_launch_updater_uses_no_window_kwargs(cache_paths, monkeypatch,
                                              tmp_path):
    """接线回归: 必须通过 src.platform.process.no_window_kwargs 统一参数。"""
    captured = {}

    def fake_popen(args, **kwargs):
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(windows.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(windows, "no_window_kwargs",
                        lambda: {"creationflags": 424242})

    windows.launch_updater(str(tmp_path), 1)

    assert captured["kwargs"]["creationflags"] == 424242


def test_launch_updater_non_windows_returns_false(cache_paths, monkeypatch,
                                                  tmp_path):
    monkeypatch.setattr(windows, "_is_windows", lambda: False)
    called = []
    monkeypatch.setattr(windows.subprocess, "Popen",
                        lambda *a, **k: called.append(1))
    assert windows.launch_updater(str(tmp_path), 1) is False
    assert called == []


# ----------------------------------------------------------------
# 待应用 / 清理
# ----------------------------------------------------------------

def _stage_pending(cache_paths):
    staging = cache_paths / windows.STAGING_DIR_NAME
    (staging / "new" / "_internal").mkdir(parents=True)
    (staging / "updater.ps1").write_text("x")
    return staging


def test_has_pending_update(cache_paths, tmp_path):
    assert not windows.has_pending_update(str(tmp_path))
    staging = _stage_pending(cache_paths)
    assert windows.has_pending_update(str(tmp_path)) is True
    (staging / "new" / "_internal" / "x").write_text("x")
    assert windows.has_pending_update(str(tmp_path)) is True
    # 缺少 new/_internal 时不算待应用
    import shutil
    shutil.rmtree(staging / "new" / "_internal")
    assert windows.has_pending_update(str(tmp_path)) is False


def test_has_pending_update_only_windows(cache_paths, tmp_path, monkeypatch):
    _stage_pending(cache_paths)
    monkeypatch.setattr(windows, "_is_windows", lambda: False)
    assert windows.has_pending_update(str(tmp_path)) is False


def test_legacy_install_update_dir_not_treated_as_pending(cache_paths,
                                                          tmp_path):
    legacy = tmp_path / windows.LEGACY_STAGING_DIR
    (legacy / "new" / "_internal").mkdir(parents=True)
    (legacy / "updater.ps1").write_text("x")
    assert windows.has_pending_update(str(tmp_path)) is False


def test_cleanup_staging(cache_paths, tmp_path):
    (tmp_path / windows.BACKUP_DIR).mkdir()
    (tmp_path / windows.BACKUP_DIR / "x").write_text("x")
    (tmp_path / windows.LEGACY_STAGING_DIR).mkdir()
    windows.cleanup_staging(str(tmp_path))
    assert not (tmp_path / windows.BACKUP_DIR).exists()
    assert not (tmp_path / windows.LEGACY_STAGING_DIR).exists()
    windows.cleanup_staging(str(tmp_path))  # 不存在时也安全


def test_cleanup_staging_keeps_pending_download(cache_paths, tmp_path):
    """回归: 手动打开旧版不得清空待应用的更新下载 (v2.2.0 踩坑)。"""
    staging = _stage_pending(cache_paths)
    (staging / "new" / "_internal" / "x").write_text("x")
    (staging / "update.zip").write_bytes(b"download")
    (tmp_path / windows.BACKUP_DIR).mkdir()

    windows.cleanup_staging(str(tmp_path))

    assert not (tmp_path / windows.BACKUP_DIR).exists()  # 旧版备份照常清理
    assert (staging / "update.zip").exists()  # 待应用下载保留
    assert (staging / "updater.ps1").exists()


def test_cleanup_staging_non_windows_noop(cache_paths, tmp_path, monkeypatch):
    backup = tmp_path / windows.BACKUP_DIR
    backup.mkdir()
    monkeypatch.setattr(windows, "_is_windows", lambda: False)
    windows.cleanup_staging(str(tmp_path))  # 空操作, 不抛异常
    assert backup.exists()


# ----------------------------------------------------------------
# WindowsUpdateBackend
# ----------------------------------------------------------------

def test_backend_check_delegates_to_checker(cache_paths, monkeypatch):
    calls = {}

    def fake_fetch(version, timeout=10.0, **kwargs):
        calls["version"] = version
        calls["timeout"] = timeout
        calls["kwargs"] = kwargs
        return None

    monkeypatch.setattr(windows, "fetch_latest", fake_fetch)
    backend = windows.WindowsUpdateBackend()

    assert backend.check("2.1.0", timeout=3.0) is None
    assert calls["version"] == "2.1.0"
    assert calls["timeout"] == 3.0
    assert calls["kwargs"]["require_asset"] is True
    assert calls["kwargs"]["asset_suffix"] == windows.WINDOWS_ASSET_SUFFIX
    assert backend.supports_self_update is True
    assert backend.name == "windows"


def test_backend_download_and_prepare_wires_checksum(cache_paths, tmp_path,
                                                     monkeypatch):
    staged = {}

    def fake_download(url, dest, progress_cb=None, check_cancel=None):
        staged["url"] = url
        staged["dest"] = dest
        with open(dest, "wb") as f:
            f.write(b"zipdata")

    monkeypatch.setattr(windows, "ensure_disk_space", lambda *a: None)
    monkeypatch.setattr(windows, "download", fake_download)
    monkeypatch.setattr(windows, "resolve_checksum",
                        lambda r: "a" * 64)
    monkeypatch.setattr(windows, "verify_sha256", lambda p, e: True)
    monkeypatch.setattr(windows, "prepare",
                        lambda z, d, v: "C:/cache/update/updater.ps1")

    stages = []
    backend = windows.WindowsUpdateBackend()
    ps1 = backend.download_and_prepare(
        _release(), str(tmp_path), stage_cb=stages.append)

    assert ps1 == "C:/cache/update/updater.ps1"
    assert staged["url"] == "https://dl/x.zip"
    assert staged["dest"].endswith(os.path.join(
        windows.STAGING_DIR_NAME, windows.ZIP_NAME))
    assert str(cache_paths) in staged["dest"]
    assert any("校验" in s for s in stages)


def test_backend_download_and_prepare_checksum_mismatch(cache_paths, tmp_path,
                                                        monkeypatch):
    def fake_download(url, dest, **kwargs):
        with open(dest, "wb") as f:
            f.write(b"zipdata")

    monkeypatch.setattr(windows, "ensure_disk_space", lambda *a: None)
    monkeypatch.setattr(windows, "download", fake_download)
    monkeypatch.setattr(windows, "resolve_checksum", lambda r: "a" * 64)
    monkeypatch.setattr(windows, "verify_sha256", lambda p, e: False)

    with pytest.raises(UpdateError, match="SHA256"):
        windows.WindowsUpdateBackend().download_and_prepare(
            _release(), str(tmp_path))


def test_backend_missing_checksum_warns_but_continues(cache_paths, tmp_path,
                                                      monkeypatch):
    """M1 回归: 无校验和必须显式提示, 但不得静默/阻断旧版升级。"""
    def fake_download(url, dest, **kwargs):
        with open(dest, "wb") as f:
            f.write(b"zipdata")

    monkeypatch.setattr(windows, "ensure_disk_space", lambda *a: None)
    monkeypatch.setattr(windows, "download", fake_download)
    monkeypatch.setattr(windows, "resolve_checksum", lambda r: None)
    monkeypatch.setattr(windows, "prepare", lambda z, d, v: "ps1")
    verify_called = []
    monkeypatch.setattr(windows, "verify_sha256",
                        lambda p, e: verify_called.append(1) or True)

    stages = []
    ps1 = windows.WindowsUpdateBackend().download_and_prepare(
        _release(), str(tmp_path), stage_cb=stages.append)

    assert ps1 == "ps1"  # 不阻断
    assert verify_called == []
    assert any("未找到安装包校验和" in s for s in stages)
    assert any("跳过" in s for s in stages)


def test_backend_install_and_pending_delegate(cache_paths, tmp_path,
                                              monkeypatch):
    calls = []
    monkeypatch.setattr(windows, "launch_updater",
                        lambda d, pid: calls.append(("launch", d, pid)) or True)
    monkeypatch.setattr(windows, "has_pending_update",
                        lambda d: calls.append(("pending", d)) or False)
    monkeypatch.setattr(windows, "cleanup_staging",
                        lambda d: calls.append(("cleanup", d)))

    backend = windows.WindowsUpdateBackend()
    assert backend.install(str(tmp_path), 7) is True
    assert backend.has_pending(str(tmp_path)) is False
    backend.cleanup(str(tmp_path))
    assert calls == [("launch", str(tmp_path), 7),
                     ("pending", str(tmp_path)),
                     ("cleanup", str(tmp_path))]


def test_backend_release_page_url(cache_paths):
    backend = windows.WindowsUpdateBackend()
    release = _release()
    assert backend.release_page_url(release) == release.html_url
    assert backend.release_page_url(None).endswith(
        "XiaoXue-Video-Tools/releases/latest")


def test_backend_open_release_page_opens_browser(cache_paths, monkeypatch):
    opened = []
    monkeypatch.setattr(windows.webbrowser, "open",
                        lambda url: opened.append(url))
    backend = windows.WindowsUpdateBackend()
    url = backend.open_release_page(_release())
    assert opened == [url]
    assert "v2.2.0" in url


# ----------------------------------------------------------------
# 兼容门面 (src/updater.py)
# ----------------------------------------------------------------

def test_facade_delegates_to_windows_module(cache_paths, tmp_path,
                                            monkeypatch):
    import src.updater as updater

    calls = []
    monkeypatch.setattr(windows, "prepare",
                        lambda z, d, v: calls.append(("prepare", z)) or "ps1")
    monkeypatch.setattr(windows, "launch_updater",
                        lambda d, p: calls.append(("launch", p)) or True)
    monkeypatch.setattr(windows, "has_pending_update",
                        lambda d: calls.append(("pending", d)) or False)
    monkeypatch.setattr(windows, "cleanup_staging",
                        lambda d: calls.append(("cleanup", d)))

    assert updater.prepare("zip", "install", "2.2.0") == "ps1"
    assert updater.launch_updater("install", 123) is True
    assert updater.has_pending_update("install") is False
    updater.cleanup_staging("install")
    assert [c[0] for c in calls] == ["prepare", "launch", "pending", "cleanup"]


def test_facade_staging_dir_points_to_cache(cache_paths, tmp_path):
    import src.updater as updater

    assert updater.STAGING_DIR == str(
        cache_paths / windows.STAGING_DIR_NAME)
    # 旧 UI 拼接方式仍可用 (绝对路径覆盖 install_dir)
    joined = os.path.join(str(tmp_path), updater.STAGING_DIR, "update.zip")
    assert joined.startswith(str(cache_paths))


def test_facade_graceful_on_non_windows(cache_paths, tmp_path, monkeypatch):
    import src.updater as updater

    monkeypatch.setattr(windows, "_is_windows", lambda: False)

    assert updater.has_pending_update(str(tmp_path)) is False
    assert updater.launch_updater(str(tmp_path), 1) is False
    updater.cleanup_staging(str(tmp_path))  # 不抛异常
    with pytest.raises(UpdateError):
        updater.prepare("zip", str(tmp_path), "2.2.0")
