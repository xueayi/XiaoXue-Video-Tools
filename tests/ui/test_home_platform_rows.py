# -*- coding: utf-8 -*-
"""首页平台能力三行测试 (M4.4)。

覆盖 AviSynth 兼容字幕 / 自动更新 / VideoToolbox 三行的文案矩阵:
* 探测未完成 (含探测中重置) → 「待检测」;
* Windows: 可用 / 可用 / 非 macOS;
* macOS + VideoToolbox: 可用 / 仅检查更新 / 可用;
* macOS 未探测到 VideoToolbox: 不可用。

平台快照由 tests/ui/conftest.py 的 platform_state_stub 隔离, 用例内直接
monkeypatch 页面模块里的 platform_capabilities, 不跑真实探测。
"""

import pytest

import src.ui.home_page as home_page_module
from src.ui.home_page import (
    AVISYNTH_AVAILABLE_TEXT,
    AVISYNTH_UNAVAILABLE_TEXT,
    PENDING_TEXT,
    SELF_UPDATE_AVAILABLE_TEXT,
    SELF_UPDATE_CHECK_ONLY_TEXT,
    VIDEOTOOLBOX_AVAILABLE_TEXT,
    VIDEOTOOLBOX_NOT_MACOS_TEXT,
    VIDEOTOOLBOX_UNAVAILABLE_TEXT,
    HomePage,
)


def _caps(probe_error=None):
    from src.capabilities.ffmpeg_probe import KEY_ENCODERS, FfmpegCaps

    return FfmpegCaps(
        ffmpeg_path="C:/bin/ffmpeg.exe",
        version="7.1",
        encoders=frozenset(KEY_ENCODERS),
        filters=frozenset(),
        hwaccels=frozenset(),
        probe_error=probe_error,
        probed_at=1.0,
    )


@pytest.fixture
def platform(monkeypatch, platform_caps_stub):
    """替换首页读取的平台能力快照 (默认 Windows, 可中途改属性)。"""
    state = platform_caps_stub()
    monkeypatch.setattr(home_page_module, "platform_capabilities",
                        lambda refresh=False: state)
    return state


def _rows(page):
    return (page._avisynth_label.text(),
            page._self_update_label.text(),
            page._videotoolbox_label.text())


# ----------------------------------------------------------------
# 待检测
# ----------------------------------------------------------------

def test_rows_pending_before_probe(qapp, platform):
    home = HomePage()

    assert _rows(home) == (PENDING_TEXT, PENDING_TEXT, PENDING_TEXT)
    for label in (home._avisynth_label, home._self_update_label,
                  home._videotoolbox_label):
        assert label.objectName() == "muted_label"
        assert "探测完成" in label.toolTip()


def test_set_probing_resets_rows(qapp, platform):
    home = HomePage()
    home.update_capabilities(_caps())
    assert _rows(home) != (PENDING_TEXT,) * 3

    home.set_probing()

    assert _rows(home) == (PENDING_TEXT, PENDING_TEXT, PENDING_TEXT)


def test_update_capabilities_none_keeps_rows_pending(qapp, platform):
    home = HomePage()
    home.update_capabilities(None)

    assert _rows(home) == (PENDING_TEXT, PENDING_TEXT, PENDING_TEXT)


# ----------------------------------------------------------------
# 平台矩阵
# ----------------------------------------------------------------

def test_windows_rows(qapp, platform):
    home = HomePage()
    home.update_capabilities(_caps())

    assert _rows(home) == (AVISYNTH_AVAILABLE_TEXT, SELF_UPDATE_AVAILABLE_TEXT,
                           VIDEOTOOLBOX_NOT_MACOS_TEXT)
    assert "AviSynth" in home._avisynth_label.toolTip()
    assert "程序内下载并安装" in home._self_update_label.toolTip()
    assert "macOS 专属" in home._videotoolbox_label.toolTip()


def test_windows_without_avisynth_dlls(qapp, platform):
    """Windows 但依赖 DLL 缺失: AviSynth 显示不可用 (平台快照给出结论)。"""
    platform.avisynth_available = False
    home = HomePage()
    home.update_capabilities(_caps())

    assert home._avisynth_label.text() == AVISYNTH_UNAVAILABLE_TEXT
    assert "libass" in home._avisynth_label.toolTip()
    # 自动更新与 VideoToolbox 行不受影响
    assert home._self_update_label.text() == SELF_UPDATE_AVAILABLE_TEXT
    assert home._videotoolbox_label.text() == VIDEOTOOLBOX_NOT_MACOS_TEXT


def test_macos_rows_with_videotoolbox(qapp, platform):
    platform.os_name = "darwin"
    platform.avisynth_available = False
    platform.self_update_available = False
    platform.videotoolbox_available = True

    home = HomePage()
    home.update_capabilities(_caps())

    assert _rows(home) == (AVISYNTH_UNAVAILABLE_TEXT,
                           SELF_UPDATE_CHECK_ONLY_TEXT,
                           VIDEOTOOLBOX_AVAILABLE_TEXT)
    assert "videotoolbox" in home._videotoolbox_label.toolTip()
    assert "Release 页面" in home._self_update_label.toolTip()


def test_macos_rows_without_videotoolbox(qapp, platform):
    platform.os_name = "darwin"
    platform.avisynth_available = False
    platform.self_update_available = False
    platform.videotoolbox_available = False

    home = HomePage()
    home.update_capabilities(_caps())

    assert home._videotoolbox_label.text() == VIDEOTOOLBOX_UNAVAILABLE_TEXT
    assert "未探测到" in home._videotoolbox_label.toolTip()


def test_rows_refresh_on_probe_failure(qapp, platform):
    """探测失败也要给出平台层面的确定结论 (AviSynth/自更新不依赖 FFmpeg)。"""
    home = HomePage()
    home.update_capabilities(_caps(probe_error="ffmpeg 不存在"))

    assert home._capability_label.text().startswith("检测失败")
    assert _rows(home) == (AVISYNTH_AVAILABLE_TEXT, SELF_UPDATE_AVAILABLE_TEXT,
                           VIDEOTOOLBOX_NOT_MACOS_TEXT)
