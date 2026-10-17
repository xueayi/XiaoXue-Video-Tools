# -*- coding: utf-8 -*-
"""FFmpeg 错误分类 —— 把失败日志 (stderr 尾部) 归类为用户可读的原因与建议。

M2.5 起本模块是错误分类的唯一实现，从两处历史逻辑迁移并整理为可维护规则表：

* ``src/core.py`` 的硬件编码器关键词 (NVENC / QSV / AMF)；
* 首版 ``src/ui/error_card.py`` 的日志归类规则与用户文案
  (含 ``src/ui/tabs/remux_tab.py`` 的容器兼容关键词)。

设计约定：

* 纯 Python，不依赖 Qt / PyQt6，可在执行层、CLI、UI 复用；
* 分类优先级：取消标志 > 规则表 (越具体越靠前) > ``exit_code == -1``
  (进程无法启动 / FFmpeg 缺失) > 未知兜底；
* 返回值 :class:`UserFacingError` 是「可直接展示」的不可变数据，
  文案在 :data:`_CATALOG` 中集中维护。

TODO(M3): 容器能力矩阵 (PR-13) 接入后，CONTAINER_INCOMPATIBLE 的建议操作
可由 ``ContainerCapability`` 动态生成，而不是固定文案。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

__all__ = [
    "ErrorCategory",
    "LOG_TAIL_MAX_LINES",
    "UserFacingError",
    "classify",
]

#: log_tail 字段最多保留的日志行数 (供「查看完整日志」定位)
LOG_TAIL_MAX_LINES = 20


class ErrorCategory(str, Enum):
    """用户可感知的 8 类错误。"""

    ENCODER_UNAVAILABLE = "encoder_unavailable"
    CONTAINER_INCOMPATIBLE = "container_incompatible"
    INPUT_NOT_FOUND = "input_not_found"
    OUTPUT_PERMISSION_DENIED = "output_permission_denied"
    SUBTITLE_FILTER_ERROR = "subtitle_filter_error"
    FFMPEG_NOT_FOUND = "ffmpeg_not_found"
    PROCESS_CANCELLED = "process_cancelled"
    UNKNOWN_FFMPEG_ERROR = "unknown_ffmpeg_error"


@dataclass(frozen=True)
class UserFacingError:
    """面向用户的错误信息 (标题 / 分类 / 可能原因 / 建议操作 / 日志尾部)。"""

    title: str
    category: ErrorCategory
    causes: Tuple[str, ...] = ()
    actions: Tuple[str, ...] = ()
    log_tail: str = ""


# ----------------------------------------------------------------
# 分类规则表 —— 匹配顺序即优先级: 越具体/越不应被误判的规则越靠前
# ----------------------------------------------------------------

# NVIDIA NVENC 错误关键词 (迁自 src/core.py _check_hardware_encoder_error)
_NVENC_KEYWORDS: Tuple[str, ...] = (
    "no nvenc capable devices found",
    "cannot load cuvidparser",
    "cannot load nvcuda.dll",
    "driver does not support the required nvenc api version",
    "the minimum required nvidia driver for nvenc",
    "nvenc encoder error",
    "failed to init nvenc",
)

# Intel QSV 错误关键词 (同上)
_QSV_KEYWORDS: Tuple[str, ...] = (
    "error initializing an mfx session",
    "device failed",
    "mfxinit failed",
    "could not initialize mfx session",
    "qsv is not supported",
)

# AMD AMF 错误关键词 (同上)
_AMF_KEYWORDS: Tuple[str, ...] = (
    "createcomponent failed",
    "amf failed",
    "amf encoder error",
    "failed to create amf",
    "amfcomponentoptimizedpush_querymhesupport",
)

# 编码器不可用: 硬件编码器关键词 + FFmpeg 通用报错
_ENCODER_KEYWORDS: Tuple[str, ...] = _NVENC_KEYWORDS + _QSV_KEYWORDS + _AMF_KEYWORDS + (
    "unknown encoder",
    "encoder not found",
    "error while opening encoder",
    "failed to open encoder",
    "cannot load encoder",
    "encoder unavailable",
    "error initializing output stream",
)

# 容器不兼容 (迁自 remux_tab.py 容器规则 + FFmpeg muxer 报错)
_CONTAINER_KEYWORDS: Tuple[str, ...] = (
    "not currently supported in container",
    "codec not currently supported in container",
    "could not find tag for codec",
    "unsupported codec in container",
    "incompatible with the container",
    "container format is not supported",
    "could not find codec parameters",
    "容器不兼容",
    "无法封装",
)

# 输入文件问题
_INPUT_KEYWORDS: Tuple[str, ...] = (
    "no such file or directory",
    "invalid data found when processing input",
    "could not open input",
    "cannot open input",
    "error opening input",
    "input file not found",
    "moov atom not found",
    "找不到输入",
    "输入文件不存在",
    "文件不存在",
)

# 输出目录/文件权限问题
_PERMISSION_KEYWORDS: Tuple[str, ...] = (
    "permission denied",
    "access is denied",
    "permissionerror",
    "permission error",
    "unable to open for writing",
    "read-only file system",
    "拒绝访问",
    "没有权限",
    "只读",
)

# 字幕滤镜问题 (含 ffmpeg 的滤镜初始化/字体错误)
_SUBTITLE_KEYWORDS: Tuple[str, ...] = (
    "error applying subtitles filter",
    "error opening filters",
    "unable to open subtitle",
    "no such filter: 'subtitles'",
    "no such filter: subtitles",
    "subtitles filter",
    "error reinitializing filters",
    "fontconfig error",
    "libass",
    "字幕滤镜",
    "无法加载字幕",
)

# FFmpeg 本体缺失
_FFMPEG_KEYWORDS: Tuple[str, ...] = (
    "ffmpeg: not found",
    "ffmpeg: command not found",
    "ffmpeg not found",
    "ffmpeg.exe not found",
    "no ffmpeg executable",
    "ffmpeg 未安装",
    "找不到 ffmpeg",
    "ffmpeg 不可用",
)

# 用户主动取消
_CANCELLED_KEYWORDS: Tuple[str, ...] = (
    "任务已停止",
    "用户取消",
    "已取消",
    "cancelled",
    "canceled",
    "user cancel",
    "received signal",
    "exiting normally, received signal",
)

#: 规则表: (分类, 关键词)。按顺序匹配，首个命中即返回。
_RULES: Tuple[Tuple[ErrorCategory, Tuple[str, ...]], ...] = (
    (ErrorCategory.FFMPEG_NOT_FOUND, _FFMPEG_KEYWORDS),
    (ErrorCategory.PROCESS_CANCELLED, _CANCELLED_KEYWORDS),
    (ErrorCategory.INPUT_NOT_FOUND, _INPUT_KEYWORDS),
    (ErrorCategory.OUTPUT_PERMISSION_DENIED, _PERMISSION_KEYWORDS),
    (ErrorCategory.SUBTITLE_FILTER_ERROR, _SUBTITLE_KEYWORDS),
    (ErrorCategory.CONTAINER_INCOMPATIBLE, _CONTAINER_KEYWORDS),
    (ErrorCategory.ENCODER_UNAVAILABLE, _ENCODER_KEYWORDS),
)

# ----------------------------------------------------------------
# 每类错误的中文标题 / 可能原因 / 建议操作
# ----------------------------------------------------------------

_CATALOG: Dict[ErrorCategory, Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = {
    ErrorCategory.ENCODER_UNAVAILABLE: (
        "硬件编码器不可用",
        (
            "显卡驱动版本过低，或与当前 FFmpeg 要求的编码 API 版本不匹配",
            "显卡/核显不支持所选硬件编码器 (NVENC / QSV / AMF)，或已在 BIOS/系统中禁用",
            "FFmpeg 构建未包含对应硬件编码器支持，或编码器被其他程序占用",
        ),
        (
            "改用 CPU 编码 (H.264 / H.265)",
            "更新显卡驱动后重试",
            "检测硬件编码能力",
        ),
    ),
    ErrorCategory.CONTAINER_INCOMPATIBLE: (
        "目标容器不兼容",
        (
            "所选视频/音频编码不受目标容器支持 (如 MP4 不支持 VP9/Opus)",
            "目标容器不支持内封所选字幕格式 (如 MP4 不支持 ASS 字幕)",
            "输出扩展名与 FFmpeg 封装器 (muxer) 不匹配",
        ),
        (
            "改用 MKV 容器重新封装",
            "转码为容器兼容的编码格式",
            "检查输出文件扩展名",
        ),
    ),
    ErrorCategory.INPUT_NOT_FOUND: (
        "找不到输入文件",
        (
            "输入路径错误、文件已被移动或删除",
            "文件名包含特殊字符，命令参数转义不完整",
            "输入文件损坏或不是 FFmpeg 支持的媒体格式",
        ),
        (
            "重新选择输入文件",
            "检查路径与文件名后重试",
            "用媒体信息工具确认文件可读",
        ),
    ),
    ErrorCategory.OUTPUT_PERMISSION_DENIED: (
        "没有文件写入权限",
        (
            "输出目录只读，或当前用户无权在该位置创建文件",
            "输出文件正被其他程序 (播放器/杀毒软件) 占用",
            "目标磁盘空间不足或路径无效",
        ),
        (
            "更换输出目录",
            "关闭占用文件的程序后重试",
            "检查磁盘空间与目录权限",
        ),
    ),
    ErrorCategory.SUBTITLE_FILTER_ERROR: (
        "字幕滤镜处理失败",
        (
            "字幕文件缺失、损坏或编码不是 UTF-8",
            "FFmpeg 构建未包含 subtitles 滤镜 (缺少 libass)",
            "字幕滤镜选项 (字体/样式/language) 参数不合法",
        ),
        (
            "检查字幕文件是否完整可读",
            "关闭字幕压制后重试",
            "确认 FFmpeg 集成字幕滤镜",
        ),
    ),
    ErrorCategory.FFMPEG_NOT_FOUND: (
        "找不到 FFmpeg",
        (
            "FFmpeg 未安装，或 bin 目录下缺少 ffmpeg.exe",
            "程序目录被移动/杀毒软件隔离了 FFmpeg 文件",
            "PATH 环境变量中未包含 FFmpeg 所在目录",
        ),
        (
            "重新下载或放置 FFmpeg",
            "在设置中检查 FFmpeg 路径",
            "查看安装说明",
        ),
    ),
    ErrorCategory.PROCESS_CANCELLED: (
        "任务已取消",
        (
            "用户手动停止了任务",
            "程序退出时主动结束了子进程",
            "FFmpeg 收到终止信号并退出",
        ),
        ("重新开始任务",),
    ),
    ErrorCategory.UNKNOWN_FFMPEG_ERROR: (
        "FFmpeg 执行失败",
        (
            "命令参数与当前 FFmpeg 版本不兼容",
            "输入/输出文件状态在任务执行期间发生变化",
            "未归类的 FFmpeg 运行错误",
        ),
        (
            "查看完整日志定位原因",
            "重试任务或降低并发",
            "反馈完整日志以便排查",
        ),
    ),
}


def _log_tail(text: str, max_lines: int = LOG_TAIL_MAX_LINES) -> str:
    """取日志末尾若干非空行。"""
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _make_error(
    category: ErrorCategory,
    raw_text: str,
    exit_code: Optional[int] = None,
) -> UserFacingError:
    """按分类目录构造 UserFacingError；未知错误附加退出码便于排查。"""
    title, causes, actions = _CATALOG[category]
    if exit_code is not None and category is ErrorCategory.UNKNOWN_FFMPEG_ERROR:
        causes = causes + (f"FFmpeg 进程退出码: {exit_code}",)
    return UserFacingError(
        title=title,
        category=category,
        causes=causes,
        actions=actions,
        log_tail=_log_tail(raw_text),
    )


def classify(
    stderr_tail: str = "",
    exit_code: Optional[int] = None,
    cancelled: bool = False,
) -> UserFacingError:
    """把 FFmpeg stderr 尾部归类为 :class:`UserFacingError`。

    Args:
        stderr_tail: FFmpeg 的 stderr 尾部文本 (可为空)。
        exit_code: 子进程退出码；``-1`` 视为进程无法启动 (FFmpeg 缺失)，
            未知错误会把退出码写进原因便于排查。
        cancelled: 是否由用户主动取消；为 True 时优先返回 PROCESS_CANCELLED，
            即使日志里同时出现其他错误关键词。

    Returns:
        可直接展示的 UserFacingError；任何输入都有兜底分类，不会返回 None。
    """
    text = stderr_tail or ""
    if cancelled:
        return _make_error(ErrorCategory.PROCESS_CANCELLED, text)

    lowered = text.lower()
    for category, keywords in _RULES:
        if any(keyword in lowered for keyword in keywords):
            return _make_error(category, text, exit_code)

    # run_ffmpeg_command 在 FFmpeg 无法启动时返回 -1（无 stderr 可归类）
    if exit_code == -1:
        return _make_error(ErrorCategory.FFMPEG_NOT_FOUND, text, exit_code)

    return _make_error(ErrorCategory.UNKNOWN_FFMPEG_ERROR, text, exit_code)
