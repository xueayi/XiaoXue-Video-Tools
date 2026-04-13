# -*- coding: utf-8 -*-
"""
流映射参数生成测试。
测试 _build_stream_map_args 辅助函数以及 build_encode_command / build_remux_command
在不同音轨/字幕选项下生成的 -map 参数是否正确。
"""
import pytest
from unittest.mock import patch

from src.core import (
    _build_stream_map_args,
    build_encode_command,
    build_remux_command,
)


# ============================================================
# 测试 _build_stream_map_args
# ============================================================

class TestBuildStreamMapArgs:
    """测试流映射参数辅助函数。"""

    # --- 音频流测试 ---

    def test_audio_all(self):
        """全部保留音频。"""
        args = _build_stream_map_args("a", "all")
        assert args == ["-map", "0:a?"]

    def test_audio_none(self):
        """不保留音频。"""
        args = _build_stream_map_args("a", "none")
        assert args == ["-an"]

    def test_audio_single_track(self):
        """单条快捷模式 - 仅第一条。"""
        args = _build_stream_map_args("a", "0")
        assert args == ["-map", "0:a:0?"]

    def test_audio_single_track_1(self):
        """单条快捷模式 - 第二条。"""
        args = _build_stream_map_args("a", "1")
        assert args == ["-map", "0:a:1?"]

    def test_audio_custom_single(self):
        """自定义模式 - 单条。"""
        args = _build_stream_map_args("a", "custom", "0")
        assert args == ["-map", "0:a:0?"]

    def test_audio_custom_multiple(self):
        """自定义模式 - 多条。"""
        args = _build_stream_map_args("a", "custom", "0,2")
        assert args == ["-map", "0:a:0?", "-map", "0:a:2?"]

    def test_audio_custom_with_spaces(self):
        """自定义模式 - 编号带空格。"""
        args = _build_stream_map_args("a", "custom", " 0 , 1 , 3 ")
        assert args == ["-map", "0:a:0?", "-map", "0:a:1?", "-map", "0:a:3?"]

    def test_audio_custom_empty(self):
        """自定义模式 - 空字符串时兜底为全部。"""
        args = _build_stream_map_args("a", "custom", "")
        # custom 但 indices 为空，走 else 分支，custom 不是数字，兜底为全部
        assert args == ["-map", "0:a?"]

    def test_audio_custom_invalid(self):
        """自定义模式 - 非法输入，返回空列表。"""
        args = _build_stream_map_args("a", "custom", "abc,xyz")
        # custom_indices.strip() 非空，进入 custom 分支，但所有元素都不是数字 → 空列表
        assert args == []

    def test_audio_custom_mixed_valid_invalid(self):
        """自定义模式 - 混合合法与非法输入。"""
        args = _build_stream_map_args("a", "custom", "0,abc,2")
        assert args == ["-map", "0:a:0?", "-map", "0:a:2?"]

    def test_audio_unknown_option_fallback(self):
        """未知选项兜底为全部保留。"""
        args = _build_stream_map_args("a", "unknown_value")
        assert args == ["-map", "0:a?"]

    # --- 字幕流测试 ---

    def test_subtitle_all(self):
        """全部保留字幕。"""
        args = _build_stream_map_args("s", "all")
        assert args == ["-map", "0:s?"]

    def test_subtitle_none(self):
        """不保留字幕。"""
        args = _build_stream_map_args("s", "none")
        assert args == ["-sn"]

    def test_subtitle_single(self):
        """单条快捷模式。"""
        args = _build_stream_map_args("s", "0")
        assert args == ["-map", "0:s:0?"]

    def test_subtitle_custom(self):
        """自定义模式。"""
        args = _build_stream_map_args("s", "custom", "0,1")
        assert args == ["-map", "0:s:0?", "-map", "0:s:1?"]


# ============================================================
# 测试 build_encode_command 流映射
# ============================================================

class TestBuildEncodeCommandStreamMap:
    """测试 build_encode_command 的流映射参数。"""

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_default_params(self, mock_ffmpeg):
        """默认参数：保留第一条音轨，不保留字幕。"""
        cmd = build_encode_command(
            input_path="input.mp4",
            output_path="output.mp4",
        )
        # 应包含视频映射
        assert "-map" in cmd
        assert "0:v:0" in cmd
        # 默认 audio_tracks="0"，应映射第一条音频
        assert "0:a:0?" in cmd
        # 默认 subtitle_tracks="none"，应有 -sn
        assert "-sn" in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_all_audio_all_subtitle(self, mock_ffmpeg):
        """保留所有音轨和字幕。"""
        cmd = build_encode_command(
            input_path="input.mkv",
            output_path="output.mkv",
            audio_tracks="all",
            subtitle_tracks="all",
        )
        assert "0:a?" in cmd
        assert "0:s?" in cmd
        assert "-c:s" in cmd
        assert "copy" in cmd[cmd.index("-c:s") + 1]

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_custom_audio_tracks(self, mock_ffmpeg):
        """自定义选择音轨 #0 和 #2。"""
        cmd = build_encode_command(
            input_path="input.mkv",
            output_path="output.mkv",
            audio_tracks="custom",
            audio_tracks_custom="0,2",
        )
        assert "0:a:0?" in cmd
        assert "0:a:2?" in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_no_audio(self, mock_ffmpeg):
        """不保留音轨。"""
        cmd = build_encode_command(
            input_path="input.mp4",
            output_path="output.mp4",
            audio_tracks="none",
        )
        assert "-an" in cmd
        # 不应该有 -c:a
        assert "-c:a" not in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_subtitle_with_copy(self, mock_ffmpeg):
        """保留字幕时应有 -c:s copy。"""
        cmd = build_encode_command(
            input_path="input.mkv",
            output_path="output.mkv",
            subtitle_tracks="0",
        )
        assert "0:s:0?" in cmd
        assert "-c:s" in cmd


# ============================================================
# 测试 build_remux_command 流映射
# ============================================================

class TestBuildRemuxCommandStreamMap:
    """测试 build_remux_command 的流映射参数。"""

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_default_all(self, mock_ffmpeg):
        """默认参数：全部保留。"""
        cmd = build_remux_command(
            input_path="input.mkv",
            output_path="output.mp4",
        )
        assert "0:v" in cmd
        assert "0:a?" in cmd
        assert "0:s?" in cmd
        assert "-c" in cmd
        assert "copy" in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_custom_audio_no_subtitle(self, mock_ffmpeg):
        """自定义音轨，不保留字幕。"""
        cmd = build_remux_command(
            input_path="input.mkv",
            output_path="output.mp4",
            audio_tracks="custom",
            audio_tracks_custom="0,1",
            subtitle_tracks="none",
        )
        assert "0:a:0?" in cmd
        assert "0:a:1?" in cmd
        assert "-sn" in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_no_audio_with_subtitle(self, mock_ffmpeg):
        """不保留音轨，保留第一条字幕。"""
        cmd = build_remux_command(
            input_path="input.mkv",
            output_path="output.mp4",
            audio_tracks="none",
            subtitle_tracks="0",
        )
        assert "-an" in cmd
        assert "0:s:0?" in cmd

    @patch("src.core.get_ffmpeg_path", return_value="ffmpeg")
    def test_single_audio_single_subtitle(self, mock_ffmpeg):
        """单条音轨 + 单条字幕。"""
        cmd = build_remux_command(
            input_path="input.mkv",
            output_path="output.mp4",
            audio_tracks="0",
            subtitle_tracks="1",
        )
        assert "0:a:0?" in cmd
        assert "0:s:1?" in cmd
