# -*- coding: utf-8 -*-
"""执行摘要卡 —— 页尾实时预览即将执行的编码参数。

**单一真值**：本组件必须调用 ``encode_params.resolve_encoder_params`` 计算参数，
与 executor (``executors.video_executor.execute_encode``) 使用完全同源的解析逻辑，
不允许在本文件另拼一套参数或复述控制台文本。

页面在任意相关控件变化时调用 :meth:`ExecutionSummaryCard.update_from_args`，
用 ``build_args()`` 的结果刷新摘要。
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel

from ..encode_params import EncodeMode, resolve_encoder_params
from ..presets import AUDIO_ENCODERS, ENCODERS, QUALITY_PRESETS, RATE_CONTROL_MODES
from ..utils import generate_output_path
from .base_tab import set_label_kind

TITLE = "执行摘要"
PLACEHOLDER = "选择输入视频后显示执行摘要"
FOOTER_HINT = "与执行器同源 (resolve_encoder_params) 实时计算；参数调整后立即更新。"

# 摘要行: (键, 中文标签)
SUMMARY_ROWS = (
    ("video", "视频"),
    ("audio", "音频"),
    ("subtitle", "字幕"),
    ("format", "输出格式"),
    ("output", "输出路径"),
)


def format_video_summary(params) -> str:
    """视频行：编码器 / CRF 或码率 / 速度 / 2-Pass / 分辨率 / 帧率。"""
    parts = [params.encoder]
    if params.bitrate:
        parts.append(f"码率 {params.bitrate}")
    elif params.crf is not None:
        parts.append(f"CRF {params.crf}")
    mode = params.get_encode_mode()
    if mode == EncodeMode.TWO_PASS:
        parts.append("2-Pass VBR")
    elif params.rc_mode and params.rc_mode != "crf":
        parts.append(f"码率控制 {params.rc_mode}")
    if params.speed_preset:
        parts.append(f"速度 {params.speed_preset}")
    if params.resolution:
        parts.append(f"分辨率 {params.resolution}")
    if params.fps:
        parts.append(f"帧率 {params.fps}")
    return " · ".join(str(part) for part in parts)


def format_audio_summary(params) -> str:
    """音频行：copy 或 编码器 + 码率（使用解析后的真实值，不做展示名替换）。"""
    if params.audio_encoder == "copy":
        return "复制（不重新编码）"
    return f"{params.audio_encoder} · {params.audio_bitrate}"


_SUBTITLE_KEEP_LABELS = {
    "all": "保留全部字幕流",
    "none": "不保留字幕流",
    "0": "仅保留第 1 条字幕 (#0)",
}


def format_subtitle_summary(params) -> str:
    """字幕行：烧录 / 保留（两个独立概念）。"""
    parts = []
    if params.subtitle_path:
        parts.append(f"烧录 {os.path.basename(params.subtitle_path)}")
        if params.compat_mode:
            parts.append("兼容渲染 (AviSynth+VSFilter)")
    else:
        parts.append("不烧录")
    if params.subtitle_tracks == "custom":
        custom = (params.subtitle_tracks_custom or "").strip() or "未填写编号"
        parts.append(f"保留自定义字幕轨道 ({custom})")
    else:
        parts.append(
            _SUBTITLE_KEEP_LABELS.get(
                params.subtitle_tracks, f"保留字幕 {params.subtitle_tracks}"
            )
        )
    return " · ".join(parts)


def format_output_format_summary(params) -> str:
    """输出格式行：以解析后的实际输出路径后缀为准。"""
    ext = os.path.splitext(params.output_path)[1]
    if not ext:
        return "未知（输出路径无扩展名）"
    return f"{ext.lstrip('.').upper()} ({ext})"


def format_output_path_summary(params, auto_generated: bool) -> str:
    """输出路径行：实际输出路径 + 自动生成标注。"""
    if auto_generated:
        return f"{params.output_path}（自动生成）"
    return params.output_path


class ExecutionSummaryCard(QGroupBox):
    """执行摘要卡（页尾）。"""

    def __init__(self, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("execution_summary")
        self.last_params = None
        self.auto_generated = False

        form = QFormLayout(self)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self._rows = {}
        for key, title in SUMMARY_ROWS:
            value = QLabel(PLACEHOLDER)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            set_label_kind(value, "muted")
            form.addRow(title, value)
            self._rows[key] = value

        self.footer_label = QLabel(FOOTER_HINT)
        self.footer_label.setObjectName("group_desc")
        self.footer_label.setWordWrap(True)
        form.addRow("", self.footer_label)

    # ----------------------------------------------------------------
    # 刷新
    # ----------------------------------------------------------------

    def update_from_args(self, args):
        """用与 executor 同源的参数解析刷新摘要。

        Args:
            args: ``EncodeTab.build_args()`` 返回的 ArgsNamespace。

        Returns:
            本次渲染使用的 ``EncodeParams``；未选择输入时返回 None (占位态)。
        """
        input_path = (getattr(args, "input", "") or "").strip()
        if not input_path:
            self.clear()
            return None

        params = resolve_encoder_params(
            args=args,
            quality_presets=QUALITY_PRESETS,
            encoders=ENCODERS,
            audio_encoders=AUDIO_ENCODERS,
            rate_control_modes=RATE_CONTROL_MODES,
            generate_output_path_func=generate_output_path,
        )
        auto_generated = not (getattr(args, "output", "") or "").strip()

        self.last_params = params
        self.auto_generated = auto_generated
        texts = {
            "video": format_video_summary(params),
            "audio": format_audio_summary(params),
            "subtitle": format_subtitle_summary(params),
            "format": format_output_format_summary(params),
            "output": format_output_path_summary(params, auto_generated),
        }
        for key, text in texts.items():
            self._rows[key].setText(text)
            set_label_kind(self._rows[key], "strong")
        self._rows["output"].setToolTip(params.output_path)
        return params

    def clear(self) -> None:
        """未选择输入：恢复占位文案。"""
        self.last_params = None
        self.auto_generated = False
        for value in self._rows.values():
            value.setText(PLACEHOLDER)
            set_label_kind(value, "muted")
        self._rows["output"].setToolTip("")

    # ----------------------------------------------------------------
    # 查询辅助
    # ----------------------------------------------------------------

    def row_text(self, key: str) -> str:
        return self._rows[key].text()

    def all_text(self) -> str:
        return "\n".join(
            f"{title}: {self._rows[key].text()}" for key, title in SUMMARY_ROWS
        )
