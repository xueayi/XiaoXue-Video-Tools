# -*- coding: utf-8 -*-
"""
命令构建快照 + preset 音频一致性回归测试 (PR-02)。

背景 bug: resolve_encoder_params 已按 preset 解析出 audio_encoder="copy",
但 execute_encode 在非自定义路径又把 audio_encoder 强制成 "aac",
导致 UI/预设文案 ("直接复制") 与最终 FFmpeg 命令不一致。

本文件从 args 出发 -> 捕获 execute_encode 传给 builder 的最终参数 -> 构建命令,
确保 "resolved 参数 = 最终命令", 并锁定关键命令形状。
不执行真实 FFmpeg。
"""
import os
import types

import pytest

import src.core as core
import src.executors.video_executor as video_executor
from src.encode_params import EncodeParams, print_encode_info
from src.presets import AUDIO_ENCODERS, ENCODERS, QUALITY_PRESETS, RATE_CONTROL_MODES
from src.task.status import TaskStatus
from src.utils import generate_output_path


# 非自定义的质量预设 (用于参数化)
PRESET_NAMES = [name for name in QUALITY_PRESETS if name != "自定义 (Custom)"]


def make_args(tmp_path, **overrides):
    """构造 execute_encode 所需的 args；input 真实存在以通过 validate()。"""
    video = tmp_path / "input_video.mp4"
    video.write_bytes(b"fake video content")
    values = dict(
        input=str(video),
        output="",
        preset="【均衡画质】x264 常用导出 (CRF18)",
        encoder="H.264 (CPU - libx264)",
        crf=18,
        speed_preset="medium",
        nvenc_preset="使用预设默认",
        resolution="",
        fps=0,
        audio_encoder="复制 (不重新编码)",
        audio_bitrate="192k",
        subtitle="",
        subtitle_mode="内嵌（烧录进画面）",
        compat_mode=False,
        extra_args="",
        debug_mode=False,
        rate_control="CRF/CQ (恒定质量)",
        video_bitrate="",
        output_format="MP4",
        output_format_custom="",
        audio_tracks="仅保留第 1 条 (#0)",
        audio_tracks_custom="",
        subtitle_tracks="不保留字幕",
        subtitle_tracks_custom="",
        post_transfer_mode="不分发",
        post_transfer_dir="",
    )
    values.update(overrides)
    return types.SimpleNamespace(**values)


def _capture_normal_command(monkeypatch, args):
    """执行 execute_encode，捕获普通编码分支传给 build_encode_command 的参数。"""
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return ["ffmpeg", "-i", "in.mp4", "out.mp4"]

    monkeypatch.setattr(video_executor, "build_encode_command", fake_build)
    monkeypatch.setattr(video_executor, "run_ffmpeg_command", lambda cmd, **kw: 0)
    monkeypatch.setattr(video_executor, "_post_transfer", lambda *a, **k: None)

    result = video_executor.execute_encode(args)
    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    return captured


def _capture_2pass_command(monkeypatch, args):
    """执行 execute_encode，捕获 2-Pass 分支传给 build_2pass_commands 的参数。"""
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return (["ffmpeg", "-pass", "1"], ["ffmpeg", "-pass", "2"])

    monkeypatch.setattr(video_executor, "build_2pass_commands", fake_build)
    monkeypatch.setattr(video_executor, "run_2pass_encode", lambda p1, p2, dry_run=False: 0)
    monkeypatch.setattr(video_executor, "_post_transfer", lambda *a, **k: None)

    result = video_executor.execute_encode(args)
    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    return captured


def _flag_value(cmd, flag):
    """返回命令中 flag 后紧跟的值。"""
    return cmd[cmd.index(flag) + 1]


def _assert_audio(cmd, expected_encoder, expected_bitrate=None):
    """断言命令音频参数：copy 时不得出现 -b:a。"""
    assert _flag_value(cmd, "-c:a") == expected_encoder
    if expected_encoder == "copy":
        assert "-b:a" not in cmd
    else:
        assert _flag_value(cmd, "-b:a") == expected_bitrate


# ---------------------------------------------------------------------------
# 1. 核心回归: 所有预设的音频声明必须与最终命令一致
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("preset_name", PRESET_NAMES)
def test_preset_audio_matches_final_command(tmp_path, monkeypatch, preset_name):
    """历史 bug 回归: 预设声明 copy, 命令就必须是 -c:a copy (而不是 aac)。"""
    args = make_args(tmp_path, preset=preset_name)
    captured = _capture_normal_command(monkeypatch, args)
    preset = QUALITY_PRESETS[preset_name]

    # 唯一数据源: 传给 builder 的参数必须来自 resolve 结果
    assert captured["audio_encoder"] == preset["audio_encoder"]
    assert captured["audio_bitrate"] == preset["audio_bitrate"]
    assert captured["encoder"] == preset["encoder"]

    cmd = core.build_encode_command(**captured)
    _assert_audio(cmd, preset["audio_encoder"], preset["audio_bitrate"])


def test_preset_copy_never_forced_to_aac(tmp_path, monkeypatch):
    """六个预设都不允许出现强制 aac 的旧行为。"""
    for preset_name in PRESET_NAMES:
        args = make_args(tmp_path, preset=preset_name)
        captured = _capture_normal_command(monkeypatch, args)
        cmd = core.build_encode_command(**captured)
        assert _flag_value(cmd, "-c:a") == "copy", preset_name
        assert "-b:a" not in cmd, preset_name


# ---------------------------------------------------------------------------
# 2. 关键命令快照
# ---------------------------------------------------------------------------

def test_golden_x264_preset_command(tmp_path, monkeypatch):
    args = make_args(tmp_path)
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)

    assert "ffmpeg" in cmd[0]
    assert "-y" in cmd
    assert _flag_value(cmd, "-c:v") == "libx264"
    assert _flag_value(cmd, "-crf") == "18"
    assert _flag_value(cmd, "-preset") == "medium"
    assert "-map" in cmd and "0:v:0" in cmd
    assert "0:a:0?" in cmd          # 默认仅保留第 1 条音轨
    assert "-sn" in cmd             # 默认不保留字幕
    _assert_audio(cmd, "copy")
    assert cmd[-1].endswith(".mp4")


def test_golden_x265_preset_command(tmp_path, monkeypatch):
    args = make_args(tmp_path, preset="【均衡画质】x265/HEVC 高效压缩 (CRF20)")
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)

    assert _flag_value(cmd, "-c:v") == "libx265"
    assert _flag_value(cmd, "-crf") == "20"
    _assert_audio(cmd, "copy")


def test_golden_nvenc_preset_command(tmp_path, monkeypatch):
    args = make_args(tmp_path, preset="【速度优先】NVIDIA 显卡加速")
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)

    assert _flag_value(cmd, "-c:v") == "h264_nvenc"
    assert _flag_value(cmd, "-cq") == "23"     # preset 的 cq 值
    assert _flag_value(cmd, "-preset") == "p4"
    _assert_audio(cmd, "copy")
    # preset extra_args 必须进入命令
    for token in ("-rc", "vbr", "-maxrate", "20M"):
        assert token in cmd


def test_custom_aac_bitrate_command(tmp_path, monkeypatch):
    """自定义模式: AAC 256k 必须原样进入命令。"""
    args = make_args(
        tmp_path,
        preset="自定义 (Custom)",
        encoder="H.264 (CPU - libx264)",
        crf=20,
        audio_encoder="AAC (推荐)",
        audio_bitrate="256k",
    )
    captured = _capture_normal_command(monkeypatch, args)

    assert captured["audio_encoder"] == "aac"
    assert captured["audio_bitrate"] == "256k"

    cmd = core.build_encode_command(**captured)
    assert _flag_value(cmd, "-c:v") == "libx264"
    _assert_audio(cmd, "aac", "256k")


def test_custom_audio_copy_command(tmp_path, monkeypatch):
    args = make_args(
        tmp_path,
        preset="自定义 (Custom)",
        audio_encoder="复制 (不重新编码)",
    )
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)
    _assert_audio(cmd, "copy")


def test_subtitle_burn_filter(tmp_path, monkeypatch):
    subtitle = tmp_path / "sub.ass"
    subtitle.write_text("[Script Info]\nTitle: test", encoding="utf-8")
    args = make_args(
        tmp_path,
        subtitle=str(subtitle),
        subtitle_tracks="全部保留",
    )
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)

    vf = _flag_value(cmd, "-vf")
    assert "subtitles=" in vf
    assert "-c:s" in cmd and _flag_value(cmd, "-c:s") == "copy"
    assert "0:s?" in cmd


def test_subtitle_embed_maps_external_track_as_soft_stream(tmp_path, monkeypatch):
    """内封: 外挂字幕作为第二个输入 map 成软字幕流, 不再走 subtitles 滤镜。"""
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    args = make_args(
        tmp_path,
        subtitle=str(subtitle),
        subtitle_mode="内封（转为软字幕流）",
        output_format="MKV",
    )
    captured = _capture_normal_command(monkeypatch, args)
    assert captured["subtitle_mode"] == "embed"

    cmd = core.build_encode_command(**captured)
    # 不烧录: 没有 subtitles 滤镜
    assert "-vf" not in cmd or "subtitles=" not in _flag_value(cmd, "-vf")
    # 两个输入 + 映射外挂字幕流
    assert cmd.count("-i") == 2
    assert _flag_value(cmd, "-i") == captured["input_path"]
    assert "1:0" in cmd
    assert "-sn" not in cmd
    assert _flag_value(cmd, "-c:s") == "copy"


def test_subtitle_embed_mov_uses_mov_text(tmp_path, monkeypatch):
    """MOV 容器里软字幕需要 mov_text, 不能直接 copy。"""
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    args = make_args(
        tmp_path,
        subtitle=str(subtitle),
        subtitle_mode="内封（转为软字幕流）",
        output_format="MOV",
    )
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)
    assert _flag_value(cmd, "-c:s") == "mov_text"


def test_subtitle_embed_keeps_selected_source_tracks(tmp_path, monkeypatch):
    """内封外挂字幕时仍可按选择保留源字幕流, 但不能再写 -sn。"""
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    args = make_args(
        tmp_path,
        subtitle=str(subtitle),
        subtitle_mode="内封（转为软字幕流）",
        subtitle_tracks="全部保留",
        output_format="MKV",
    )
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)
    assert "0:s?" in cmd
    assert "1:0" in cmd
    assert "-sn" not in cmd


def test_subtitle_none_mode_ignores_external_file(tmp_path, monkeypatch):
    """不处理: 选了文件也不烧录、不内封。"""
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    args = make_args(tmp_path, subtitle=str(subtitle), subtitle_mode="不处理")
    captured = _capture_normal_command(monkeypatch, args)
    assert captured["subtitle_mode"] == "none"
    cmd = core.build_encode_command(**captured)
    assert cmd.count("-i") == 1
    assert "1:0" not in cmd
    assert "subtitles=" not in " ".join(cmd)


def test_stream_mapping_modes(tmp_path, monkeypatch):
    # 全部保留
    args = make_args(tmp_path, audio_tracks="全部保留", subtitle_tracks="全部保留")
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)
    assert "0:a?" in cmd and "0:s?" in cmd
    assert "-an" not in cmd

    # 不保留音轨 / 字幕
    args2 = make_args(tmp_path, audio_tracks="不保留音轨", subtitle_tracks="不保留字幕")
    captured2 = _capture_normal_command(monkeypatch, args2)
    cmd2 = core.build_encode_command(**captured2)
    assert "-an" in cmd2
    assert "-sn" in cmd2
    assert "-c:a" not in cmd2


# ---------------------------------------------------------------------------
# 3. CPU 2-Pass
# ---------------------------------------------------------------------------

def test_cpu_two_pass_command(tmp_path, monkeypatch):
    args = make_args(
        tmp_path,
        preset="自定义 (Custom)",
        encoder="H.264 (CPU - libx264)",
        rate_control="2-Pass VBR (两遍编码)",
        video_bitrate="10M",
    )
    captured = _capture_2pass_command(monkeypatch, args)

    # 2-Pass 分支同样必须使用 resolved 音频参数 (旧 bug: 强制 aac)
    assert captured["audio_encoder"] == "copy"
    assert captured["audio_bitrate"] == "192k"
    assert captured["encoder"] == "libx264"

    pass1, pass2 = core.build_2pass_commands(**captured)
    assert "-pass" in pass1 and _flag_value(pass1, "-pass") == "1"
    assert "-an" in pass1
    assert pass1[-1] == ("NUL" if os.name == "nt" else "/dev/null")

    assert _flag_value(pass2, "-pass") == "2"
    assert _flag_value(pass2, "-b:v") == "10M"
    _assert_audio(pass2, "copy")
    assert pass2[-1] == captured["output_path"]


# ---------------------------------------------------------------------------
# 4. remux / extract 快照
# ---------------------------------------------------------------------------

def test_remux_command_snapshot():
    cmd = core.build_remux_command(
        "in.mkv", "out.mp4", audio_tracks="all", subtitle_tracks="all"
    )
    assert "-c" in cmd and _flag_value(cmd, "-c") == "copy"
    assert "0:v" in cmd and "0:a?" in cmd and "0:s?" in cmd
    assert "-y" in cmd
    assert cmd[-1] == "out.mp4"


def test_extract_audio_copy_snapshot():
    cmd = core.build_extract_audio_command(
        "in.mp4", "out.m4a", audio_encoder="copy", audio_bitrate="192k"
    )
    assert "-vn" in cmd
    _assert_audio(cmd, "copy")


def test_extract_audio_transcode_snapshot():
    cmd = core.build_extract_audio_command(
        "in.mp4", "out.mp3", audio_encoder="libmp3lame", audio_bitrate="320k"
    )
    _assert_audio(cmd, "libmp3lame", "320k")


def test_extract_video_snapshot():
    cmd = core.build_extract_video_command("in.mp4", "out_noaudio.mp4")
    assert "-an" in cmd
    assert _flag_value(cmd, "-c:v") == "copy"


# ---------------------------------------------------------------------------
# 5. 日志可核对: print_encode_info 输出音频行
# ---------------------------------------------------------------------------

def test_print_encode_info_contains_audio(capsys):
    copy_params = EncodeParams(
        input_path="a.mp4", output_path="b.mp4", audio_encoder="copy"
    )
    print_encode_info(copy_params, QUALITY_PRESETS)
    assert "音频: 直接复制" in capsys.readouterr().out

    aac_params = EncodeParams(
        input_path="a.mp4", output_path="b.mp4",
        audio_encoder="aac", audio_bitrate="256k", is_custom=True,
    )
    print_encode_info(aac_params, QUALITY_PRESETS)
    out = capsys.readouterr().out
    assert "音频: aac / 256k" in out

# ---------------------------------------------------------------------------
# 6. M3.2: 硬件 RC 真实映射 (不再伪装 2-Pass)
# ---------------------------------------------------------------------------

def test_hardware_2pass_selection_uses_real_vbr_multipass(tmp_path, monkeypatch):
    """硬件 + 2-Pass: 走普通分支, 命令回退 VBR + multipass, 不出现 -2pass。"""
    args = make_args(
        tmp_path,
        preset="自定义 (Custom)",
        encoder="H.264 (NVIDIA NVENC)",
        rate_control="2-Pass VBR (两遍编码)",
        video_bitrate="10M",
    )
    captured = _capture_normal_command(monkeypatch, args)

    cmd = core.build_encode_command(**captured)
    assert "-2pass" not in cmd
    assert "vbr_hq" not in cmd
    assert _flag_value(cmd, "-rc") == "vbr"
    assert _flag_value(cmd, "-multipass") == "fullres"
    assert _flag_value(cmd, "-c:v") == "h264_nvenc"


def test_hardware_2pass_qsv_amf_fall_back_without_fake_2pass(tmp_path, monkeypatch):
    for encoder in ("H.264 (Intel QSV)", "H.264 (AMD AMF)"):
        args = make_args(
            tmp_path,
            preset="自定义 (Custom)",
            encoder=encoder,
            rate_control="2-Pass VBR (两遍编码)",
            video_bitrate="10M",
        )
        captured = _capture_normal_command(monkeypatch, args)
        cmd = core.build_encode_command(**captured)
        assert "-2pass" not in cmd, encoder
        assert "vbr_hq" not in cmd, encoder


def test_nvenc_preset_command_keeps_preset_quality_snapshot(tmp_path, monkeypatch):
    """预设模式仍是 -cq + 预设 extra_args (能力映射只作用于自定义模式)。"""
    args = make_args(tmp_path, preset="【速度优先】NVIDIA 显卡加速")
    captured = _capture_normal_command(monkeypatch, args)
    cmd = core.build_encode_command(**captured)

    assert "-2pass" not in cmd
    assert _flag_value(cmd, "-cq") == "23"
    assert _flag_value(cmd, "-preset") == "p4"
    _assert_audio(cmd, "copy")


def test_custom_nvenc_crf_maps_to_rc_vbr_cq():
    cmd = core.build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_nvenc", crf=20, rc_mode="crf")
    assert _flag_value(cmd, "-rc") == "vbr"
    assert _flag_value(cmd, "-cq") == "20"
    assert _flag_value(cmd, "-b:v") == "0"
    assert "-2pass" not in cmd


def test_custom_amf_speed_uses_quality_flag():
    cmd = core.build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_amf", crf=20, rc_mode="crf",
        speed_preset="balanced")
    assert _flag_value(cmd, "-quality") == "balanced"
    assert "-preset" not in cmd
