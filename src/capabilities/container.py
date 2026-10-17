# -*- coding: utf-8 -*-
"""容器能力矩阵与兼容性预检（纯 Python，无 Qt / 不调用 ffmpeg）。

用途：
    * 封装转换（remux）前预检「输入流编码 × 目标容器」是否可用；
    * 视频压制前预检「输出容器 × 实际编码器」是否合法。

矩阵以 FFmpeg 实际封装能力为准并刻意保守：
    * 只判断「容器层能否承载该编码」，不判断分辨率/码率等参数问题；
    * 未知容器、未知编码器一律不做拦截（返回 ok），避免误伤用户；
    * 未知 codec 名视为不兼容（无法确认时保守拦截，message 注明「未知编码器」）。

本模块不修改 ``src/capabilities/__init__.py``（M3.1 维护），可由
``from src.capabilities.container import ...`` 直接导入。
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Optional, Tuple

from ..presets import ENCODERS


# ----------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------

@dataclass(frozen=True)
class ContainerCapability:
    """单个容器（封装格式）的能力描述。"""

    extension: str
    display: str
    video_codecs: FrozenSet[str] = field(default_factory=frozenset)
    audio_codecs: FrozenSet[str] = field(default_factory=frozenset)
    subtitle_codecs: FrozenSet[str] = field(default_factory=frozenset)
    notes: str = ""


@dataclass(frozen=True)
class ContainerIssue:
    """一条流与目标容器不兼容的明细。"""

    stream_kind: str            # "video" / "audio" / "subtitle"
    codec: str                  # ffprobe codec_name（未知时为空串）
    index: int                  # 流在同类型流中的编号
    message: str                # 可读的明细说明


@dataclass(frozen=True)
class ContainerCheckResult:
    """兼容性预检结果。"""

    ok: bool
    reasons: Tuple[str, ...] = ()
    suggestions: Tuple[str, ...] = ()
    issues: Tuple[ContainerIssue, ...] = ()


# ----------------------------------------------------------------
# 容器矩阵（codec 名使用 ffprobe codec_name 规范名）
# ----------------------------------------------------------------

CONTAINERS: Dict[str, ContainerCapability] = {
    ".mp4": ContainerCapability(
        extension=".mp4",
        display="MP4",
        video_codecs=frozenset({"h264", "hevc", "av1", "mpeg4"}),
        audio_codecs=frozenset({"aac", "mp3", "ac3", "eac3", "opus"}),
        subtitle_codecs=frozenset({"mov_text"}),
        notes="opus 为实验性支持、兼容性差；字幕仅 mov_text",
    ),
    ".m4v": ContainerCapability(
        extension=".m4v",
        display="MP4 (M4V)",
        video_codecs=frozenset({"h264", "hevc", "av1", "mpeg4"}),
        audio_codecs=frozenset({"aac", "mp3", "ac3", "eac3", "opus"}),
        subtitle_codecs=frozenset({"mov_text"}),
        notes="M4V 与 MP4 同源（Apple 生态），兼容性同 MP4",
    ),
    ".mkv": ContainerCapability(
        extension=".mkv",
        display="MKV",
        video_codecs=frozenset({
            "h264", "hevc", "av1", "vp9", "vp8",
            "mpeg2video", "mpeg4", "prores",
        }),
        audio_codecs=frozenset({
            "aac", "opus", "vorbis", "flac", "ac3", "eac3", "dts", "pcm",
        }),
        subtitle_codecs=frozenset({
            "srt", "ass", "mov_text", "pgs", "webvtt",
        }),
        notes="兼容性最广，多音轨/多字幕；prores 等部分编码仅容器层支持",
    ),
    ".mov": ContainerCapability(
        extension=".mov",
        display="MOV",
        video_codecs=frozenset({"h264", "hevc", "prores", "mjpeg", "mpeg4"}),
        audio_codecs=frozenset({"aac", "pcm"}),
        subtitle_codecs=frozenset({"mov_text"}),
        notes="PCM 建议 pcm_s16le/pcm_s24le；字幕仅 mov_text",
    ),
    ".webm": ContainerCapability(
        extension=".webm",
        display="WebM",
        video_codecs=frozenset({"vp8", "vp9", "av1"}),
        audio_codecs=frozenset({"opus", "vorbis"}),
        subtitle_codecs=frozenset({"webvtt"}),
        notes="常规不封装字幕，仅 WebVTT 有限支持",
    ),
    ".m4a": ContainerCapability(
        extension=".m4a",
        display="M4A",
        video_codecs=frozenset(),
        audio_codecs=frozenset({"aac", "alac"}),
        subtitle_codecs=frozenset(),
        notes="仅音频容器，不支持视频流与字幕流",
    ),
    ".ts": ContainerCapability(
        extension=".ts",
        display="TS",
        video_codecs=frozenset({"h264", "hevc", "mpeg2video"}),
        audio_codecs=frozenset({"aac", "mp3", "ac3", "eac3"}),
        subtitle_codecs=frozenset(),
        notes="不承载常规软字幕（DVB 字幕不在此列）",
    ),
}


#: 各流类型在整个矩阵中出现过的 codec（用于区分「已知但不支持」与「未知编码器」）
_KNOWN_CODECS_BY_KIND = {
    kind: frozenset().union(*[
        getattr(capability, f"{kind}_codecs")
        for capability in CONTAINERS.values()
    ])
    for kind in ("video", "audio", "subtitle")
}


#: 流类型中文名
_KIND_LABELS = {
    "video": "视频",
    "audio": "音频",
    "subtitle": "字幕",
}

#: ffprobe codec_name -> 矩阵规范名（只放同义别名，避免矩阵写错）
_CODEC_ALIASES = {
    "video": {
        "mpeg2": "mpeg2video",
    },
    "audio": {},
    "subtitle": {
        "subrip": "srt",
        "hdmv_pgs_subtitle": "pgs",
        "pgssub": "pgs",
    },
}

#: 每个容器推荐的视频编码（建议文案用）
_VIDEO_ADVICE = {
    ".mp4": "H.264/HEVC",
    ".m4v": "H.264/HEVC",
    ".mkv": "H.264/HEVC",
    ".mov": "H.264/ProRes",
    ".webm": "VP9/AV1",
    ".m4a": "H.264",
    ".ts": "H.264/MPEG-2",
}

#: 可选的替代容器优先级（建议文案用，MKV 兼容性最广放最前）
_CONTAINER_PRIORITY = (".mkv", ".mp4", ".mov", ".ts", ".m4v")

#: 编码器二进制名 -> 矩阵规范 codec（从 ENCODERS 展示名反查，保持与预设同源）
def _build_encoder_codec_map(encoders: Dict[str, str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for display_name, binary in encoders.items():
        if "264" in str(display_name):
            codec = "h264"
        elif "265" in str(display_name) or "HEVC" in str(display_name).upper():
            codec = "hevc"
        else:
            continue
        mapping[str(binary).lower()] = codec
    return mapping


_ENCODER_CODECS = _build_encoder_codec_map(ENCODERS)

#: codec -> 展示名（原因文案用）
_CODEC_DISPLAY = {
    "h264": "H.264",
    "hevc": "H.265/HEVC",
}


# ----------------------------------------------------------------
# 工具
# ----------------------------------------------------------------

def normalize_extension(extension: Optional[str]) -> str:
    """把扩展名归一为小写、带前导点；空值返回空串。"""
    text = str(extension or "").strip().lower()
    if not text:
        return ""
    return text if text.startswith(".") else "." + text


def resolve_container(extension: Optional[str]) -> Optional[ContainerCapability]:
    """按扩展名取容器能力；未知容器返回 None（调用方不做预检）。"""
    return CONTAINERS.get(normalize_extension(extension))


#: 压制输出中允许「保留内封字幕流」的容器。
#: MP4/MOV 虽然支持 mov_text，但兼容性差且源字幕多为 ASS/PGS，产品上只开放
#: MKV（推荐）与 MOV；TS/M4A/WebM 等不开放。
EMBEDDED_SUBTITLE_FORMATS: Tuple[str, ...] = ("mkv", "mov")


def supports_embedded_subtitles(extension: Optional[str]) -> bool:
    """该输出扩展名是否支持保留内封字幕流（软字幕）。"""
    normalized = normalize_extension(extension)
    return normalized.lstrip(".") in EMBEDDED_SUBTITLE_FORMATS


def embedded_subtitle_note() -> str:
    """界面提示：说明哪些输出格式支持保留内封字幕流。"""
    labels = " / ".join(ext.upper() for ext in EMBEDDED_SUBTITLE_FORMATS)
    return f"仅 {labels} 输出格式支持保留内封字幕流；其它格式该选项不可用。"


def _normalize_codec(kind: str, codec: str) -> str:
    """把 ffprobe codec_name 归一为矩阵规范名。

    * PCM 家族（pcm_s16le / pcm_s24le / pcm_f32le...）统一为 ``pcm``；
    * mpeg2 -> mpeg2video、subrip -> srt、hdmv_pgs_subtitle -> pgs 等别名；
    * 未知 codec 原样返回（小写），空串表示未知编码器。
    """
    name = str(codec or "").strip().lower()
    if not name:
        return ""
    if name.startswith("pcm_"):
        return "pcm"
    return _CODEC_ALIASES.get(kind, {}).get(name, name)


def _dedupe(items: Iterable[str]) -> Tuple[str, ...]:
    """按出现顺序去重（保持可读性，避免同一原因刷屏）。"""
    seen = set()
    result = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _build_remux_suggestions(
    capability: ContainerCapability,
    target_ext: str,
    kinds: Iterable[str],
) -> Tuple[str, ...]:
    """按不兼容的流类型生成可操作建议（去重、最多 3 条）。"""
    kinds = set(kinds)
    suggestions = []
    if kinds & {"video", "audio"}:
        video_advice = _VIDEO_ADVICE.get(target_ext, "H.264")
        suggestions.append(f"使用视频压制转码为 {video_advice} 视频 + AAC 音频")
    if "subtitle" in kinds:
        suggestions.append("移除不兼容字幕轨，或转为 mov_text/srt 等兼容字幕")
    if target_ext != ".mkv":
        suggestions.append("改为 MKV 封装（兼容性最广）")
    return _dedupe(suggestions)[:3]


# ----------------------------------------------------------------
# 预检：封装转换
# ----------------------------------------------------------------

def check_remux(media_info, target_ext: Optional[str]) -> ContainerCheckResult:
    """预检「媒体文件的流编码 × 目标容器」是否可无损封装。

    Args:
        media_info: ``DetailedMediaInfo``（duck-typed：需要
            video_streams/audio_streams/subtitle_streams，每个流含
            codec_name 与 index 属性）。None 表示探测失败，直接放行。
        target_ext: 目标容器扩展名（如 ".mp4" / "mp4"）。

    Returns:
        ContainerCheckResult: ok=False 时 reasons 给出可读原因、
        suggestions 给出可操作建议、issues 给出逐流明细；
        未知容器 / 探测失败时返回 ok=True（不做预检）。
    """
    capability = resolve_container(target_ext)
    if capability is None or media_info is None:
        return ContainerCheckResult(ok=True)

    issues = []
    reasons = []
    kinds_with_issues = set()

    stream_groups = (
        ("video", getattr(media_info, "video_streams", ()) or (),
         capability.video_codecs),
        ("audio", getattr(media_info, "audio_streams", ()) or (),
         capability.audio_codecs),
        ("subtitle", getattr(media_info, "subtitle_streams", ()) or (),
         capability.subtitle_codecs),
    )
    for kind, streams, allowed in stream_groups:
        kind_label = _KIND_LABELS[kind]
        for stream in streams:
            raw_codec = str(getattr(stream, "codec_name", "") or "")
            codec = _normalize_codec(kind, raw_codec)
            index = int(getattr(stream, "index", 0) or 0)
            if not codec:
                # 未知编码器：无法确认兼容性，保守判为不兼容
                reason = (
                    f"{capability.display} 容器不支持{kind_label}编码"
                    f"（未知编码器）"
                )
                message = (
                    f"{kind_label}流 #{index} 编码未知，"
                    f"无法确认能否封装进 {capability.display} 容器"
                )
            elif codec in allowed:
                continue
            elif codec not in _KNOWN_CODECS_BY_KIND[kind]:
                # 矩阵未收录的 codec：无法确认兼容性，保守判为不兼容
                reason = (
                    f"{capability.display} 容器不支持{kind_label}编码"
                    f"（未知编码器 {raw_codec or codec}）"
                )
                message = (
                    f"{kind_label}流 #{index} 编码 {raw_codec or codec} 未知，"
                    f"无法确认能否封装进 {capability.display} 容器"
                )
            else:
                reason = (
                    f"{capability.display} 容器不支持{kind_label}编码 {codec}"
                )
                message = (
                    f"{kind_label}流 #{index} 编码 {raw_codec or codec} "
                    f"无法封装进 {capability.display} 容器"
                )
            issues.append(ContainerIssue(
                stream_kind=kind,
                codec=codec or raw_codec,
                index=index,
                message=message,
            ))
            reasons.append(reason)
            kinds_with_issues.add(kind)

    if not issues:
        return ContainerCheckResult(ok=True)

    normalized_ext = normalize_extension(target_ext)
    suggestions = _build_remux_suggestions(
        capability, normalized_ext, kinds_with_issues)
    return ContainerCheckResult(
        ok=False,
        reasons=_dedupe(reasons),
        suggestions=suggestions,
        issues=tuple(issues),
    )


# ----------------------------------------------------------------
# 预检：视频压制输出容器 × 编码器
# ----------------------------------------------------------------

def encoder_codec(encoder_binary: Optional[str]) -> Optional[str]:
    """把 ffmpeg 编码器二进制名反查为矩阵 codec；无法反查返回 None。"""
    name = str(encoder_binary or "").strip().lower()
    if not name:
        return None
    if name in _ENCODER_CODECS:
        return _ENCODER_CODECS[name]
    # 兜底：按名称中的 264/265 推断（覆盖未来新增的硬件编码器变体）
    if "265" in name or "hevc" in name:
        return "hevc"
    if "264" in name:
        return "h264"
    return None


def check_encode_output(
    encoder_binary: Optional[str],
    target_ext: Optional[str],
) -> ContainerCheckResult:
    """预检「实际视频编码器 × 目标输出容器」是否合法。

    Args:
        encoder_binary: ffmpeg 视频编码器名（如 "libx264" / "h264_nvenc"），
            来自 ``resolve_encoder_params`` 的最终结果。
        target_ext: 输出容器扩展名（如 ".mp4"）。

    Returns:
        ContainerCheckResult: ok=False 时给出原因与可操作建议；
        未知容器 / 无法反查编码器时返回 ok=True（不做拦截）。
    """
    capability = resolve_container(target_ext)
    if capability is None:
        return ContainerCheckResult(ok=True)

    codec = encoder_codec(encoder_binary)
    if codec is None:
        return ContainerCheckResult(ok=True)

    if not capability.video_codecs:
        reason = f"{capability.display} 容器不支持视频流（仅音频容器）"
        suggestion = "改选 MP4/MKV 等视频容器"
        issue = ContainerIssue(
            stream_kind="video",
            codec=codec,
            index=0,
            message=reason,
        )
        return ContainerCheckResult(
            ok=False, reasons=(reason,),
            suggestions=(suggestion,), issues=(issue,))

    if codec in capability.video_codecs:
        return ContainerCheckResult(ok=True)

    codec_label = _CODEC_DISPLAY.get(codec, codec)
    reason = f"{capability.display} 容器不支持视频编码 {codec_label}"

    # 支持该 codec 的替代容器（按兼容性优先级，排除当前目标容器）
    target = normalize_extension(target_ext)
    alternatives = []
    for ext in _CONTAINER_PRIORITY:
        if ext == target:
            continue
        cap = CONTAINERS.get(ext)
        if cap is not None and codec in cap.video_codecs:
            alternatives.append(cap.display)
    supported_advice = _VIDEO_ADVICE.get(target, "H.264/HEVC")
    if alternatives:
        suggestion = (
            f"改选 {'/'.join(alternatives[:3])} 容器，"
            f"或使用 {supported_advice} 编码"
        )
    else:
        suggestion = f"使用 {supported_advice} 编码"

    issue = ContainerIssue(
        stream_kind="video",
        codec=codec,
        index=0,
        message=reason,
    )
    return ContainerCheckResult(
        ok=False,
        reasons=(reason,),
        suggestions=(suggestion,),
        issues=(issue,),
    )
