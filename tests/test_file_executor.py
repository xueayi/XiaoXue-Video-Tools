# -*- coding: utf-8 -*-
"""
文件执行器模块测试用例。

测试 src/executors/file_executor.py 中的封装转换和图片转换功能。
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import List, Optional

from src.executors.file_executor import (
    execute_remux,
    execute_image_convert,
)


@dataclass
class MockRemuxArgs:
    """模拟封装转换参数对象"""
    remux_input: List[str] = None
    remux_output: str = ""
    remux_preset: str = "MP4 (H.264 兼容)"
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
        args.remux_preset = "MP4 (H.264 兼容)"
        
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
        args.remux_preset = "MKV (多轨封装)"
        
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
        args.remux_preset = "MP4 (H.264 兼容)"
        
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
        args.remux_preset = "MP4 (H.264 兼容)"
        
        execute_remux(args)
        
        mock_build.assert_called_once()
    
    @patch('src.executors.file_executor.run_ffmpeg_command')
    @patch('src.executors.file_executor.build_remux_command')
    def test_execute_remux_preset_extension(self, mock_build, mock_run, mock_video_files):
        """测试不同预设使用不同扩展名"""
        mock_build.return_value = ["ffmpeg", "-i", "input.mkv", "output.mkv"]
        mock_run.return_value = 0
        
        presets_extensions = {
            "MP4 (H.264 兼容)": ".mp4",
            "MKV (多轨封装)": ".mkv",
            "MOV (Apple 生态)": ".mov",
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
        mock_convert.return_value = (3, 0, [])
        
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
        mock_convert.return_value = (3, 0, [])
        
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
        mock_convert.return_value = (3, 0, [])
        
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
        mock_convert.return_value = (3, 0, [])
        
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
