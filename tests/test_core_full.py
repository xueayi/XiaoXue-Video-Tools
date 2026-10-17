# -*- coding: utf-8 -*-
"""core.py 覆盖测试: 命令构建 + FFmpeg 执行 (mock Popen)。"""

import pytest

import src.core as core
from src.core import (
    _build_stream_map_args, _check_hardware_encoder_error,
    build_2pass_commands, build_encode_command, build_extract_audio_command,
    build_extract_video_command, build_remux_command,
    build_replace_audio_command, run_2pass_encode, run_ffmpeg_command,
)
from src.process import CompletedProcess, ExecutableMissingError


# ----------------------------------------------------------------
# 流映射
# ----------------------------------------------------------------

@pytest.mark.parametrize("stream_type, none_flag", [("a", "-an"), ("s", "-sn")])
def test_stream_map_none(stream_type, none_flag):
    assert _build_stream_map_args(stream_type, "none") == [none_flag]


def test_stream_map_all():
    assert _build_stream_map_args("a", "all") == ["-map", "0:a?"]


def test_stream_map_custom():
    args = _build_stream_map_args("a", "custom", "0, 2, x")
    assert args == ["-map", "0:a:0?", "-map", "0:a:2?"]


def test_stream_map_digit_and_fallback():
    assert _build_stream_map_args("a", "1") == ["-map", "0:a:1?"]
    assert _build_stream_map_args("a", "whatever") == ["-map", "0:a?"]
    assert _build_stream_map_args("a", "custom", "") == ["-map", "0:a?"]


# ----------------------------------------------------------------
# 命令构建
# ----------------------------------------------------------------

def _flag_value(cmd, flag):
    """返回命令中 flag 后紧跟的参数值。"""
    return cmd[cmd.index(flag) + 1]


def test_build_encode_basic():
    cmd = build_encode_command("in.mp4", "out.mp4")
    assert cmd[0].endswith("ffmpeg") or "ffmpeg" in cmd[0]
    assert "out.mp4" == cmd[-1]
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-crf" not in cmd  # 默认无 crf


def test_build_encode_preset_full():
    cmd = build_encode_command(
        "in.mp4", "out.mp4",
        preset_name="【均衡画质】x264 常用导出 (CRF18)",
        subtitle_path="C:\\subs\\a.ass",
        resolution="1280x720", fps=30)
    joined = " ".join(cmd)
    assert "-crf" in cmd and "18" in cmd
    assert "subtitles=" in joined and "1280" in joined
    assert "-r" in cmd and "30" in cmd


def test_build_encode_nvenc_preset_extra_args():
    cmd = build_encode_command(
        "in.mp4", "out.mp4", preset_name="【速度优先】NVIDIA 显卡加速",
        extra_args="-tune film")
    assert "h264_nvenc" in cmd
    assert "-rc" in cmd and "vbr" in cmd  # 预设 extra_args 注入
    assert "-tune" in cmd  # 用户 extra_args 与预设合并
    cmd2 = build_encode_command(
        "in.mp4", "out.mp4", preset_name="【速度优先】NVIDIA 显卡加速")
    assert "-rc" in cmd2 and "vbr" in cmd2  # 无用户参数时仅预设参数


def test_build_encode_rc_modes():
    nvenc_vbr = build_encode_command("i.mp4", "o.mp4", encoder="h264_nvenc",
                                     bitrate="8M", rc_mode="vbr")
    assert "-rc" in nvenc_vbr and "vbr" in nvenc_vbr
    amf_cbr = build_encode_command("i.mp4", "o.mp4", encoder="h264_amf",
                                   bitrate="8M", rc_mode="cbr")
    # M3.2: AMF CBR = -rc cbr -b:v X -maxrate X (无 minrate)
    assert "-rc" in amf_cbr and "cbr" in amf_cbr
    assert "-maxrate" in amf_cbr and "-minrate" not in amf_cbr
    qsv_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_qsv", crf=20)
    assert "-global_quality" in qsv_cq
    amf_crf = build_encode_command("i.mp4", "o.mp4", encoder="h264_amf", crf=20)
    assert "-qp_i" in amf_crf
    cpu_2pass = build_encode_command("i.mp4", "o.mp4", bitrate="8M",
                                     rc_mode="2pass")
    # M3.2: CPU 2pass 在单命令层面只给 -b:v (真两遍由 build_2pass_commands 负责)
    assert _flag_value(cpu_2pass, "-b:v") == "8M"
    assert "-maxrate" not in cpu_2pass
    nvenc_2pass = build_encode_command("i.mp4", "o.mp4", encoder="h264_nvenc",
                                       bitrate="8M", rc_mode="2pass")
    # 硬件不再伪装 2-Pass: NVENC 回退 VBR + multipass
    assert "vbr_hq" not in nvenc_2pass
    assert "-2pass" not in nvenc_2pass
    assert "-multipass" in nvenc_2pass and "fullres" in nvenc_2pass
    amf_2pass = build_encode_command("i.mp4", "o.mp4", encoder="h264_amf",
                                     bitrate="8M", rc_mode="2pass")
    assert "vbr_peak" in amf_2pass
    assert "-2pass" not in amf_2pass
    nvenc_2pass_cq = build_encode_command("i.mp4", "o.mp4",
                                          encoder="h264_nvenc", crf=20,
                                          rc_mode="2pass")
    assert "-cq" in nvenc_2pass_cq
    assert "-2pass" not in nvenc_2pass_cq
    qsv_2pass_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_qsv",
                                        crf=20, rc_mode="2pass")
    assert "-global_quality" in qsv_2pass_cq
    cbr_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_nvenc",
                                  crf=20, rc_mode="cbr")
    assert "-cq" in cbr_cq
    vbr_cq_cpu = build_encode_command("i.mp4", "o.mp4", crf=20, rc_mode="vbr")
    assert "-crf" in vbr_cq_cpu
    vbr_cpu_bitrate = build_encode_command("i.mp4", "o.mp4", bitrate="8M",
                                           rc_mode="vbr")
    assert "-maxrate" in vbr_cpu_bitrate
    cbr_cpu = build_encode_command("i.mp4", "o.mp4", bitrate="8M",
                                   rc_mode="cbr")
    assert "-minrate" in cbr_cpu
    cbr_cpu_cq = build_encode_command("i.mp4", "o.mp4", crf=20, rc_mode="cbr")
    assert "-crf" in cbr_cpu_cq
    vbr_nv_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_nvenc",
                                     crf=20, rc_mode="vbr")
    assert "-cq" in vbr_nv_cq
    vbr_amf_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_amf",
                                      crf=20, rc_mode="vbr")
    # AMF 无码率时回退 CQP (M3.2: 不再是 CPU 的 -crf)
    assert "-rc" in vbr_amf_cq and "cqp" in vbr_amf_cq
    assert "-qp_i" in vbr_amf_cq and "-crf" not in vbr_amf_cq
    cbr_qsv_cq = build_encode_command("i.mp4", "o.mp4", encoder="h264_qsv",
                                      crf=20, rc_mode="cbr")
    assert "-global_quality" in cbr_qsv_cq


def test_build_encode_hardware_rc_real_mapping():
    """M3.2: 硬件 RC 映射到自身参数, 不再出现假的 -2pass。"""
    nvenc_crf = build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_nvenc", crf=20, rc_mode="crf")
    assert _flag_value(nvenc_crf, "-rc") == "vbr"
    assert _flag_value(nvenc_crf, "-cq") == "20"
    assert _flag_value(nvenc_crf, "-b:v") == "0"
    assert "-2pass" not in nvenc_crf

    nvenc_cbr = build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_nvenc", bitrate="8M", rc_mode="cbr")
    assert _flag_value(nvenc_cbr, "-rc") == "cbr"
    assert "-minrate" in nvenc_cbr and "-maxrate" in nvenc_cbr

    qsv_crf = build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_qsv", crf=22, rc_mode="crf")
    assert _flag_value(qsv_crf, "-global_quality") == "22"

    amf_crf = build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_amf", crf=22, rc_mode="crf")
    assert _flag_value(amf_crf, "-rc") == "cqp"
    assert _flag_value(amf_crf, "-qp_i") == "22"


def test_build_encode_amf_uses_quality_speed_flag():
    """AMF 速度档使用 -quality, 而不是 x264 风格的 -preset。"""
    cmd = build_encode_command(
        "i.mp4", "o.mp4", encoder="h264_amf", crf=20, rc_mode="crf",
        speed_preset="balanced")
    assert _flag_value(cmd, "-quality") == "balanced"
    assert "-preset" not in cmd
    cpu = build_encode_command(
        "i.mp4", "o.mp4", encoder="libx264", crf=20, rc_mode="crf",
        speed_preset="medium")
    assert _flag_value(cpu, "-preset") == "medium"
    assert "-quality" not in cpu


def test_build_encode_hardware_2pass_prints_fallback_hint(capsys):
    build_encode_command("i.mp4", "o.mp4", encoder="h264_nvenc",
                         bitrate="8M", rc_mode="2pass")
    out = capsys.readouterr().out
    assert "[提示]" in out and "不支持 2-Pass" in out and "multipass" in out

    # CPU 真正的两遍编码分支不打印回退提示
    build_encode_command("i.mp4", "o.mp4", bitrate="8M", rc_mode="2pass")
    out_cpu = capsys.readouterr().out
    assert "[提示]" not in out_cpu


def test_build_encode_hardware_never_fake_2pass():
    for encoder in ("h264_nvenc", "hevc_nvenc", "h264_qsv", "h264_amf"):
        for rc in ("2pass", "vbr", "cbr", "crf"):
            cmd = build_encode_command(
                "i.mp4", "o.mp4", encoder=encoder, bitrate="8M",
                crf=20, rc_mode=rc)
            assert "-2pass" not in cmd, (encoder, rc)
            assert "vbr_hq" not in cmd, (encoder, rc)



def test_build_encode_audio_subtitle_switches():
    cmd = build_encode_command("i.mp4", "o.mp4", audio_tracks="none",
                               subtitle_tracks="none")
    assert "-an" in cmd and "-sn" in cmd
    assert "-c:a" not in cmd
    cmd2 = build_encode_command("i.mp4", "o.mp4", audio_tracks="all",
                                subtitle_tracks="all")
    assert "-c:a" in cmd2 and "-c:s" in cmd2
    cmd3 = build_encode_command("i.mp4", "o.mp4", audio_tracks="none",
                                audio_encoder="copy")
    assert "-c:a" not in cmd3
    cmd4 = build_encode_command("i.mp4", "o.mp4", audio_tracks="all",
                                audio_encoder="copy")
    assert "-b:a" not in cmd4


def test_build_encode_extra_args_and_fallback_resolution():
    cmd = build_encode_command("i.mp4", "o.mp4", extra_args="-ss 10")
    assert "-ss" in cmd and "10" in cmd
    cmd2 = build_encode_command("i.mp4", "o.mp4", resolution="not-a-res")
    assert "-vf" not in cmd2
    cmd3 = build_encode_command("i.mp4", "o.mp4", resolution="axb")
    assert "scale=a:b" in " ".join(cmd3)  # 宽高不合法时原样透传


def test_build_replace_audio_command():
    cmd = build_replace_audio_command("v.mp4", "a.m4a", "o.mp4")
    assert "-map" in cmd and "1:a:0" in cmd and "-c:v" in cmd and "copy" in cmd
    cmd2 = build_replace_audio_command("v.mp4", "a.m4a", "o.mp4",
                                       audio_encoder="copy")
    assert "-b:a" not in cmd2


def test_build_remux_command():
    cmd = build_remux_command("i.mkv", "o.mp4", audio_tracks="none")
    assert "-c" in cmd and "copy" in cmd and "-an" in cmd


def test_build_extract_audio_video():
    cmd = build_extract_audio_command("i.mp4", "o.m4a")
    assert "-vn" in cmd and "-b:a" in cmd
    cmd2 = build_extract_audio_command("i.mp4", "o.m4a", audio_encoder="copy")
    assert "-b:a" not in cmd2
    cmd3 = build_extract_video_command("i.mp4", "o.mp4")
    assert "-an" in cmd3 and "copy" in cmd3


# ----------------------------------------------------------------
# 2-Pass
# ----------------------------------------------------------------

def test_build_2pass_cpu():
    p1, p2 = build_2pass_commands("i.mp4", "o.mp4", bitrate="10M",
                                  speed_preset="medium")
    assert "-pass" in p1 and "1" in p1
    assert "-pass" in p2 and "2" in p2
    assert "-an" in p1 and "NUL" in p1 or "/dev/null" in p1


def test_build_2pass_nvenc_amf_qsv():
    p1, p2 = build_2pass_commands("i.mp4", "o.mp4", encoder="h264_nvenc",
                                  bitrate="10M")
    assert "-multipass" in p1
    p1a, p2a = build_2pass_commands("i.mp4", "o.mp4", encoder="h264_amf",
                                    bitrate="10M")
    assert "-2pass" in p1a
    p1b, _ = build_2pass_commands(
        "i.mp4", "o.mp4", preset_name="【均衡画质】x264 常用导出 (CRF18)",
        bitrate="10M", subtitle_path="s.ass", extra_args="-tune film",
        audio_tracks="all", subtitle_tracks="all")
    joined = " ".join(p1b)
    assert "subtitles=" in joined and "-tune" in joined


def test_run_2pass_dry_run():
    rc = run_2pass_encode(["ffmpeg", "1"], ["ffmpeg", "2"], dry_run=True)
    assert rc == 0


def test_run_2pass_pass1_fails(monkeypatch):
    monkeypatch.setattr(core, "run_ffmpeg_command", lambda *a, **k: 1)
    assert run_2pass_encode(["a"], ["b"]) == 1


def test_run_2pass_success_cleans_log(monkeypatch, tmp_path, monkeypatch_tmp=None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ffmpeg2pass.log").write_text("x")
    calls = []

    def fake_run(cmd, dry_run=False, **kw):
        calls.append(cmd)
        return 0
    monkeypatch.setattr(core, "run_ffmpeg_command", fake_run)
    rc = run_2pass_encode(["a"], ["b"])
    assert rc == 0 and len(calls) == 2
    assert not (tmp_path / "ffmpeg2pass.log").exists()


# ----------------------------------------------------------------
# run_ffmpeg_command (经 ProcessRunner; mock run_ffmpeg_streaming)
# ----------------------------------------------------------------

def _fake_streaming(lines=(), exit_code=0, cancelled=False, channel="stderr"):
    """模拟 run_ffmpeg_streaming 的双通道回调 (M2.4)。

    channel="stderr" 时把 lines 走日志通道, channel="progress" 时走进度通道;
    两者都会额外转发给兼容的 on_line 通道 (与真实实现一致)。
    """

    def fake(cmd, on_line=None, on_progress=None, on_log=None, env=None):
        for line in lines:
            if channel == "progress" and on_progress is not None:
                on_progress(line)
            if channel == "stderr" and on_log is not None:
                on_log(line)
            if on_line is not None:
                on_line(line)
        return CompletedProcess(exit_code=exit_code, cancelled=cancelled)
    return fake


def test_run_ffmpeg_dry_run():
    assert run_ffmpeg_command(["ffmpeg", "-y"], dry_run=True) == 0


def test_run_ffmpeg_success(monkeypatch, capsys):
    progress_lines = ["frame=1\n", "progress=continue\n"]

    def fake(cmd, on_line=None, on_progress=None, on_log=None, env=None):
        for line in progress_lines:
            on_progress(line)
        on_log("stderr 日志行\n")
        return CompletedProcess(exit_code=0)

    monkeypatch.setattr(core, "run_ffmpeg_streaming", fake)
    got = []
    rc = run_ffmpeg_command(["ffmpeg"], progress_callback=got.append)
    assert rc == 0
    # 进度回调只收 stdout 进度行, stderr 日志行只进日志
    assert got == progress_lines
    out = capsys.readouterr().out
    assert "stderr 日志行" in out
    assert "progress=continue" not in out


def test_run_ffmpeg_without_explicit_progress_callback(monkeypatch):
    """未显式传 progress_callback 时仍正常执行 (GUI 走 TaskContext 通道)。"""
    monkeypatch.setattr(core, "run_ffmpeg_streaming", _fake_streaming(
        [""], exit_code=0))
    assert run_ffmpeg_command(["ffmpeg"]) == 0


def test_run_ffmpeg_nonzero_with_hw_error(monkeypatch):
    monkeypatch.setattr(core, "run_ffmpeg_streaming", _fake_streaming(
        ["No NVENC capable devices found\n"], exit_code=1))
    assert run_ffmpeg_command(["ffmpeg"]) == 1


def test_run_ffmpeg_filenotfound(monkeypatch):
    def boom(*args, **kwargs):
        raise ExecutableMissingError("找不到可执行文件: ffmpeg")
    monkeypatch.setattr(core, "run_ffmpeg_streaming", boom)
    assert run_ffmpeg_command(["ffmpeg"]) == -1


def test_run_ffmpeg_generic_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("io error")
    monkeypatch.setattr(core, "run_ffmpeg_streaming", boom)
    assert run_ffmpeg_command(["ffmpeg"]) == -1


def test_run_ffmpeg_cancelled_raises(monkeypatch):
    from src.task.context import TaskCancelled
    monkeypatch.setattr(core, "run_ffmpeg_streaming", _fake_streaming(
        exit_code=0, cancelled=True))
    with pytest.raises(TaskCancelled):
        run_ffmpeg_command(["ffmpeg"])


def test_run_ffmpeg_none_exit_code_returns_minus_one(monkeypatch):
    monkeypatch.setattr(core, "run_ffmpeg_streaming", _fake_streaming(
        exit_code=None))
    assert run_ffmpeg_command(["ffmpeg"]) == -1


def test_run_2pass_cancelled_between_passes(monkeypatch):
    from src.task.context import (
        TaskCancelled, TaskContext, reset_current_task, set_current_task,
    )
    calls = []

    def fake_run(cmd, dry_run=False, **kw):
        calls.append(cmd)
        return 0
    monkeypatch.setattr(core, "run_ffmpeg_command", fake_run)

    context = TaskContext()
    context.cancel()
    token = set_current_task(context)
    try:
        with pytest.raises(TaskCancelled):
            run_2pass_encode(["a"], ["b"])
    finally:
        reset_current_task(token)
    assert len(calls) == 1  # Pass 1 后已取消, 不再启动 Pass 2


# ----------------------------------------------------------------
# 硬件编码器错误提示
# ----------------------------------------------------------------

def test_check_hw_error_nvenc():
    _check_hardware_encoder_error(
        ["Error while opening encoder", "No NVENC capable devices found"])
    _check_hardware_encoder_error(
        ["The minimum required Nvidia driver for nvenc is missing"])


def test_check_hw_error_amf_and_none():
    _check_hardware_encoder_error(["AMF encoder init failed"])
    _check_hardware_encoder_error(["some other error"])


def test_build_encode_full_matrix():
    """穷举 rc_mode x 编码器 x 质量参数, 确保全分支覆盖。"""
    for rc in [None, "2pass", "vbr", "cbr"]:
        for enc in ["libx264", "h264_nvenc", "h264_qsv", "h264_amf"]:
            for q in [{"crf": 20}, {"bitrate": "8M"}]:
                cmd = build_encode_command("i.mp4", "o.mp4", encoder=enc,
                                           rc_mode=rc, **q)
                assert "-c:v" in cmd
                assert cmd[-1] == "o.mp4"


def test_check_hw_error_qsv_and_amf():
    _check_hardware_encoder_error(["Error initializing an MFX session"])
    _check_hardware_encoder_error(["CreateComponent failed"])


def test_check_hw_error_driver_keyword():
    _check_hardware_encoder_error(
        ["Cannot load cuvidparser", "Failed to init NVENC"])


def test_build_2pass_resolution_and_fps():
    p1, p2 = build_2pass_commands("i.mp4", "o.mp4", bitrate="10M",
                                  resolution="1280x720", fps=30)
    joined = " ".join(p1)
    assert "scale=1280:720" in joined
    assert "-r" in p1
    p1b, p2b = build_2pass_commands("i.mp4", "o.mp4", bitrate="10M",
                                    resolution="axb")
    p1c, _ = build_2pass_commands("i.mp4", "o.mp4", bitrate="10M",
                                  subtitle_path="C:\s.ass")
    assert "subtitles=" in " ".join(p1c)


def test_run_2pass_cleanup_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ffmpeg2pass.log").write_text("x")

    def fake_remove(p):
        raise OSError("locked")
    monkeypatch.setattr(core.os, "remove", fake_remove)

    def fake_run(cmd, dry_run=False, **kw):
        return 0
    monkeypatch.setattr(core, "run_ffmpeg_command", fake_run)
    assert run_2pass_encode(["a"], ["b"]) == 0
