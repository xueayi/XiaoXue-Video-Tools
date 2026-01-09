# -*- coding: utf-8 -*-
"""
预设配置模块：包含编码器和质量预设。
"""

# 编码器选项 (显示名称 -> ffmpeg 编码器参数)
ENCODERS = {
    "H.264 (CPU - libx264)": "libx264",
    "H.264 (NVIDIA NVENC)": "h264_nvenc",
    "H.264 (Intel QSV)": "h264_qsv",
    "H.264 (AMD AMF)": "h264_amf",
    "H.265/HEVC (CPU - libx265)": "libx265",
    "H.265/HEVC (NVIDIA NVENC)": "hevc_nvenc",
    "复制 (不重新编码)": "copy",
}

# 质量预设
# 每个预设包含: crf, bitrate (可选), preset (速度), 分辨率, 帧率
QUALITY_PRESETS = {
    "【标准推荐】1080P/60FPS 均衡": {
        "encoder": "libx264",
        "crf": 20,
        "preset": "medium",
        "resolution": "1920x1080",
        "fps": 60,
        "audio_bitrate": "192k",
        "description": "适合日常 B 站投稿，画质与文件大小均衡。"
    },
    "【极致画质】4K/高动态/AMV": {
        "encoder": "libx264",
        "crf": 16,
        "preset": "slow",
        "resolution": None,  # 保持原分辨率
        "fps": None,  # 保持原帧率
        "audio_bitrate": "320k",
        "description": "高码率极致画质，适合 AMV 或对画质要求极高的投稿。"
    },
    "【速度优先】NVIDIA 显卡加速": {
        "encoder": "h264_nvenc",
        "crf": None,  # NVENC 使用 cq 而非 crf
        "cq": 23,
        "preset": "p4",  # NVENC preset
        "resolution": None,
        "fps": None,
        "audio_bitrate": "192k",
        "description": "利用 NVIDIA 显卡快速编码，适合赶稿。"
    },
    "自定义 (Custom)": {
        "encoder": None,
        "crf": None,
        "preset": None,
        "resolution": None,
        "fps": None,
        "audio_bitrate": None,
        "description": "手动指定所有参数。"
    }
}

# 音频编码器
AUDIO_ENCODERS = {
    "AAC (推荐)": "aac",
    "MP3": "libmp3lame",
    "复制 (不重新编码)": "copy",
}

# 音频码率选项
AUDIO_BITRATES = ["128k", "192k", "256k", "320k"]

# x264/x265 速度预设
CPU_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]

# NVENC 速度预设
NVENC_PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
