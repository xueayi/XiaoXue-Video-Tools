# -*- coding: utf-8 -*-
"""输入媒体卡 —— 拖拽/选择输入视频，并以卡片形式展示探测到的媒体信息。

探测本身仍由页面 (EncodeTab._do_probe) 在 UI 线程调用 ``probe_detailed`` 完成，
本模块只负责渲染 ``DetailedMediaInfo``，不发起任何阻塞调用。

拖拽输入框复用 ``base_tab.FileDropLineEdit``：页面通过 ``form`` 属性把它插入
卡片内部（``BaseTab.add_file_chooser``），因此拖拽/浏览/替换行为与其它页面一致。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout, QGroupBox, QLabel, QVBoxLayout,
)

from .base_tab import repolish, set_label_kind
from .widgets import make_form_layout

# 卡片展示的 8 个字段: (字段键, 中文标签)。顺序即卡片内展示顺序。
INFO_FIELDS = (
    ("filename", "文件名"),
    ("resolution", "分辨率"),
    ("codec", "编码"),
    ("fps", "帧率"),
    ("duration", "时长"),
    ("size", "大小"),
    ("audio_tracks", "音轨数"),
    ("subtitle_tracks", "字幕数"),
)

EMPTY_VALUE = "—"
IDLE_HINT = "拖入视频文件，或点击「浏览」选择"
SUCCESS_PREFIX = "已探测"
ERROR_PREFIX = "探测失败"

# 卡片标题
TITLE = "输入媒体"

# 信息网格每行展示的字段数量
_FIELDS_PER_ROW = 4


def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为可读大小 (与媒体信息页口径一致)。"""
    if size_bytes <= 0:
        return "未知"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_duration(seconds: float) -> str:
    """秒数 -> HH:MM:SS / MM:SS；无效值返回空字符串。"""
    if not seconds or seconds <= 0:
        return ""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_fps(fps: float) -> str:
    """帧率 -> "23.976 fps"；无效值返回空字符串。"""
    if not fps or fps <= 0:
        return ""
    return f"{fps:g} fps"


def _codec_text(video_stream) -> str:
    """视频 codec 文案，如 "h264 (High)"。"""
    if video_stream is None or not video_stream.codec_name:
        return ""
    codec = video_stream.codec_name
    profile = getattr(video_stream, "profile", "")
    if profile:
        return f"{codec} ({profile})"
    return codec


class InputMediaCard(QGroupBox):
    """输入媒体卡：文件选择行 + 8 项媒体信息 + 探测状态。"""

    def __init__(self, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("input_media_card")
        # 最近一次渲染的 DetailedMediaInfo (测试/调试可读)
        self.last_info = None

        outer = QVBoxLayout(self)
        # QGroupBox 的 QSS padding 已提供内边距，布局不再叠加
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # 文件选择行插入点：页面复用 BaseTab.add_file_chooser 填充
        self.form = make_form_layout()
        outer.addLayout(self.form)

        # 媒体信息网格 (2 行 x 4 列)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.field_labels = {}
        for position, (key, title) in enumerate(INFO_FIELDS):
            name_label = QLabel(title)
            name_label.setObjectName("muted_label")
            value_label = QLabel(EMPTY_VALUE)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            row, column = divmod(position, _FIELDS_PER_ROW)
            grid.addWidget(name_label, row, column * 2)
            grid.addWidget(value_label, row, column * 2 + 1)
            self.field_labels[key] = value_label
        for column in range(_FIELDS_PER_ROW):
            grid.setColumnStretch(column * 2 + 1, 1)
        outer.addLayout(grid)

        self.status_label = QLabel(IDLE_HINT)
        self.status_label.setWordWrap(True)
        set_label_kind(self.status_label, "muted")
        outer.addWidget(self.status_label)

    # ----------------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------------

    def render(self, info) -> None:
        """用 ``DetailedMediaInfo`` 渲染 8 个字段。"""
        if info is None:
            self.reset()
            return
        errors = getattr(info, "errors", None)
        if errors:
            self.set_error(errors[0])
            return

        self.last_info = info
        video = info.video_streams[0] if info.video_streams else None
        values = {
            "filename": info.filename,
            "resolution": (
                f"{video.width}x{video.height}"
                if video is not None and video.width and video.height
                else ""
            ),
            "codec": _codec_text(video),
            "fps": format_fps(video.fps) if video is not None else "",
            "duration": format_duration(info.duration_sec),
            "size": format_file_size(info.file_size_bytes),
            "audio_tracks": str(len(info.audio_streams)),
            "subtitle_tracks": str(len(info.subtitle_streams)),
        }
        for key, label in self.field_labels.items():
            label.setText(values.get(key) or EMPTY_VALUE)
            set_label_kind(label, "strong")

        status_parts = [f"{SUCCESS_PREFIX}：{info.filename}"]
        duration = format_duration(info.duration_sec)
        if duration:
            status_parts.append(duration)
        self._set_status("  ·  ".join(status_parts), "strong", error=False)

    def set_error(self, message: str) -> None:
        """探测失败：清空字段并显示错误态。"""
        self.last_info = None
        for label in self.field_labels.values():
            label.setText(EMPTY_VALUE)
            set_label_kind(label, "muted")
        message = (message or "").strip()
        text = f"{ERROR_PREFIX}：{message}" if message else ERROR_PREFIX
        self._set_status(text, "error", error=True)

    def reset(self) -> None:
        """无输入 / 无探测结果：恢复占位态。"""
        self.last_info = None
        for label in self.field_labels.values():
            label.setText(EMPTY_VALUE)
            set_label_kind(label, "muted")
        self._set_status(IDLE_HINT, "muted", error=False)

    # ----------------------------------------------------------------
    # 内部
    # ----------------------------------------------------------------

    def _set_status(self, text: str, kind: str, error: bool) -> None:
        self.status_label.setText(text)
        set_label_kind(self.status_label, kind)
        self.setProperty("probeError", error)
        repolish(self)

    # ----------------------------------------------------------------
    # 测试辅助
    # ----------------------------------------------------------------

    def field_text(self, key: str) -> str:
        return self.field_labels[key].text()

    def field_values(self) -> dict:
        return {key: label.text() for key, label in self.field_labels.items()}
