# -*- coding: utf-8 -*-
"""src/capabilities/ffmpeg_probe.py 单元测试 (M3.1)。

纯 Python, 不依赖 Qt / 真实 FFmpeg:
* 解析函数用 canned 文本;
* probe_ffmpeg 用 monkeypatch 替换 subprocess.run, 覆盖部分失败 / 超时 /
  可执行文件缺失 / 未知异常;
* 单例用 monkeypatch 的 probe_ffmpeg 覆盖 refresh / set 注入语义。
"""

import subprocess

import pytest

from src.capabilities import ffmpeg_probe as fp
from src.capabilities.ffmpeg_probe import (
    KEY_ENCODERS,
    FfmpegCaps,
    available_key_encoders,
    caps_ready,
    failed_caps,
    get_capabilities,
    nvenc_available,
    parse_encoder_kinds,
    parse_encoders,
    parse_filters,
    parse_hwaccels,
    parse_version,
    probe_ffmpeg,
    set_capabilities,
    short_probe_error,
)

VERSION_TEXT = (
    "ffmpeg version 7.1-full_build-www.gyan.dev Copyright (c) 2000-2024 "
    "the FFmpeg developers\n"
    "built with gcc 14.2.0 (Rev3, Built by MSYS2 project)\n"
    "configuration: --enable-gpl --enable-libx264 --enable-libx265\n"
)

ENCODERS_TEXT = """Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ...X.. = Codec is experimental
 ....B. = Supports draw_horiz_band
 .....D = Supports direct rendering method 1
 ------
 V....D libx264              H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V....D libx265              H.265 / HEVC (codec hevc)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
 V....D hevc_nvenc           NVIDIA NVENC hevc encoder (codec hevc)
 V....D h264_qsv             H.264 (Intel Quick Sync Video acceleration) (codec h264)
 V....D h264_amf             AMD AMF H.264 Encoder (codec h264)
 A....D aac                  AAC (Advanced Audio Coding)
 A....D libmp3lame           libmp3lame MP3 (MPEG audio layer 3) (codec mp3)
 S..... ass                  ASS (Advanced SubStation Alpha) subtitle (codec ass)
 S..... srt                  SubRip subtitle (codec subrip)
"""

FILTERS_TEXT = """Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  N = Dynamic number and/or type of input/output
  | = Source or sink filter
 TSC aap               AA->A      Apply Affine Projection algorithm to first audio stream.
 ... abench            A->A       Benchmark part of a filtergraph.
 ..C acompressor       A->A       Audio compressor.
 TS. adeclick          A->A       Remove impulsive noise from input audio.
 ... asubcut           A->A       Cut the input audio from time begin to end.
 ... subtitles         V->V       Render text subtitles onto input video using the libass library.
 ... scale             V->V       Scale the input video size and/or convert the image format.
"""

HWACCELS_TEXT = """Hardware acceleration methods:
cuda
videotoolbox
vaapi
qsv
"""

EXPECTED_ENCODERS = frozenset({
    "libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_qsv",
    "h264_amf", "aac", "libmp3lame", "ass", "srt",
})

EXPECTED_FILTERS = frozenset({
    "aap", "abench", "acompressor", "adeclick", "asubcut", "subtitles",
    "scale",
})


@pytest.fixture(autouse=True)
def _reset_caps_singleton():
    """每个用例前后清空进程级单例, 避免用例间互相污染。"""
    set_capabilities(None)
    yield
    set_capabilities(None)


# ----------------------------------------------------------------
# 纯解析函数
# ----------------------------------------------------------------

def test_parse_version_from_canned_text():
    assert parse_version(VERSION_TEXT) == "7.1-full_build-www.gyan.dev"


def test_parse_version_missing_returns_empty():
    assert parse_version("") == ""
    assert parse_version("built with gcc 14.2.0") == ""
    assert parse_version(None) == ""


def test_parse_encoders_canned_text():
    assert parse_encoders(ENCODERS_TEXT) == EXPECTED_ENCODERS
    # 图例行 (含 "=") 不得被当成编码器名
    assert "=" not in parse_encoders(ENCODERS_TEXT)


def test_parse_encoder_kinds_distinguishes_video_audio_subtitle():
    kinds = parse_encoder_kinds(ENCODERS_TEXT)
    assert kinds["h264_nvenc"] == "V"
    assert kinds["aac"] == "A"
    assert kinds["ass"] == "S"
    assert len(kinds) == len(EXPECTED_ENCODERS)


def test_parse_encoders_empty_and_none():
    assert parse_encoders("") == frozenset()
    assert parse_encoders(None) == frozenset()
    assert parse_encoder_kinds("Encoders:\n ------") == {}


def test_parse_filters_canned_text():
    assert parse_filters(FILTERS_TEXT) == EXPECTED_FILTERS
    assert "Timeline" not in parse_filters(FILTERS_TEXT)


def test_parse_filters_empty():
    assert parse_filters("") == frozenset()
    assert parse_filters(None) == frozenset()


def test_parse_hwaccels_skips_header():
    assert parse_hwaccels(HWACCELS_TEXT) == frozenset(
        {"cuda", "videotoolbox", "vaapi", "qsv"})


def test_parse_hwaccels_without_header():
    assert parse_hwaccels("cuda\nvideotoolbox\n") == frozenset(
        {"cuda", "videotoolbox"})


def test_parse_hwaccels_empty():
    assert parse_hwaccels("") == frozenset()
    assert parse_hwaccels(None) == frozenset()


# ----------------------------------------------------------------
# 展示辅助
# ----------------------------------------------------------------

def _caps(**overrides):
    data = dict(
        ffmpeg_path="C:/bin/ffmpeg.exe",
        version="7.1",
        encoders=frozenset(KEY_ENCODERS),
        filters=frozenset({"scale"}),
        hwaccels=frozenset({"cuda"}),
        probe_error=None,
        probed_at=1.0,
    )
    data.update(overrides)
    return FfmpegCaps(**data)


def test_caps_helpers_ok():
    caps = _caps()
    assert caps.ok is True
    assert caps.has_encoder("libx264") is True
    assert caps.has_encoder("h265_amf") is False
    assert available_key_encoders(caps) == frozenset(KEY_ENCODERS)
    assert nvenc_available(caps) is True


def test_caps_helpers_failure_and_none():
    bad = _caps(probe_error="boom", encoders=frozenset())
    assert bad.ok is False
    assert available_key_encoders(bad) == frozenset()
    assert nvenc_available(bad) is False
    assert available_key_encoders(None) == frozenset()
    assert nvenc_available(None) is False


def test_short_probe_error_truncates_and_flattens():
    text = "第一行\n  第二行  " + "x" * 300
    short = short_probe_error(text, limit=40)
    assert "\n" not in short
    assert len(short) == 40
    assert short.endswith("…")
    assert short_probe_error("短错误") == "短错误"
    assert short_probe_error(None) == ""
    assert short_probe_error(_caps(probe_error="快照错误")) == "快照错误"


def test_failed_caps_fields():
    caps = failed_caps("找不到 FFmpeg", ffmpeg_path="/no/ffmpeg")
    assert caps.ffmpeg_path == "/no/ffmpeg"
    assert caps.probe_error == "找不到 FFmpeg"
    assert caps.version == ""
    assert caps.encoders == frozenset()
    assert caps.probed_at > 0


# ----------------------------------------------------------------
# probe_ffmpeg: 子进程全部成功
# ----------------------------------------------------------------

class _Completed:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def _run_factory(outputs=None, errors=None, returncodes=None):
    """构造 subprocess.run 假实现: 按命令行最后一个参数 (-flag) 分派。"""
    outputs = outputs or {}
    errors = errors or {}
    returncodes = returncodes or {}

    def fake_run(cmd, **kwargs):
        flag = cmd[-1]
        if flag in errors:
            raise errors[flag]
        return _Completed(
            stdout=outputs.get(flag, ""),
            returncode=returncodes.get(flag, 0),
        )

    return fake_run


def test_probe_ffmpeg_success(monkeypatch):
    captured = []
    outputs = {
        "-version": VERSION_TEXT,
        "-encoders": ENCODERS_TEXT,
        "-filters": FILTERS_TEXT,
        "-hwaccels": HWACCELS_TEXT,
    }

    def fake_run(cmd, **kwargs):
        captured.append((cmd, kwargs))
        return _Completed(stdout=outputs[cmd[-1]])

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    caps = probe_ffmpeg(path="/fake/ffmpeg", timeout=3.0)

    assert caps.ffmpeg_path == "/fake/ffmpeg"
    assert caps.version == "7.1-full_build-www.gyan.dev"
    assert caps.encoders == EXPECTED_ENCODERS
    assert caps.filters == EXPECTED_FILTERS
    assert caps.hwaccels == frozenset({"cuda", "videotoolbox", "vaapi", "qsv"})
    assert caps.probe_error is None
    assert isinstance(caps.probed_at, float) and caps.probed_at > 0
    assert [cmd[-1] for cmd, _kw in captured] == [
        "-version", "-encoders", "-filters", "-hwaccels"]
    assert all(kw["timeout"] == 3.0 for _cmd, kw in captured)
    assert all(kw["capture_output"] is True for _cmd, kw in captured)
    assert captured[0][0][0] == "/fake/ffmpeg"


def test_probe_ffmpeg_windows_uses_creationflags(monkeypatch):
    """Windows 下必须带 CREATE_NO_WINDOW, 避免无控制台时弹窗。"""
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(fp.os, "name", "nt")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return _Completed(stdout="")

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    probe_ffmpeg(path="ffmpeg", timeout=1.0)
    assert captured.get("creationflags") == subprocess.CREATE_NO_WINDOW


def test_subprocess_kwargs_posix_empty(monkeypatch):
    monkeypatch.setattr(fp.os, "name", "posix")
    assert fp._subprocess_kwargs() == {}


def test_probe_ffmpeg_uses_utils_path_when_path_none(monkeypatch):
    monkeypatch.setattr(fp, "get_ffmpeg_path", lambda: "/auto/ffmpeg")
    monkeypatch.setattr(
        fp.subprocess, "run",
        _run_factory(outputs={"-version": VERSION_TEXT}))
    caps = probe_ffmpeg()
    assert caps.ffmpeg_path == "/auto/ffmpeg"


# ----------------------------------------------------------------
# probe_ffmpeg: 部分失败 / 超时 / 缺失 / 未知异常
# ----------------------------------------------------------------

def test_probe_ffmpeg_partial_failure_keeps_partial_results(monkeypatch):
    errors = {"-encoders": subprocess.TimeoutExpired("-encoders", 15)}
    outputs = {
        "-version": VERSION_TEXT,
        "-filters": FILTERS_TEXT,
        "-hwaccels": HWACCELS_TEXT,
    }
    monkeypatch.setattr(
        fp.subprocess, "run",
        _run_factory(outputs=outputs, errors=errors))
    caps = probe_ffmpeg(path="/fake/ffmpeg", timeout=15)

    assert caps.version
    assert caps.encoders == frozenset()
    assert caps.filters == EXPECTED_FILTERS
    assert caps.hwaccels == frozenset({"cuda", "videotoolbox", "vaapi", "qsv"})
    assert caps.probe_error is not None
    assert "-encoders" in caps.probe_error and "超时" in caps.probe_error


def test_probe_ffmpeg_nonzero_exit_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        fp.subprocess, "run",
        _run_factory(
            outputs={"-version": VERSION_TEXT},
            returncodes={"-filters": 1},
        ))
    caps = probe_ffmpeg(path="/fake/ffmpeg")
    assert caps.probe_error is not None
    assert "-filters" in caps.probe_error and "1" in caps.probe_error
    # version 已拿到, 保留部分结果
    assert caps.version.startswith("7.1")


def test_probe_ffmpeg_missing_executable(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("No such file: ffmpeg")
    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    caps = probe_ffmpeg(path="/no/ffmpeg")
    assert caps.probe_error is not None
    assert "找不到 FFmpeg" in caps.probe_error
    assert caps.version == "" and caps.encoders == frozenset()


def test_probe_ffmpeg_all_stages_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 15))
    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    caps = probe_ffmpeg(path="/slow/ffmpeg", timeout=2)
    assert caps.probe_error is not None
    assert caps.probe_error.count("超时") >= 1


def test_probe_ffmpeg_unknown_exception_swallowed(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise ValueError("坏输出")
    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    caps = probe_ffmpeg(path="/fake/ffmpeg")
    assert caps.probe_error is not None
    assert "ValueError" in caps.probe_error


def test_probe_ffmpeg_final_guard_never_raises(monkeypatch):
    """_probe_impl 内部意外异常也必须被最外层收敛为 failed caps。"""
    def boom(**kwargs):
        raise RuntimeError("内部爆炸")
    monkeypatch.setattr(fp, "_probe_impl", boom)
    caps = probe_ffmpeg(path="/fake/ffmpeg")
    assert caps.probe_error is not None
    assert "能力探测异常" in caps.probe_error


# ----------------------------------------------------------------
# 进程级单例
# ----------------------------------------------------------------

def _fake_caps_factory(calls):
    def fake_probe(timeout=15.0):
        calls.append(timeout)
        return _caps(ffmpeg_path=f"probe-{len(calls)}")
    return fake_probe


def test_singleton_probes_lazily_and_caches(monkeypatch):
    calls = []
    monkeypatch.setattr(fp, "probe_ffmpeg", _fake_caps_factory(calls))
    assert caps_ready() is False

    first = get_capabilities()
    assert calls == [15.0]
    assert caps_ready() is True
    assert first.ffmpeg_path == "probe-1"

    second = get_capabilities()
    assert calls == [15.0]  # 命中缓存, 不再探测
    assert second is first

    refreshed = get_capabilities(refresh=True, timeout=3.0)
    assert calls == [15.0, 3.0]
    assert refreshed.ffmpeg_path == "probe-2"
    assert get_capabilities() is refreshed


def test_singleton_set_capabilities_injection_and_clear(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("有缓存时不应触发探测")
    monkeypatch.setattr(fp, "probe_ffmpeg", boom)

    caps = _caps()
    set_capabilities(caps)
    assert caps_ready() is True
    assert get_capabilities() is caps

    set_capabilities(None)
    assert caps_ready() is False


def test_ffmpeg9_two_flag_filter_lines():
    text = ('Filters:\n  T.. = Timeline support\n  .S. = Slice threading\n'
            '  ------\n .. subtitles         V->V       Render text subtitles.\n'
            ' TS scale             V->V       Scale video.\n')
    assert fp.parse_filters(text) == frozenset({'subtitles', 'scale'})
