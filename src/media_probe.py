# -*- coding: utf-8 -*-
"""
媒体元数据探测模块：通过 ffprobe 获取视频/音频/图片的完整流信息，并生成格式化报告。

与 qc.py 的区别：
- qc.py 侧重于兼容性检测，只解析基础信息（第一条视频/音频流）。
- media_probe.py 侧重于信息展示，完整列出所有流的详细信息，类似 MediaInfo。
"""
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from colorama import Fore, Style

from .utils import get_ffprobe_path

# 常见语言代码到中文名称的映射
LANGUAGE_NAMES = {
    "chi": "中文", "zho": "中文", "cmn": "中文",
    "jpn": "日语", "eng": "英语", "kor": "韩语",
    "fra": "法语", "fre": "法语", "deu": "德语", "ger": "德语",
    "spa": "西班牙语", "ita": "意大利语", "por": "葡萄牙语",
    "rus": "俄语", "ara": "阿拉伯语", "hin": "印地语",
    "und": "未指定",
}

# 常见媒体文件扩展名 (用于目录扫描)
PROBE_EXTENSIONS = {
    # 视频格式
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv",
    ".m4v", ".ts", ".mts", ".m2ts", ".mpg", ".mpeg", ".m2",
    # 音频格式
    ".mp3", ".aac", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".opus",
    # 图片格式
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".webp", ".heic", ".avif",
}


@dataclass
class StreamInfo:
    """单条流的信息。"""
    index: int              # 在同类型流中的编号 (如音频流 #0, #1, #2)
    stream_index: int       # 在 ffprobe 中的全局流编号
    codec_type: str         # video / audio / subtitle
    codec_name: str = ""    # 编码器名称
    codec_long_name: str = ""  # 编码器完整名称
    profile: str = ""       # Profile (如 High, Main 等)
    level: str = ""         # Level (如 4.1)
    # 视频流特有
    width: int = 0
    height: int = 0
    fps: float = 0.0
    pix_fmt: str = ""       # 色彩空间 (yuv420p 等)
    # 音频流特有
    sample_rate: int = 0    # 采样率
    channels: int = 0       # 声道数
    channel_layout: str = ""  # 声道布局 (stereo, 5.1 等)
    # 通用
    bitrate_kbps: int = 0
    language: str = ""      # 语言标签 (如 jpn, chi, eng)
    title: str = ""         # 流标题


@dataclass
class DetailedMediaInfo:
    """完整文件的元数据。"""
    path: str
    filename: str = ""
    file_size_bytes: int = 0
    format_name: str = ""
    format_long_name: str = ""
    duration_sec: float = 0.0
    total_bitrate_kbps: int = 0
    video_streams: List[StreamInfo] = field(default_factory=list)
    audio_streams: List[StreamInfo] = field(default_factory=list)
    subtitle_streams: List[StreamInfo] = field(default_factory=list)
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.filename = os.path.basename(self.path)


def probe_detailed(file_path: str) -> Optional[DetailedMediaInfo]:
    """
    使用 ffprobe 获取媒体文件的完整元数据。

    Args:
        file_path: 文件路径。

    Returns:
        DetailedMediaInfo 对象，若失败则返回带有错误信息的对象。
    """
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-print_format", "json",
        file_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )

        if result.returncode != 0:
            info = DetailedMediaInfo(path=file_path)
            info.errors.append(f"ffprobe 无法读取文件: {result.stderr.strip()}")
            return info

        data = json.loads(result.stdout)
        return _parse_detailed_output(file_path, data)

    except Exception as e:
        info = DetailedMediaInfo(path=file_path)
        info.errors.append(f"探测失败: {str(e)}")
        return info


def _parse_detailed_output(file_path: str, data: Dict[str, Any]) -> DetailedMediaInfo:
    """解析 ffprobe JSON 输出为 DetailedMediaInfo。"""
    info = DetailedMediaInfo(path=file_path)

    # 文件大小
    try:
        info.file_size_bytes = os.path.getsize(file_path)
    except OSError:
        pass

    # 格式信息
    fmt = data.get("format", {})
    info.format_name = fmt.get("format_name", "")
    info.format_long_name = fmt.get("format_long_name", "")
    info.duration_sec = float(fmt.get("duration", 0))
    info.total_bitrate_kbps = int(fmt.get("bit_rate", 0)) // 1000 if fmt.get("bit_rate") else 0

    # 流信息 — 按类型分组并编号
    streams = data.get("streams", [])
    video_idx = 0
    audio_idx = 0
    subtitle_idx = 0

    for stream in streams:
        codec_type = stream.get("codec_type", "")
        tags = stream.get("tags", {})

        stream_info = StreamInfo(
            index=0,  # 稍后赋值
            stream_index=int(stream.get("index", 0)),
            codec_type=codec_type,
            codec_name=stream.get("codec_name", "unknown"),
            codec_long_name=stream.get("codec_long_name", ""),
            profile=stream.get("profile", ""),
            level=str(stream.get("level", "")) if stream.get("level") else "",
            language=tags.get("language", ""),
            title=tags.get("title", ""),
        )

        # 码率
        bit_rate_str = stream.get("bit_rate", "0")
        try:
            stream_info.bitrate_kbps = int(bit_rate_str) // 1000 if bit_rate_str else 0
        except (ValueError, TypeError):
            stream_info.bitrate_kbps = 0

        if codec_type == "video":
            stream_info.index = video_idx
            stream_info.width = int(stream.get("width", 0))
            stream_info.height = int(stream.get("height", 0))
            stream_info.pix_fmt = stream.get("pix_fmt", "")

            # 帧率解析
            fps_str = stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, fps_str.split("/"))
                stream_info.fps = round(num / den, 3) if den else 0
            except (ValueError, ZeroDivisionError):
                stream_info.fps = 0

            info.video_streams.append(stream_info)
            video_idx += 1

        elif codec_type == "audio":
            stream_info.index = audio_idx
            stream_info.sample_rate = int(stream.get("sample_rate", 0)) if stream.get("sample_rate") else 0
            stream_info.channels = int(stream.get("channels", 0))
            stream_info.channel_layout = stream.get("channel_layout", "")

            info.audio_streams.append(stream_info)
            audio_idx += 1

        elif codec_type == "subtitle":
            stream_info.index = subtitle_idx
            info.subtitle_streams.append(stream_info)
            subtitle_idx += 1

    # 章节信息
    chapters = data.get("chapters", [])
    for ch in chapters:
        ch_info = {
            "id": ch.get("id", 0),
            "start_time": float(ch.get("start_time", 0)),
            "end_time": float(ch.get("end_time", 0)),
            "title": ch.get("tags", {}).get("title", ""),
        }
        info.chapters.append(ch_info)

    return info


def _format_file_size(size_bytes: int) -> str:
    """将字节数格式化为可读的文件大小。"""
    if size_bytes <= 0:
        return "未知"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_duration(seconds: float) -> str:
    """将秒数格式化为 HH:MM:SS.mm。"""
    if seconds <= 0:
        return "00:00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def _get_language_display(lang_code: str) -> str:
    """获取语言代码的显示名称。"""
    if not lang_code:
        return ""
    name = LANGUAGE_NAMES.get(lang_code, "")
    if name:
        return f"[{lang_code}] {name}"
    return f"[{lang_code}]"


def format_media_report(info: DetailedMediaInfo) -> str:
    """
    将 DetailedMediaInfo 格式化为可读的文本报告。

    Args:
        info: 详细媒体信息对象。

    Returns:
        格式化后的报告字符串。
    """
    lines = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"文件: {info.filename}")
    lines.append(f"路径: {info.path}")
    lines.append(f"大小: {_format_file_size(info.file_size_bytes)}")
    lines.append(f"时长: {_format_duration(info.duration_sec)}")
    if info.format_name:
        fmt_display = info.format_name
        if info.format_long_name:
            fmt_display += f" ({info.format_long_name})"
        lines.append(f"容器: {fmt_display}")
    if info.total_bitrate_kbps > 0:
        lines.append(f"总码率: {info.total_bitrate_kbps:,} kbps")
    lines.append(sep)

    # 错误信息
    if info.errors:
        for err in info.errors:
            lines.append(f"  [错误] {err}")
        return "\n".join(lines)

    # 视频流
    for vs in info.video_streams:
        lines.append("")
        lines.append(f"  ── 视频流 #{vs.index} " + "─" * 40)

        # 编码器信息
        codec_display = vs.codec_name
        if vs.profile:
            codec_display += f" ({vs.profile}"
            if vs.level and vs.level != "-99":
                # level 通常是整数 * 10，如 41 表示 4.1
                try:
                    level_val = int(vs.level)
                    if level_val > 0:
                        codec_display += f", Level {level_val / 10:.1f}"
                except ValueError:
                    pass
            codec_display += ")"
        lines.append(f"  编码器:      {codec_display}")

        if vs.width and vs.height:
            lines.append(f"  分辨率:      {vs.width}x{vs.height}")
        if vs.fps > 0:
            lines.append(f"  帧率:        {vs.fps} fps")
        if vs.pix_fmt:
            lines.append(f"  色彩空间:    {vs.pix_fmt}")
        if vs.bitrate_kbps > 0:
            lines.append(f"  码率:        {vs.bitrate_kbps:,} kbps")

    # 音频流
    for aus in info.audio_streams:
        lines.append("")
        lang_display = _get_language_display(aus.language)
        title_display = aus.title or ""
        header_extra = ""
        if lang_display:
            header_extra += f" {lang_display}"
        if title_display:
            header_extra += f" {title_display}" if header_extra else f" {title_display}"
        lines.append(f"  ── 音频流 #{aus.index} ──{header_extra} " + "─" * max(1, 30 - len(header_extra)))

        codec_display = aus.codec_name
        if aus.profile:
            codec_display += f" ({aus.profile})"
        lines.append(f"  编码器:      {codec_display}")
        if aus.sample_rate > 0:
            lines.append(f"  采样率:      {aus.sample_rate} Hz")
        if aus.channels > 0:
            ch_display = str(aus.channels)
            if aus.channel_layout:
                ch_display += f" ({aus.channel_layout})"
            lines.append(f"  声道:        {ch_display}")
        if aus.bitrate_kbps > 0:
            lines.append(f"  码率:        {aus.bitrate_kbps:,} kbps")

    # 字幕流
    for ss in info.subtitle_streams:
        lines.append("")
        lang_display = _get_language_display(ss.language)
        title_display = ss.title or ""
        header_extra = ""
        if lang_display:
            header_extra += f" {lang_display}"
        if title_display:
            header_extra += f" {title_display}" if header_extra else f" {title_display}"
        lines.append(f"  ── 字幕流 #{ss.index} ──{header_extra} " + "─" * max(1, 30 - len(header_extra)))
        lines.append(f"  编码器:      {ss.codec_name}")

    # 章节信息
    if info.chapters:
        lines.append("")
        lines.append(f"  ── 章节信息 ({len(info.chapters)} 章) " + "─" * 30)
        for ch in info.chapters:
            start = _format_duration(ch.get("start_time", 0))
            title = ch.get("title", "")
            lines.append(f"  {start}  {title}")

    # 使用提示（当有多音轨或多字幕时）
    if len(info.audio_streams) > 1 or len(info.subtitle_streams) > 1:
        lines.append("")
        lines.append("─" * 60)
        lines.append("【提示】在「视频压制」或「封装转换」中:")

        if len(info.audio_streams) > 1:
            # 构建示例
            track_hints = []
            for aus in info.audio_streams:
                lang = _get_language_display(aus.language) or aus.codec_name
                track_hints.append(f"#{aus.index}={lang}")
            lines.append(f"  音轨: {', '.join(track_hints)}")
            # 示例
            lines.append(f"  → 例: 保留前两条音轨，音轨编号填写: 0,1")

        if len(info.subtitle_streams) > 1:
            track_hints = []
            for ss in info.subtitle_streams:
                lang = _get_language_display(ss.language) or ss.codec_name
                track_hints.append(f"#{ss.index}={lang}")
            lines.append(f"  字幕: {', '.join(track_hints)}")
            lines.append(f"  → 例: 仅保留第一条字幕，字幕编号填写: 0")

        lines.append("─" * 60)

    return "\n".join(lines)


def generate_media_report(results: List[DetailedMediaInfo], output_path: str) -> str:
    """
    将多个文件的元数据报告批量输出到 TXT 文件。

    Args:
        results: DetailedMediaInfo 列表。
        output_path: 报告输出路径。

    Returns:
        完整报告内容。
    """
    lines = []
    lines.append("=" * 60)
    lines.append("小雪工具箱 - 媒体元数据检测报告")
    lines.append(f"共 {len(results)} 个文件")
    lines.append("=" * 60)

    for info in results:
        lines.append("")
        lines.append(format_media_report(info))

    lines.append("")
    lines.append("=" * 60)
    lines.append("报告生成完毕")
    lines.append("=" * 60)

    report_content = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"{Fore.GREEN}[成功] 报告已保存到: {output_path}{Style.RESET_ALL}")
    return report_content
