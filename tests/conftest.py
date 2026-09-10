# -*- coding: utf-8 -*-
"""
pytest 配置和通用 fixtures。
"""
import sys

import pytest

from PIL import Image
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
    preset: str = "【均衡画质】x264 常用导出 (CRF18)"
    
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


@pytest.fixture
def fake_imgutils(monkeypatch):
    """注入假 imgutils 包, 记录调用并可控返回。"""
    import types

    import src.nsfw_detect as nsfw

    state = {"rating": ("general", 0.9), "censors": []}

    fake_validate_mod = types.ModuleType("imgutils.validate")

    def fake_rating(path):
        return state["rating"]
    fake_validate_mod.anime_rating = fake_rating

    fake_censor_mod = types.ModuleType("imgutils.detect.censor")

    def fake_censors(path):
        return state["censors"]
    fake_censor_mod.detect_censors = fake_censors

    fake_detect_mod = types.ModuleType("imgutils.detect")
    fake_root = types.ModuleType("imgutils")

    sys.modules["imgutils"] = fake_root
    sys.modules["imgutils.validate"] = fake_validate_mod
    sys.modules["imgutils.detect"] = fake_detect_mod
    sys.modules["imgutils.detect.censor"] = fake_censor_mod

    nsfw._imgutils_available = None

    yield state

    for m in ["imgutils", "imgutils.validate", "imgutils.detect",
              "imgutils.detect.censor"]:
        sys.modules.pop(m, None)
    nsfw._imgutils_available = None


@pytest.fixture
def png_file(tmp_path):
    p = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), (200, 100, 100)).save(p)
    return str(p)


@pytest.fixture(autouse=True)
def _restore_notify_globals():
    """保护 notify_config 模块级全局状态, 防止测试间污染。"""
    import src.notify_config as nc
    saved = dict(nc._notify_config)
    loaded = nc._notify_config_loaded
    yield
    nc._notify_config.clear()
    nc._notify_config.update(saved)
    nc._notify_config_loaded = loaded
