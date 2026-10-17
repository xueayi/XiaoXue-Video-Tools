# -*- coding: utf-8 -*-
"""src/ffmpeg/errors.py 测试: 8 类错误规则、取消优先、退出码透传、兜底。

纯 Python 测试 (不依赖 Qt); 样例均来自真实 FFmpeg / 本项目历史错误日志。
"""

import dataclasses

import pytest

from src.ffmpeg.errors import (
    LOG_TAIL_MAX_LINES,
    ErrorCategory,
    UserFacingError,
    classify,
)

# (stderr 样例, 期望分类)
_SAMPLES = [
    # 硬件编码器 (迁自 core.py 的 NVIDIA / Intel / AMD 关键词)
    ("[h264_nvenc @ 000001f4] No NVENC capable devices found",
     ErrorCategory.ENCODER_UNAVAILABLE),
    ("[h264_nvenc @ 000001f4] Cannot load nvcuda.dll",
     ErrorCategory.ENCODER_UNAVAILABLE),
    ("Error initializing an MFX session: device failed",
     ErrorCategory.ENCODER_UNAVAILABLE),
    ("CreateComponent failed for AMF encoder", ErrorCategory.ENCODER_UNAVAILABLE),
    ("Unknown encoder 'h264_qsv'", ErrorCategory.ENCODER_UNAVAILABLE),
    # 容器不兼容 (迁自 remux 容器规则)
    ("[mp4 @ 0000] Could not find tag for codec vp9 in stream #0, "
     "codec not currently supported in container",
     ErrorCategory.CONTAINER_INCOMPATIBLE),
    ("容器不兼容，建议改用 MKV", ErrorCategory.CONTAINER_INCOMPATIBLE),
    # 输入文件
    ("[in#0 @ 0000] Error opening input: No such file or directory",
     ErrorCategory.INPUT_NOT_FOUND),
    ("Invalid data found when processing input", ErrorCategory.INPUT_NOT_FOUND),
    # 输出权限
    ("[out#0/mp4 @ 0000] Error opening output out.mp4: Permission denied",
     ErrorCategory.OUTPUT_PERMISSION_DENIED),
    ("Access is denied", ErrorCategory.OUTPUT_PERMISSION_DENIED),
    # 字幕滤镜
    ("Error opening filters! Error applying subtitles filter",
     ErrorCategory.SUBTITLE_FILTER_ERROR),
    ("No such filter: 'subtitles'", ErrorCategory.SUBTITLE_FILTER_ERROR),
    # FFmpeg 本体缺失
    ("ffmpeg: command not found", ErrorCategory.FFMPEG_NOT_FOUND),
    ("找不到 FFmpeg，请重新放置 ffmpeg.exe", ErrorCategory.FFMPEG_NOT_FOUND),
    # 取消 (文本形态)
    ("Exiting normally, received signal 2.", ErrorCategory.PROCESS_CANCELLED),
    ("任务已停止", ErrorCategory.PROCESS_CANCELLED),
    # 未知
    ("some completely unexpected muxer failure", ErrorCategory.UNKNOWN_FFMPEG_ERROR),
]


def test_error_category_has_eight_members():
    assert len(ErrorCategory) == 8
    assert len({category.value for category in ErrorCategory}) == 8


@pytest.mark.parametrize("stderr_tail,expected", _SAMPLES)
def test_classify_samples(stderr_tail, expected):
    error = classify(stderr_tail)
    assert error.category is expected
    assert error.title
    assert error.causes
    assert error.actions
    assert isinstance(error.causes, tuple)
    assert isinstance(error.actions, tuple)


def test_every_category_has_catalog_content():
    """8 类都要能实际命中 (样例覆盖) 且都有标题/原因/建议。"""
    covered = {expected for _text, expected in _SAMPLES}
    assert covered == set(ErrorCategory)

    for text, _expected in _SAMPLES:
        error = classify(text)
        assert error.title.strip()
        assert all(cause.strip() for cause in error.causes)
        assert all(action.strip() for action in error.actions)


# ----------------------------------------------------------------
# 优先级与兜底
# ----------------------------------------------------------------

def test_cancelled_flag_has_priority():
    """取消优先于任何日志关键词 (即使日志里是 NVENC 错误)。"""
    error = classify(
        "[h264_nvenc @ 0000] No NVENC capable devices found", cancelled=True)
    assert error.category is ErrorCategory.PROCESS_CANCELLED
    assert error.title == "任务已取消"
    assert any("停止" in cause for cause in error.causes)


def test_empty_stderr_falls_back_to_unknown_with_suggestions():
    error = classify("")
    assert error.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR
    assert "FFmpeg 执行失败" == error.title
    assert len(error.actions) >= 2
    assert any("日志" in action for action in error.actions)


def test_none_stderr_is_tolerated():
    error = classify(None)
    assert error.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR


# ----------------------------------------------------------------
# exit_code 透传
# ----------------------------------------------------------------

def test_exit_code_minus_one_means_ffmpeg_missing():
    """run_ffmpeg_command 启动失败返回 -1 且通常没有 stderr。"""
    error = classify("", exit_code=-1)
    assert error.category is ErrorCategory.FFMPEG_NOT_FOUND


def test_exit_code_appears_in_unknown_causes():
    error = classify("unexpected failure", exit_code=4294967295)
    assert error.category is ErrorCategory.UNKNOWN_FFMPEG_ERROR
    assert any("4294967295" in cause for cause in error.causes)


def test_exit_code_does_not_override_keyword_rules():
    error = classify(
        "[out#0/mp4 @ 0000] Error opening output: Permission denied",
        exit_code=1,
    )
    assert error.category is ErrorCategory.OUTPUT_PERMISSION_DENIED
    assert not any("退出码" in cause for cause in error.causes)


def test_keyword_match_has_priority_over_exit_code_heuristic():
    error = classify("No NVENC capable devices found", exit_code=-1)
    assert error.category is ErrorCategory.ENCODER_UNAVAILABLE


# ----------------------------------------------------------------
# 数据模型
# ----------------------------------------------------------------

def test_log_tail_keeps_last_lines_only():
    lines = [f"line {i}" for i in range(30)]
    lines.append("No NVENC capable devices found")
    error = classify("\n".join(lines))
    tail_lines = error.log_tail.splitlines()
    assert len(tail_lines) == LOG_TAIL_MAX_LINES == 20
    assert tail_lines[-1] == "No NVENC capable devices found"


def test_user_facing_error_is_frozen():
    error = classify("no such file or directory")
    with pytest.raises(dataclasses.FrozenInstanceError):
        error.title = "改不了"  # type: ignore[misc]


def test_user_facing_error_defaults():
    error = UserFacingError(title="标题", category=ErrorCategory.UNKNOWN_FFMPEG_ERROR)
    assert error.causes == ()
    assert error.actions == ()
    assert error.log_tail == ""
