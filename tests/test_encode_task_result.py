# -*- coding: utf-8 -*-
"""execute_encode 返回 TaskResult 的语义测试 (M2.1)。

覆盖: 成功产出 / FFmpeg 非零退出 / 失败保留已产出文件 / dry_run / 分发失败降级为警告。
不执行真实 FFmpeg (run_ffmpeg_command 全部 mock)。
"""

import types

import pytest

import src.executors.video_executor as ve
from src.task.result import TaskResult
from src.task.status import TaskStatus


def make_args(tmp_path, **overrides):
    """构造 execute_encode 所需 args（input 真实存在以通过 validate）。"""
    video = tmp_path / "input.mp4"
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


@pytest.fixture
def mocked_run(monkeypatch):
    """mock 命令构建与执行, 返回可注入退出码的 state。"""
    state = {"return_code": 0}
    monkeypatch.setattr(
        ve, "build_encode_command",
        lambda **kwargs: ["ffmpeg", "-i", "in.mp4", "out.mp4"])
    monkeypatch.setattr(
        ve, "run_ffmpeg_command",
        lambda cmd, **kwargs: state["return_code"])
    return state


@pytest.fixture
def captured(mocked_run, monkeypatch):
    """在 mocked_run 基础上屏蔽分发 (大多数用例不关心)。"""
    monkeypatch.setattr(ve, "_post_transfer", lambda *a, **k: [])
    return mocked_run


def test_success_result_has_output_and_zero_exit(tmp_path, captured):
    result = ve.execute_encode(make_args(tmp_path))
    assert isinstance(result, TaskResult)
    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    assert result.outputs
    assert result.outputs[0].endswith(".mp4")
    assert result.legacy_success is True


def test_ffmpeg_nonzero_exit_is_failed(tmp_path, captured):
    captured["return_code"] = 1
    result = ve.execute_encode(make_args(tmp_path))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 1
    assert "退出码 1" in result.message
    assert result.legacy_success is False


def test_failed_result_keeps_produced_output(tmp_path, captured):
    captured["return_code"] = 2
    args = make_args(tmp_path, output=str(tmp_path / "partial.mp4"))
    (tmp_path / "partial.mp4").write_bytes(b"partial")

    result = ve.execute_encode(args)
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 2
    assert result.outputs == (str(tmp_path / "partial.mp4"),)


def test_dry_run_marks_details_and_skips_transfer(tmp_path, mocked_run, monkeypatch):
    transfer_calls = []
    monkeypatch.setattr(
        ve, "_post_transfer", lambda *a, **k: transfer_calls.append(a))
    result = ve.execute_encode(make_args(tmp_path, debug_mode=True))
    assert result.status is TaskStatus.SUCCESS
    assert result.details["dry_run"] is True
    assert result.outputs == ()
    assert "未实际执行" in result.message
    assert transfer_calls == []


def test_validation_failure_is_failed_without_exit_code(tmp_path, captured):
    result = ve.execute_encode(
        make_args(tmp_path, input=str(tmp_path / "missing.mp4")))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code is None
    assert "输入文件不存在" in result.message


def test_transfer_failure_becomes_warning(tmp_path, mocked_run, monkeypatch):
    def boom(src, dst, mode="copy"):
        raise OSError("no space left")

    monkeypatch.setattr(ve, "transfer_file", boom)
    args = make_args(
        tmp_path,
        output=str(tmp_path / "out.mp4"),
        post_transfer_mode="复制到指定目录",
        post_transfer_dir=str(tmp_path / "dest"),
    )
    (tmp_path / "dest").mkdir()
    (tmp_path / "out.mp4").write_bytes(b"x")

    result = ve.execute_encode(args)
    assert result.status is TaskStatus.SUCCESS  # 编码成功, 分发失败不改变状态
    assert any("分发失败" in warning for warning in result.warnings)
