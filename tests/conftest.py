# -*- coding: utf-8 -*-
"""
pytest 配置和通用 fixtures。
"""

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
def png_file(tmp_path):
    p = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), (200, 100, 100)).save(p)
    return str(p)


@pytest.fixture(scope="session")
def media_binaries():
    """真实媒体验证可选依赖。"""
    import shutil
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    paths = []
    for name in ("ffmpeg", "ffprobe"):
        candidates = [root / "build/macos-media/bin" / name, root / "bin" / (name + ".exe")]
        found = next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)
        found = found or shutil.which(name)
        if not found:
            pytest.skip("真实媒体验证需要 ffmpeg 和 ffprobe")
        paths.append(found)
    return tuple(paths)


@pytest.fixture(scope="session")
def requires_libass(media_binaries):
    """硬字幕用例前置: 当前 FFmpeg 必须编译了 libass。

    系统包管理器装的 FFmpeg 常常不带 libass(Homebrew 默认构建就没有),
    此时 ``subtitles`` 滤镜不可用。跳过而不是失败, 避免把环境缺失误判成回归;
    带内置 FFmpeg 的构建(冻结包 / CI 的 macos-media)仍会真正跑这条用例。
    """
    import subprocess

    ffmpeg, _ = media_binaries
    listing = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=60).stdout
    available = {parts[1] for parts in
                 (line.split() for line in listing.splitlines()) if len(parts) > 1}
    if "subtitles" not in available:
        pytest.skip("当前 FFmpeg 未编译 libass (缺少 subtitles 滤镜)")
    return ffmpeg
