# -*- coding: utf-8 -*-
"""
视频执行器模块测试用例。

测试 src/executors/video_executor.py 中的视频压制、音频替换、音频抽取功能。
主要测试参数解析和命令构建的正确性。
"""
import pytest
import os
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass
from typing import Optional

from src.executors.video_executor import (
    execute_encode,
    execute_replace_audio,
    execute_extract_audio,
)
from src.executors.common import print_task_header


@dataclass
class MockArgs:
    """模拟 argparse 参数对象"""
    # 通用
    input: str = ""
    output: str = ""
    
    # 视频压制
    preset: str = "【均衡画质】x264常用导出(CRF18)"
    encoder: str = "H.264 (CPU - libx264)"
    crf: int = 18
    bitrate: str = ""
    speed_preset: str = "medium"
    nvenc_preset: str = "p4"
    resolution: str = ""  # 添加缺失的属性
    resolution_preset: str = "不限制"
    resolution_custom: str = ""
    fps: int = 0  # 修改为 int 类型，0 表示不限制
    audio_encoder: str = "AAC (推荐)"
    audio_bitrate: str = "192k"
    audio_enc: str = "AAC (推荐)"
    audio_br: str = "192k"
    subtitle: str = ""
    extra_args: str = ""
    compat_mode: bool = False
    rc_mode: str = "CRF/CQ (恒定质量)"
    rate_control: str = "CRF/CQ (恒定质量)"
    video_bitrate: str = ""
    debug_mode: bool = True  # dry_run 使用此属性
    dry_run: bool = True  # 默认 dry_run 避免实际执行
    
    # 音频替换
    video_input: str = ""
    audio_input: str = ""
    audio_output: str = ""
    
    # 音频抽取
    extract_input: str = ""
    extract_output: str = ""
    extract_encoder: str = "AAC (推荐)"
    extract_bitrate: str = "192k"


class TestPrintTaskHeader:
    """测试任务标题打印"""
    
    def test_print_task_header_output(self, capsys):
        """测试标题打印格式"""
        print_task_header("测试任务")
        
        captured = capsys.readouterr()
        assert "测试任务" in captured.out
        assert "=" in captured.out  # 包含分隔线


class TestExecuteEncode:
    """测试视频压制执行器"""
    
    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """创建临时视频文件"""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_text("fake video content")
        return str(video_file)
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_encode_command')
    def test_execute_encode_preset_mode(self, mock_build, mock_run, mock_video_file):
        """测试预设模式编码"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.input = mock_video_file
        args.output = ""  # 自动生成
        args.preset = "【均衡画质】x264常用导出(CRF18)"
        args.dry_run = True
        
        result = execute_encode(args)
        
        # 由于 dry_run=True，应该返回成功
        assert result == 0 or mock_build.called
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_encode_command')
    def test_execute_encode_custom_mode(self, mock_build, mock_run, mock_video_file):
        """测试自定义模式编码"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mp4", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.input = mock_video_file
        args.output = ""
        args.preset = "自定义 (Custom)"
        args.encoder = "H.264 (CPU - libx264)"
        args.crf = 20
        args.speed_preset = "slow"
        args.dry_run = True
        
        result = execute_encode(args)
        
        assert result == 0 or mock_build.called
    
    def test_execute_encode_missing_input(self):
        """测试输入文件不存在时的错误处理"""
        args = MockArgs()
        args.input = "/nonexistent/path/video.mp4"
        args.output = "/tmp/output.mp4"
        args.dry_run = True
        
        result = execute_encode(args)
        
        # 应该返回错误码
        assert result == 1


class TestExecuteReplaceAudio:
    """测试音频替换执行器"""
    
    @pytest.fixture
    def mock_files(self, tmp_path):
        """创建临时测试文件"""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_text("fake video")
        
        audio_file = tmp_path / "test_audio.mp3"
        audio_file.write_text("fake audio")
        
        return str(video_file), str(audio_file)
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_replace_audio_command')
    def test_execute_replace_audio_with_output(self, mock_build, mock_run, mock_files):
        """测试指定输出路径的音频替换"""
        video_path, audio_path = mock_files
        mock_build.return_value = ["ffmpeg", "-i", video_path, "-i", audio_path, "output.mp4"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.video_input = video_path
        args.audio_input = audio_path
        args.audio_output = "/tmp/replaced.mp4"
        args.audio_enc = "AAC (推荐)"
        args.audio_br = "192k"
        
        execute_replace_audio(args)
        
        mock_build.assert_called_once()
        mock_run.assert_called_once()
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_replace_audio_command')
    def test_execute_replace_audio_auto_output(self, mock_build, mock_run, mock_files):
        """测试自动生成输出路径"""
        video_path, audio_path = mock_files
        mock_build.return_value = ["ffmpeg", "-i", video_path, "-i", audio_path, "output.mp4"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.video_input = video_path
        args.audio_input = audio_path
        args.audio_output = ""  # 自动生成
        args.audio_enc = "AAC (推荐)"
        args.audio_br = "192k"
        
        execute_replace_audio(args)
        
        # 验证 build 被调用，且输出路径被自动生成
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert "_replaced" in call_kwargs.get("output_path", "")


class TestExecuteExtractAudio:
    """测试音频抽取执行器"""
    
    @pytest.fixture
    def mock_video_file(self, tmp_path):
        """创建临时视频文件"""
        video_file = tmp_path / "test_video.mp4"
        video_file.write_text("fake video content")
        return str(video_file)
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_extract_audio_command')
    def test_execute_extract_audio_aac(self, mock_build, mock_run, mock_video_file):
        """测试抽取为 AAC 格式"""
        mock_build.return_value = ["ffmpeg", "-i", mock_video_file, "output.m4a"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.extract_input = mock_video_file
        args.extract_output = ""  # 自动生成 .m4a
        args.extract_encoder = "AAC (推荐)"
        args.extract_bitrate = "192k"
        
        execute_extract_audio(args)
        
        mock_build.assert_called_once()
        # 验证扩展名推断正确
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("output_path", "").endswith(".m4a")
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_extract_audio_command')
    def test_execute_extract_audio_mp3(self, mock_build, mock_run, mock_video_file):
        """测试抽取为 MP3 格式"""
        mock_build.return_value = ["ffmpeg", "-i", mock_video_file, "output.mp3"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.extract_input = mock_video_file
        args.extract_output = ""  # 自动生成 .mp3
        args.extract_encoder = "MP3"
        args.extract_bitrate = "320k"
        
        execute_extract_audio(args)
        
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("output_path", "").endswith(".mp3")
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_extract_audio_command')
    def test_execute_extract_audio_wav(self, mock_build, mock_run, mock_video_file):
        """测试抽取为 WAV 格式"""
        mock_build.return_value = ["ffmpeg", "-i", mock_video_file, "output.wav"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.extract_input = mock_video_file
        args.extract_output = ""
        args.extract_encoder = "WAV (无损)"
        args.extract_bitrate = "192k"
        
        execute_extract_audio(args)
        
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("output_path", "").endswith(".wav")
    
    @patch('src.executors.video_executor.run_ffmpeg_command')
    @patch('src.executors.video_executor.build_extract_audio_command')
    def test_execute_extract_audio_flac(self, mock_build, mock_run, mock_video_file):
        """测试抽取为 FLAC 格式"""
        mock_build.return_value = ["ffmpeg", "-i", mock_video_file, "output.flac"]
        mock_run.return_value = 0
        
        args = MockArgs()
        args.extract_input = mock_video_file
        args.extract_output = ""
        args.extract_encoder = "FLAC (无损)"
        args.extract_bitrate = "192k"
        
        execute_extract_audio(args)
        
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs.get("output_path", "").endswith(".flac")
