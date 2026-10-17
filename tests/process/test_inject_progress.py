# -*- coding: utf-8 -*-
"""src/process/progress.inject_progress 的注入位置/幂等/非 ffmpeg 测试 (M2.4)。

同时验证各命令 builder 的注入结果不破坏既有命令快照形状
(输出路径仍是最后一个参数, 关键 flag 位置不变)。
"""

import os

import pytest

import src.core as core
from src.compat_encoder import build_compat_encode_command
from src.process.progress import PROGRESS_ARGS, inject_progress


def _flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# ----------------------------------------------------------------
# 基础规则
# ----------------------------------------------------------------

def test_injects_before_output_path():
    cmd = ["ffmpeg", "-y", "-i", "in.mp4", "-c:v", "libx264", "out.mp4"]
    result = inject_progress(cmd)
    assert result == [
        "ffmpeg", "-y", "-i", "in.mp4", "-c:v", "libx264",
        *PROGRESS_ARGS, "out.mp4",
    ]
    assert result[-1] == "out.mp4"
    assert result.index("-progress") == len(result) - 1 - len(PROGRESS_ARGS)


def test_does_not_mutate_input_list():
    cmd = ["ffmpeg", "-i", "in.mp4", "out.mp4"]
    before = list(cmd)
    inject_progress(cmd)
    assert cmd == before


def test_idempotent_when_progress_already_present():
    once = inject_progress(["ffmpeg", "-i", "in.mp4", "out.mp4"])
    twice = inject_progress(once)
    assert twice == once
    assert once.count("-progress") == 1
    assert once.count("-nostats") == 1


def test_respects_user_supplied_progress():
    cmd = ["ffmpeg", "-progress", "pipe:2", "-i", "in.mp4", "out.mp4"]
    assert inject_progress(cmd) == cmd


def test_non_ffmpeg_command_unchanged():
    cmd = ["python", "-c", "print(1)"]
    assert inject_progress(cmd) == cmd


def test_ffprobe_not_injected():
    cmd = ["ffprobe", "-v", "error", "in.mp4"]
    assert inject_progress(cmd) == cmd


def test_non_ffmpeg_executable_with_ffmpeg_substring_not_injected():
    # 必须是 ffmpeg 本体; 包装脚本/名字含 ffmpeg 的其它可执行文件不注入
    cmd = ["ffmpeg-wrapper", "-i", "in.mp4", "out.mp4"]
    assert inject_progress(cmd) == cmd
    assert inject_progress(["my-ffmpeg.exe", "-i", "a", "b"]) == [
        "my-ffmpeg.exe", "-i", "a", "b"]


def test_ffmpeg_exe_path_and_uppercase():
    cmd = [r"C:\bin\ffmpeg.EXE", "-y", "-i", "in.mp4", "out.mp4"]
    result = inject_progress(cmd)
    assert result.count("-progress") == 1
    assert result[-1] == "out.mp4"


def test_empty_and_single_token_commands():
    assert inject_progress([]) == []
    assert inject_progress(["ffmpeg"]) == ["ffmpeg"]
    assert inject_progress(["python"]) == ["python"]


def test_progress_args_are_expected_values():
    assert PROGRESS_ARGS == (
        "-progress", "pipe:1", "-nostats", "-stats_period", "0.5")


# ----------------------------------------------------------------
# 各 builder 注入点
# ----------------------------------------------------------------

def _builder_cases():
    return [
        ("encode", lambda: core.build_encode_command("in.mp4", "out.mp4")),
        ("replace_audio", lambda: core.build_replace_audio_command(
            "v.mp4", "a.mp4", "out.mp4")),
        ("remux", lambda: core.build_remux_command("in.mkv", "out.mp4")),
        ("extract_audio", lambda: core.build_extract_audio_command(
            "in.mp4", "out.m4a")),
        ("extract_video", lambda: core.build_extract_video_command(
            "in.mp4", "out_noaudio.mp4")),
        ("compat", lambda: build_compat_encode_command(
            "s.avs", "v.mp4", "out.mp4")),
    ]


@pytest.mark.parametrize("name,builder", _builder_cases())
def test_builders_inject_progress_before_output(name, builder):
    cmd = builder()
    assert cmd.count("-progress") == 1, name
    assert _flag_value(cmd, "-progress") == "pipe:1"
    assert "-nostats" in cmd
    assert _flag_value(cmd, "-stats_period") == "0.5"
    # 注入在输出路径之前: 输出路径仍是最后一个参数
    assert cmd[-1].endswith((".mp4", ".m4a", ".mkv")), name
    assert cmd.index("-progress") < len(cmd) - 1


def test_builder_injection_keeps_extra_args_before_progress():
    cmd = core.build_encode_command("in.mp4", "out.mp4", extra_args="-ss 10 -t 30")
    assert cmd.index("-ss") < cmd.index("-progress")
    assert cmd[-1] == "out.mp4"


def test_two_pass_injects_only_pass2():
    pass1, pass2 = core.build_2pass_commands("in.mp4", "out.mp4")
    assert "-progress" not in pass1
    assert pass1[-1] == ("NUL" if os.name == "nt" else "/dev/null")
    assert pass2.count("-progress") == 1
    assert pass2[-1] == "out.mp4"


def test_two_pass_audio_and_mapping_still_resolvable():
    """注入不得改变 -c:a / -map / pass 参数的可定位性 (快照测试同款断言)。"""
    _, pass2 = core.build_2pass_commands(
        "in.mp4", "out.mp4", encoder="H.264 (CPU - libx264)",
        bitrate="10M", audio_encoder="copy")
    assert _flag_value(pass2, "-c:a") == "copy"
    assert "-b:a" not in pass2
    assert "0:v:0" in pass2
    assert _flag_value(pass2, "-pass") == "2"
    assert pass2[-1] == "out.mp4"


def test_golden_encode_shape_unchanged_by_injection():
    """等价于 test_command_snapshot 的关键形状断言 (注入后仍成立)。"""
    cmd = core.build_encode_command(
        "in.mp4", "out.mp4",
        preset_name="【均衡画质】x264 常用导出 (CRF18)",
        encoder="H.264 (CPU - libx264)", crf=18,
        speed_preset="medium", audio_encoder="copy",
        audio_tracks="0", subtitle_tracks="none")
    assert _flag_value(cmd, "-c:v") == "libx264"
    assert _flag_value(cmd, "-crf") == "18"
    assert _flag_value(cmd, "-preset") == "medium"
    assert "-sn" in cmd
    assert "0:a:0?" in cmd
    assert cmd[-1] == "out.mp4"


def test_builder_outputs_are_lists_of_str():
    for _name, builder in _builder_cases():
        cmd = builder()
        assert isinstance(cmd, list)
        assert all(isinstance(part, str) for part in cmd)


def test_compat_legacy_build_command_still_valid_without_progress():
    """compat_encoder 直接调用 ffmpeg 时已注入; 旧入口行为保持可用。"""
    cmd = build_compat_encode_command("s.avs", "v.mp4", "o.mp4")
    from src.process.progress import inject_progress as inject

    assert inject(cmd) == cmd  # 已注入 -> 幂等
