# -*- coding: utf-8 -*-
"""错误卡片 —— 把 FFmpeg/任务失败日志归类为用户可读的原因与建议操作。

本模块包含三部分:
    * :class:`ErrorCategory` —— 8 类用户可感知错误 (PR-11 将迁入
      ``src/ffmpeg/errors.py`` 统一为后端错误模型)；
    * :func:`classify_log_text` —— 从日志文本迁移现有 ``core.py`` 的
      NVIDIA/QSV/AMF 关键词与 ``remux_tab`` 的容器兼容规则，做首版归类；
    * :class:`ErrorCard` —— 展示标题、可能原因 (hint 样式) 与操作按钮，
      操作/日志按钮只发信号，由上层决定行为。

TODO(PR-11): 分类规则迁至 ``src/ffmpeg/errors.py``，UI 只消费 ``ErrorInfo``。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

# 日志尾部最多保留的行数 (供「查看完整日志」定位)
_LOG_TAIL_LINES = 20


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


@dataclass
class ErrorInfo:
    """错误卡片的展示数据 (原因用 hint 样式，动作为按钮)。"""

    title: str
    causes: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    log_tail: str = ""
    category: ErrorCategory = ErrorCategory.UNKNOWN_FFMPEG_ERROR


# ----------------------------------------------------------------
# 分类规则 —— 首版从 core.py / remux_tab.py 迁移
# ----------------------------------------------------------------

# NVIDIA NVENC 错误关键词 (迁自 src/core.py _check_hardware_encoder_error)
_NVENC_KEYWORDS = (
    "no nvenc capable devices found",
    "cannot load cuvidparser",
    "driver does not support the required nvenc api version",
    "the minimum required nvidia driver for nvenc",
    "nvenc encoder error",
    "failed to init nvenc",
)

# Intel QSV 错误关键词 (同上)
_QSV_KEYWORDS = (
    "error initializing an mfx session",
    "device failed",
    "mfxinit failed",
    "could not initialize mfx session",
    "qsv is not supported",
)

# AMD AMF 错误关键词 (同上)
_AMF_KEYWORDS = (
    "createcomponent failed",
    "amf failed",
    "amf encoder error",
    "failed to create amf",
    "amfcomponentoptimizedpush_querymhesupport",
)

# 编码器不可用附加关键词 (FFmpeg 通用报错)
_ENCODER_KEYWORDS = _NVENC_KEYWORDS + _QSV_KEYWORDS + _AMF_KEYWORDS + (
    "unknown encoder",
    "encoder not found",
    "error while opening encoder",
    "failed to open encoder",
    "cannot load encoder",
    "encoder unavailable",
)

# 容器不兼容关键词 (迁自 src/ui/tabs/remux_tab.py 容器规则 + FFmpeg 日志)
_CONTAINER_KEYWORDS = (
    "not currently supported in container",
    "codec not currently supported in container",
    "could not find tag for codec",
    "unsupported codec in container",
    "incompatible with the container",
    "container format is not supported",
    "容器不兼容",
    "无法封装",
)

# 输入文件问题关键词
_INPUT_KEYWORDS = (
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

# 输出目录/文件权限关键词
_PERMISSION_KEYWORDS = (
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

# 字幕滤镜关键词
_SUBTITLE_KEYWORDS = (
    "error applying subtitles filter",
    "unable to open subtitle",
    "no such filter: 'subtitles'",
    "no such filter: subtitles",
    "subtitles filter",
    "error reinitializing filters",
    "fontconfig error",
    "字幕滤镜",
    "无法加载字幕",
)

# FFmpeg 本体缺失关键词
_FFMPEG_KEYWORDS = (
    "ffmpeg: not found",
    "ffmpeg: command not found",
    "ffmpeg not found",
    "ffmpeg.exe not found",
    "no ffmpeg executable",
    "ffmpeg 未安装",
    "找不到 ffmpeg",
    "ffmpeg 不可用",
)

# 用户主动取消关键词
_CANCELLED_KEYWORDS = (
    "任务已停止",
    "用户取消",
    "已取消",
    "cancelled",
    "canceled",
    "user cancel",
    "received signal",
    "exiting normally, received signal",
)

# 匹配顺序即优先级：越具体/越不应被误判的规则越靠前
# TODO(PR-11): 整套规则迁至 src/ffmpeg/errors.py，UI 只消费 ErrorInfo。
_CLASSIFY_RULES = (
    (ErrorCategory.FFMPEG_NOT_FOUND, _FFMPEG_KEYWORDS),
    (ErrorCategory.PROCESS_CANCELLED, _CANCELLED_KEYWORDS),
    (ErrorCategory.INPUT_NOT_FOUND, _INPUT_KEYWORDS),
    (ErrorCategory.OUTPUT_PERMISSION_DENIED, _PERMISSION_KEYWORDS),
    (ErrorCategory.SUBTITLE_FILTER_ERROR, _SUBTITLE_KEYWORDS),
    (ErrorCategory.CONTAINER_INCOMPATIBLE, _CONTAINER_KEYWORDS),
    (ErrorCategory.ENCODER_UNAVAILABLE, _ENCODER_KEYWORDS),
)

# 每类错误的中文标题/原因/建议操作
_CATEGORY_CATALOG = {
    ErrorCategory.ENCODER_UNAVAILABLE: (
        "硬件编码器不可用",
        [
            "显卡驱动版本过低，或与当前 FFmpeg 要求的编码 API 版本不匹配",
            "显卡/核显不支持所选硬件编码器 (NVENC / QSV / AMF)，或已在 BIOS/系统中禁用",
            "FFmpeg 构建未包含对应硬件编码器支持，或编码器被其他程序占用",
        ],
        ["改用 CPU 编码 (H.264 / H.265)", "更新显卡驱动后重试", "检测硬件编码能力"],
    ),
    ErrorCategory.CONTAINER_INCOMPATIBLE: (
        "目标容器不兼容",
        [
            "所选视频/音频编码不受目标容器支持 (如 MP4 不支持 VP9/Opus)",
            "目标容器不支持内封所选字幕格式 (如 MP4 不支持 ASS 字幕)",
            "输出扩展名与 FFmpeg 封装器 (muxer) 不匹配",
        ],
        ["改用 MKV 容器重新封装", "转码为容器兼容的编码格式", "检查输出文件扩展名"],
    ),
    ErrorCategory.INPUT_NOT_FOUND: (
        "找不到输入文件",
        [
            "输入路径错误、文件已被移动或删除",
            "文件名包含特殊字符，命令参数转义不完整",
            "输入文件损坏或不是 FFmpeg 支持的媒体格式",
        ],
        ["重新选择输入文件", "检查路径与文件名后重试", "用媒体信息工具确认文件可读"],
    ),
    ErrorCategory.OUTPUT_PERMISSION_DENIED: (
        "没有文件写入权限",
        [
            "输出目录只读，或当前用户无权在该位置创建文件",
            "输出文件正被其他程序 (播放器/杀毒软件) 占用",
            "目标磁盘空间不足或路径无效",
        ],
        ["更换输出目录", "关闭占用文件的程序后重试", "检查磁盘空间与目录权限"],
    ),
    ErrorCategory.SUBTITLE_FILTER_ERROR: (
        "字幕滤镜处理失败",
        [
            "字幕文件缺失、损坏或编码不是 UTF-8",
            "FFmpeg 构建未包含 subtitles 滤镜 (缺少 libass)",
            "字幕滤镜选项 (字体/样式/language) 参数不合法",
        ],
        ["检查字幕文件是否完整可读", "关闭字幕压制后重试", "确认 FFmpeg 集成字幕滤镜"],
    ),
    ErrorCategory.FFMPEG_NOT_FOUND: (
        "找不到 FFmpeg",
        [
            "FFmpeg 未安装，或 bin 目录下缺少 ffmpeg.exe",
            "程序目录被移动/杀毒软件隔离了 FFmpeg 文件",
            "PATH 环境变量中未包含 FFmpeg 所在目录",
        ],
        ["重新下载或放置 FFmpeg", "在设置中检查 FFmpeg 路径", "查看安装说明"],
    ),
    ErrorCategory.PROCESS_CANCELLED: (
        "任务已取消",
        [
            "用户手动停止了任务",
            "程序退出时主动结束了子进程",
            "FFmpeg 收到终止信号并退出",
        ],
        ["重新开始任务"],
    ),
    ErrorCategory.UNKNOWN_FFMPEG_ERROR: (
        "FFmpeg 执行失败",
        [
            "命令参数与当前 FFmpeg 版本不兼容",
            "输入/输出文件状态在任务执行期间发生变化",
            "未归类的 FFmpeg 运行错误",
        ],
        ["查看完整日志定位原因", "重试任务或降低并发", "反馈完整日志以便排查"],
    ),
}


def _log_tail(text: str, max_lines: int = _LOG_TAIL_LINES) -> str:
    """取日志末尾若干非空行。"""
    lines = [line.rstrip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _make_info(category: ErrorCategory, raw_text: str) -> ErrorInfo:
    title, causes, actions = _CATEGORY_CATALOG[category]
    return ErrorInfo(
        title=title,
        causes=list(causes),
        actions=list(actions),
        log_tail=_log_tail(raw_text),
        category=category,
    )


def classify_log_text(text: str) -> ErrorInfo:
    """把 FFmpeg/任务日志归类为 :class:`ErrorInfo`。

    匹配顺序见 ``_CLASSIFY_RULES``；无命中时返回 UNKNOWN_FFMPEG_ERROR，
    保证任何失败都能渲染错误卡片。
    """
    raw = text or ""
    lowered = raw.lower()
    for category, keywords in _CLASSIFY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return _make_info(category, raw)
    return _make_info(ErrorCategory.UNKNOWN_FFMPEG_ERROR, raw)


class ErrorCard(QFrame):
    """错误卡片：标题 + 可能原因 (hint 样式) + 建议操作按钮。"""

    #: 用户点击某个建议操作 (参数: 操作文案)
    action_requested = pyqtSignal(str)
    #: 用户点击「查看完整日志」
    log_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("error_card")
        self._error = None
        self._action_buttons = []
        self._build_ui()
        self.hide()

    # ----------------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------------

    @property
    def error(self):
        """当前展示的 ErrorInfo (未展示时 None)。"""
        return self._error

    def show(self, error: ErrorInfo):
        """展示一个 ErrorInfo (替代 QWidget.show 的无参形式)。"""
        if not isinstance(error, ErrorInfo):
            raise TypeError(f"ErrorCard.show 需要 ErrorInfo，收到 {type(error).__name__}")
        self._error = error
        self._title_label.setText(error.title)
        self._render_causes(error.causes)
        self._render_actions(error.actions)
        self._log_btn.setVisible(True)
        self._log_btn.setToolTip(
            "查看完整日志" if error.log_tail else "暂无更多日志，可查看运行日志面板"
        )
        self.setVisible(True)

    # ----------------------------------------------------------------
    # 构建
    # ----------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self._title_label = QLabel()
        self._title_label.setObjectName("error_title")
        self._title_label.setWordWrap(True)
        root.addWidget(self._title_label)

        self._cause_header = QLabel("可能的原因")
        self._cause_header.setObjectName("muted_label")
        root.addWidget(self._cause_header)

        self._causes_layout = QVBoxLayout()
        self._causes_layout.setContentsMargins(0, 0, 0, 0)
        self._causes_layout.setSpacing(2)
        root.addLayout(self._causes_layout)

        self._action_header = QLabel("建议操作")
        self._action_header.setObjectName("muted_label")
        root.addWidget(self._action_header)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        actions_row.addLayout(self._actions_layout, 1)

        self._log_btn = QPushButton("查看完整日志")
        self._log_btn.setObjectName("error_log_btn")
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.clicked.connect(self.log_requested.emit)
        actions_row.addWidget(self._log_btn, 0)
        root.addLayout(actions_row)

    # ----------------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------------

    def _render_causes(self, causes):
        _clear_layout(self._causes_layout)
        self._cause_header.setVisible(bool(causes))
        for cause in causes:
            label = QLabel(f"•  {cause}")
            label.setObjectName("hint_info")  # 复用主题里的 hint 次要文本样式
            label.setWordWrap(True)
            self._causes_layout.addWidget(label)

    def _render_actions(self, actions):
        _clear_layout(self._actions_layout)
        self._action_buttons = []
        self._action_header.setVisible(bool(actions))
        for action in actions:
            btn = QPushButton(action)
            btn.setObjectName("error_action_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda _checked=False, text=action: self.action_requested.emit(text)
            )
            self._actions_layout.addWidget(btn)
            self._action_buttons.append(btn)
        self._actions_layout.addStretch(1)


def _clear_layout(layout):
    """移除布局内全部控件 (延迟销毁，避免跨测试悬挂对象)。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
