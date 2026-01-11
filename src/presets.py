# -*- coding: utf-8 -*-
"""
预设配置模块：包含编码器和质量预设。
"""

# 编码器选项 (显示名称 -> ffmpeg 编码器参数)
# 注意：视频压制模块不再提供"复制"选项，该功能由封装转换模块提供
ENCODERS = {
    "H.264 (CPU - libx264)": "libx264",
    "H.264 (NVIDIA NVENC)": "h264_nvenc",
    "H.264 (Intel QSV)": "h264_qsv",
    "H.264 (AMD AMF)": "h264_amf",
    "H.265/HEVC (CPU - libx265)": "libx265",
    "H.265/HEVC (NVIDIA NVENC)": "hevc_nvenc",
}

# 质量预设
# 每个预设包含: encoder, crf, preset (速度), 分辨率, 帧率, 音频编码器, 音频码率
QUALITY_PRESETS = {
    "【均衡画质】x264常用导出(CRF18)": {
        "encoder": "libx264",
        "crf": 18,
        "preset": "medium",
        "resolution": None,
        "fps": None,
        "audio_encoder": "copy",  # 默认复制音频流
        "audio_bitrate": "192k",  # 仅在需要转码时使用
        "description": "适合日常 B 站投稿，画质与文件大小均衡。"
    },
    "【极致画质】4K/高动态/AMV": {
        "encoder": "libx264",
        "crf": 16,
        "preset": "slow",
        "resolution": None,
        "fps": None,
        "audio_encoder": "copy",
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
        "audio_encoder": "copy",
        "audio_bitrate": "192k",
        "extra_args": "-rc vbr -b:v 0 -maxrate 20M",
        "description": "利用 NVIDIA 显卡快速编码，适合赶稿。"
    },
    "【画质优先】NVIDIA 显卡加速 (HQ)": {
        "encoder": "h264_nvenc",
        "crf": None,
        "cq": 19,
        "preset": "p7",
        "resolution": None,
        "fps": None,
        "audio_encoder": "copy",
        "audio_bitrate": "320k",
        "extra_args": "-rc vbr -b:v 0 -maxrate 20M",
        "description": "N 卡高质量导出，使用动态码率 (VBR) 和 p7 预设。"
    },
    "自定义 (Custom)": {
        "encoder": None,
        "crf": None,
        "preset": None,
        "resolution": None,
        "fps": None,
        "audio_encoder": None,  # 自定义模式由用户选择
        "audio_bitrate": None,
        "description": "手动指定所有参数。"
    }
}

# 音频编码器
AUDIO_ENCODERS = {
    "AAC (推荐)": "aac",
    "MP3": "libmp3lame",
    "WAV (无损)": "pcm_s16le",
    "FLAC (无损)": "flac",
    "复制 (不重新编码)": "copy",
}

# 音频码率选项
AUDIO_BITRATES = ["128k", "192k", "256k", "320k"]

# x264/x265 速度预设
CPU_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]

# NVENC 速度预设
NVENC_PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]

# 通用码率控制模式 (根据编码器自动适配参数)
# - CRF/CQ 模式: 恒定质量，由质量值控制
# - VBR 模式: 可变码率，需要设置目标码率
# - CBR 模式: 恒定码率，适合直播推流
# - 2-Pass 模式: 两遍编码，更精确的码率控制
RATE_CONTROL_MODES = {
    "CRF/CQ (恒定质量)": "crf",        # 默认，最常用
    "VBR (可变码率)": "vbr",            # 需要设置码率
    "CBR (恒定码率)": "cbr",            # 恒定码率，适合推流
    "2-Pass VBR (两遍编码)": "2pass",   # 更精确的码率控制
}

# 常用视频码率预设
VIDEO_BITRATES = ["", "2M", "4M", "6M", "8M", "10M", "15M", "20M", "30M", "50M"]

# 分辨率预设 (用于 QC 检测)
RESOLUTION_PRESETS = {
    "不限制": "",
    "4K (3840x2160)": "3840x2160",
    "2K (2560x1440)": "2560x1440",
    "1080P (1920x1080)": "1920x1080",
    "720P (1280x720)": "1280x720",
    "480P (854x480)": "854x480",
    "自定义": "custom"
}

# 封装转换预设 (Remux)
REMUX_PRESETS = {
    "MP4 (H.264 兼容)": {
        "extension": ".mp4",
        "description": "最广泛兼容的格式，适合大多数播放器和平台",
    },
    "MKV (多轨封装)": {
        "extension": ".mkv",
        "description": "支持多音轨、多字幕轨道，适合资源存档",
    },
    "MOV (Apple 生态)": {
        "extension": ".mov",
        "description": "适合 Final Cut Pro、Mac 生态剪辑",
    },
    "TS (广播流)": {
        "extension": ".ts",
        "description": "MPEG 传输流，适合广播级应用",
    },
    "WEBM (Web 视频)": {
        "extension": ".webm",
        "description": "适合网页嵌入播放 (需 VP8/VP9/AV1 编码)",
    },
    "MXF (专业后期)": {
        "extension": ".mxf",
        "description": "专业广播/后期工作流标准封装",
    },
    "AVI (传统格式)": {
        "extension": ".avi",
        "description": "传统 Windows 视频格式",
    },
    "自定义": {
        "extension": None,
        "description": "手动指定输出路径和扩展名",
    },
}

# 图片格式预设 (用于图片格式转换)
IMAGE_FORMATS = {
    "PNG (无损)": ".png",
    "JPG/JPEG (有损压缩)": ".jpg",
    "WEBP (Web 优化)": ".webp",
    "BMP (位图)": ".bmp",
    "GIF (动图)": ".gif",
    "TIFF (专业)": ".tiff",
    "自定义": None,
}

# 重命名模式预设
RENAME_MODES = {
    "原地重命名": "rename_in_place",
    "复制并重命名": "copy_rename",
    "移动并重命名": "move_rename",
}

# 重命名目标类型预设
RENAME_TARGETS = {
    "仅图片": "images",
    "仅视频": "videos",
    "图片和视频": "both",
}

# 重命名行为预设
RENAME_BEHAVIORS = {
    "递归模式（保持目录结构）": True,
    "非递归模式": False,
}
