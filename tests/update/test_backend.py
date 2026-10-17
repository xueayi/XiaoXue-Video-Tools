# -*- coding: utf-8 -*-
"""更新后端协议 / 平台工厂 / check-only 语义测试 (M4.2)。

覆盖:
    * :func:`src.update.backend.get_update_backend` 的平台选择
      (win32+自更新能力 → Windows / darwin → macOS / 其它 → check-only);
    * :class:`CheckOnlyBackend` 的写盘操作必须抛
      :class:`UpdateNotSupportedError` (继承 UpdateError, UI 统一捕获);
    * check-only 的检查/待应用/清理/Release 页面语义;
    * 跳过版本设置的读写 (QSettings)。
"""

from types import SimpleNamespace

import pytest

import src.update.backend as backend
import src.update.checker as checker
from src.update.backend import (
    CheckOnlyBackend,
    UpdateBackend,
    get_update_backend,
)
from src.update.checker import (
    ReleaseInfo,
    UpdateError,
    UpdateNotSupportedError,
)
from src.update.macos import MacUpdateBackend
from src.update.windows import WindowsUpdateBackend


def _caps(os_name, self_update=False):
    """平台能力快照替身 (工厂只读 os_name / self_update_available)。"""
    return SimpleNamespace(os_name=os_name,
                           self_update_available=self_update)


def _release(**overrides):
    data = dict(
        version="2.2.0",
        asset_name="XiaoXueToolbox_v2.2.0_Windows_x64.zip",
        asset_url="https://dl/x.zip",
        asset_size=10,
        sha256_url="https://dl/x.zip.sha256",
        notes="",
        html_url=("https://github.com/xueayi/XiaoXue-Video-Tools"
                  "/releases/tag/v2.2.0"),
    )
    data.update(overrides)
    return ReleaseInfo(**data)


def _api_response(payload, status_code=200):
    class R:
        def __init__(self):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload
    return R()


#: check-only 场景: 发行页没有当前平台安装包资产
CHECK_ONLY_PAYLOAD = {
    "tag_name": "v2.2.0",
    "body": "更新说明",
    "html_url": ("https://github.com/xueayi/XiaoXue-Video-Tools"
                 "/releases/tag/v2.2.0"),
    "assets": [],
}


# ----------------------------------------------------------------
# 平台工厂
# ----------------------------------------------------------------

def test_factory_windows_with_self_update_capability():
    b = get_update_backend(platform="win32", capabilities=_caps("win32", True))
    assert isinstance(b, WindowsUpdateBackend)
    assert b.name == "windows"
    assert b.supports_self_update is True


def test_factory_windows_without_capability_falls_back_to_check_only():
    """能力快照说不能自更新 (安装目录不可写等): 退化为 check-only。"""
    caps = _caps("win32", False)
    b = get_update_backend(platform="win32", capabilities=caps)
    assert type(b) is CheckOnlyBackend


def test_factory_macos():
    b = get_update_backend(platform="darwin", capabilities=_caps("darwin"))
    assert isinstance(b, MacUpdateBackend)
    assert b.name == "macos"
    assert b.supports_self_update is False


@pytest.mark.parametrize("platform", ["linux", "linux2", "freebsd13"])
def test_factory_other_platforms_are_check_only(platform):
    b = get_update_backend(platform=platform, capabilities=_caps(platform))
    assert type(b) is CheckOnlyBackend
    assert b.name == "check-only"
    assert b.supports_self_update is False


def test_factory_defaults_to_platform_capabilities(monkeypatch):
    """不传参时读取 platform_capabilities() 快照决定后端。"""
    import src.platform.capabilities as caps_mod

    monkeypatch.setattr(caps_mod, "platform_capabilities",
                        lambda refresh=False: _caps("win32", True))
    assert isinstance(get_update_backend(), WindowsUpdateBackend)

    monkeypatch.setattr(caps_mod, "platform_capabilities",
                        lambda refresh=False: _caps("darwin"))
    assert isinstance(get_update_backend(), MacUpdateBackend)


def test_all_backends_satisfy_protocol():
    for b in (WindowsUpdateBackend(), MacUpdateBackend(), CheckOnlyBackend()):
        assert isinstance(b, UpdateBackend)


# ----------------------------------------------------------------
# check-only 语义
# ----------------------------------------------------------------

def test_check_only_check_does_not_require_asset(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(CHECK_ONLY_PAYLOAD))
    info = CheckOnlyBackend().check("2.1.0")
    assert info is not None
    assert info.version == "2.2.0"
    assert info.asset_url == "" and info.sha256_url == ""
    assert info.html_url.endswith("/v2.2.0")


def test_check_only_check_returns_none_when_up_to_date(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(CHECK_ONLY_PAYLOAD))
    assert CheckOnlyBackend().check("2.2.0") is None


def test_check_only_write_operations_raise_update_error(tmp_path):
    """下载/安装必须抛 UpdateNotSupportedError (UI 统一捕获, 不崩溃)。"""
    b = CheckOnlyBackend()

    with pytest.raises(UpdateNotSupportedError) as exc:
        b.download_and_prepare(_release(), str(tmp_path))
    assert isinstance(exc.value, UpdateError)
    assert "Release 页面" in str(exc.value)

    with pytest.raises(UpdateNotSupportedError):
        b.install(str(tmp_path), 1)

    assert list(tmp_path.iterdir()) == []  # 不下载/不落盘


def test_check_only_never_pending_and_cleanup_is_noop(tmp_path, cache_paths):
    """即便存在 Windows 布局的待应用文件, check-only 也恒 False 且不清理。"""
    staging = cache_paths / "update"
    (staging / "new" / "_internal").mkdir(parents=True)
    (staging / "updater.ps1").write_text("x")
    (tmp_path / "_backup").mkdir()

    b = CheckOnlyBackend()
    assert b.has_pending(str(tmp_path)) is False
    b.cleanup(str(tmp_path))
    assert (tmp_path / "_backup").exists()
    assert (staging / "updater.ps1").exists()


def test_check_only_release_page_url():
    b = CheckOnlyBackend()
    assert b.release_page_url().endswith("XiaoXue-Video-Tools/releases/latest")

    release = _release()
    assert b.release_page_url(release) == release.html_url


def test_check_only_open_release_page_opens_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(backend.webbrowser, "open",
                        lambda url: opened.append(url))

    release = _release()
    url = CheckOnlyBackend().open_release_page(release)

    assert opened == [release.html_url]
    assert url == release.html_url


# ----------------------------------------------------------------
# 跳过版本 (QSettings, 跨平台共享)
# ----------------------------------------------------------------

def test_skip_version_roundtrip(isolated_qsettings):
    assert backend.get_skip_version() == ""
    backend.set_skip_version("2.2.0")
    assert backend.get_skip_version() == "2.2.0"
