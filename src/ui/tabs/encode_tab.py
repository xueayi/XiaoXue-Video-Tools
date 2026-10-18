# -*- coding: utf-8 -*-
"""视频压制标签页。

信息架构：
    A. 常规选项     —— 输入视频 / 字幕文件 / 输出路径 (高频输入) + 8 项媒体信息
    B. 字幕策略     —— 外挂字幕处理方式 (内嵌烧录 / 内封软字幕 / 不处理)
                       + 兼容模式 + 保留源字幕流
    C. 视频输出策略 —— 5 张目标卡映射现有质量预设 + "更多预设" + 输出格式/分辨率
    D. 音频输出策略 —— 音频编码/码率 + 音轨选择 (逐轨勾选挂在分组内)
    E. 压制后分发   —— 成品自动复制/移动 (文档未提, 保留功能)
    F. 片段截取     —— 当前视频内多段裁剪拼接
    G. 高级设置     —— 默认折叠: encoder/RC/CRF/码率/fps/流编号/extra_args/debug
    H. 执行摘要     —— 页尾卡片, 与 executor 同源 (resolve_encoder_params) 实时预览

硬约束：所有控件属性名、``build_args()`` 键集与 command 保持不变。
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox, QSizePolicy, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QWidget, QToolButton,
)

from ..base_tab import BaseTab, set_label_kind, ACTION_BTN_WIDTH
from ..args_builder import ArgsNamespace
from ..execution_summary import ExecutionSummaryCard
from ..input_media_card import InputMediaCard
from ..output_plan_card import OutputPlanCard
from ..track_row import TrackRow
from ..clip_editor import ClipEditor
from ..media_probe_worker import start_media_probe
from ...capabilities.encoder import (
    build_encoder_capabilities,
    default_speed_preset,
    encoder_capability,
    encoder_definition,
)
from ...capabilities.container import (
    EMBEDDED_SUBTITLE_FORMATS,
    embedded_subtitle_note,
    supports_embedded_subtitles,
)
from ...presets import (
    ENCODERS, QUALITY_PRESETS, ALL_QUALITY_PRESETS, APPLE_QUALITY_PRESETS,
    APPLE_H264_PRESET, APPLE_HEVC_PRESET, CPU_PRESETS, NVENC_PRESETS,
    AUDIO_ENCODERS, AUDIO_BITRATES, RATE_CONTROL_MODES,
    VIDEO_BITRATES, AUDIO_TRACK_OPTIONS, SUBTITLE_TRACK_OPTIONS,
    SUBTITLE_MODES, POST_TRANSFER_MODES, ENCODE_OUTPUT_FORMATS,
)
from ...media_probe import probe_detailed, LANGUAGE_NAMES
from ...platform.capabilities import platform_capabilities
from ..subtitle_font_panel import SubtitleFontPanel

# 默认预设：保持与改造前一致（均衡 H.264 / CRF18）
DEFAULT_PRESET = "【均衡画质】x264 常用导出 (CRF18)"

# 能力探测判定不可用时的 CPU 回退编码器
CPU_FALLBACK_ENCODER = "H.264 (CPU - libx264)"

#: 编码器不可用 / 预设依赖的编码器不可用时的悬停提示
ENCODER_UNAVAILABLE_HINT = "未检测到该硬件编码器"
PRESET_ENCODER_UNAVAILABLE_HINT = "依赖的硬件编码器不可用"

#: 「兼容模式 (字幕)」的说明 (AviSynth 不可用时整行隐藏并清空提示, M4.4)
COMPAT_MODE_TOOLTIP = (
    "开启：使用 AviSynth+VSFilter 渲染字幕。\n"
    "关闭 (默认)：使用 FFmpeg 内置 libass 渲染。"
)

# 预设模式下会被预设覆盖、因而禁用的控件提示
PRESET_LOCK_HINT = (
    "预设模式：分辨率 / 帧率 / 音频编码参数由所选预设决定，手动设置不会生效。\n"
    "如需自由调整，请在「视频输出策略」中选择「自定义 (Custom)」。"
)

#: 「复制视频流」预设的说明
COPY_MODE_HINT = (
    "复制视频流：画面不重新编码（画质无损、速度最快），因此不能烧录字幕、"
    "也不能调整画质/分辨率；可更换封装、音轨与内封字幕流。"
)


class EncodeTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("视频压制", parent)

        # ---- M3.2 编码器能力状态 (探测完成前保持全量可选) ----
        self._caps = None
        self.encoder_capabilities = build_encoder_capabilities(None)

        # ================================================================
        # A. 常规选项（高频：输入视频 / 字幕文件 / 输出路径）
        # ================================================================
        self.input_media_card = InputMediaCard()
        self._main_layout.addWidget(self.input_media_card)
        self.input_edit = self.add_file_chooser(
            self.input_media_card.form, "输入视频",
            "视频文件 (*.mp4 *.mov *.avi *.mkv);;所有文件 (*.*)",
            "选择要处理的视频文件（支持拖拽，或点击「浏览」替换）",
        )
        self.subtitle_edit = self.add_file_chooser(
            self.input_media_card.form, "字幕文件 (可选)",
            "字幕文件 (*.srt *.ass *.ssa);;所有文件 (*.*)",
            "选择外挂字幕文件；处理方式（内嵌烧录 / 内封软字幕）在下方「字幕策略」中选择",
        )
        self.output_edit = self.add_file_saver(
            self.input_media_card.form, "输出路径 (可选)",
            "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*.*)",
            "留空则自动生成: 原文件名_编码器简称.格式\n"
            "如 我的视频.mp4 + libx264 -> 我的视频_x264.mp4",
        )

        # ================================================================
        # B. 字幕策略（紧随输入，常用配置）
        # ================================================================
        subtitles = self.add_group(
            "字幕策略",
            "外挂字幕文件在「常规选项」中选择；这里决定内嵌还是内封，以及是否保留源字幕流。",
        )
        self.subtitle_group = subtitles.parentWidget()
        # 兼容模式行所在分组 (AviSynth 门禁按平台能力收起该行)
        self.common_group = self.subtitle_group

        self.subtitle_mode_combo = self.add_combo(
            subtitles, "字幕处理方式",
            list(SUBTITLE_MODES.keys()), "内嵌（烧录进画面）",
            "内嵌：把外挂字幕烧进画面（硬字幕，播放器无法关闭）\n"
            "内封：把外挂字幕作为独立软字幕流写入容器（播放器可开关，仅 MKV / MOV）\n"
            "不处理：忽略所选外挂字幕文件",
        )
        self.compat_mode_cb = self.add_checkbox(
            subtitles, "兼容模式 (字幕)", False, COMPAT_MODE_TOOLTIP,
        )

        self.font_panel = SubtitleFontPanel(self)
        subtitles.addRow(self.font_panel)

        self._add_section_label(subtitles, "源视频字幕流（软字幕）")
        self.subtitle_tracks_combo = self.add_combo(
            subtitles, "保留字幕流",
            list(SUBTITLE_TRACK_OPTIONS.keys()), "不保留字幕",
            "保留源视频容器里已有的字幕轨（播放器可开关/切换）",
        )
        self._subtitle_default_tooltip = self.subtitle_tracks_combo.toolTip()
        self._sub_track_box = QWidget()
        self._sub_track_box.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._sub_track_host = QVBoxLayout(self._sub_track_box)
        self._sub_track_host.setContentsMargins(0, 0, 0, 0)
        self._sub_track_host.setSpacing(6)
        subtitles.addRow(self._sub_track_box)
        self.add_hint(
            subtitles,
            embedded_subtitle_note(),
            "info",
        )

        # ================================================================
        # C. 视频输出策略（方案卡 + 视频编码基础参数）
        # ================================================================
        self.output_plan_card = OutputPlanCard(current=DEFAULT_PRESET)
        self._main_layout.addWidget(self.output_plan_card)
        # 复用卡内的预设下拉作为唯一 preset_combo
        self.preset_combo = self.output_plan_card.preset_combo
        # 方案卡下方追加视频基础参数 (输出格式 / 分辨率 ...)
        common = self.output_plan_card.param_form()
        self.video_group = self.output_plan_card

        # 画质：只读镜像 crf_spin，真实控件在高级设置
        quality_row = QHBoxLayout()
        quality_row.setSpacing(8)
        self.quality_mirror_label = QLabel()
        set_label_kind(self.quality_mirror_label, "strong")
        self._quality_hint = QLabel("只读镜像；可在「高级设置」中调整")
        set_label_kind(self._quality_hint, "muted")
        quality_row.addWidget(self.quality_mirror_label)
        quality_row.addWidget(self._quality_hint)
        quality_row.addStretch(1)
        common.addRow("画质", quality_row)

        self.output_format_combo = self.add_combo(
            common, "输出格式",
            list(ENCODE_OUTPUT_FORMATS.keys()), "MP4",
            "选择输出容器格式（内封外挂字幕需 MKV / MOV）",
        )
        self.output_format_custom_edit = self.add_text_input(
            common, "自定义格式", "",
            "填写扩展名，如 ts、webm",
        )
        self.resolution_edit = self.add_text_input(
            common, "分辨率", "",
            "如 1920x1080，留空保持原分辨率 (预设模式下由预设决定)",
        )

        self._preset_lock_hint = self.add_hint(
            common, PRESET_LOCK_HINT, "info"
        )

        # ================================================================
        # D. 音频输出策略
        # ================================================================
        audio = self.add_group(
            "音频输出策略",
            "音频编码、码率，以及要保留的音轨。",
        )
        self.audio_group = audio.parentWidget()
        self.audio_encoder_combo = self.add_combo(
            audio, "音频编码器",
            list(AUDIO_ENCODERS.keys()), "复制 (不重新编码)",
        )
        self.audio_bitrate_combo = self.add_combo(
            audio, "音频码率", AUDIO_BITRATES, "192k",
        )
        # 音轨选择：静态下拉 + 探测到的逐轨勾选 (始终可见)
        self.audio_tracks_combo = self.add_combo(
            audio, "保留音轨",
            list(AUDIO_TRACK_OPTIONS.keys()), "仅保留第 1 条 (#0)",
            "快捷选择保留的音轨；检测到具体轨道后可在下方逐轨勾选",
        )
        self._audio_track_box = QWidget()
        self._audio_track_box.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._audio_track_host = QVBoxLayout(self._audio_track_box)
        self._audio_track_host.setContentsMargins(0, 0, 0, 0)
        self._audio_track_host.setSpacing(6)
        audio.addRow(self._audio_track_box)
        self.add_hint(
            audio,
            "注意: MP4 格式不支持多音轨，需保留多轨请输出 MKV 格式",
            "warning",
        )

        # ================================================================
        # E. 轨道检测（音轨挂到音频策略，字幕轨挂到字幕策略）
        # ================================================================
        self._audio_checks: list = []
        self._sub_checks: list = []
        self._last_probe_info = None
        self._probe_generation = 0
        #: 防止「下拉 <-> 逐轨勾选」互相同步时递归
        self._syncing_tracks = False
        self._build_track_panel()

        # ================================================================
        # F. 压制后分发（文档未提但保留，位置固定在输出方案之后）
        # ================================================================
        transfer = self.add_group(
            "压制后分发",
            "压制完成后自动将成品复制或移动到指定目录。",
        )
        self.transfer_group = transfer.parentWidget()
        self.post_transfer_mode_combo = self.add_combo(
            transfer, "分发模式",
            list(POST_TRANSFER_MODES.keys()), "不分发",
        )
        self.post_transfer_dir_edit = self.add_dir_chooser(
            transfer, "目标目录",
            "选择成品分发的目标目录 (支持已挂载的网络位置)",
        )

        # ================================================================
        # F. 视频片段截取
        # ================================================================
        self.clip_editor = ClipEditor()
        self._main_layout.addWidget(self.clip_editor)

        # ================================================================
        # G. 高级设置（默认折叠）
        # ================================================================
        advanced = self.add_collapsible_group("高级设置")
        self.advanced_layout = advanced
        self.advanced_content = advanced.parentWidget()
        self.advanced_header = self._container.findChild(QToolButton, "fold_header")
        self.add_hint(
            advanced,
            "以下编码/质量参数仅在「输出方案」选择「自定义 (Custom)」时生效；\n"
            "预设模式下由预设决定 (画质镜像见「常用设置」)。",
            "info",
        )

        self.encoder_combo = self.add_combo(
            advanced, "视频编码器",
            [k for k, v in ENCODERS.items() if v != "copy"],
            "H.264 (CPU - libx264)",
            "选择视频编码器 (CPU/NVIDIA/Intel/AMD)",
        )
        self.speed_preset_combo = self.add_combo(
            advanced, "编码速度", CPU_PRESETS, "medium",
            "编码速度预设 (越慢画质越好)",
        )
        self.nvenc_preset_combo = self.add_combo(
            advanced, "N卡速度档位",
            ["使用预设默认"] + NVENC_PRESETS, "使用预设默认",
            "NVENC 速度档位 (p1最快/p7最慢)",
        )
        self.rate_control_combo = self.add_combo(
            advanced, "码率控制模式",
            list(RATE_CONTROL_MODES.keys()), "CRF/CQ (恒定质量)",
        )
        self.crf_spin = self.add_spinbox(
            advanced, "质量值 (CRF/CQ)", 0, 51, 18,
            "0-51，越低画质越好，推荐 18-23",
        )
        self.video_bitrate_combo = self.add_combo(
            advanced, "目标码率", VIDEO_BITRATES, "",
            "CRF/CQ 模式留空；VBR/CBR/2-Pass 模式设置码率",
        )
        self.fps_spin = self.add_spinbox(
            advanced, "帧率", 0, 240, 0,
            "如 30、60，填 0 保持原帧率 (预设模式下由预设决定)",
        )
        self.add_hint(
            advanced,
            "CRF/CQ: 恒定质量 (推荐)，由上方质量值控制\n"
            "VBR: 可变码率，设置平均码率  |  CBR: 恒定码率，适合推流\n"
            "2-Pass: 两遍编码，精确控制目标码率",
            "info",
        )

        self._add_section_label(advanced, "流选择（自定义编号）")
        self.audio_tracks_custom_edit = self.add_text_input(
            advanced, "音轨编号 (自定义)", "",
            "填写要保留的音轨编号，多条用逗号分隔，如: 0,1",
        )
        self.subtitle_tracks_custom_edit = self.add_text_input(
            advanced, "字幕编号 (自定义)", "",
            "填写要保留的字幕编号，如: 0,2",
        )

        self._add_section_label(advanced, "其它")
        self.extra_args_edit = self.add_text_input(
            advanced, "额外 FFmpeg 参数", "",
            "多个参数用空格分隔",
        )
        self.add_hint(
            advanced,
            "填写示例: -ss 00:01:00 -t 30 -tune animation\n"
            "参数会追加到 FFmpeg 命令末尾，多个参数用空格分隔",
            "info",
        )
        self.debug_mode_cb = self.add_checkbox(
            advanced, "Debug 模式", False,
            "勾选后仅打印 FFmpeg 命令，不执行实际编码",
        )

        # ================================================================
        # H. 执行摘要（页尾卡片）
        # ================================================================
        self.summary_card = ExecutionSummaryCard()
        self._main_layout.addWidget(self.summary_card)
        self.add_stretch()

        # ================================================================
        # 控件联动
        # ================================================================
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.rate_control_combo.currentTextChanged.connect(self._on_rate_control_changed)
        self.encoder_combo.currentTextChanged.connect(self._on_encoder_changed)
        self.output_format_combo.currentTextChanged.connect(self._on_output_format_changed)
        self.audio_tracks_combo.currentTextChanged.connect(self._on_audio_tracks_changed)
        self.subtitle_tracks_combo.currentTextChanged.connect(self._on_subtitle_tracks_changed)
        self.subtitle_mode_combo.currentTextChanged.connect(self._on_subtitle_mode_changed)
        self.post_transfer_mode_combo.currentTextChanged.connect(self._on_transfer_changed)
        self.input_edit.textChanged.connect(self._on_input_changed)
        # 内封字幕流可用性依赖输出扩展名（自定义/与输入相同也要跟着刷新）
        self.output_format_custom_edit.textChanged.connect(
            lambda _text: self._sync_subtitle_stream_availability())
        self.input_edit.textChanged.connect(
            lambda _text: self._sync_subtitle_stream_availability())
        self.crf_spin.valueChanged.connect(self._update_quality_mirror)

        # 执行摘要实时刷新：复用全部联动信号 + 输出路径等文本输入
        self._connect_summary_signals()
        self.font_panel.changed.connect(self._refresh_summary)
        self.font_panel.request_current_mark.connect(lambda: self.font_panel.set_source_time(
            self.clip_editor.preview.mark_us() if self.clip_editor.preview else None))
        for signal in (self.input_edit.textChanged, self.subtitle_edit.textChanged,
                       self.subtitle_mode_combo.currentTextChanged, self.encoder_combo.currentTextChanged,
                       self.resolution_edit.textChanged, self.preset_combo.currentTextChanged):
            signal.connect(self._sync_font_panel)
        self._sync_font_panel()
        self.clip_editor.changed.connect(self._refresh_summary)

        self._on_preset_changed(self.preset_combo.currentText())
        self._on_output_format_changed(self.output_format_combo.currentText())
        self._on_audio_tracks_changed(self.audio_tracks_combo.currentText())
        self._on_subtitle_tracks_changed(self.subtitle_tracks_combo.currentText())
        self._on_subtitle_mode_changed(self.subtitle_mode_combo.currentText())
        self._on_transfer_changed(self.post_transfer_mode_combo.currentText())
        self._update_quality_mirror()
        self._refresh_summary()

        # M4.4: AviSynth 不可用的平台隐藏「兼容模式 (字幕)」整行
        self._sync_avisynth_availability()
        if hasattr(self, 'font_panel'):
            self._sync_font_panel()

    # ----------------------------------------------------------------
    # 平台能力门禁 (M4.4)
    # ----------------------------------------------------------------

    def _compat_mode_layout(self):
        """「兼容模式 (字幕)」所在的 QFormLayout; 找不到返回 None。"""
        group = getattr(self, "common_group", None)
        try:
            return group.layout() if group is not None else None
        except RuntimeError:  # pragma: no cover - 底层 C++ 对象已释放
            return None

    def _sync_avisynth_availability(self, state=None):
        """按 ``platform_capabilities().avisynth_available`` 显示/隐藏兼容模式行。

        AviSynth + VSFilter 只在 Windows 且依赖 DLL 齐全时可用: 不可用时把
        复选框与表单标签整行收起, 并清空其 tooltip (普通 libass 字幕烧录
        路径保持不变); 可用时行为与以前完全一致。
        平台差异一律由平台能力快照给出, 这里不直接判断运行平台。
        """
        if state is None:
            state = platform_capabilities()
        available = bool(getattr(state, "avisynth_available", False))

        layout = self._compat_mode_layout()
        if layout is not None and hasattr(layout, "setRowVisible"):
            try:
                layout.setRowVisible(self.compat_mode_cb, available)
            except (TypeError, RuntimeError):  # pragma: no cover - Qt 版本兜底
                layout = None
        if layout is None:
            self.compat_mode_cb.setVisible(available)
            label = self._compat_mode_label()
            if label is not None:
                label.setVisible(available)

        # 隐藏时一并收起说明 (tooltip); 恢复可用时还原
        self.compat_mode_cb.setToolTip(COMPAT_MODE_TOOLTIP if available else "")
        return available

    def _compat_mode_label(self):
        """「兼容模式 (字幕)」的表单标签 (QFormLayout.labelForField)。"""
        layout = self._compat_mode_layout()
        if layout is None or not hasattr(layout, "labelForField"):
            return None
        return layout.labelForField(self.compat_mode_cb)

    # ----------------------------------------------------------------
    # 常用设置辅助
    # ----------------------------------------------------------------

    @staticmethod
    def _add_section_label(layout, text):
        """在表单中插入小节标题 (accent 色)。"""
        label = QLabel(text)
        label.setObjectName("accent_label")
        layout.addRow("", label)
        return label

    def _is_custom_mode(self) -> bool:
        text = self.preset_combo.currentText()
        return "自定义" in text or "Custom" in text

    def _update_quality_mirror(self, *_args):
        """画质只读镜像：始终反映 crf_spin 当前值。"""
        preset = ALL_QUALITY_PRESETS.get(self.preset_combo.currentText())
        if preset and preset.get("encoder") == "copy":
            self.quality_mirror_label.setText("视频流直接复制（不重新编码）")
            return
        value = self.crf_spin.value()
        if self._is_custom_mode():
            mode = self.rate_control_combo.currentText().split(" (")[0]
            self.quality_mirror_label.setText(f"{mode} · 质量值 {value}")
        else:
            self.quality_mirror_label.setText(f"质量值 {value}（由预设决定）")

    # ----------------------------------------------------------------
    # 控件联动
    # ----------------------------------------------------------------

    def _on_preset_changed(self, preset_name):
        """当质量预设切换时，自动填充关联参数并控制可编辑状态。"""
        is_custom = self._is_custom_mode()

        self.encoder_combo.setEnabled(is_custom)
        self.speed_preset_combo.setEnabled(is_custom)
        self.nvenc_preset_combo.setEnabled(is_custom)
        self.rate_control_combo.setEnabled(is_custom)
        self.crf_spin.setEnabled(is_custom)
        self.video_bitrate_combo.setEnabled(is_custom)
        self._apply_preset_lock(is_custom)

        preset = ALL_QUALITY_PRESETS.get(preset_name)
        if not preset or preset.get("encoder") is None:
            if is_custom:
                self._on_rate_control_changed(self.rate_control_combo.currentText())
                self._on_encoder_changed(self.encoder_combo.currentText())
            self._apply_copy_mode(False)
            self._update_quality_mirror()
            return

        self._apply_copy_mode(preset.get("encoder") == "copy")

        definition = encoder_definition(preset["encoder"])
        if definition is not None:
            self.encoder_combo.setCurrentText(definition.display)

        if preset.get("crf") is not None:
            self.crf_spin.setValue(preset["crf"])
        elif preset.get("cq") is not None:
            self.crf_spin.setValue(preset["cq"])

        if preset.get("preset"):
            if preset["preset"] in ("p1", "p2", "p3", "p4", "p5", "p6", "p7"):
                self.nvenc_preset_combo.setCurrentText(preset["preset"])
            else:
                self.speed_preset_combo.setCurrentText(preset["preset"])

        if preset.get("audio_encoder"):
            for name, value in AUDIO_ENCODERS.items():
                if value == preset["audio_encoder"]:
                    self.audio_encoder_combo.setCurrentText(name)
                    break

        if preset.get("audio_bitrate"):
            self.audio_bitrate_combo.setCurrentText(preset["audio_bitrate"])

        self._update_quality_mirror()

    def _apply_copy_mode(self, copy_mode: bool):
        """「复制视频流」模式: 不能烧录字幕, 但仍可内封外挂字幕。

        画面不重新编码时 ``subtitles`` 滤镜不可用, 因此已选字幕不能继续内嵌:
        自动切到「内封」(容器不支持时由参数校验给出明确提示), 字幕文件保留,
        不再像旧版那样直接清空。
        """
        if (copy_mode and self.subtitle_edit.text().strip()
                and SUBTITLE_MODES.get(self.subtitle_mode_combo.currentText()) == "burn"
                and supports_embedded_subtitles(self.current_output_extension())):
            self.subtitle_mode_combo.setCurrentText("内封（转为软字幕流）")
        # 兼容模式的可用性只取决于处理方式, 统一交回 _on_subtitle_mode_changed
        self._on_subtitle_mode_changed(self.subtitle_mode_combo.currentText())
        self._preset_lock_hint.setText(
            COPY_MODE_HINT if copy_mode else PRESET_LOCK_HINT)

    def _apply_preset_lock(self, is_custom: bool):
        """预设模式下禁用会被预设覆盖的控件，并显示说明，避免输入被静默忽略。"""
        locked = not is_custom
        for widget in (
            self.resolution_edit,
            self.fps_spin,
            self.audio_encoder_combo,
            self.audio_bitrate_combo,
        ):
            widget.setEnabled(not locked)
        self._preset_lock_hint.setVisible(locked)

    def _on_rate_control_changed(self, mode_name):
        """当码率控制模式切换时，调整质量值/码率控件的可用状态。"""
        is_crf = "CRF" in mode_name or "CQ" in mode_name
        self.crf_spin.setEnabled(is_crf)
        self.video_bitrate_combo.setEnabled(not is_crf)
        self._update_quality_mirror()

    def _on_encoder_changed(self, encoder_name):
        """编码器切换: 联动 RC 选项 / 速度档下拉 (仅自定义模式可用)。"""
        is_custom = self._is_custom_mode()
        capability = self._capability_for_display(encoder_name)
        is_nvenc = capability is not None and "nvenc" in capability.name

        is_apple = capability is not None and capability.quality_flag == "-q:v"
        previous_apple = self.crf_spin.maximum() == 100
        self.crf_spin.setRange(0, 100 if is_apple else 51)
        if previous_apple != is_apple:
            self.crf_spin.setValue(65 if is_apple else 18)
        self.crf_spin.setToolTip(
            "Apple 质量值 0–100，越高画质越好" if is_apple
            else "CRF/CQ 质量值 0–51，越低画质越好")

        # 速度档: NVENC 用 p1..p7 档位下拉; QSV/AMF/CPU 用各自速度下拉
        if capability is not None and not is_nvenc:
            self._rebuild_speed_options(capability)
        self.nvenc_preset_combo.setEnabled(is_custom and is_nvenc)
        self.speed_preset_combo.setEnabled(is_custom and not is_nvenc)

        # RC 选项: CPU 4 项, 硬件 3 项 (去掉 2-Pass); 当前项不支持时回退 CRF/CQ
        self._rebuild_rate_control_options(capability)
        if is_custom:
            self._on_rate_control_changed(self.rate_control_combo.currentText())

    # ----------------------------------------------------------------
    # M3.2 编码器能力联动
    # ----------------------------------------------------------------

    def _capability_for_display(self, display):
        """按下拉展示名取能力快照 (未探测时 available=None)。"""
        for capability in self.encoder_capabilities:
            if capability.display == display:
                return capability
        resolved = encoder_capability(display, self._caps)
        if resolved is not None:
            return resolved
        capabilities = build_encoder_capabilities(self._caps)
        return capabilities[0]

    @staticmethod
    def _set_combo_items(combo, items, preferred):
        """重建下拉项并尽量保留当前选择 (阻塞信号, 避免中间态触发联动)。"""
        items = list(items)
        blocked = combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItems(items)
            target = preferred if preferred in items else (
                items[0] if items else "")
            if target:
                combo.setCurrentText(target)
        finally:
            combo.blockSignals(blocked)
        return combo.currentText()

    def _rebuild_rate_control_options(self, capability):
        """按编码器能力重建码率控制模式下拉 (硬件隐藏 2-Pass)。"""
        supported = set(capability.rc_modes) if capability is not None else {
            "crf", "vbr", "cbr", "2pass"}
        choices = [
            display for display, mode in RATE_CONTROL_MODES.items()
            if mode in supported
        ]
        current = self.rate_control_combo.currentText()
        selected = self._set_combo_items(
            self.rate_control_combo, choices, current or "CRF/CQ (恒定质量)")
        if selected != current and self._is_custom_mode():
            self._on_rate_control_changed(selected)
        self.rate_control_combo.setToolTip(
            "" if len(choices) == len(RATE_CONTROL_MODES)
            else "该编码器不支持 2-Pass，已隐藏该选项")

    def _rebuild_speed_options(self, capability):
        """按编码器能力重建速度档下拉 (AMF=speed/balanced/quality)。"""
        values = list(capability.speed_values)
        current = self.speed_preset_combo.currentText()
        preferred = (current if current in values
                     else default_speed_preset(capability))
        self._set_combo_items(self.speed_preset_combo, values, preferred)
        self.speed_preset_combo.setToolTip(
            f"编码速度 (默认 {default_speed_preset(capability)})")

    def _preset_enabled(self, preset_name) -> bool:
        """预设依赖的编码器是否可用 (未知/CPU/复制视为可用)。"""
        preset = ALL_QUALITY_PRESETS.get(preset_name)
        if not preset:
            return True
        encoder = preset.get("encoder")
        if not encoder or encoder == "copy":
            return True
        capability = encoder_capability(encoder, self._caps)
        return capability is not None and capability.available is not False

    def _encoder_item_enabled(self, display) -> bool:
        """编码器下拉中该展示名是否可用 (保持与视图置灰状态一致)。"""
        model = self.encoder_combo.model()
        for index in range(self.encoder_combo.count()):
            if self.encoder_combo.itemText(index) != display:
                continue
            item = model.item(index) if model is not None else None
            return True if item is None else item.isEnabled()
        return False

    def _nvenc_state(self, caps):
        """NVENC 硬件卡三态: None=待检测 / True=可用 / False=不可用。"""
        if caps is None or getattr(caps, "probe_error", None):
            return None
        nvenc_caps = [
            cap for cap in self.encoder_capabilities if "nvenc" in cap.name
        ]
        if not nvenc_caps:
            return False
        return any(cap.available is True for cap in nvenc_caps)

    # ----------------------------------------------------------------
    # 能力探测结果应用 (main_window 探测完成后调用)
    # ----------------------------------------------------------------

    def apply_capabilities(self, caps=None):
        """按 FFmpeg 能力探测结果联动编码器 / 预设 / 硬件卡。

        Args:
            caps: FfmpegCaps 快照; None 表示未知/探测失败 —— 保持全量可选,
                硬件卡显示「待能力检测」。
        """
        self._caps = caps
        self.encoder_capabilities = build_encoder_capabilities(caps)
        by_display = {cap.display: cap for cap in self.encoder_capabilities}

        current_encoder = self.encoder_combo.currentText()
        self._set_combo_items(self.encoder_combo, by_display, current_encoder)
        presets = dict(QUALITY_PRESETS)
        for name, preset in APPLE_QUALITY_PRESETS.items():
            if any(cap.name == preset["encoder"] for cap in self.encoder_capabilities):
                presets[name] = preset
        current_preset = self.preset_combo.currentText()
        self.output_plan_card.presets = presets
        self._set_combo_items(self.preset_combo, presets, current_preset)

        # 0) M4.4: 平台能力 (AviSynth) 决定兼容模式行是否展示
        #    (主窗口在推送前已刷新平台能力快照)
        self._sync_avisynth_availability()
        if hasattr(self, 'font_panel'):
            self._sync_font_panel()

        # 1) 编码器下拉: 探测为不可用的项置灰 + 悬停提示
        model = self.encoder_combo.model()
        for index in range(self.encoder_combo.count()):
            display = self.encoder_combo.itemText(index)
            capability = by_display.get(display)
            unavailable = (capability is not None
                           and capability.available is False)
            item = model.item(index) if model is not None else None
            if item is not None:
                item.setEnabled(not unavailable)
                item.setData(
                    ENCODER_UNAVAILABLE_HINT if unavailable else None,
                    Qt.ItemDataRole.ToolTipRole,
                )

        # 2) 当前编码器不可用 -> 回退 CPU 编码器 (CPU 也不可用时取首个可用项)
        current = by_display.get(self.encoder_combo.currentText())
        if current is not None and current.available is False:
            fallback = CPU_FALLBACK_ENCODER
            if not self._encoder_item_enabled(fallback):
                fallback = next(
                    (cap.display for cap in self.encoder_capabilities
                     if cap.available is not False),
                    CPU_FALLBACK_ENCODER,
                )
            self.encoder_combo.setCurrentText(fallback)

        # 3) 预设下拉: 依赖不可用编码器的预设同样置灰 + 提示
        preset_model = self.preset_combo.model()
        for index in range(self.preset_combo.count()):
            preset_name = self.preset_combo.itemText(index)
            unavailable = not self._preset_enabled(preset_name)
            item = (preset_model.item(index)
                    if preset_model is not None else None)
            if item is not None:
                item.setEnabled(not unavailable)
                item.setData(
                    PRESET_ENCODER_UNAVAILABLE_HINT if unavailable else None,
                    Qt.ItemDataRole.ToolTipRole,
                )
        # 当前预设不可用 -> 回退默认预设 (默认也需可用) 或首个可用预设
        if not self._preset_enabled(self.preset_combo.currentText()):
            fallbacks = [DEFAULT_PRESET] + [
                name for name in QUALITY_PRESETS if name != DEFAULT_PRESET
            ]
            for preset_name in fallbacks:
                if self._preset_enabled(preset_name):
                    self.preset_combo.setCurrentText(preset_name)
                    break

        # 4) 硬件目标卡三态
        apple_names = {cap.name for cap in self.encoder_capabilities
                       if "videotoolbox" in cap.name}
        apple_preset = (APPLE_H264_PRESET if "h264_videotoolbox" in apple_names
                        else APPLE_HEVC_PRESET if "hevc_videotoolbox" in apple_names else None)
        self.output_plan_card.set_hardware_available(
            True if apple_preset else self._nvenc_state(caps))
        self.output_plan_card.set_hardware_preset(
            apple_preset or "【速度优先】NVIDIA 显卡加速",
            "Apple VideoToolbox" if apple_preset else "NVENC")

        # 5) 重新应用当前编码器联动 + 刷新摘要
        self._on_encoder_changed(self.encoder_combo.currentText())
        self._refresh_summary()

    def _on_output_format_changed(self, text):
        self.output_format_custom_edit.setEnabled("自定义" in text)
        self._sync_subtitle_stream_availability()

    def current_output_extension(self) -> str:
        """当前输出格式对应的扩展名（含自定义 / 与输入相同）。"""
        text = self.output_format_combo.currentText()
        extension = ENCODE_OUTPUT_FORMATS.get(text, "")
        if extension is None:  # 自定义
            extension = self.output_format_custom_edit.text().strip()
        if not extension and text == "与输入相同":
            extension = os.path.splitext(self.input_edit.text())[1]
        return extension or ""

    def _sync_subtitle_stream_availability(self):
        """只有 MKV / MOV 输出才允许保留内封字幕流；其它格式禁用并清空。"""
        supported = supports_embedded_subtitles(self.current_output_extension())

        self.subtitle_tracks_combo.setEnabled(supported)
        if supported:
            self.subtitle_tracks_combo.setToolTip(self._subtitle_default_tooltip)
        else:
            self.subtitle_tracks_combo.setToolTip(
                "当前输出格式不支持内封字幕流，如需保留请将输出格式改为 "
                + " / ".join(ext.upper() for ext in EMBEDDED_SUBTITLE_FORMATS))
            if self.subtitle_tracks_combo.currentText() != "不保留字幕":
                self.subtitle_tracks_combo.setCurrentText("不保留字幕")

        self.subtitle_tracks_custom_edit.setEnabled(
            supported and "自定义" in self.subtitle_tracks_combo.currentText())

        # 内封外挂字幕同样依赖容器能力: 不支持时禁用该选项并回退到内嵌
        self._sync_embed_option_availability(supported)

        # 自动检测的轨道面板：字幕勾选与容器同步禁用/清空
        for checkbox, _index in self._sub_checks:
            if supported:
                checkbox.setEnabled(True)
            else:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
        track_container = getattr(self, "_track_sub_container", None)
        if track_container is not None:
            track_container.setEnabled(supported)

        self._refresh_summary()

    def _sync_embed_option_availability(self, supported: bool) -> None:
        """输出容器不支持字幕流时禁用「内封」选项, 并把当前值回退到内嵌。"""
        combo = self.subtitle_mode_combo
        model = combo.model()
        for row in range(combo.count()):
            if SUBTITLE_MODES.get(combo.itemText(row)) != "embed":
                continue
            item = model.item(row) if model is not None and hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(supported)
                item.setToolTip(
                    "" if supported else
                    "当前输出格式不支持内封字幕流，请改为 "
                    + " / ".join(ext.upper() for ext in EMBEDDED_SUBTITLE_FORMATS))
            if not supported and combo.currentIndex() == row:
                combo.setCurrentText("内嵌（烧录进画面）")

    def _on_subtitle_mode_changed(self, text):
        """字幕处理方式变化: 兼容模式仅在内嵌烧录时可用。"""
        mode = SUBTITLE_MODES.get(text, "burn")
        burn = mode == "burn"
        self.compat_mode_cb.setEnabled(burn)
        if not burn and self.compat_mode_cb.isChecked():
            self.compat_mode_cb.setChecked(False)
        if hasattr(self, "summary_card"):
            self._refresh_summary()

    def _on_audio_tracks_changed(self, text):
        self.audio_tracks_custom_edit.setEnabled("自定义" in text)
        self._apply_track_combo_to_checks("audio", text)

    def _on_subtitle_tracks_changed(self, text):
        supported = self.subtitle_tracks_combo.isEnabled()
        self.subtitle_tracks_custom_edit.setEnabled(
            supported and "自定义" in text)
        if supported:
            self._apply_track_combo_to_checks("subtitle", text)

    def _on_transfer_changed(self, mode):
        self.post_transfer_dir_edit.setEnabled("不分发" not in mode)

    # ----------------------------------------------------------------
    # 执行摘要联动
    # ----------------------------------------------------------------

    def _connect_summary_signals(self):
        """把全部会影响执行参数的控件信号接到摘要刷新。"""
        signals = (
            self.input_edit.textChanged,
            self.output_edit.textChanged,
            self.subtitle_edit.textChanged,
            self.compat_mode_cb.toggled,
            self.preset_combo.currentTextChanged,
            self.encoder_combo.currentTextChanged,
            self.speed_preset_combo.currentTextChanged,
            self.nvenc_preset_combo.currentTextChanged,
            self.rate_control_combo.currentTextChanged,
            self.crf_spin.valueChanged,
            self.video_bitrate_combo.currentTextChanged,
            self.output_format_combo.currentTextChanged,
            self.output_format_custom_edit.textChanged,
            self.resolution_edit.textChanged,
            self.fps_spin.valueChanged,
            self.audio_encoder_combo.currentTextChanged,
            self.audio_bitrate_combo.currentTextChanged,
            self.audio_tracks_combo.currentTextChanged,
            self.audio_tracks_custom_edit.textChanged,
            self.subtitle_tracks_combo.currentTextChanged,
            self.subtitle_tracks_custom_edit.textChanged,
            self.extra_args_edit.textChanged,
            self.debug_mode_cb.toggled,
        )
        for signal in signals:
            signal.connect(self._refresh_summary)

    def _refresh_summary(self, *_args):
        """重新计算并渲染执行摘要（未选输入时显示占位）。"""
        summary = getattr(self, "summary_card", None)
        if summary is None:
            return
        try:
            summary.update_from_args(self.build_args())
        except ValueError as exc:
            summary.clear()
            summary.footer_label.setText(str(exc))

    # ================================================================
    # 轨道自动检测
    # ================================================================

    def _build_track_panel(self):
        """把轨道检测控件挂到音频/字幕策略分组 (静态下拉始终保留)。"""
        # 音频策略: 检测状态 + 逐轨勾选 + 重新检测
        self._track_status = QLabel("选择输入视频后自动检测音频/字幕轨道")
        self._track_status.setWordWrap(True)
        set_label_kind(self._track_status, "muted")
        self._audio_track_host.addWidget(self._track_status)

        self._track_audio_container = QWidget()
        self._track_audio_layout = QVBoxLayout(self._track_audio_container)
        self._track_audio_layout.setContentsMargins(0, 0, 0, 0)
        self._track_audio_layout.setSpacing(6)
        self._track_audio_container.setVisible(False)
        self._audio_track_host.addWidget(self._track_audio_container)

        self._track_no_hint = QLabel()
        self._track_no_hint.setWordWrap(True)
        self._track_no_hint.setObjectName("muted_label")
        self._track_no_hint.setVisible(False)
        self._audio_track_host.addWidget(self._track_no_hint)

        btn_row = QHBoxLayout()
        self._probe_btn = QPushButton("重新检测")
        self._probe_btn.setFixedWidth(ACTION_BTN_WIDTH)
        self._probe_btn.setVisible(False)
        self._probe_btn.clicked.connect(self._do_probe)
        btn_row.addWidget(self._probe_btn)
        btn_row.addStretch()
        self._audio_track_host.addLayout(btn_row)

        # 字幕策略: 逐轨勾选
        self._track_sub_container = QWidget()
        self._track_sub_layout = QVBoxLayout(self._track_sub_container)
        self._track_sub_layout.setContentsMargins(0, 0, 0, 0)
        self._track_sub_layout.setSpacing(6)
        self._track_sub_container.setVisible(False)
        self._sub_track_host.addWidget(self._track_sub_container)

    def _on_input_changed(self):
        self.clip_editor.set_input(self.input_edit.text())
        self._do_probe()

    def _show_probe_error(self, message: str):
        """探测错误态：轨道面板与输入媒体卡同步显示错误。"""
        self._track_status.setText(message)
        set_label_kind(self._track_status, "error")
        self._track_audio_container.setVisible(False)
        self._track_sub_container.setVisible(False)
        self._track_no_hint.setVisible(False)
        self._probe_btn.setVisible(True)
        self._last_probe_info = None
        self._update_static_track_visibility(True)
        self.input_media_card.set_error(message)

    def _do_probe(self):
        path = self.input_edit.text().strip()
        self._probe_generation += 1
        self._reset_track_panel()
        if not path:
            self._reset_track_panel()
            self.input_media_card.reset()
            self._refresh_summary()
            return

        if not os.path.isfile(path):
            self._show_probe_error(f"文件不存在: {os.path.basename(path)}")
            self._refresh_summary()
            return

        self._track_status.setText("正在后台检测媒体信息…")
        start_media_probe(path, self._probe_generation, self._finish_probe, probe_detailed)

    def _finish_probe(self, result):
        path, generation, info = result
        if generation != self._probe_generation or path != self.input_edit.text().strip():
            return
        if info and info.errors:
            self._show_probe_error(f"检测失败: {info.errors[0]}")
            self._refresh_summary()
            return

        if not info:
            self._reset_track_panel()
            self.input_media_card.reset()
            self._refresh_summary()
            return

        self._last_probe_info = info
        self._populate_tracks(info)
        self.input_media_card.render(info)
        self.clip_editor.set_duration_us(round(info.clip_duration_sec * 1_000_000), authoritative=True)
        self._refresh_summary()

    def _reset_track_panel(self):
        self._last_probe_info = None
        self._clear_layout(self._track_audio_layout)
        self._clear_layout(self._track_sub_layout)
        self._audio_checks.clear()
        self._sub_checks.clear()
        self._track_audio_container.setVisible(False)
        self._track_sub_container.setVisible(False)
        self._track_no_hint.setVisible(False)
        self._probe_btn.setVisible(False)
        self._track_status.setText("选择输入视频后自动检测音频/字幕轨道")
        set_label_kind(self._track_status, "muted")
        self._update_static_track_visibility(True)
        self._sync_subtitle_stream_availability()

    def _update_static_track_visibility(self, show: bool):
        """静态轨道下拉始终可见（检测到具体轨道时在下方追加逐轨勾选）。

        修复：选择输入视频后「保留字幕流 / 保留音轨」不再消失，始终可选。
        """
        for widget in (
            self.audio_tracks_combo, self.audio_tracks_custom_edit,
            self.subtitle_tracks_combo, self.subtitle_tracks_custom_edit,
        ):
            widget.setVisible(True)
        self.audio_tracks_custom_edit.setEnabled(
            "自定义" in self.audio_tracks_combo.currentText())
        self.subtitle_tracks_custom_edit.setEnabled(
            self.subtitle_tracks_combo.isEnabled()
            and "自定义" in self.subtitle_tracks_combo.currentText())

    def _populate_tracks(self, info):
        self._clear_layout(self._track_audio_layout)
        self._clear_layout(self._track_sub_layout)
        self._audio_checks.clear()
        self._sub_checks.clear()

        # 文件摘要
        parts = [info.filename]
        if info.video_streams:
            vs = info.video_streams[0]
            if vs.width and vs.height:
                parts.append(f"{vs.width}x{vs.height}")
        if info.duration_sec > 0:
            dur = self._fmt_dur(info.duration_sec)
            if dur:
                parts.append(dur)
        self._track_status.setText("  |  ".join(parts))
        set_label_kind(self._track_status, "strong")

        has_tracks = False

        if info.audio_streams:
            has_tracks = True
            header = QLabel("音频轨道")
            header.setObjectName("accent_label")
            self._track_audio_layout.addWidget(header)
            for stream in info.audio_streams:
                row = TrackRow(
                    *self._stream_row_text(stream, "audio"), checked=False)
                row.toggled.connect(self._refresh_summary)
                row.toggled.connect(
                    lambda _checked: self._on_track_checks_changed("audio"))
                self._track_audio_layout.addWidget(row)
                self._audio_checks.append((row, stream.index))
            self._track_audio_container.setVisible(True)
        else:
            self._track_audio_container.setVisible(False)

        if info.subtitle_streams:
            has_tracks = True
            header = QLabel("字幕轨道")
            header.setObjectName("accent_label")
            self._track_sub_layout.addWidget(header)
            for stream in info.subtitle_streams:
                row = TrackRow(
                    *self._stream_row_text(stream, "subtitle"), checked=False)
                row.toggled.connect(self._refresh_summary)
                row.toggled.connect(
                    lambda _checked: self._on_track_checks_changed("subtitle"))
                self._track_sub_layout.addWidget(row)
                self._sub_checks.append((row, stream.index))
            self._track_sub_container.setVisible(True)
        else:
            self._track_sub_container.setVisible(False)

        if not has_tracks:
            self._track_no_hint.setText("此文件未检测到音频或字幕轨道。")
            self._track_no_hint.setVisible(True)
        else:
            self._track_no_hint.setText(
                "勾选需要保留的轨道；也可用上方下拉快速选择。"
            )
            set_label_kind(self._track_no_hint, "muted")
            self._track_no_hint.setVisible(True)

        self._probe_btn.setVisible(True)
        self._update_static_track_visibility(True)
        # 逐轨勾选跟随上方下拉的当前选择 (默认: 音轨第 1 条 / 字幕不保留)
        self._apply_track_combo_to_checks(
            "audio", self.audio_tracks_combo.currentText())
        self._apply_track_combo_to_checks(
            "subtitle", self.subtitle_tracks_combo.currentText())
        self._sync_subtitle_stream_availability()

    def _stream_row_text(self, stream, stream_type):
        """把轨道拆成 (主标题, 次要信息) 供卡片式轨道行显示。"""
        codec = stream.codec_name or "未知编码"
        title = f"#{stream.index}  {codec}"
        full = self._build_stream_label(stream, stream_type)
        detail = full.split("  ·  ", 1)[1] if "  ·  " in full else ""
        return title, detail

    def _on_track_checks_changed(self, kind: str):
        """逐轨勾选变化 -> 反写上方快捷下拉 (避免两套状态不一致)。"""
        if self._syncing_tracks:
            return
        checks = self._audio_checks if kind == "audio" else self._sub_checks
        if not checks:
            return
        combo = (self.audio_tracks_combo if kind == "audio"
                 else self.subtitle_tracks_combo)
        custom_edit = (self.audio_tracks_custom_edit if kind == "audio"
                       else self.subtitle_tracks_custom_edit)
        checked = [idx for row, idx in checks if row.isChecked()]
        none_key = "不保留音轨" if kind == "audio" else "不保留字幕"
        self._syncing_tracks = True
        try:
            if len(checked) == len(checks):
                combo.setCurrentText("全部保留")
            elif checked:
                combo.setCurrentText("自定义选择 (填写编号)")
                custom_edit.setText(",".join(str(idx) for idx in checked))
            else:
                combo.setCurrentText(none_key)
        finally:
            self._syncing_tracks = False
        self._refresh_summary()

    def _apply_track_combo_to_checks(self, kind: str, text: str):
        """快捷下拉 -> 逐轨勾选 (自定义模式保持手动选择)。"""
        if self._syncing_tracks:
            return
        checks = self._audio_checks if kind == "audio" else self._sub_checks
        if not checks:
            return
        none_key = "不保留音轨" if kind == "audio" else "不保留字幕"
        self._syncing_tracks = True
        try:
            if text == "全部保留":
                for row, _index in checks:
                    row.setChecked(True)
            elif text == none_key:
                for row, _index in checks:
                    row.setChecked(False)
            elif text.startswith("仅保留第 1 条"):
                for row, index in checks:
                    row.setChecked(index == 0)
            # 「自定义选择」: 以逐轨勾选/编号框为准, 不覆盖
        finally:
            self._syncing_tracks = False

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
        lang_code = stream.language
        if lang_code:
            name = LANGUAGE_NAMES.get(lang_code, "")
            lang_str = f"[{lang_code}] {name}" if name else f"[{lang_code}]"
            parts.append(lang_str)
        if stream.title:
            parts.append(stream.title)
        return "  ·  ".join(parts)

    @staticmethod
    def _fmt_dur(seconds: float) -> str:
        if seconds <= 0:
            return ""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

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

    # ================================================================
    # build_args
    # ================================================================

    def build_args(self):
        # 轨道选择：优先使用自动检测的复选框，否则用静态下拉
        if self._audio_checks:
            audio_key, audio_custom = self._resolve_track_selection(
                self._audio_checks, "全部保留", "不保留音轨"
            )
        else:
            audio_key = self.audio_tracks_combo.currentText()
            audio_custom = self.audio_tracks_custom_edit.text()

        if self._sub_checks:
            sub_key, sub_custom = self._resolve_track_selection(
                self._sub_checks, "全部保留", "不保留字幕"
            )
        else:
            sub_key = self.subtitle_tracks_combo.currentText()
            sub_custom = self.subtitle_tracks_custom_edit.text()

        # 输出容器不支持内封字幕流时, 强制不保留 (与界面禁用保持一致)
        if not supports_embedded_subtitles(self.current_output_extension()):
            sub_key, sub_custom = "不保留字幕", ""

        result = ArgsNamespace(
            command=self.command_name,
            input=self.input_edit.text(),
            output=self.output_edit.text(),
            subtitle=self.subtitle_edit.text(),
            subtitle_mode=self.subtitle_mode_combo.currentText(),
            compat_mode=self.compat_mode_cb.isChecked(),
            preset=self.preset_combo.currentText(),
            encoder=self.encoder_combo.currentText(),
            speed_preset=self.speed_preset_combo.currentText(),
            nvenc_preset=self.nvenc_preset_combo.currentText(),
            rate_control=self.rate_control_combo.currentText(),
            crf=self.crf_spin.value(),
            video_bitrate=self.video_bitrate_combo.currentText(),
            output_format=self.output_format_combo.currentText(),
            output_format_custom=self.output_format_custom_edit.text(),
            resolution=self.resolution_edit.text(),
            fps=self.fps_spin.value(),
            audio_encoder=self.audio_encoder_combo.currentText(),
            audio_bitrate=self.audio_bitrate_combo.currentText(),
            audio_tracks=audio_key,
            audio_tracks_custom=audio_custom,
            subtitle_tracks=sub_key,
            subtitle_tracks_custom=sub_custom,
            post_transfer_mode=self.post_transfer_mode_combo.currentText(),
            post_transfer_dir=self.post_transfer_dir_edit.text(),
            extra_args=self.extra_args_edit.text(),
            debug_mode=self.debug_mode_cb.isChecked(),
        )
        font_options = self.font_panel.options()
        if font_options.enabled:
            result.subtitle_fonts = font_options
        plan = self.clip_editor.plan()
        if plan is not None:
            result.clip_plan = plan
        return result

    def _sync_font_panel(self, *_):
        state = platform_capabilities()
        is_macos = bool(getattr(state, 'is_macos', False))
        caps = self._caps or getattr(state, 'ffmpeg_caps', None)
        has_filter = caps is not None and 'subtitles' in caps.filters
        extension = os.path.splitext(self.subtitle_edit.text())[1].lower()
        burn = SUBTITLE_MODES.get(self.subtitle_mode_combo.currentText()) == 'burn'
        available = is_macos and has_filter and burn and extension in ('.ass', '.ssa')
        self.font_panel.setVisible(is_macos)
        self.font_panel.set_inputs(self.input_edit.text(), self.subtitle_edit.text())
        self.font_panel.set_available(available, '字体增强需支持 libass 的 FFmpeg，并选择 ASS/SSA 硬字幕烧录')
        params = getattr(self.summary_card, 'last_params', None)
        self.font_panel.set_resolution(params.resolution if params else None)

    def prepare_execution(self):
        self.clip_editor.validate_inputs()
        self.font_panel.require_ready()

    def set_running(self, running):
        self.clip_editor.set_running(running)
        self.font_panel.set_running(running)

    def release(self):
        self._probe_generation += 1
        self.clip_editor.release()
        self.font_panel.release()
