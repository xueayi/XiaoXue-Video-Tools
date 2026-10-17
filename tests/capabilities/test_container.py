# -*- coding: utf-8 -*-
"""容器能力矩阵与兼容性预检单元测试（纯 Python，无 ffmpeg / Qt 调用）。

覆盖：
    * CONTAINERS 矩阵完整性（扩展名/能力字段/关键 codec）；
    * check_remux 各容器正反例、未知 codec 保守拦截、未知容器放行、
      reasons/suggestions/issues 的可读性与去重；
    * check_encode_output 输出容器 × 编码器组合（含 ENCODERS 全量 meta 校验）。
"""

import dataclasses

import pytest

from src.capabilities.container import (
    CONTAINERS,
    ContainerCapability,
    ContainerCheckResult,
    ContainerIssue,
    check_encode_output,
    check_remux,
    encoder_codec,
    normalize_extension,
    resolve_container,
)
from src.media_probe import DetailedMediaInfo, StreamInfo
from src.presets import ENCODERS

EXPECTED_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".webm", ".m4a", ".ts"}


def make_info(video="h264", audio="aac", subtitle=None, extra_audio=()):
    """构造一个含视频/音频/字幕流的 DetailedMediaInfo。"""
    info = DetailedMediaInfo(path="C:/media/a.mkv")
    if video is not None:
        info.video_streams.append(StreamInfo(
            index=0, stream_index=0, codec_type="video",
            codec_name=video))
    audio_codecs = []
    if audio is not None:
        audio_codecs.append(audio)
    audio_codecs.extend(extra_audio)
    for idx, codec in enumerate(audio_codecs):
        info.audio_streams.append(StreamInfo(
            index=idx, stream_index=idx + 1, codec_type="audio",
            codec_name=codec))
    if subtitle is not None:
        info.subtitle_streams.append(StreamInfo(
            index=0, stream_index=9, codec_type="subtitle",
            codec_name=subtitle))
    return info


# ----------------------------------------------------------------
# 矩阵完整性
# ----------------------------------------------------------------

def test_matrix_covers_required_containers():
    assert set(CONTAINERS) == EXPECTED_EXTENSIONS


def test_capability_fields_are_consistent():
    for extension, capability in CONTAINERS.items():
        assert isinstance(capability, ContainerCapability)
        assert capability.extension == extension
        assert capability.display
        assert isinstance(capability.video_codecs, frozenset)
        assert isinstance(capability.audio_codecs, frozenset)
        assert isinstance(capability.subtitle_codecs, frozenset)
        assert isinstance(capability.notes, str)


def test_m4v_matches_mp4():
    mp4 = CONTAINERS[".mp4"]
    m4v = CONTAINERS[".m4v"]
    assert m4v.video_codecs == mp4.video_codecs
    assert m4v.audio_codecs == mp4.audio_codecs
    assert m4v.subtitle_codecs == mp4.subtitle_codecs


def test_m4a_is_audio_only():
    cap = CONTAINERS[".m4a"]
    assert cap.video_codecs == frozenset()
    assert cap.subtitle_codecs == frozenset()
    assert {"aac", "alac"} <= cap.audio_codecs


def test_mkv_is_most_permissive():
    cap = CONTAINERS[".mkv"]
    assert {"h264", "hevc", "av1", "vp9", "prores"} <= cap.video_codecs
    assert {"aac", "opus", "flac", "dts", "pcm"} <= cap.audio_codecs
    assert {"srt", "ass", "mov_text", "pgs"} <= cap.subtitle_codecs


def test_mp4_notes_flag_experimental_opus():
    notes = CONTAINERS[".mp4"].notes
    assert "opus" in notes.lower()
    assert "实验" in notes


def test_webm_has_no_regular_subtitle_codecs():
    cap = CONTAINERS[".webm"]
    assert "srt" not in cap.subtitle_codecs
    assert "ass" not in cap.subtitle_codecs
    assert "webvtt" in cap.subtitle_codecs


def test_ts_has_no_soft_subtitle_codecs():
    assert CONTAINERS[".ts"].subtitle_codecs == frozenset()


def test_resolve_container_normalizes_extension():
    assert resolve_container("mp4") is CONTAINERS[".mp4"]
    assert resolve_container(".MP4") is CONTAINERS[".mp4"]
    assert resolve_container("  .MkV ") is CONTAINERS[".mkv"]
    assert resolve_container(".xyz") is None
    assert resolve_container("") is None
    assert resolve_container(None) is None


def test_normalize_extension_helper():
    assert normalize_extension(".MP4") == ".mp4"
    assert normalize_extension("mkv") == ".mkv"
    assert normalize_extension("") == ""
    assert normalize_extension(None) == ""


def test_result_dataclasses_are_frozen():
    result = ContainerCheckResult(ok=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ok = False
    issue = ContainerIssue(stream_kind="video", codec="h264", index=0,
                           message="m")
    with pytest.raises(dataclasses.FrozenInstanceError):
        issue.codec = "hevc"


# ----------------------------------------------------------------
# check_remux: 兼容正例
# ----------------------------------------------------------------

def test_remux_mp4_fully_compatible():
    result = check_remux(make_info("h264", "aac", "mov_text"), ".mp4")
    assert result.ok is True
    assert result.reasons == () and result.issues == ()


def test_remux_m4v_fully_compatible():
    result = check_remux(make_info("hevc", "ac3", "mov_text"), ".m4v")
    assert result.ok is True


def test_remux_mkv_vp9_opus_ass():
    result = check_remux(make_info("vp9", "opus", "ass"), ".mkv")
    assert result.ok is True


def test_remux_mkv_prores_flac_pgs():
    result = check_remux(make_info("prores", "flac", "hdmv_pgs_subtitle"),
                         ".mkv")
    assert result.ok is True


def test_remux_mkv_mpeg2_and_pcm_aliases():
    # 矩阵规范名为 mpeg2video / pcm，ffprobe 常见写法 mpeg2 / pcm_s16le 需归一
    result = check_remux(make_info("mpeg2", "pcm_s16le"), ".mkv")
    assert result.ok is True


def test_remux_mov_prores_pcm():
    info = make_info("prores", "pcm_s24le", "mov_text")
    assert check_remux(info, ".mov").ok is True


def test_remux_webm_vp9_opus_webvtt():
    assert check_remux(make_info("vp9", "opus", "webvtt"), ".webm").ok is True


def test_remux_m4a_aac():
    assert check_remux(make_info(None, "aac"), ".m4a").ok is True


def test_remux_ts_h264_aac():
    assert check_remux(make_info("h264", "aac"), ".ts").ok is True


def test_remux_ts_mpeg2_alias():
    assert check_remux(make_info("mpeg2", "mp3"), ".ts").ok is True


def test_remux_extension_without_dot():
    assert check_remux(make_info("h264", "aac"), "mkv").ok is True


# ----------------------------------------------------------------
# check_remux: 不兼容反例
# ----------------------------------------------------------------

def test_remux_mp4_rejects_vp9_video():
    result = check_remux(make_info("vp9", "aac"), ".mp4")
    assert result.ok is False
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.stream_kind == "video" and issue.codec == "vp9"
    joined = "；".join(result.reasons)
    assert "MP4" in joined and "视频" in joined and "vp9" in joined
    assert result.suggestions
    assert any("MKV" in s for s in result.suggestions)


def test_remux_mp4_rejects_vorbis_audio():
    result = check_remux(make_info("h264", "vorbis"), ".mp4")
    assert result.ok is False
    assert "音频" in result.reasons[0] and "vorbis" in result.reasons[0]
    assert result.issues[0].stream_kind == "audio"


def test_remux_mp4_rejects_ass_subtitle():
    result = check_remux(make_info("h264", "aac", "ass"), ".mp4")
    assert result.ok is False
    assert result.issues[0].stream_kind == "subtitle"
    assert "字幕" in result.reasons[0]
    assert any("字幕" in s for s in result.suggestions)


def test_remux_webm_rejects_h264():
    result = check_remux(make_info("h264", "opus"), ".webm")
    assert result.ok is False
    assert "WebM" in result.reasons[0]
    assert "h264" in result.reasons[0]


def test_remux_m4a_rejects_video_stream():
    result = check_remux(make_info("h264", "aac"), ".m4a")
    assert result.ok is False
    assert result.issues[0].stream_kind == "video"


def test_remux_ts_rejects_vp9():
    result = check_remux(make_info("vp9", "aac"), ".ts")
    assert result.ok is False
    assert result.issues[0].stream_kind == "video"


def test_remux_unknown_codec_is_conservatively_rejected():
    result = check_remux(make_info("weird_codec", "aac"), ".mp4")
    assert result.ok is False
    joined = "；".join(result.reasons)
    assert "未知编码器" in joined
    issue = result.issues[0]
    assert issue.stream_kind == "video" and issue.codec == "weird_codec"
    assert result.suggestions


def test_remux_empty_codec_is_conservatively_rejected():
    result = check_remux(make_info("", "aac"), ".mp4")
    assert result.ok is False
    assert any("未知编码器" in reason for reason in result.reasons)


# ----------------------------------------------------------------
# check_remux: 放行 / 聚合 / 去重
# ----------------------------------------------------------------

def test_remux_unknown_container_is_not_checked():
    result = check_remux(make_info("vp9", "vorbis", "ass"), ".xyz")
    assert result.ok is True
    assert result.reasons == () and result.suggestions == ()


def test_remux_none_media_info_is_allowed():
    assert check_remux(None, ".mp4").ok is True


def test_remux_multiple_issues_aggregate_and_cap_suggestions():
    info = make_info("vp9", "vorbis", "ass")
    result = check_remux(info, ".mp4")
    assert result.ok is False
    assert len(result.issues) == 3
    assert len(result.reasons) == 3
    assert len(set(result.reasons)) == len(result.reasons)  # 原因去重
    assert 0 < len(result.suggestions) <= 3


def test_remux_duplicate_codec_reasons_are_deduped():
    info = make_info("h264", "vorbis", extra_audio=("vorbis",))
    result = check_remux(info, ".mp4")
    assert result.ok is False
    assert len(result.issues) == 2
    assert len(result.reasons) == 1  # 相同原因只保留一条
    # 建议同样去重
    assert len(set(result.suggestions)) == len(result.suggestions)


def test_remux_issue_message_contains_stream_index():
    info = make_info("h264", "vorbis")
    result = check_remux(info, ".mp4")
    assert "音频流 #0" in result.issues[0].message


def test_remux_subtitle_only_suggestion_has_no_transcode():
    info = make_info("h264", "aac", "ass")
    result = check_remux(info, ".mp4")
    assert result.ok is False
    assert all("转码" not in suggestion for suggestion in result.suggestions)
    assert any("MKV" in suggestion for suggestion in result.suggestions)


# ----------------------------------------------------------------
# check_encode_output
# ----------------------------------------------------------------

@pytest.mark.parametrize("binary, extension", [
    ("libx264", ".mp4"),
    ("h264_nvenc", ".mkv"),
    ("h264_qsv", ".mov"),
    ("h264_amf", ".ts"),
    ("libx265", ".mp4"),
    ("hevc_nvenc", ".m4v"),
])
def test_encode_output_compatible_combinations(binary, extension):
    result = check_encode_output(binary, extension)
    assert result.ok is True
    assert result.reasons == () and result.suggestions == ()


def test_encode_output_webm_rejects_h264_with_suggestions():
    result = check_encode_output("libx264", ".webm")
    assert result.ok is False
    assert "WebM" in result.reasons[0]
    assert "H.264" in result.reasons[0]
    suggestions = "；".join(result.suggestions)
    assert "VP9/AV1" in suggestions
    assert "MKV" in suggestions
    assert result.issues[0].stream_kind == "video"


def test_encode_output_webm_rejects_h264_nvenc():
    assert check_encode_output("h264_nvenc", ".webm").ok is False


def test_encode_output_m4a_rejects_video_encoder():
    result = check_encode_output("libx264", ".m4a")
    assert result.ok is False
    assert "仅音频" in result.reasons[0]
    assert any("MP4" in s for s in result.suggestions)


def test_encode_output_unknown_container_is_allowed():
    assert check_encode_output("libx264", ".xyz").ok is True
    assert check_encode_output("libx264", "").ok is True


def test_encode_output_unknown_encoder_is_allowed():
    # 无法反查 codec 的编码器不做拦截（避免误伤扩展编码器）
    assert check_encode_output("libvpx-vp9", ".webm").ok is True
    assert check_encode_output("", ".mp4").ok is True


def test_encoder_codec_reverse_mapping():
    assert encoder_codec("libx264") == "h264"
    assert encoder_codec("h264_nvenc") == "h264"
    assert encoder_codec("libx265") == "hevc"
    assert encoder_codec("hevc_nvenc") == "hevc"
    assert encoder_codec("h264_custom_variant") == "h264"  # 名称兜底推断
    assert encoder_codec("some_hevc_encoder") == "hevc"
    assert encoder_codec("libvpx-vp9") is None


@pytest.mark.parametrize("binary", sorted(set(ENCODERS.values())))
def test_all_preset_encoders_are_supported_by_mp4_and_mkv(binary):
    """ENCODERS 里每个编码器都必须能被反查，且 MP4/MKV 均可承载。"""
    assert encoder_codec(binary) in ("h264", "hevc")
    assert check_encode_output(binary, ".mp4").ok is True
    assert check_encode_output(binary, ".mkv").ok is True
