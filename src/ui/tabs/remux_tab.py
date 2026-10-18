# -*- coding: utf-8 -*-
"""封装转换标签页 —— 支持自动检测音轨/字幕轨道。"""

import os

from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QWidget,
)
from PyQt6.QtCore import Qt

from ..base_tab import BaseTab, set_label_kind, ACTION_BTN_WIDTH
from ..track_row import TrackRow
from ..args_builder import ArgsNamespace
from ...presets import REMUX_PRESETS
from ...media_probe import probe_detailed, LANGUAGE_NAMES
from ...capabilities.container import check_remux


def _format_duration_short(seconds: float) -> str:
    if seconds <= 0:
        return ""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _lang_display(code: str) -> str:
    if not code:
        return ""
    name = LANGUAGE_NAMES.get(code, "")
    return f"[{code}] {name}" if name else f"[{code}]"


class RemuxTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("封装转换", parent)

        # ---- 输入 ----
        io = self.add_group("输入/输出设置")
        self.remux_input_edit = self.add_multi_file_chooser(
            io, "输入文件 (可多选)",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm *.ts *.mxf);;所有文件 (*.*)",
            "选择要转换的文件 (可批量选择多个)",
        )

        # ---- 轨道检测面板 ----
        self._audio_checks = []
        self._sub_checks = []
        self._build_track_panel()

        # ---- 输出格式 ----
        fmt = self.add_group(
            "输出格式",
            "选择封装预设，或选择「自定义」并在下方填写目标后缀名。",
        )
        self.remux_preset_combo = self.add_combo(
            fmt, "封装预设",
            list(REMUX_PRESETS.keys()), "MP4",
        )
        self.add_hint(
            fmt,
            "MP4: 最广泛兼容  |  MKV: 多音轨多字幕  |  MOV: Apple 生态\n"
            "TS: 广播传输流  |  WEBM: 网页播放  |  MXF: 专业后期",
            "info",
        )
        self.remux_format_custom_edit = self.add_text_input(
            fmt, "自定义后缀名", "",
            "当上方预设选择 '自定义' 时，在此输入扩展名 (如 wmv, ogg)",
        )
        self.remux_output_edit = self.add_dir_chooser(
            fmt, "输出目录 (可选)",
            "批量模式: 选择输出目录。单文件留空则在原位置生成",
        )
        self.remux_overwrite_cb = self.add_checkbox(
            fmt, "覆盖原文件", False,
            "⚠️ 危险: 转换后删除原文件，仅保留新文件",
        )
        self.add_hint(
            fmt,
            "不重新编码，速度极快。某些编码不兼容某些容器。",
            "tip",
        )

        # 兼容性警告标签
        self._compat_warn_label = QLabel("")
        self._compat_warn_label.setWordWrap(True)
        self._compat_warn_label.setVisible(False)
        self._compat_warn_label.setObjectName("hint_warning")
        self._main_layout.addWidget(self._compat_warn_label)

        self.add_stretch()

        # ---- 信号 ----
        self.remux_input_edit.textChanged.connect(self._on_input_changed)
        self.remux_preset_combo.currentTextChanged.connect(self._on_preset_changed)

        self._on_preset_changed(self.remux_preset_combo.currentText())

    # ================================================================
    # 轨道检测面板
    # ================================================================

    def _build_track_panel(self):
        self._track_group = QGroupBox("轨道选择 (自动检测)")
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._track_group.setLayout(outer)

        self._track_status = QLabel("请选择输入文件以自动检测轨道信息")
        self._track_status.setWordWrap(True)
        set_label_kind(self._track_status, "muted")
        outer.addWidget(self._track_status)

        self._audio_container = QWidget()
        self._audio_layout = QVBoxLayout(self._audio_container)
        self._audio_layout.setContentsMargins(0, 0, 0, 0)
        self._audio_layout.setSpacing(3)
        self._audio_container.setVisible(False)
        outer.addWidget(self._audio_container)

        self._sub_container = QWidget()
        self._sub_layout = QVBoxLayout(self._sub_container)
        self._sub_layout.setContentsMargins(0, 0, 0, 0)
        self._sub_layout.setSpacing(3)
        self._sub_container.setVisible(False)
        outer.addWidget(self._sub_container)

        self._no_track_hint = QLabel()
        self._no_track_hint.setWordWrap(True)
        self._no_track_hint.setObjectName("muted_label")
        self._no_track_hint.setVisible(False)
        outer.addWidget(self._no_track_hint)

        btn_row = QHBoxLayout()
        self._probe_btn = QPushButton("重新检测")
        self._probe_btn.setFixedWidth(ACTION_BTN_WIDTH)
        self._probe_btn.setVisible(False)
        self._probe_btn.clicked.connect(self._do_probe)
        btn_row.addWidget(self._probe_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        self._main_layout.addWidget(self._track_group)

    def _clear_container(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_preset_changed(self, preset_name):
        is_custom = preset_name == "自定义"
        self.remux_format_custom_edit.setEnabled(is_custom)
        if not is_custom:
            self.remux_format_custom_edit.clear()
        self._check_compat()

    def _on_input_changed(self):
        self._do_probe()

    def _do_probe(self):
        paths = self.get_multi_paths(self.remux_input_edit)
        if not paths:
            self._reset_track_panel()
            return

        first = paths[0]
        if not os.path.isfile(first):
            self._track_status.setText(f"文件不存在: {os.path.basename(first)}")
            set_label_kind(self._track_status, "error")
            self._audio_container.setVisible(False)
            self._sub_container.setVisible(False)
            self._no_track_hint.setVisible(False)
            self._probe_btn.setVisible(True)
            return

        info = probe_detailed(first)
        if info and info.errors:
            self._track_status.setText(f"检测失败: {info.errors[0]}")
            set_label_kind(self._track_status, "error")
            self._audio_container.setVisible(False)
            self._sub_container.setVisible(False)
            self._no_track_hint.setVisible(False)
            self._probe_btn.setVisible(True)
            return

        if not info:
            self._reset_track_panel()
            return

        self._last_probe_info = info
        self._populate_tracks(info, len(paths) > 1)
        self._check_compat()

    def _reset_track_panel(self):
        self._last_probe_info = None
        self._clear_container(self._audio_layout)
        self._clear_container(self._sub_layout)
        self._audio_checks.clear()
        self._sub_checks.clear()
        self._audio_container.setVisible(False)
        self._sub_container.setVisible(False)
        self._no_track_hint.setVisible(False)
        self._probe_btn.setVisible(False)
        self._track_status.setText("请选择输入文件以自动检测轨道信息")
        set_label_kind(self._track_status, "muted")

    def _populate_tracks(self, info, is_batch):
        self._clear_container(self._audio_layout)
        self._clear_container(self._sub_layout)
        self._audio_checks.clear()
        self._sub_checks.clear()

        # 文件摘要
        parts = [info.filename]
        if info.video_streams:
            vs = info.video_streams[0]
            if vs.width and vs.height:
                parts.append(f"{vs.width}x{vs.height}")
        dur = _format_duration_short(info.duration_sec)
        if dur:
            parts.append(dur)
        summary = "  |  ".join(parts)
        if is_batch:
            summary += "\n(批量模式 — 显示第一个文件的轨道信息，其余文件沿用相同选择)"
        self._track_status.setText(summary)
        set_label_kind(self._track_status, "strong")

        has_tracks = False

        # 音频轨道
        if info.audio_streams:
            has_tracks = True
            header = QLabel("音频轨道")
            header.setObjectName("accent_label")
            self._audio_layout.addWidget(header)

            for stream in info.audio_streams:
                title, detail = self._stream_row_text(stream, "audio")
                row = TrackRow(title, detail, checked=True)
                self._audio_layout.addWidget(row)
                self._audio_checks.append((row, stream.index))

            self._audio_container.setVisible(True)
        else:
            self._audio_container.setVisible(False)

        # 字幕轨道
        if info.subtitle_streams:
            has_tracks = True
            header = QLabel("字幕轨道")
            header.setObjectName("accent_label")
            self._sub_layout.addWidget(header)

            for stream in info.subtitle_streams:
                title, detail = self._stream_row_text(stream, "subtitle")
                row = TrackRow(title, detail, checked=True)
                self._sub_layout.addWidget(row)
                self._sub_checks.append((row, stream.index))

            self._sub_container.setVisible(True)
        else:
            self._sub_container.setVisible(False)

        if not has_tracks:
            self._no_track_hint.setText("此文件未检测到音频或字幕轨道。")
            self._no_track_hint.setVisible(True)
        else:
            self._no_track_hint.setText("取消勾选不需要保留的轨道")
            set_label_kind(self._no_track_hint, "muted")
            self._no_track_hint.setVisible(True)

        self._probe_btn.setVisible(True)

    @staticmethod
    def _stream_row_text(stream, stream_type):
        """把轨道拆成 (主标题, 次要信息) 供卡片式轨道行显示。"""
        codec = stream.codec_name or "未知编码"
        title = f"#{stream.index}  {codec}"
        full = RemuxTab._build_stream_label(stream, stream_type)
        detail = full.split("  ·  ", 1)[1] if "  ·  " in full else ""
        return title, detail

    @staticmethod
    def _build_stream_label(stream, stream_type):
        parts = [f"#{stream.index}  {stream.codec_name}"]
        if stream_type == "audio":
            if stream.channels:
                ch = f"{stream.channels}ch"
                if stream.channel_layout:
                    ch += f" ({stream.channel_layout})"
                parts.append(ch)
            if stream.sample_rate:
                parts.append(f"{stream.sample_rate}Hz")
            if stream.bitrate_kbps:
                parts.append(f"{stream.bitrate_kbps}kbps")
        lang = _lang_display(stream.language)
        if lang:
            parts.append(lang)
        if stream.title:
            parts.append(stream.title)
        return "  ·  ".join(parts)

    # ================================================================
    # 容器兼容性检测
    # ================================================================

    def _check_compat(self):
        """用容器能力矩阵检查源文件编码与目标容器，显示原因与建议。

        探测结果来自 ``_do_probe``（选择文件时同步探测首个文件）；
        兼容、未知容器或没有探测结果时隐藏提示标签。
        """
        info = getattr(self, "_last_probe_info", None)

        preset = self.remux_preset_combo.currentText()
        preset_info = REMUX_PRESETS.get(preset, {})
        ext = preset_info.get("extension", "")
        if preset == "自定义":
            custom = self.remux_format_custom_edit.text().strip()
            ext = ("." + custom) if custom and not custom.startswith(".") else custom

        if info is None or not ext:
            self._compat_warn_label.setVisible(False)
            return

        result = check_remux(info, ext)
        if result.ok:
            self._compat_warn_label.setVisible(False)
            return

        lines = ["⚠ 兼容性警告:"]
        lines.extend(f"  • {reason}" for reason in result.reasons)
        if result.suggestions:
            lines.append("建议:")
            lines.extend(f"  • {suggestion}" for suggestion in result.suggestions)
        self._compat_warn_label.setText("\n".join(lines))
        self._compat_warn_label.setVisible(True)

    # ================================================================
    # build_args
    # ================================================================

    def build_args(self):
        audio_key, audio_custom = self._resolve_track_selection(
            self._audio_checks, "全部保留", "不保留音轨"
        )
        sub_key, sub_custom = self._resolve_track_selection(
            self._sub_checks, "全部保留", "不保留字幕"
        )

        return ArgsNamespace(
            command=self.command_name,
            remux_input=self.get_multi_paths(self.remux_input_edit),
            remux_preset=self.remux_preset_combo.currentText(),
            remux_format_custom=self.remux_format_custom_edit.text(),
            remux_output=self.remux_output_edit.text(),
            remux_overwrite=self.remux_overwrite_cb.isChecked(),
            remux_audio_tracks=audio_key,
            remux_audio_tracks_custom=audio_custom,
            remux_subtitle_tracks=sub_key,
            remux_subtitle_tracks_custom=sub_custom,
        )

    @staticmethod
    def _resolve_track_selection(checks, all_key, none_key):
        """将复选框状态转换为 executor 兼容的 (key, custom_string)。"""
        if not checks:
            return all_key, ""

        checked = [idx for cb, idx in checks if cb.isChecked()]
        total = len(checks)

        if len(checked) == total:
            return all_key, ""
        if len(checked) == 0:
            return none_key, ""
        return "自定义选择 (填写编号)", ",".join(str(i) for i in checked)
