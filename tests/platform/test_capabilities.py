# -*- coding: utf-8 -*-
"""src/platform/capabilities.py 单元测试 (M4.1)。

覆盖: 平台矩阵 (Windows/macOS/Linux)、AviSynth DLL 判定、自更新、
VideoToolbox 判定 (依赖 M3 FfmpegCaps 快照)、M3 快照懒加载、单例/reset。
"""

import pytest

from src.capabilities.ffmpeg_probe import FfmpegCaps
from src.platform import capabilities as caps


@pytest.fixture(autouse=True)
def _reset_capabilities_singleton():
    caps.reset_platform_capabilities()
    yield
    caps.reset_platform_capabilities()


def _m3_caps(encoders=(), probe_error=None):
    return FfmpegCaps(
        ffmpeg_path="/bin/ffmpeg",
        version="7.1",
        encoders=frozenset(encoders),
        filters=frozenset({"scale"}),
        hwaccels=frozenset({"cuda"}),
        probe_error=probe_error,
        probed_at=1.0,
    )


def _prepare(monkeypatch, tmp_path, platform, m3_caps=None):
    """隔离平台/资源目录/ffmpeg 路径/M3 快照。"""
    resource = tmp_path / "res"
    (resource / "bin").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(caps, "_current_platform", lambda: platform)
    monkeypatch.setattr(caps, "resolve_resource_dir", lambda: resource)
    monkeypatch.setattr(caps, "get_ffmpeg_path", lambda: "/bin/ffmpeg")
    monkeypatch.setattr(caps, "get_ffprobe_path", lambda: "/bin/ffprobe")
    monkeypatch.setattr(caps, "caps_ready", lambda: m3_caps is not None)
    monkeypatch.setattr(caps, "get_capabilities", lambda: m3_caps)
    return resource


# ----------------------------------------------------------------
# 平台判定属性
# ----------------------------------------------------------------

def test_platform_flags_windows():
    state = caps.PlatformCapabilities(os_name="win32")
    assert state.is_windows is True
    assert state.is_macos is False
    assert state.is_linux is False


def test_platform_flags_macos():
    state = caps.PlatformCapabilities(os_name="darwin")
    assert state.is_windows is False
    assert state.is_macos is True
    assert state.is_linux is False


@pytest.mark.parametrize("name", ["linux", "linux2"])
def test_platform_flags_linux(name):
    state = caps.PlatformCapabilities(os_name=name)
    assert state.is_linux is True
    assert state.is_windows is False
    assert state.is_macos is False


def test_defaults_are_conservative():
    state = caps.PlatformCapabilities(os_name="win32")
    assert state.ffmpeg_path == "" and state.ffprobe_path == ""
    assert state.ffmpeg_caps is None
    assert state.avisynth_available is False
    assert state.self_update_available is False
    assert state.videotoolbox_available is False


# ----------------------------------------------------------------
# Windows: AviSynth / 自更新
# ----------------------------------------------------------------

def test_windows_avisynth_available_when_dlls_present(monkeypatch, tmp_path):
    resource = _prepare(monkeypatch, tmp_path, "win32")
    (resource / "bin" / "AviSynth.dll").write_bytes(b"x")
    (resource / "bin" / "VSFilter.dll").write_bytes(b"x")

    state = caps.detect()

    assert state.is_windows is True
    assert state.avisynth_available is True
    assert state.self_update_available is True
    assert state.videotoolbox_available is False


def test_windows_avisynth_requires_both_dlls(monkeypatch, tmp_path):
    resource = _prepare(monkeypatch, tmp_path, "win32")
    (resource / "bin" / "AviSynth.dll").write_bytes(b"x")
    # 缺 VSFilter.dll
    assert caps.detect().avisynth_available is False


def test_windows_avisynth_false_without_bin(monkeypatch, tmp_path):
    resource = _prepare(monkeypatch, tmp_path, "win32")
    (resource / "bin").rmdir()  # 只有空 res 目录
    assert caps.detect().avisynth_available is False


def test_detect_populates_ffmpeg_paths(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, "win32")
    state = caps.detect()
    assert state.ffmpeg_path == "/bin/ffmpeg"
    assert state.ffprobe_path == "/bin/ffprobe"


def test_detect_path_getter_error_does_not_raise(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, "win32")

    def boom():
        raise RuntimeError("path 解析失败")

    monkeypatch.setattr(caps, "get_ffmpeg_path", boom)
    state = caps.detect()
    assert state.ffmpeg_path == ""


# ----------------------------------------------------------------
# macOS: AviSynth 恒不可用 / VideoToolbox
# ----------------------------------------------------------------

def test_macos_disables_avisynth_and_self_update(monkeypatch, tmp_path):
    resource = _prepare(monkeypatch, tmp_path, "darwin")
    # 即使资源里恰好有 Windows DLL, macOS 也不可用
    (resource / "bin" / "AviSynth.dll").write_bytes(b"x")
    (resource / "bin" / "VSFilter.dll").write_bytes(b"x")

    state = caps.detect()

    assert state.is_macos is True
    assert state.avisynth_available is False
    assert state.self_update_available is False


def test_macos_videotoolbox_available(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"libx264", "h264_videotoolbox"})
    _prepare(monkeypatch, tmp_path, "darwin", m3_caps=m3)

    state = caps.detect()

    assert state.ffmpeg_caps is m3
    assert state.videotoolbox_available is True


def test_macos_videotoolbox_hevc(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"hevc_videotoolbox"})
    _prepare(monkeypatch, tmp_path, "darwin", m3_caps=m3)
    assert caps.detect().videotoolbox_available is True


def test_macos_videotoolbox_false_without_encoder(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"libx264", "libx265"})
    _prepare(monkeypatch, tmp_path, "darwin", m3_caps=m3)
    assert caps.detect().videotoolbox_available is False


def test_macos_videotoolbox_false_without_snapshot(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, "darwin", m3_caps=None)
    state = caps.detect()
    assert state.ffmpeg_caps is None
    assert state.videotoolbox_available is False


def test_macos_videotoolbox_false_on_probe_error(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"h264_videotoolbox"}, probe_error="探测失败")
    _prepare(monkeypatch, tmp_path, "darwin", m3_caps=m3)
    assert caps.detect().videotoolbox_available is False


def test_linux_all_platform_features_false(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"h264_videotoolbox"})
    _prepare(monkeypatch, tmp_path, "linux", m3_caps=m3)

    state = caps.detect()

    assert state.is_linux is True
    assert state.avisynth_available is False
    assert state.self_update_available is False
    assert state.videotoolbox_available is False


# ----------------------------------------------------------------
# M3 快照懒加载 / 单例
# ----------------------------------------------------------------

def test_ffmpeg_caps_lazy_loaded_from_m3(monkeypatch, tmp_path):
    m3 = _m3_caps(encoders={"libx264"})
    _prepare(monkeypatch, tmp_path, "win32", m3_caps=m3)
    assert caps.detect().ffmpeg_caps is m3


def test_ffmpeg_caps_not_probed_when_m3_not_ready(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, "win32", m3_caps=None)

    def boom():
        raise AssertionError("M3 未就绪时不应触发探测")

    monkeypatch.setattr(caps, "get_capabilities", boom)
    assert caps.detect().ffmpeg_caps is None


def test_platform_capabilities_singleton_and_refresh(monkeypatch, tmp_path):
    calls = []

    def fake_detect():
        calls.append(1)
        return caps.PlatformCapabilities(os_name="win32", ffmpeg_path="x")

    monkeypatch.setattr(caps, "detect", fake_detect)

    first = caps.platform_capabilities()
    assert caps.platform_capabilities() is first
    assert calls == [1]

    refreshed = caps.platform_capabilities(refresh=True)
    assert refreshed is not first
    assert calls == [1, 1]

    caps.reset_platform_capabilities()
    third = caps.platform_capabilities()
    assert third is not refreshed
    assert calls == [1, 1, 1]
