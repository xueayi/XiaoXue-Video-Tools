# -*- coding: utf-8 -*-
"""
媒体元数据探测模块测试。
使用 mock 的 ffprobe 输出测试解析逻辑。
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from src.media_probe import (
    probe_detailed,
    format_media_report,
    generate_media_report,
    _parse_detailed_output,
    _format_file_size,
    _format_duration,
    _get_language_display,
    StreamInfo,
    DetailedMediaInfo,
)


# ============================================================
# 测试用 ffprobe 输出数据
# ============================================================

MOCK_FFPROBE_OUTPUT_MULTI_TRACK = {
    "format": {
        "filename": "example.mkv",
        "format_name": "matroska,webm",
        "format_long_name": "Matroska / WebM",
        "duration": "5025.120",
        "bit_rate": "2641000",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "codec_long_name": "H.264 / AVC",
            "profile": "High",
            "level": 41,
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "24000/1001",
            "pix_fmt": "yuv420p",
            "bit_rate": "2200000",
            "tags": {},
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "bit_rate": "192000",
            "tags": {"language": "jpn", "title": "日本語"},
        },
        {
            "index": 2,
            "codec_type": "audio",
            "codec_name": "aac",
            "codec_long_name": "AAC (Advanced Audio Coding)",
            "profile": "LC",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "bit_rate": "192000",
            "tags": {"language": "chi"},
        },
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "ass",
            "codec_long_name": "ASS (Advanced SubStation Alpha) subtitle",
            "tags": {"language": "chi", "title": "简体中文字幕"},
        },
        {
            "index": 4,
            "codec_type": "subtitle",
            "codec_name": "srt",
            "codec_long_name": "SubRip subtitle",
            "tags": {"language": "jpn"},
        },
    ],
    "chapters": [
        {
            "id": 0,
            "start_time": "0.000000",
            "end_time": "120.000000",
            "tags": {"title": "Opening"},
        },
        {
            "id": 1,
            "start_time": "120.000000",
            "end_time": "5025.120000",
            "tags": {"title": "Main"},
        },
    ],
}

MOCK_FFPROBE_OUTPUT_SIMPLE = {
    "format": {
        "filename": "simple.mp4",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "format_long_name": "QuickTime / MOV",
        "duration": "60.0",
        "bit_rate": "5000000",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "profile": "Main",
            "width": 1280,
            "height": 720,
            "r_frame_rate": "30/1",
            "pix_fmt": "yuv420p",
            "tags": {},
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "profile": "LC",
            "sample_rate": "44100",
            "channels": 2,
            "channel_layout": "stereo",
            "bit_rate": "128000",
            "tags": {},
        },
    ],
    "chapters": [],
}


# ============================================================
# 测试 _parse_detailed_output
# ============================================================

class TestParseDetailedOutput:
    """测试 ffprobe JSON 解析逻辑。"""

    def test_parse_multi_track(self):
        """测试多音轨、多字幕的完整解析。"""
        info = _parse_detailed_output("D:\\test\\example.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        
        assert info.filename == "example.mkv"
        assert info.format_name == "matroska,webm"
        assert info.duration_sec == 5025.120
        assert info.total_bitrate_kbps == 2641
        
        # 视频流
        assert len(info.video_streams) == 1
        vs = info.video_streams[0]
        assert vs.index == 0
        assert vs.codec_name == "h264"
        assert vs.profile == "High"
        assert vs.width == 1920
        assert vs.height == 1080
        assert vs.pix_fmt == "yuv420p"
        assert vs.fps == pytest.approx(23.976, abs=0.001)
        assert vs.bitrate_kbps == 2200
        
        # 音频流
        assert len(info.audio_streams) == 2
        assert info.audio_streams[0].index == 0
        assert info.audio_streams[0].language == "jpn"
        assert info.audio_streams[0].title == "日本語"
        assert info.audio_streams[0].sample_rate == 48000
        assert info.audio_streams[0].channels == 2
        assert info.audio_streams[1].index == 1
        assert info.audio_streams[1].language == "chi"
        
        # 字幕流
        assert len(info.subtitle_streams) == 2
        assert info.subtitle_streams[0].index == 0
        assert info.subtitle_streams[0].codec_name == "ass"
        assert info.subtitle_streams[0].language == "chi"
        assert info.subtitle_streams[0].title == "简体中文字幕"
        assert info.subtitle_streams[1].index == 1
        assert info.subtitle_streams[1].codec_name == "srt"
        
        # 章节
        assert len(info.chapters) == 2
        assert info.chapters[0]["title"] == "Opening"
        assert info.chapters[1]["start_time"] == 120.0

    def test_parse_simple(self):
        """测试简单单音轨文件的解析。"""
        info = _parse_detailed_output("D:\\test\\simple.mp4", MOCK_FFPROBE_OUTPUT_SIMPLE)
        
        assert len(info.video_streams) == 1
        assert len(info.audio_streams) == 1
        assert len(info.subtitle_streams) == 0
        assert len(info.chapters) == 0
        
        assert info.video_streams[0].width == 1280
        assert info.audio_streams[0].language == ""

    def test_parse_empty_streams(self):
        """测试无流信息的情况。"""
        data = {"format": {"duration": "10.0"}, "streams": []}
        info = _parse_detailed_output("test.mp3", data)
        
        assert len(info.video_streams) == 0
        assert len(info.audio_streams) == 0
        assert len(info.subtitle_streams) == 0

    def test_parse_missing_fields(self):
        """测试缺少字段时的容错。"""
        data = {
            "format": {},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                }
            ],
        }
        info = _parse_detailed_output("test.mp4", data)
        assert info.duration_sec == 0.0
        assert info.total_bitrate_kbps == 0
        assert info.video_streams[0].width == 0


# ============================================================
# 测试格式化函数
# ============================================================

class TestFormatFunctions:
    """测试格式化辅助函数。"""

    def test_format_file_size(self):
        assert _format_file_size(0) == "未知"
        assert _format_file_size(500) == "500 B"
        assert _format_file_size(1024) == "1.0 KB"
        assert _format_file_size(1024 * 1024) == "1.00 MB"
        assert _format_file_size(1024 * 1024 * 1024) == "1.00 GB"
        assert _format_file_size(1536 * 1024 * 1024) == "1.50 GB"

    def test_format_duration(self):
        assert _format_duration(0) == "00:00:00"
        assert _format_duration(60) == "00:01:00.00"
        assert _format_duration(3661.5) == "01:01:01.50"
        assert _format_duration(5025.12) == "01:23:45.12"

    def test_get_language_display(self):
        assert _get_language_display("") == ""
        assert _get_language_display("jpn") == "[jpn] 日语"
        assert _get_language_display("chi") == "[chi] 中文"
        assert _get_language_display("eng") == "[eng] 英语"
        assert _get_language_display("xyz") == "[xyz]"


# ============================================================
# 测试报告生成
# ============================================================

class TestFormatMediaReport:
    """测试报告格式化。"""

    def test_report_contains_stream_numbers(self):
        """测试报告中是否包含流编号。"""
        info = _parse_detailed_output("test.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        report = format_media_report(info)
        
        assert "视频流 #0" in report
        assert "音频流 #0" in report
        assert "音频流 #1" in report
        assert "字幕流 #0" in report
        assert "字幕流 #1" in report

    def test_report_contains_language(self):
        """测试报告中是否包含语言信息。"""
        info = _parse_detailed_output("test.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        report = format_media_report(info)
        
        assert "jpn" in report
        assert "日语" in report
        assert "chi" in report
        assert "中文" in report

    def test_report_contains_usage_hint(self):
        """测试多轨道文件报告是否包含使用提示。"""
        info = _parse_detailed_output("test.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        report = format_media_report(info)
        
        assert "提示" in report
        assert "音轨编号" in report or "音轨" in report

    def test_report_no_hint_for_single_track(self):
        """测试单轨道文件报告不包含提示。"""
        info = _parse_detailed_output("test.mp4", MOCK_FFPROBE_OUTPUT_SIMPLE)
        report = format_media_report(info)
        
        assert "提示" not in report

    def test_report_with_errors(self):
        """测试带有错误信息的报告。"""
        info = DetailedMediaInfo(path="broken.mp4")
        info.errors.append("ffprobe 无法读取文件")
        report = format_media_report(info)
        
        assert "错误" in report
        assert "无法读取" in report

    def test_report_contains_chapters(self):
        """测试报告中是否包含章节信息。"""
        info = _parse_detailed_output("test.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        report = format_media_report(info)
        
        assert "章节信息" in report
        assert "Opening" in report
        assert "Main" in report


class TestGenerateMediaReport:
    """测试批量报告输出。"""

    def test_generate_report_file(self, tmp_path):
        """测试报告文件生成。"""
        info1 = _parse_detailed_output("test1.mkv", MOCK_FFPROBE_OUTPUT_MULTI_TRACK)
        info2 = _parse_detailed_output("test2.mp4", MOCK_FFPROBE_OUTPUT_SIMPLE)

        output_path = str(tmp_path / "report.txt")
        content = generate_media_report([info1, info2], output_path)

        # 文件应该存在
        assert (tmp_path / "report.txt").exists()
        # 内容应该包含两个文件的信息
        assert "共 2 个文件" in content
        # filename 来自传入的 file_path，不是 ffprobe 返回的
        assert "test1.mkv" in content
        assert "test2.mp4" in content
