# -*- coding: utf-8 -*-
"""编码器能力模型 + 码率控制 (RC) 真实参数映射 (M3.2)。

单一数据源:
    * 编码器清单来自 :mod:`src.presets` 的 ``ENCODERS``（display -> 二进制名），
      新增/删除编码器只需改 presets，本模块与 UI 自动跟随；
    * FFmpeg 实际可用性来自 :class:`src.capabilities.ffmpeg_probe.FfmpegCaps`；
    * 本模块为纯 Python（只 import presets），不依赖 Qt，可独立单测。

术语:
    * ``display``: UI/预设里使用的展示名（``presets.ENCODERS`` 的键）；
    * ``name``: FFmpeg 二进制编码器名（``presets.ENCODERS`` 的值）；
    * ``rc_modes``: 逻辑码率控制模式（crf/vbr/cbr/2pass），与
      ``presets.RATE_CONTROL_MODES`` 的值域一致；
    * ``quality_flag`` / ``speed_flag``: 恒定质量值 / 速度档对应的 FFmpeg 参数名。

能力矩阵（M3.2 约定, M4.4 补充 VideoToolbox）:
    ============  ==========================  ==========================
    编码器         rc_modes                    速度档
    ============  ==========================  ==========================
    CPU           crf / vbr / cbr / 2pass     CPU_PRESETS
    NVENC         crf(vbr+cq) / vbr / cbr     p1..p7
    QSV           crf(gq) / vbr / cbr         CPU_PRESETS
    AMF           crf(cqp) / vbr / cbr        speed/balanced/quality
    VideoToolbox  crf(q:v) / vbr              auto/true/false
    ============  ==========================  ==========================
    2-Pass 仅 CPU 支持；硬件选择 2-Pass 时回退到各自的最佳可用模式并给出说明。

VideoToolbox (M4.4) 只在 macOS 且 ffmpeg 实际探测到 ``h264_videotoolbox`` /
``hevc_videotoolbox`` 时进入能力目录 (Windows/Linux 或未探测完成时不出现);
平台判定统一走 :func:`src.platform.capabilities.platform_capabilities`, 本模块
不直接判断 ``sys.platform``。
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ..presets import CPU_PRESETS, ENCODERS, NVENC_PRESETS

# ----------------------------------------------------------------
# 码率控制模式 (逻辑值, 与 presets.RATE_CONTROL_MODES 的值一致)
# ----------------------------------------------------------------

RC_CRF = "crf"
RC_VBR = "vbr"
RC_CBR = "cbr"
RC_TWO_PASS = "2pass"

CPU_RC_MODES: Tuple[str, ...] = (RC_CRF, RC_VBR, RC_CBR, RC_TWO_PASS)
HARDWARE_RC_MODES: Tuple[str, ...] = (RC_CRF, RC_VBR, RC_CBR)
#: VideoToolbox 只有恒定质量与 VBR, 不支持 2-Pass / CBR
VIDEOTOOLBOX_RC_MODES: Tuple[str, ...] = (RC_CRF, RC_VBR)

#: AMF 速度档 (`-quality` 的取值, 不是 x264 风格 preset)
AMF_SPEED_VALUES: Tuple[str, ...] = ("speed", "balanced", "quality")

#: VideoToolbox 无 ``-preset``, 只有 ``-prio_speed`` 三态: auto / true(优先速度)
#: / false(优先画质); 取值本身就是 ffmpeg 可接受的参数值。
VIDEOTOOLBOX_SPEED_VALUES: Tuple[str, ...] = ("auto", "true", "false")

#: VideoToolbox 编码器 (二进制名, 展示名); 顺序固定, 与
#: :data:`src.platform.capabilities.VIDEOTOOLBOX_ENCODERS` 同源
VIDEOTOOLBOX_ENCODER_SPECS: Tuple[Tuple[str, str], ...] = (
    ("h264_videotoolbox", "H.264 (Apple VideoToolbox)"),
    ("hevc_videotoolbox", "H.265/HEVC (Apple VideoToolbox)"),
)
VIDEOTOOLBOX_ENCODER_NAMES = frozenset(
    name for name, _display in VIDEOTOOLBOX_ENCODER_SPECS)

# 内部家族标识
FAMILY_CPU = "cpu"
FAMILY_NVENC = "nvenc"
FAMILY_QSV = "qsv"
FAMILY_AMF = "amf"
FAMILY_VIDEOTOOLBOX = "videotoolbox"

_SPEED_VALUES = {
    FAMILY_CPU: tuple(CPU_PRESETS),
    FAMILY_NVENC: tuple(NVENC_PRESETS),
    FAMILY_QSV: tuple(CPU_PRESETS),
    FAMILY_AMF: AMF_SPEED_VALUES,
    FAMILY_VIDEOTOOLBOX: VIDEOTOOLBOX_SPEED_VALUES,
}

_SPEED_FLAGS = {
    FAMILY_CPU: "-preset",
    FAMILY_NVENC: "-preset",
    FAMILY_QSV: "-preset",
    FAMILY_AMF: "-quality",
    FAMILY_VIDEOTOOLBOX: "-prio_speed",
}

_QUALITY_FLAGS = {
    FAMILY_CPU: "-crf",
    FAMILY_NVENC: "-cq",
    FAMILY_QSV: "-global_quality",
    FAMILY_AMF: "-qp_i",
    FAMILY_VIDEOTOOLBOX: "-q:v",
}

_MULTIPASS_ARGS = {
    FAMILY_NVENC: ("-multipass", "fullres"),
}

_RC_MODES = {
    FAMILY_CPU: CPU_RC_MODES,
    FAMILY_NVENC: HARDWARE_RC_MODES,
    FAMILY_QSV: HARDWARE_RC_MODES,
    FAMILY_AMF: HARDWARE_RC_MODES,
    FAMILY_VIDEOTOOLBOX: VIDEOTOOLBOX_RC_MODES,
}

_NOTES = {
    FAMILY_CPU: "",
    FAMILY_NVENC: "NVIDIA 硬件编码；不支持 2-Pass, 选择 2-Pass 时回退 VBR + multipass",
    FAMILY_QSV: "Intel QSV 硬件编码；不支持 2-Pass, 选择 2-Pass 时回退 CRF/CQ",
    FAMILY_AMF: "AMD AMF 硬件编码；速度档使用 -quality speed/balanced/quality",
    FAMILY_VIDEOTOOLBOX: (
        "Apple VideoToolbox 硬件编码；不支持 2-Pass, 选择 2-Pass 时回退 CRF/VBR"),
}


def _family_of(name: str) -> str:
    """由二进制名判断编码器家族；未知按 CPU 处理。"""
    text = str(name or "").lower()
    if text in ("libx264", "libx265"):
        return FAMILY_CPU
    if "nvenc" in text:
        return FAMILY_NVENC
    if "qsv" in text:
        return FAMILY_QSV
    if "amf" in text:
        return FAMILY_AMF
    if "videotoolbox" in text:
        return FAMILY_VIDEOTOOLBOX
    return FAMILY_CPU


def _codec_of(name: str) -> str:
    """由二进制名判断视频 codec: h264 / hevc。"""
    text = str(name or "").lower()
    if "265" in text or "hevc" in text:
        return "hevc"
    return "h264"


@dataclass(frozen=True)
class EncoderCapability:
    """单个编码器的不可变能力快照。"""

    name: str                       # FFmpeg 二进制编码器名 (如 "libx264")
    display: str                    # presets.ENCODERS 的展示名
    codec: str                      # "h264" / "hevc"
    is_hardware: bool               # 是否硬件编码器
    available: Optional[bool]       # True/False/None(=未探测, 不隐藏)
    rc_modes: Tuple[str, ...]       # 支持的逻辑码率控制模式
    speed_values: Tuple[str, ...]   # 速度档取值
    speed_flag: str                 # 速度档参数名 (如 "-preset" / "-quality")
    quality_flag: str               # 恒定质量参数名 (如 "-crf" / "-cq")
    multipass_args: Tuple[str, ...] = ()  # 多遍/多重编码参数 (NVENC)
    notes: str = ""


def _build_capability(name: str, display: str,
                      available: Optional[bool]) -> EncoderCapability:
    family = _family_of(name)
    return EncoderCapability(
        name=name,
        display=display,
        codec=_codec_of(name),
        is_hardware=family != FAMILY_CPU,
        available=available,
        rc_modes=_RC_MODES[family],
        speed_values=_SPEED_VALUES[family],
        speed_flag=_SPEED_FLAGS[family],
        quality_flag=_QUALITY_FLAGS[family],
        multipass_args=_MULTIPASS_ARGS.get(family, ()),
        notes=_NOTES[family],
    )


def current_platform() -> str:
    """当前平台标识 (取自平台能力快照; 单测可 monkeypatch 本函数)。

    这里**不**直接判断 ``sys.platform``: 平台判定统一由
    :mod:`src.platform.capabilities` 提供, 本模块只消费其结果。
    平台层异常时返回空串 (等价于"非 macOS", 不追加平台专属编码器)。
    """
    try:
        from ..platform.capabilities import platform_capabilities

        return str(platform_capabilities().os_name or "")
    except Exception:  # pragma: no cover - 平台层异常不影响能力目录
        return ""


def _videotoolbox_capabilities(probed_encoders, platform: Optional[str]) -> list:
    """macOS 且探测到 VideoToolbox 编码器时追加的能力快照。

    出现条件 (缺一不可, 避免给出本平台无法执行的选项):
        * 平台为 ``darwin`` (Windows/Linux 一律不出现);
        * 有真实探测结果 (``caps`` 为 None 或探测失败时不出现);
        * ffmpeg 编码器列表里确实有 ``h264_videotoolbox`` / ``hevc_videotoolbox``。
    """
    resolved = current_platform() if platform is None else str(platform or "")
    if resolved != "darwin":
        return []
    return [
        _build_capability(name, display, True)
        for name, display in VIDEOTOOLBOX_ENCODER_SPECS
        if name in probed_encoders
    ]


def build_encoder_capabilities(caps=None, platform=None
                               ) -> Tuple[EncoderCapability, ...]:
    """构建全部编码器能力（按 ``presets.ENCODERS`` 顺序）。

    Args:
        caps: :class:`FfmpegCaps` 快照；None / 探测失败时所有编码器
            ``available=None``（未知 → UI 保持可选，不隐藏），
            也不会追加 VideoToolbox 编码器。
        platform: 覆盖平台标识（``sys.platform`` 值, 测试用）；缺省读取
            :func:`src.platform.capabilities.platform_capabilities`。

    Returns:
        不可变能力元组; macOS 且探测到 VideoToolbox 时在末尾追加
        ``h264_videotoolbox`` / ``hevc_videotoolbox``。
    """
    probed = caps is not None and not getattr(caps, "probe_error", None)
    probed_encoders = (
        frozenset(getattr(caps, "encoders", frozenset())) if probed else frozenset()
    )
    capabilities = []
    for display, name in ENCODERS.items():
        available = (name in probed_encoders) if probed else None
        capabilities.append(_build_capability(name, display, available))
    capabilities.extend(_videotoolbox_capabilities(probed_encoders, platform))
    return tuple(capabilities)


def visible_encoders(caps=None, platform=None) -> Tuple[EncoderCapability, ...]:
    """可展示/可选的编码器：排除探测明确不可用的项（未知仍然保留）。"""
    return tuple(
        cap for cap in build_encoder_capabilities(caps, platform)
        if cap.available is not False
    )


def encoder_capability(binary_or_display, caps=None,
                       platform=None) -> Optional[EncoderCapability]:
    """按二进制名或展示名查找能力快照；找不到返回 None。"""
    if binary_or_display is None:
        return None
    key = str(binary_or_display).strip()
    if not key:
        return None
    for cap in build_encoder_capabilities(caps, platform):
        if key == cap.name or key == cap.display:
            return cap
    return None


def encoder_definition(binary_or_display) -> Optional[EncoderCapability]:
    """编码器参数定义独立于当前平台与探测结果；可见性仍由能力目录控制。"""
    key = str(binary_or_display or "").strip()
    for display, name in tuple(ENCODERS.items()) + tuple(
            (display, name) for name, display in VIDEOTOOLBOX_ENCODER_SPECS):
        if key in (name, display):
            return _build_capability(name, display, None)
    return None


def _coerce_capability(cap) -> EncoderCapability:
    """把 ``EncoderCapability | str | None`` 归一为能力快照。

    未知编码器按 CPU 处理（保持与旧行为一致的 crf/cq 映射），避免调用方崩溃。
    """
    if isinstance(cap, EncoderCapability):
        return cap
    resolved = encoder_definition(cap)
    if resolved is not None:
        return resolved
    name = str(cap or "libx264").strip() or "libx264"
    return _build_capability(name, name, None)


def supported_rc_modes(cap) -> Tuple[str, ...]:
    """编码器支持的逻辑码率控制模式元组。"""
    return _coerce_capability(cap).rc_modes


def default_speed_preset(cap) -> str:
    """自定义模式下该编码器的默认速度档。"""
    family = _family_of(_coerce_capability(cap).name)
    return {
        FAMILY_CPU: "medium",
        FAMILY_QSV: "medium",
        FAMILY_NVENC: "p4",
        FAMILY_AMF: "balanced",
        FAMILY_VIDEOTOOLBOX: "auto",
    }[family]


# ----------------------------------------------------------------
# RC 参数映射
# ----------------------------------------------------------------

@dataclass(frozen=True)
class RcPlan:
    """一次码率控制映射的结果。"""

    args: Tuple[str, ...] = ()      # 追加到 FFmpeg 命令的参数
    effective_mode: str = RC_CRF    # 实际生效的（逻辑）模式
    note: str = ""                  # 需要提示用户/日志的说明 (正常映射为空)


def _bitrate_value(bitrate) -> Optional[str]:
    if bitrate is None:
        return None
    text = str(bitrate).strip()
    return text or None


def _quality_value(crf) -> Optional[str]:
    if crf is None:
        return None
    text = str(crf).strip()
    return text or None


def _quality_args(family: str, quality: str) -> Tuple[str, ...]:
    """恒定质量参数 (按编码器家族)。"""
    if family == FAMILY_CPU:
        return ("-crf", quality)
    if family == FAMILY_NVENC:
        # CQ 走 VBR 模式: 必须同时给 -b:v 0 才等价于恒定质量
        return ("-rc", "vbr", "-cq", quality, "-b:v", "0")
    if family == FAMILY_QSV:
        return ("-global_quality", quality)
    if family == FAMILY_VIDEOTOOLBOX:
        # VideoToolbox 恒定质量: -q:v (不写 -b:v, 由编码器自行控制码率)
        return ("-q:v", quality)
    # AMF: CQP + qp_i/qp_p
    return ("-rc", "cqp", "-qp_i", quality, "-qp_p", quality)


def _vbr_args(family: str, bitrate: str) -> Tuple[str, ...]:
    if family == FAMILY_CPU:
        return ("-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate)
    if family == FAMILY_NVENC:
        return ("-rc", "vbr", "-b:v", bitrate,
                "-maxrate", bitrate, "-bufsize", bitrate)
    if family == FAMILY_QSV:
        return ("-b:v", bitrate, "-maxrate", bitrate)
    if family == FAMILY_VIDEOTOOLBOX:
        return ("-b:v", bitrate)
    return ("-rc", "vbr_peak", "-b:v", bitrate)


def _cbr_args(family: str, bitrate: str) -> Tuple[str, ...]:
    if family == FAMILY_CPU:
        return ("-b:v", bitrate, "-minrate", bitrate,
                "-maxrate", bitrate, "-bufsize", bitrate)
    if family == FAMILY_NVENC:
        return ("-rc", "cbr", "-b:v", bitrate,
                "-minrate", bitrate, "-maxrate", bitrate)
    if family == FAMILY_QSV:
        return ("-b:v", bitrate, "-maxrate", bitrate)
    if family == FAMILY_VIDEOTOOLBOX:
        # VideoToolbox 无独立 CBR 模式, 按目标码率约束 (rc_modes 里也不提供)
        return ("-b:v", bitrate)
    return ("-rc", "cbr", "-b:v", bitrate, "-maxrate", bitrate)


def _fallback_plan(family: str, quality: Optional[str], rate: Optional[str],
                   reason: str) -> RcPlan:
    """通用回退：优先恒定质量，其次 VBR。"""
    if quality is not None:
        return RcPlan(_quality_args(family, quality), RC_CRF,
                      f"{reason}，已回退 CRF/CQ")
    if rate is not None:
        return RcPlan(_vbr_args(family, rate), RC_VBR,
                      f"{reason}，已回退 VBR")
    return RcPlan((), RC_CRF, f"{reason}，且未提供质量值/目标码率")


def plan_rate_control(cap, rc_mode, crf=None,
                      bitrate=None) -> RcPlan:
    """把逻辑码率控制模式映射为编码器真实 FFmpeg 参数。

    Args:
        cap: :class:`EncoderCapability` / 二进制名 / 展示名（None 按 CPU 处理）。
        rc_mode: 逻辑模式（crf/vbr/cbr/2pass）。
        crf: 恒定质量值（CPU=CRF / NVENC=CQ / QSV=global_quality / AMF=QP）。
        bitrate: 目标码率字符串（如 "8M"）。

    Returns:
        :class:`RcPlan`；``effective_mode`` 与请求不同时表示发生了回退，
        ``note`` 给出回退原因（正常映射为空).
    """
    capability = _coerce_capability(cap)
    family = _family_of(capability.name)
    mode = str(rc_mode or RC_CRF).strip().lower()
    quality = _quality_value(crf)
    rate = _bitrate_value(bitrate)

    # ---- 2-Pass: 仅 CPU 真支持, 硬件回退自身最佳模式 ----
    if mode == RC_TWO_PASS:
        if family == FAMILY_CPU:
            if rate is not None:
                return RcPlan(("-b:v", rate), RC_TWO_PASS, "真正的两遍编码")
            return _fallback_plan(family, quality, None, "2-Pass 模式缺少目标码率")
        if family == FAMILY_NVENC:
            if rate is not None:
                return RcPlan(
                    ("-rc", "vbr", "-b:v", rate,
                     "-maxrate", rate, "-bufsize", rate)
                    + capability.multipass_args,
                    RC_VBR,
                    "NVENC 不支持 2-Pass，已使用 VBR + multipass",
                )
            if quality is not None:
                return RcPlan(
                    _quality_args(family, quality) + capability.multipass_args,
                    RC_CRF,
                    "NVENC 不支持 2-Pass，已回退 CRF/CQ + multipass",
                )
            return RcPlan((), RC_CRF, "NVENC 不支持 2-Pass，且未提供码率/质量值")
        if family == FAMILY_QSV:
            if quality is not None:
                return RcPlan(_quality_args(family, quality), RC_CRF,
                              "QSV 不支持 2-Pass，已回退 CRF/CQ")
            if rate is not None:
                return RcPlan(_vbr_args(family, rate), RC_VBR,
                              "QSV 不支持 2-Pass，已回退 VBR")
            return RcPlan((), RC_CRF, "QSV 不支持 2-Pass，且未提供码率/质量值")
        if family == FAMILY_VIDEOTOOLBOX:
            if quality is not None:
                return RcPlan(_quality_args(family, quality), RC_CRF,
                              "VideoToolbox 不支持 2-Pass，已回退 CRF/CQ")
            if rate is not None:
                return RcPlan(_vbr_args(family, rate), RC_VBR,
                              "VideoToolbox 不支持 2-Pass，已回退 VBR")
            return RcPlan((), RC_CRF,
                          "VideoToolbox 不支持 2-Pass，且未提供码率/质量值")
        # AMF
        if rate is not None:
            return RcPlan(_vbr_args(family, rate), RC_VBR,
                          "AMF 不支持 2-Pass，已回退 VBR")
        if quality is not None:
            return RcPlan(_quality_args(family, quality), RC_CRF,
                          "AMF 不支持 2-Pass，已回退 CQP")
        return RcPlan((), RC_CRF, "AMF 不支持 2-Pass，且未提供码率/质量值")

    # ---- 恒定质量 CRF/CQ ----
    if mode == RC_CRF:
        if quality is not None:
            return RcPlan(_quality_args(family, quality), RC_CRF, "")
        if rate is not None:
            return RcPlan(_vbr_args(family, rate), RC_VBR,
                          "未设置 CRF/CQ 质量值，已回退 VBR")
        return RcPlan((), RC_CRF, "未设置 CRF/CQ 质量值")

    # ---- VBR ----
    if mode == RC_VBR:
        if rate is not None:
            return RcPlan(_vbr_args(family, rate), RC_VBR, "")
        return _fallback_plan(family, quality, None, "VBR 模式缺少目标码率")

    # ---- CBR ----
    if mode == RC_CBR:
        if rate is not None:
            return RcPlan(_cbr_args(family, rate), RC_CBR, "")
        return _fallback_plan(family, quality, None, "CBR 模式缺少目标码率")

    # ---- 未知模式: 回退恒定质量 ----
    if quality is not None:
        return RcPlan(_quality_args(family, quality), RC_CRF,
                      f"未知码率控制模式 {mode}，已回退 CRF/CQ")
    return RcPlan((), RC_CRF, f"未知码率控制模式 {mode}")


#: RC 计划对外别名（见 __all__）
__all__ = [
    "AMF_SPEED_VALUES",
    "CPU_RC_MODES",
    "EncoderCapability",
    "HARDWARE_RC_MODES",
    "RC_CBR",
    "RC_CRF",
    "RC_TWO_PASS",
    "RC_VBR",
    "RcPlan",
    "VIDEOTOOLBOX_ENCODER_NAMES",
    "VIDEOTOOLBOX_ENCODER_SPECS",
    "VIDEOTOOLBOX_RC_MODES",
    "VIDEOTOOLBOX_SPEED_VALUES",
    "build_encoder_capabilities",
    "current_platform",
    "default_speed_preset",
    "encoder_capability",
    "encoder_definition",
    "plan_rate_control",
    "supported_rc_modes",
    "visible_encoders",
]
