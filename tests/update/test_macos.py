# -*- coding: utf-8 -*-
"""macOS check-only 更新后端测试 (M4.2)。

macOS 首版不做应用内自动替换, 只允许: 检查 Release → 提示新版本 →
打开 Release 页面手动下载。因此这里断言的重点是「只读」:
    * 检查更新不下载、不写盘 (自定义暂存目录都不会被创建);
    * ``download_and_prepare`` / ``install`` 抛 UpdateNotSupportedError;
    * ``has_pending`` 恒 False、``cleanup`` 空操作;
    * Release 页面 URL: 优先用发行 html_url, 否则回退最新发行页。
"""

from types import SimpleNamespace

import pytest

import src.update.checker as checker
import src.update.macos as macos
from src.update.backend import CheckOnlyBackend, get_update_backend
from src.update.checker import (
    MACOS_ASSET_SUFFIX,
    REPO_URL,
    ReleaseInfo,
    UpdateError,
    UpdateNotSupportedError,
)
from src.update.macos import (
    MacUpdateBackend,
    open_release_page,
    release_page_url,
)

LATEST_PAGE = f"{REPO_URL}/releases/latest"


def _release(**overrides):
    """macOS 发行包信息 (即便有资产, check-only 也不下载)。"""
    data = dict(
        version="2.2.0",
        asset_name=f"XiaoXueToolbox_v2.2.0{MACOS_ASSET_SUFFIX}",
        asset_url="https://dl/mac.zip",
        asset_size=10,
        sha256_url="https://dl/mac.zip.sha256",
        notes="更新说明",
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


WINDOWS_ASSET = {
    "name": "XiaoXueToolbox_v2.2.0_Windows_x64.zip",
    "browser_download_url": "https://dl/std.zip",
    "size": 10,
}

#: 发行页同时有 Windows / macOS 资产
RELEASE_PAYLOAD = {
    "tag_name": "v2.2.0",
    "body": "更新说明",
    "html_url": ("https://github.com/xueayi/XiaoXue-Video-Tools"
                 "/releases/tag/v2.2.0"),
    "assets": [WINDOWS_ASSET, {
        "name": f"XiaoXueToolbox_v2.2.0{MACOS_ASSET_SUFFIX}",
        "browser_download_url": "https://dl/mac.zip",
        "size": 20,
    }],
}

#: macOS check-only 的主场景: 发行页只有 Windows 资产
NO_MACOS_ASSET_PAYLOAD = dict(RELEASE_PAYLOAD, assets=[WINDOWS_ASSET])


# ----------------------------------------------------------------
# 后端属性 / 工厂
# ----------------------------------------------------------------

def test_macos_backend_is_check_only():
    b = MacUpdateBackend()
    assert isinstance(b, CheckOnlyBackend)
    assert b.name == "macos"
    assert b.supports_self_update is False
    assert b.asset_suffix == MACOS_ASSET_SUFFIX


def test_factory_selects_macos_backend():
    caps = SimpleNamespace(os_name="darwin", self_update_available=False)
    b = get_update_backend(platform="darwin", capabilities=caps)
    assert isinstance(b, MacUpdateBackend)


# ----------------------------------------------------------------
# 检查更新 (只读)
# ----------------------------------------------------------------

def test_macos_check_reports_new_version_without_asset(monkeypatch):
    """发行页没有 macOS 资产时也必须能提示新版本 (不再报「未找到安装包」)。"""
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(NO_MACOS_ASSET_PAYLOAD))

    info = MacUpdateBackend().check("2.1.0")

    assert info is not None
    assert info.version == "2.2.0"
    assert info.asset_url == "" and info.sha256_url == ""
    assert "更新说明" in info.notes
    assert info.html_url.endswith("/v2.2.0")


def test_macos_check_picks_macos_asset_when_present(monkeypatch):
    """资产挑选按 macOS 后缀 (未来接自动更新时不会误拿 Windows 包)。"""
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(RELEASE_PAYLOAD))

    info = MacUpdateBackend().check("2.1.0")

    assert info.asset_url == "https://dl/mac.zip"
    assert info.asset_name.endswith(MACOS_ASSET_SUFFIX)


def test_macos_check_returns_none_when_up_to_date(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(RELEASE_PAYLOAD))
    assert MacUpdateBackend().check("2.2.0") is None
    assert MacUpdateBackend().check("2.3.0") is None


def test_macos_check_does_not_download(monkeypatch, cache_paths):
    """check-only: 检查更新绝不触发下载, 也不创建暂存目录。"""
    calls = []
    monkeypatch.setattr(checker, "download",
                        lambda *a, **k: calls.append(a))
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _api_response(RELEASE_PAYLOAD))

    info = MacUpdateBackend().check("2.1.0")

    assert info is not None
    assert calls == []
    assert not cache_paths.exists()


# ----------------------------------------------------------------
# 写盘操作: 明确不支持 (但不崩溃)
# ----------------------------------------------------------------

def test_macos_download_and_prepare_not_supported(tmp_path):
    with pytest.raises(UpdateNotSupportedError) as exc:
        MacUpdateBackend().download_and_prepare(_release(), str(tmp_path))
    assert isinstance(exc.value, UpdateError)  # UI 可统一捕获
    assert "Release 页面" in str(exc.value)
    assert list(tmp_path.iterdir()) == []


def test_macos_install_not_supported(tmp_path):
    with pytest.raises(UpdateNotSupportedError):
        MacUpdateBackend().install(str(tmp_path), 1234)


def test_macos_has_pending_always_false(tmp_path, cache_paths):
    """即便存在 Windows 布局的待应用文件, macOS 也恒为 False。"""
    staging = cache_paths / "update"
    (staging / "new" / "_internal").mkdir(parents=True)
    (staging / "updater.ps1").write_text("x")

    assert MacUpdateBackend().has_pending(str(tmp_path)) is False


def test_macos_cleanup_is_noop(tmp_path):
    (tmp_path / "_backup").mkdir()
    MacUpdateBackend().cleanup(str(tmp_path))
    assert (tmp_path / "_backup").exists()


# ----------------------------------------------------------------
# Release 页面
# ----------------------------------------------------------------

def test_release_page_url_prefers_release_html_url():
    release = _release()
    assert MacUpdateBackend().release_page_url(release) == release.html_url
    assert release_page_url(release) == release.html_url


def test_release_page_url_falls_back_to_latest():
    assert MacUpdateBackend().release_page_url() == LATEST_PAGE
    assert MacUpdateBackend().release_page_url(None) == LATEST_PAGE
    assert release_page_url(None) == LATEST_PAGE
    assert release_page_url(_release(html_url="")) == LATEST_PAGE


def test_open_release_page_opens_browser(monkeypatch):
    opened = []
    monkeypatch.setattr(macos.webbrowser, "open",
                        lambda url: opened.append(url))

    release = _release()
    assert MacUpdateBackend().open_release_page(release) == release.html_url

    # 模块级函数入口 (无发行信息 → 最新发行页)
    assert open_release_page(None) == LATEST_PAGE

    assert opened == [release.html_url, LATEST_PAGE]
