# -*- coding: utf-8 -*-
"""
pytest 配置和通用 fixtures。
"""
import pytest
import os
import tempfile
from dataclasses import dataclass
from typing import Optional


@dataclass
class MockArgs:
    """
    模拟 argparse 解析后的参数对象。
    用于测试 execute_encode 及相关函数。
    """
    # 输入输出
    input: str = ""
    output: str = ""
    
    # 预设
    preset: str = "【均衡画质】x264常用导出(CRF18)"
    
    # 编码器设置
    encoder: str = "H.264 (CPU - libx264)"
    speed_preset: str = "medium"
    nvenc_preset: str = "使用预设默认"
    
    # 质量与码率
    rate_control: str = "CRF/CQ (恒定质量)"
    crf: int = 18
    video_bitrate: str = ""
    
    # 视频输出
    resolution: str = ""
    fps: int = 0
    
    # 音频设置
    audio_encoder: str = "复制 (不重新编码)"
    audio_bitrate: str = "192k"
    
    # 字幕与兼容模式
    subtitle: str = ""
    compat_mode: bool = False
    
    # 高级选项
    extra_args: str = ""
    debug_mode: bool = True  # 默认 dry_run 模式


@pytest.fixture
def mock_video_file(tmp_path):
    """创建一个模拟的视频文件。"""
    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"fake video content")
    return str(video_file)


@pytest.fixture
def mock_subtitle_file(tmp_path):
    """创建一个模拟的字幕文件。"""
    subtitle_file = tmp_path / "test_subtitle.ass"
    subtitle_file.write_text("[Script Info]\nTitle: Test", encoding="utf-8")
    return str(subtitle_file)


@pytest.fixture
def base_args(mock_video_file):
    """创建基础的 MockArgs 对象。"""
    return MockArgs(input=mock_video_file)


@pytest.fixture
def custom_args(mock_video_file):
    """创建自定义模式的 MockArgs 对象。"""
    return MockArgs(
        input=mock_video_file,
        preset="自定义 (Custom)",
        encoder="H.264 (CPU - libx264)",
        crf=20,
    )
