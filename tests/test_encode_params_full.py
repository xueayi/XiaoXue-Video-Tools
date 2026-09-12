# -*- coding: utf-8 -*-
"""encode_params.py 覆盖测试。"""

import pytest

from src.encode_params import (
    EncodeMode, EncodeParams, print_encode_info, resolve_encoder_params,
)
from src.presets import (
    AUDIO_ENCODERS, AUDIO_TRACK_OPTIONS, ENCODERS, QUALITY_PRESETS,
    RATE_CONTROL_MODES, SUBTITLE_TRACK_OPTIONS,
)
from src.utils import generate_output_path


class Args:
    """模拟 argparse 参数。"""

    def __init__(self, **kw):
        defaults = dict(
            input="in.mp4", output="", preset="自定义 (Custom)",
            encoder="H.264 (CPU - libx264)", speed_preset="medium",
            nvenc_preset="使用预设默认", rate_control="CRF/CQ (恒定质量)",
            crf=18, video_bitrate="", resolution="", fps=0,
            audio_encoder="复制 (不重新编码)", audio_bitrate="192k",
            subtitle="", compat_mode=False, extra_args="",
            debug_mode=False, output_format="MP4 (默认)",
            output_format_custom="", audio_tracks="仅保留第 1 条 (#0)",
            audio_tracks_custom="", subtitle_tracks="不保留字幕",
            subtitle_tracks_custom="",
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


def _resolve(**kw):
    return resolve_encoder_params(
        Args(**kw), QUALITY_PRESETS, ENCODERS, AUDIO_ENCODERS,
        RATE_CONTROL_MODES, generate_output_path)


def test_resolve_preset_mode():
    params = _resolve(preset="【均衡画质】x264 常用导出 (CRF18)")
    assert params.encoder == "libx264"
    assert params.crf == 18
    assert params.speed_preset == "medium"
    assert params.is_custom is False
    assert params.rc_mode is None
    assert params.output_path == "in_x264.mp4"


def test_resolve_preset_with_nvenc_user_preset():
    params = _resolve(preset="【速度优先】NVIDIA 显卡加速",
                      nvenc_preset="p7")
    assert params.encoder == "h264_nvenc"
    assert params.speed_preset == "p7"
    assert params.crf == 23


def test_resolve_preset_nvenc_default_preset():
    params = _resolve(preset="【速度优先】NVIDIA 显卡加速")
    assert params.speed_preset == "p4"  # 预设默认档位


def test_resolve_custom_cpu():
    params = _resolve()
    assert params.encoder == "libx264"
    assert params.crf == 18
    assert params.speed_preset == "medium"
    assert params.is_custom is True


def test_resolve_custom_nvenc_default_p4():
    params = _resolve(encoder="H.264 (NVIDIA NVENC)")
    assert params.encoder == "h264_nvenc"
    assert params.speed_preset == "p4"


def test_resolve_custom_nvenc_user_preset():
    params = _resolve(encoder="H.264 (NVIDIA NVENC)",
                      nvenc_preset="p6")
    assert params.speed_preset == "p6"


def test_resolve_custom_vbr_bitrate():
    params = _resolve(rate_control="VBR (可变码率)", video_bitrate="8000k")
    assert params.rc_mode == "vbr"
    assert params.bitrate == "8000k"


def test_resolve_output_custom_format():
    params = _resolve(output_format="自定义", output_format_custom="ts")
    assert params.output_path.endswith(".ts")
    params2 = _resolve(output_format="自定义", output_format_custom="mkv",
                       output="out.mp4")
    assert params2.output_path == "out.mp4"


def test_resolve_track_options():
    params = _resolve(audio_tracks="自定义选择 (填写编号)",
                      audio_tracks_custom="0,2",
                      subtitle_tracks="自定义选择 (填写编号)",
                      subtitle_tracks_custom="1")
    assert params.audio_tracks == "custom"
    assert params.audio_tracks_custom == "0,2"
    assert params.subtitle_tracks == "custom"
    assert params.subtitle_tracks_custom == "1"


def test_resolve_subtitle_and_compat():
    params = _resolve(subtitle="sub.ass", compat_mode=True)
    assert params.subtitle_path == "sub.ass"
    assert params.compat_mode is True


def test_get_encode_mode_normal():
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4")
    assert p.get_encode_mode() == EncodeMode.NORMAL


def test_get_encode_mode_compat():
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4",
                     compat_mode=True, subtitle_path="s.ass")
    assert p.get_encode_mode() == EncodeMode.COMPAT


def test_get_encode_mode_twopass():
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4", is_custom=True,
                     rc_mode="2pass", bitrate="5000k")
    assert p.get_encode_mode() == EncodeMode.TWO_PASS


def test_validate_ok(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    p = EncodeParams(input_path=str(f), output_path="o.mp4")
    ok, msg = p.validate()
    assert ok is True and msg == ""


def test_validate_missing_input():
    p = EncodeParams(input_path="Z:/no.mp4", output_path="o.mp4")
    ok, msg = p.validate()
    assert ok is False and "输入文件不存在" in msg


def test_validate_missing_subtitle(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    p = EncodeParams(input_path=str(f), output_path="o.mp4",
                     subtitle_path="Z:/no.ass")
    ok, msg = p.validate()
    assert ok is False and "字幕文件不存在" in msg


def test_validate_crf_range(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    p = EncodeParams(input_path=str(f), output_path="o.mp4", crf=99)
    ok, msg = p.validate()
    assert ok is False and "CRF" in msg


@pytest.mark.parametrize("res", ["1920", "axb", "x"])
def test_validate_bad_resolution(tmp_path, res):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    p = EncodeParams(input_path=str(f), output_path="o.mp4", resolution=res)
    ok, msg = p.validate()
    assert ok is False and "分辨率" in msg


def test_validate_good_resolution(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    p = EncodeParams(input_path=str(f), output_path="o.mp4",
                     resolution="1920x1080")
    ok, _ = p.validate()
    assert ok is True


def test_print_encode_info_preset(capsys):
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4",
                     preset_name="【均衡画质】x264 常用导出 (CRF18)")
    print_encode_info(p, QUALITY_PRESETS)
    out = capsys.readouterr().out
    assert "[预设]" in out and "CRF" in out


def test_print_encode_info_custom(capsys):
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4", is_custom=True,
                     rc_mode="vbr", bitrate="8000k")
    print_encode_info(p, QUALITY_PRESETS)
    out = capsys.readouterr().out
    assert "[自定义模式]" in out and "码率控制" in out


def test_print_encode_info_modes(capsys):
    p = EncodeParams(input_path="a.mp4", output_path="b.mp4",
                     compat_mode=True, subtitle_path="s.ass")
    print_encode_info(p, QUALITY_PRESETS)
    assert "兼容模式" in capsys.readouterr().out
    p2 = EncodeParams(input_path="a.mp4", output_path="b.mp4", is_custom=True,
                      rc_mode="2pass", bitrate="5M")
    print_encode_info(p2, QUALITY_PRESETS)
    assert "2-Pass" in capsys.readouterr().out
