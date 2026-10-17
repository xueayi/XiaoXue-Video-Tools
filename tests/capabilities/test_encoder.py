# -*- coding: utf-8 -*-
"""编码器能力模型 + 硬件 RC 映射测试 (M3.2)。

覆盖:
* 能力构建 (全可用 / 无硬件 / 探测失败未知 / caps=None)、
* 单一数据源 (KEY_ENCODERS 与 presets.ENCODERS 一致)、
* rc_modes / speed_values / speed_flag / quality_flag / multipass、
* plan_rate_control 全矩阵 (含硬件 2-Pass 回退 note 与 multipass)。
"""

import dataclasses

import pytest

from src.capabilities.encoder import (
    AMF_SPEED_VALUES,
    CPU_RC_MODES,
    HARDWARE_RC_MODES,
    RC_CBR,
    RC_CRF,
    RC_TWO_PASS,
    RC_VBR,
    RcPlan,
    build_encoder_capabilities,
    default_speed_preset,
    encoder_capability,
    plan_rate_control,
    supported_rc_modes,
    visible_encoders,
)
from src.capabilities.ffmpeg_probe import KEY_ENCODERS, FfmpegCaps
from src.presets import CPU_PRESETS, ENCODERS, NVENC_PRESETS

ALL_ENCODERS = frozenset(ENCODERS.values())
HARDWARE_ENCODERS = frozenset(
    {"h264_nvenc", "hevc_nvenc", "h264_qsv", "h264_amf"})


def _caps(encoders=None, probe_error=None):
    names = ALL_ENCODERS if encoders is None else frozenset(encoders)
    return FfmpegCaps(
        ffmpeg_path="C:/bin/ffmpeg.exe",
        version="7.1",
        encoders=frozenset(names),
        filters=frozenset({"scale"}),
        hwaccels=frozenset({"cuda"}),
        probe_error=probe_error,
        probed_at=1.0,
    )


# ----------------------------------------------------------------
# 能力构建
# ----------------------------------------------------------------

def test_key_encoders_come_from_presets():
    """单一数据源: KEY_ENCODERS 必须来自 presets.ENCODERS。"""
    assert KEY_ENCODERS == tuple(ENCODERS.values())
    assert set(KEY_ENCODERS) == set(ENCODERS.values())


def test_build_all_available():
    capabilities = build_encoder_capabilities(_caps())
    assert len(capabilities) == len(ENCODERS)
    assert tuple(cap.name for cap in capabilities) == tuple(ENCODERS.values())
    assert tuple(cap.display for cap in capabilities) == tuple(ENCODERS.keys())
    assert all(cap.available is True for cap in capabilities)
    assert visible_encoders(_caps()) == capabilities


def test_build_no_hardware_marks_only_hardware_unavailable():
    cpu_only = frozenset({"libx264", "libx265"})
    capabilities = build_encoder_capabilities(_caps(cpu_only))
    available = {cap.name: cap.available for cap in capabilities}
    assert available["libx264"] is True
    assert available["libx265"] is True
    for name in HARDWARE_ENCODERS:
        assert available[name] is False
    assert tuple(cap.name for cap in visible_encoders(_caps(cpu_only))) == (
        "libx264", "libx265")


def test_build_probe_failure_means_unknown():
    capabilities = build_encoder_capabilities(
        _caps(encoders=set(), probe_error="boom"))
    assert all(cap.available is None for cap in capabilities)
    # 未知时不能隐藏任何编码器
    assert len(visible_encoders(_caps(probe_error="boom"))) == len(ENCODERS)


def test_build_none_caps_means_unknown():
    capabilities = build_encoder_capabilities(None)
    assert all(cap.available is None for cap in capabilities)


def test_encoder_fields():
    caps = _caps()
    by_name = {cap.name: cap for cap in build_encoder_capabilities(caps)}
    assert by_name["libx264"].is_hardware is False
    assert by_name["libx264"].codec == "h264"
    assert by_name["libx265"].codec == "hevc"
    assert by_name["hevc_nvenc"].codec == "hevc"
    assert by_name["h264_nvenc"].is_hardware is True
    assert by_name["h264_qsv"].is_hardware is True
    assert by_name["h264_amf"].is_hardware is True
    assert by_name["h264_nvenc"].multipass_args == ("-multipass", "fullres")
    assert by_name["h264_qsv"].multipass_args == ()
    assert by_name["h264_amf"].multipass_args == ()


def test_supported_rc_modes():
    caps = _caps()
    assert supported_rc_modes(encoder_capability("libx264", caps)) == (
        RC_CRF, RC_VBR, RC_CBR, RC_TWO_PASS)
    assert supported_rc_modes(encoder_capability("libx265", caps)) == (
        RC_CRF, RC_VBR, RC_CBR, RC_TWO_PASS)
    for name in HARDWARE_ENCODERS:
        modes = supported_rc_modes(encoder_capability(name, caps))
        assert modes == HARDWARE_RC_MODES == (RC_CRF, RC_VBR, RC_CBR)
        assert RC_TWO_PASS not in modes
    # 传字符串也支持 (UI/日志便利)
    assert supported_rc_modes("h264_nvenc") == HARDWARE_RC_MODES
    assert supported_rc_modes("不存在") == CPU_RC_MODES


def test_speed_values_and_flags():
    caps = _caps()
    cpu = encoder_capability("libx264", caps)
    assert cpu.speed_values == tuple(CPU_PRESETS)
    assert cpu.speed_flag == "-preset"
    assert cpu.quality_flag == "-crf"

    nvenc = encoder_capability("h264_nvenc", caps)
    assert nvenc.speed_values == tuple(NVENC_PRESETS)
    assert nvenc.speed_flag == "-preset"
    assert nvenc.quality_flag == "-cq"

    qsv = encoder_capability("h264_qsv", caps)
    assert qsv.speed_values == tuple(CPU_PRESETS)
    assert qsv.quality_flag == "-global_quality"

    amf = encoder_capability("h264_amf", caps)
    assert amf.speed_values == AMF_SPEED_VALUES == (
        "speed", "balanced", "quality")
    assert amf.speed_flag == "-quality"
    assert amf.quality_flag == "-qp_i"


def test_encoder_capability_lookup():
    caps = _caps(encoders=["libx264", "h264_nvenc"])
    by_binary = encoder_capability("h264_nvenc", caps)
    by_display = encoder_capability("H.264 (NVIDIA NVENC)", caps)
    assert by_binary is not None and by_display is not None
    assert by_binary.name == by_display.name == "h264_nvenc"
    assert by_binary.available is True
    assert encoder_capability("h264_amf", caps).available is False
    assert encoder_capability("不存在", caps) is None
    assert encoder_capability(None, caps) is None


def test_default_speed_preset():
    assert default_speed_preset("libx264") == "medium"
    assert default_speed_preset("h264_qsv") == "medium"
    assert default_speed_preset("h264_nvenc") == "p4"
    assert default_speed_preset("h264_amf") == "balanced"


def test_capabilities_are_frozen():
    capability = encoder_capability("libx264")
    with pytest.raises(dataclasses.FrozenInstanceError):
        capability.available = False  # type: ignore[misc]


# ----------------------------------------------------------------
# RC 映射: CPU
# ----------------------------------------------------------------

def test_plan_cpu_crf():
    plan = plan_rate_control("libx264", RC_CRF, crf=20)
    assert plan == RcPlan(args=("-crf", "20"), effective_mode=RC_CRF, note="")


def test_plan_cpu_vbr_and_cbr():
    vbr = plan_rate_control("libx264", RC_VBR, bitrate="8M")
    assert vbr.args == ("-b:v", "8M", "-maxrate", "8M", "-bufsize", "8M")
    assert vbr.effective_mode == RC_VBR

    cbr = plan_rate_control("libx265", RC_CBR, bitrate="8M")
    assert cbr.args == (
        "-b:v", "8M", "-minrate", "8M", "-maxrate", "8M", "-bufsize", "8M")
    assert cbr.effective_mode == RC_CBR


def test_plan_cpu_2pass_note():
    plan = plan_rate_control("libx264", RC_TWO_PASS, bitrate="10M")
    assert plan.args == ("-b:v", "10M")
    assert plan.effective_mode == RC_TWO_PASS
    assert "真正的两遍编码" in plan.note


def test_plan_cpu_missing_bitrate_falls_back_to_crf():
    plan = plan_rate_control("libx264", RC_VBR, crf=22)
    assert plan.args == ("-crf", "22")
    assert plan.effective_mode == RC_CRF
    assert "缺少目标码率" in plan.note

    plan_no_values = plan_rate_control("libx264", RC_VBR)
    assert plan_no_values.args == ()
    assert plan_no_values.effective_mode == RC_CRF


# ----------------------------------------------------------------
# RC 映射: NVENC
# ----------------------------------------------------------------

def test_plan_nvenc_crf_uses_cq_vbr():
    plan = plan_rate_control("h264_nvenc", RC_CRF, crf=23)
    assert plan.args == ("-rc", "vbr", "-cq", "23", "-b:v", "0")
    assert plan.effective_mode == RC_CRF
    assert plan.note == ""


def test_plan_nvenc_vbr_and_cbr():
    vbr = plan_rate_control("h264_nvenc", RC_VBR, bitrate="8M")
    assert vbr.args == ("-rc", "vbr", "-b:v", "8M",
                        "-maxrate", "8M", "-bufsize", "8M")
    cbr = plan_rate_control("hevc_nvenc", RC_CBR, bitrate="8M")
    assert cbr.args == ("-rc", "cbr", "-b:v", "8M",
                        "-minrate", "8M", "-maxrate", "8M")


def test_plan_nvenc_2pass_falls_back_to_vbr_multipass():
    plan = plan_rate_control("h264_nvenc", RC_TWO_PASS, bitrate="8M")
    assert plan.effective_mode == RC_VBR
    assert "-2pass" not in plan.args
    assert plan.args == ("-rc", "vbr", "-b:v", "8M", "-maxrate", "8M",
                         "-bufsize", "8M", "-multipass", "fullres")
    assert plan.note == "NVENC 不支持 2-Pass，已使用 VBR + multipass"


def test_plan_nvenc_2pass_without_bitrate_falls_back_to_cq():
    plan = plan_rate_control("h264_nvenc", RC_TWO_PASS, crf=20)
    assert plan.effective_mode == RC_CRF
    assert plan.args == ("-rc", "vbr", "-cq", "20", "-b:v", "0",
                         "-multipass", "fullres")
    assert "-2pass" not in plan.args


# ----------------------------------------------------------------
# RC 映射: QSV / AMF
# ----------------------------------------------------------------

def test_plan_qsv_modes():
    crf = plan_rate_control("h264_qsv", RC_CRF, crf=22)
    assert crf.args == ("-global_quality", "22")
    vbr = plan_rate_control("h264_qsv", RC_VBR, bitrate="8M")
    assert vbr.args == ("-b:v", "8M", "-maxrate", "8M")
    cbr = plan_rate_control("h264_qsv", RC_CBR, bitrate="8M")
    assert cbr.args == ("-b:v", "8M", "-maxrate", "8M")

    fallback = plan_rate_control("h264_qsv", RC_TWO_PASS, crf=22)
    assert fallback.effective_mode == RC_CRF
    assert fallback.args == ("-global_quality", "22")
    assert "QSV 不支持 2-Pass" in fallback.note

    vbr_fallback = plan_rate_control("h264_qsv", RC_TWO_PASS, bitrate="8M")
    assert vbr_fallback.effective_mode == RC_VBR
    assert vbr_fallback.args == ("-b:v", "8M", "-maxrate", "8M")


def test_plan_amf_modes():
    crf = plan_rate_control("h264_amf", RC_CRF, crf=22)
    assert crf.args == ("-rc", "cqp", "-qp_i", "22", "-qp_p", "22")
    vbr = plan_rate_control("h264_amf", RC_VBR, bitrate="8M")
    assert vbr.args == ("-rc", "vbr_peak", "-b:v", "8M")
    cbr = plan_rate_control("h264_amf", RC_CBR, bitrate="8M")
    assert cbr.args == ("-rc", "cbr", "-b:v", "8M", "-maxrate", "8M")

    fallback = plan_rate_control("h264_amf", RC_TWO_PASS, bitrate="8M")
    assert fallback.effective_mode == RC_VBR
    assert fallback.args == ("-rc", "vbr_peak", "-b:v", "8M")
    assert "AMF 不支持 2-Pass" in fallback.note


def test_hardware_plans_never_claim_2pass():
    caps = _caps()
    for name in HARDWARE_ENCODERS:
        capability = encoder_capability(name, caps)
        plan = plan_rate_control(capability, RC_TWO_PASS, bitrate="8M", crf=20)
        assert plan.effective_mode != RC_TWO_PASS, name
        assert "-2pass" not in plan.args, name
        assert plan.note, name  # 回退必须附带说明


# ----------------------------------------------------------------
# 入参归一
# ----------------------------------------------------------------

def test_plan_accepts_capability_and_display_name():
    caps = _caps()
    capability = encoder_capability("h264_nvenc", caps)
    from_cap = plan_rate_control(capability, RC_CRF, crf=23)
    from_display = plan_rate_control("H.264 (NVIDIA NVENC)", RC_CRF, crf=23)
    assert from_cap == from_display


def test_plan_unknown_encoder_falls_back_to_cpu_mapping():
    plan = plan_rate_control("unknown_enc", RC_CRF, crf=18)
    assert plan.args == ("-crf", "18")


def test_plan_unknown_mode_falls_back_to_crf():
    plan = plan_rate_control("libx264", "weird", crf=18)
    assert plan.args == ("-crf", "18")
    assert plan.effective_mode == RC_CRF
    assert "未知码率控制模式" in plan.note


def test_plan_strips_whitespace_values():
    plan = plan_rate_control("libx264", RC_CRF, crf=" 20 ")
    assert plan.args == ("-crf", "20")
    vbr = plan_rate_control("libx264", RC_VBR, bitrate=" 8M ")
    assert vbr.args[1] == "8M"
