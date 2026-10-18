# -*- coding: utf-8 -*-
"""
文件执行器模块测试用例。

测试 src/executors/file_executor.py 中的封装转换和图片转换功能。
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import List, Optional

from src.executors.file_executor import (
    execute_remux,
    execute_image_convert,
)
from src.image_converter import FileConvertResult
from src.media_probe import DetailedMediaInfo, StreamInfo
from src.task.status import TaskStatus


def success_results(input_paths, target_ext=".png"):
    """构造一批“转换成功且输出存在”的逐文件结果。"""
    return [
        FileConvertResult(
            source=p,
            output=str(Path(p).with_suffix(target_ext)),
            status="success",
        )
        for p in input_paths
    ]


@dataclass
class MockRemuxArgs:
    """模拟封装转换参数对象"""
    remux_input: List[str] = None
    remux_output: str = ""
    remux_preset: str = "MP4"
    remux_overwrite: bool = False
    
    def __post_init__(self):
        if self.remux_input is None:
            self.remux_input = []


@dataclass
class MockImageConvertArgs:
    """模拟图片转换参数对象"""
    img_input: List[str] = None
    img_output_dir: str = ""
    img_format: str = "PNG (无损)"
    img_format_custom: str = ""
    img_quality: int = 95
    img_overwrite: bool = False
    img_skip_same_format: bool = True
    
    def __post_init__(self):
        if self.img_input is None:
            self.img_input = []


class TestExecuteRemux:
    """测试封装转换执行器"""
    
    @pytest.fixture
    def mock_video_files(self, tmp_path):
        """创建临时视频文件"""
        files = []
        for i in range(3):
            video_file = tmp_path / f"test_video_{i}.mkv"
            video_file.write_text(f"fake video content {i}")
            files.append(str(video_file))
        return files
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_single_file(self, mock_build, mock_run, mock_video_files):
        """测试单文件封装转换"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockRemuxArgs()
        args.remux_input = [mock_video_files[0]]
        args.remux_preset = "MP4"
        
        execute_remux(args)
        
        mock_build.assert_called_once()
        mock_run.assert_called_once()
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_batch(self, mock_build, mock_run, mock_video_files):
        """测试批量封装转换"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockRemuxArgs()
        args.remux_input = mock_video_files
        args.remux_preset = "MKV"
        
        execute_remux(args)
        
        # 应该为每个文件调用一次
        assert mock_build.call_count == 3
        assert mock_run.call_count == 3
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_with_output_dir(self, mock_build, mock_run, mock_video_files, tmp_path):
        """测试指定输出目录"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockRemuxArgs()
        args.remux_input = [mock_video_files[0]]
        args.remux_output = str(output_dir)
        args.remux_preset = "MP4"
        
        execute_remux(args)
        
        mock_build.assert_called_once()
        # 验证输出路径包含指定目录
        call_kwargs = mock_build.call_args.kwargs
        assert str(output_dir) in call_kwargs.get("output_path", "")
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_string_input(self, mock_build, mock_run, mock_video_files):
        """测试字符串输入（非列表）"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mp4"]
        mock_run.return_value = 0
        
        args = MockRemuxArgs()
        args.remux_input = mock_video_files[0]  # 字符串而非列表
        args.remux_preset = "MP4"
        
        execute_remux(args)
        
        mock_build.assert_called_once()
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_preset_extension(self, mock_build, mock_run, mock_video_files):
        """测试不同预设使用不同扩展名"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mkv"]
        mock_run.return_value = 0
        
        presets_extensions = {
            "MP4": ".mp4",
            "MKV": ".mkv",
            "MOV": ".mov",
        }
        
        for preset, expected_ext in presets_extensions.items():
            mock_build.reset_mock()
            
            args = MockRemuxArgs()
            args.remux_input = [mock_video_files[0]]
            args.remux_preset = preset
            
            execute_remux(args)
            
            call_kwargs = mock_build.call_args.kwargs
            output_path = call_kwargs.get("output_path", "")
            assert output_path.endswith(expected_ext), f"预设 {preset} 应使用扩展名 {expected_ext}"


    # ------------------------------------------------------------
    # 容器预检 (M3.3): 不兼容时不启动 ffmpeg，失败的源绝不删
    # ------------------------------------------------------------

    @staticmethod
    def _probe_info(path, video="h264", audio="aac", errors=None):
        info = DetailedMediaInfo(path=str(path))
        if video is not None:
            info.video_streams.append(StreamInfo(
                index=0, stream_index=0, codec_type="video",
                codec_name=video))
        if audio is not None:
            info.audio_streams.append(StreamInfo(
                index=0, stream_index=1, codec_type="audio",
                codec_name=audio))
        info.errors.extend(errors or [])
        return info

    def test_execute_remux_preflight_incompatible_skips_ffmpeg(
            self, monkeypatch, tmp_path):
        """容器预检不兼容: 不构建/执行 ffmpeg，记失败，源文件保留。"""
        src = tmp_path / "vp9.mkv"
        src.write_bytes(b"x")
        info = self._probe_info(src, video="vp9")
        monkeypatch.setattr(
            "src.executors.file_executor.probe_detailed", lambda p: info)
        run_calls = []
        build_calls = []
        monkeypatch.setattr(
            "src.executors.file_executor.run_ffmpeg_command",
            lambda cmd, **k: run_calls.append(cmd) or 0)
        monkeypatch.setattr(
            "src.executors.file_executor.build_remux_command",
            lambda **k: build_calls.append(k) or ["ffmpeg"])

        args = MockRemuxArgs()
        args.remux_input = [str(src)]
        args.remux_preset = "MP4"
        args.remux_overwrite = True

        result = execute_remux(args)

        assert run_calls == [] and build_calls == []  # 未启动 ffmpeg
        assert result.status is TaskStatus.FAILED
        assert "MP4" in result.message and "vp9" in result.message
        assert "建议" in result.message and "MKV" in result.message
        assert src.exists()  # 预检失败 -> 源文件绝不删
        assert not (tmp_path / "vp9_remux.mp4").exists()

    def test_execute_remux_preflight_compatible_runs_ffmpeg(
            self, monkeypatch, tmp_path):
        """容器预检兼容: 正常进入 ffmpeg 流程。"""
        src = tmp_path / "ok.mkv"
        src.write_bytes(b"x")
        info = self._probe_info(src, video="h264", audio="aac")
        monkeypatch.setattr(
            "src.executors.file_executor.probe_detailed", lambda p: info)
        run_calls = []
        monkeypatch.setattr(
            "src.executors.file_executor.run_ffmpeg_command",
            lambda cmd, **k: run_calls.append(cmd) or 0)

        args = MockRemuxArgs()
        args.remux_input = [str(src)]
        args.remux_preset = "MP4"

        result = execute_remux(args)

        assert len(run_calls) == 1
        assert result.status is TaskStatus.SUCCESS

    def test_execute_remux_preflight_probe_error_continues(
            self, monkeypatch, tmp_path):
        """预检探测失败: 跳过预检，按原流程继续（避免误伤）。"""
        src = tmp_path / "broken.mkv"
        src.write_bytes(b"x")
        info = self._probe_info(src, video=None, audio=None,
                                errors=["ffprobe 无法读取文件"])
        monkeypatch.setattr(
            "src.executors.file_executor.probe_detailed", lambda p: info)
        run_calls = []
        monkeypatch.setattr(
            "src.executors.file_executor.run_ffmpeg_command",
            lambda cmd, **k: run_calls.append(cmd) or 0)

        args = MockRemuxArgs()
        args.remux_input = [str(src)]

        result = execute_remux(args)

        assert len(run_calls) == 1
        assert result.status is TaskStatus.SUCCESS


class TestExecuteImageConvert:
    """测试图片转换执行器"""
    
    @pytest.fixture
    def mock_image_files(self, tmp_path):
        """创建临时图片文件"""
        files = []
        for i, ext in enumerate([".jpg", ".png", ".bmp"]):
            img_file = tmp_path / f"test_image_{i}{ext}"
            img_file.write_text(f"fake image content {i}")
            files.append(str(img_file))
        return files
    
    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_to_png(self, mock_convert, mock_image_files):
        """测试转换为 PNG 格式"""
        mock_convert.return_value = success_results(mock_image_files)
        
        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "PNG (无损)"
        
        execute_image_convert(args)
        
        mock_convert.assert_called_once()
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["target_extension"] == ".png"
    
    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_to_jpg(self, mock_convert, mock_image_files):
        """测试转换为 JPG 格式"""
        mock_convert.return_value = success_results(mock_image_files)
        
        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "JPG/JPEG (有损压缩)"
        
        execute_image_convert(args)
        
        mock_convert.assert_called_once()
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["target_extension"] == ".jpg"
    
    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_custom_format(self, mock_convert, mock_image_files):
        """测试自定义格式"""
        mock_convert.return_value = success_results(mock_image_files)
        
        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "自定义"
        args.img_format_custom = "tga"
        
        execute_image_convert(args)
        
        mock_convert.assert_called_once()
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["target_extension"] == ".tga"
    
    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_quality(self, mock_convert, mock_image_files):
        """测试质量参数传递"""
        mock_convert.return_value = success_results(mock_image_files)
        
        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "JPG/JPEG (有损压缩)"
        args.img_quality = 80
        
        execute_image_convert(args)
        
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["quality"] == 80
    
    def test_execute_image_convert_custom_no_extension(self, mock_image_files, capsys):
        """测试自定义格式未指定扩展名时的错误处理"""
        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "自定义"
        args.img_format_custom = ""  # 未指定
        
        execute_image_convert(args)
        
        captured = capsys.readouterr()
        assert "错误" in captured.out or "必须输入扩展名" in captured.out

    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_skip_same_format(self, mock_convert, mock_image_files):
        """测试默认跳过同格式文件"""
        mock_convert.return_value = success_results(mock_image_files[:2]) + [
            FileConvertResult(source=mock_image_files[2], output=None, status="skipped")
        ]

        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "PNG (无损)"
        args.img_skip_same_format = True

        execute_image_convert(args)

        mock_convert.assert_called_once()
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["skip_same_format"] is True

    @patch('src.executors.file_executor.batch_convert_images')
    def test_execute_image_convert_no_skip(self, mock_convert, mock_image_files):
        """测试关闭跳过同格式时正常转换"""
        mock_convert.return_value = success_results(mock_image_files)

        args = MockImageConvertArgs()
        args.img_input = mock_image_files
        args.img_format = "PNG (无损)"
        args.img_skip_same_format = False

        execute_image_convert(args)

        mock_convert.assert_called_once()
        call_kwargs = mock_convert.call_args.kwargs
        assert call_kwargs["skip_same_format"] is False
