# -*- coding: utf-8 -*-
"""视频压制标签页。

信息架构 (PR-04)：
    A. 输入媒体卡   —— 拖拽/选择输入，展示 8 项媒体信息
    B. 输出方案卡   —— 5 张目标卡映射现有质量预设 + "更多预设" (全部预设)
    C. 常用设置     —— 画质镜像 / 输出格式 / 分辨率 / 输出路径 / 音频 / 字幕
    D. 轨道选择     —— 探测到的音频/字幕轨道勾选 (保留既有能力)
    E. 压制后分发   —— 成品自动复制/移动 (文档未提, 保留功能)
    F. 高级设置     —— 默认折叠: encoder/RC/CRF/码率/fps/流编号/extra_args/debug
    G. 在线文档
    H. 执行摘要     —— 页尾卡片, 与 executor 同源 (resolve_encoder_params) 实时预览

硬约束：所有控件属性名、``build_args()`` 键集与 command 保持不变。
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QWidget, QToolButton,
)

from ..base_tab import BaseTab, set_label_kind, ACTION_BTN_WIDTH
from ..args_builder import ArgsNamespace
from ..execution_summary import ExecutionSummaryCard
from ..input_media_card import InputMediaCard
from ..output_plan_card import OutputPlanCard
from ...capabilities.encoder import (
    build_encoder_capabilities,
    default_speed_preset,
    encoder_capability,
)
from ...presets import (
    ENCODERS, QUALITY_PRESETS, CPU_PRESETS, NVENC_PRESETS,
    AUDIO_ENCODERS, AUDIO_BITRATES, RATE_CONTROL_MODES,
    VIDEO_BITRATES, AUDIO_TRACK_OPTIONS, SUBTITLE_TRACK_OPTIONS,
    POST_TRANSFER_MODES, ENCODE_OUTPUT_FORMATS,
)
from ...media_probe import probe_detailed, LANGUAGE_NAMES

# 默认预设：保持与改造前一致（均衡 H.264 / CRF18）
DEFAULT_PRESET = "【均衡画质】x264 常用导出 (CRF18)"

# 能力探测判定不可用时的 CPU 回退编码器
CPU_FALLBACK_ENCODER = "H.264 (CPU - libx264)"

#: 编码器不可用 / 预设依赖的编码器不可用时的悬停提示
ENCODER_UNAVAILABLE_HINT = "未检测到该硬件编码器"
PRESET_ENCODER_UNAVAILABLE_HINT = "依赖的硬件编码器不可用"

# 预设模式下会被预设覆盖、因而禁用的控件提示
PRESET_LOCK_HINT = (
    "预设模式：分辨率 / 帧率 / 音频编码参数由所选预设决定，手动设置不会生效。\n"
    "如需自由调整，请在「输出方案」中选择「自定义 (Custom)」。"
)


class EncodeTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("视频压制", parent)

        # ---- M3.2 编码器能力状态 (探测完成前保持全量可选) ----
        self._caps = None
        self.encoder_capabilities = build_encoder_capabilities(None)

        # ================================================================
        # A. 输入媒体卡
        # ================================================================
        self.input_media_card = InputMediaCard()
        self._main_layout.addWidget(self.input_media_card)
        self.input_edit = self.add_file_chooser(
            self.input_media_card.form, "输入视频",
            "视频文件 (*.mp4 *.mov *.avi *.mkv);;所有文件 (*.*)",
            "选择要处理的视频文件（支持拖拽，或点击「浏览」替换）",
        )

        # ================================================================
        # B. 输出方案卡（5 张目标卡 + 更多预设）
        # ================================================================
        self.output_plan_card = OutputPlanCard(current=DEFAULT_PRESET)
        self._main_layout.addWidget(self.output_plan_card)
        # 复用卡内的预设下拉作为唯一 preset_combo（全部 7 项保持可选）
        self.preset_combo = self.output_plan_card.preset_combo

        # ================================================================
        # C. 常用设置
        # ================================================================
        common = self.add_group(
            "常用设置",
            "日常导出最常用的参数；其余参数收在页面下方「高级设置」中。",
        )
        self.common_group = common.parentWidget()

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
            list(ENCODE_OUTPUT_FORMATS.keys()), "MP4 (默认)",
            "选择输出容器格式",
        )
        self.output_format_custom_edit = self.add_text_input(
            common, "自定义格式", "",
            "填写扩展名，如 ts、webm",
        )
        self.resolution_edit = self.add_text_input(
            common, "分辨率", "",
            "如 1920x1080，留空保持原分辨率 (预设模式下由预设决定)",
        )
        self.output_edit = self.add_file_saver(
            common, "输出路径 (可选)",
            "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*.*)",
            "留空则自动生成: 原文件名_编码器简称.格式\n"
            "如 我的视频.mp4 + libx264 -> 我的视频_x264.mp4",
        )

        self._preset_lock_hint = self.add_hint(
            common, PRESET_LOCK_HINT, "info"
        )

        # 音频策略
        self._add_section_label(common, "音频策略")
        self.audio_encoder_combo = self.add_combo(
            common, "音频编码器",
            list(AUDIO_ENCODERS.keys()), "复制 (不重新编码)",
        )
        self.audio_bitrate_combo = self.add_combo(
            common, "音频码率", AUDIO_BITRATES, "192k",
        )
        # 音轨选择：静态下拉 (无探测数据时使用)
        self.audio_tracks_combo = self.add_combo(
            common, "保留音轨",
            list(AUDIO_TRACK_OPTIONS.keys()), "仅保留第 1 条 (#0)",
            "快捷选择保留的音轨。注意：MP4 不支持多音轨。",
        )
        self.add_hint(
            common,
            "注意: MP4 格式不支持多音轨，需保留多轨请输出 MKV 格式",
            "warning",
        )

        # 字幕
        self._add_section_label(common, "字幕")
        self.subtitle_edit = self.add_file_chooser(
            common, "字幕文件 (可选)",
            "字幕文件 (*.srt *.ass *.ssa);;所有文件 (*.*)",
            "选择要烧录的字幕文件 (留空则不烧录)",
        )
        self.compat_mode_cb = self.add_checkbox(
            common, "兼容模式 (字幕)", False,
            "开启：使用 AviSynth+VSFilter 渲染字幕。\n"
            "关闭 (默认)：使用 FFmpeg 内置 libass 渲染。",
        )
        self.subtitle_tracks_combo = self.add_combo(
            common, "保留字幕",
            list(SUBTITLE_TRACK_OPTIONS.keys()), "不保留字幕",
            "注意：MP4 不支持 ASS 字幕。",
        )
        self.add_hint(
            common,
            "「字幕烧录」= 硬编码到画面中，不可关闭\n"
            "「保留字幕流」= 保留在容器中可切换的字幕轨\n"
            "两者是不同概念，可同时使用；MP4 不支持 ASS 字幕，"
            "需要时请选择「不保留字幕」或输出 MKV 格式。",
            "info",
        )

        # ================================================================
        # D. 轨道自动检测（既有能力，保留独立分组）
        # ================================================================
        self._audio_checks: list = []
        self._sub_checks: list = []
        self._last_probe_info = None
        self._build_track_panel()

        # ================================================================
        # E. 压制后分发（文档未提但保留，位置固定在常用设置之后）
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
        self.add_hint(
            transfer,
            "将 WebDAV / SMB / 网盘 挂载为本地磁盘后，\n"
            "选择该挂载路径即可实现 压制完成 → 自动上传到 NAS/云端",
            "tip",
        )

        # ================================================================
        # F. 高级设置（默认折叠）
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
        # G. 在线文档
        # ================================================================
        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Video-Encode",
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
        self.post_transfer_mode_combo.currentTextChanged.connect(self._on_transfer_changed)
        self.input_edit.textChanged.connect(self._on_input_changed)
        self.crf_spin.valueChanged.connect(self._update_quality_mirror)

        # 执行摘要实时刷新：复用全部联动信号 + 输出路径等文本输入
        self._connect_summary_signals()

        self._on_preset_changed(self.preset_combo.currentText())
        self._on_output_format_changed(self.output_format_combo.currentText())
        self._on_audio_tracks_changed(self.audio_tracks_combo.currentText())
        self._on_subtitle_tracks_changed(self.subtitle_tracks_combo.currentText())
        self._on_transfer_changed(self.post_transfer_mode_combo.currentText())
        self._update_quality_mirror()
        self._refresh_summary()

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

        preset = QUALITY_PRESETS.get(preset_name)
        if not preset or preset.get("encoder") is None:
            if is_custom:
                self._on_rate_control_changed(self.rate_control_combo.currentText())
                self._on_encoder_changed(self.encoder_combo.currentText())
            self._update_quality_mirror()
            return

        for name, value in ENCODERS.items():
            if value == preset["encoder"]:
                self.encoder_combo.setCurrentText(name)
                break

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
        """预设依赖的编码器是否可用 (未知/CPU 视为可用)。"""
        preset = QUALITY_PRESETS.get(preset_name)
        if not preset:
            return True
        encoder = preset.get("encoder")
        if not encoder:
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
        self.output_plan_card.set_hardware_available(self._nvenc_state(caps))

        # 5) 重新应用当前编码器联动 + 刷新摘要
        self._on_encoder_changed(self.encoder_combo.currentText())
        self._refresh_summary()

    def _on_output_format_changed(self, text):
        self.output_format_custom_edit.setEnabled("自定义" in text)

    def _on_audio_tracks_changed(self, text):
        self.audio_tracks_custom_edit.setEnabled("自定义" in text)

    def _on_subtitle_tracks_changed(self, text):
        self.subtitle_tracks_custom_edit.setEnabled("自定义" in text)

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
        summary.update_from_args(self.build_args())

    # ================================================================
    # 轨道自动检测
    # ================================================================

    def _build_track_panel(self):
        self._track_group = QGroupBox("轨道选择 (自动检测)")
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._track_group.setLayout(outer)

        self._track_status = QLabel("选择输入视频后自动检测音频/字幕轨道")
        self._track_status.setWordWrap(True)
        set_label_kind(self._track_status, "muted")
        outer.addWidget(self._track_status)

        self._track_audio_container = QWidget()
        self._track_audio_layout = QVBoxLayout(self._track_audio_container)
        self._track_audio_layout.setContentsMargins(0, 0, 0, 0)
        self._track_audio_layout.setSpacing(3)
        self._track_audio_container.setVisible(False)
        outer.addWidget(self._track_audio_container)

        self._track_sub_container = QWidget()
        self._track_sub_layout = QVBoxLayout(self._track_sub_container)
        self._track_sub_layout.setContentsMargins(0, 0, 0, 0)
        self._track_sub_layout.setSpacing(3)
        self._track_sub_container.setVisible(False)
        outer.addWidget(self._track_sub_container)

        self._track_no_hint = QLabel()
        self._track_no_hint.setWordWrap(True)
        self._track_no_hint.setObjectName("muted_label")
        self._track_no_hint.setVisible(False)
        outer.addWidget(self._track_no_hint)

        btn_row = QHBoxLayout()
        self._probe_btn = QPushButton("重新检测")
        self._probe_btn.setFixedWidth(ACTION_BTN_WIDTH)
        self._probe_btn.setVisible(False)
        self._probe_btn.clicked.connect(self._do_probe)
        btn_row.addWidget(self._probe_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        self._main_layout.addWidget(self._track_group)

    def _on_input_changed(self):
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
        if not path:
            self._reset_track_panel()
            self.input_media_card.reset()
            self._refresh_summary()
            return

        if not os.path.isfile(path):
            self._show_probe_error(f"文件不存在: {os.path.basename(path)}")
            self._refresh_summary()
            return

        info = probe_detailed(path)
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

    def _update_static_track_visibility(self, show: bool):
        """显示/隐藏静态音轨和字幕选择控件。"""
        self.audio_tracks_combo.setVisible(show)
        self.audio_tracks_custom_edit.setVisible(show)
        self.subtitle_tracks_combo.setVisible(show)
        self.subtitle_tracks_custom_edit.setVisible(show)

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
            header = QLabel("音频轨道:")
            header.setObjectName("accent_label")
            self._track_audio_layout.addWidget(header)
            for stream in info.audio_streams:
                label = self._build_stream_label(stream, "audio")
                cb = QCheckBox(label)
                cb.setChecked(True)
                cb.toggled.connect(self._refresh_summary)
                self._track_audio_layout.addWidget(cb)
                self._audio_checks.append((cb, stream.index))
            self._track_audio_container.setVisible(True)
        else:
            self._track_audio_container.setVisible(False)

        if info.subtitle_streams:
            has_tracks = True
            header = QLabel("字幕轨道:")
            header.setObjectName("accent_label")
            self._track_sub_layout.addWidget(header)
            for stream in info.subtitle_streams:
                label = self._build_stream_label(stream, "subtitle")
                cb = QCheckBox(label)
                cb.setChecked(False)
                cb.toggled.connect(self._refresh_summary)
                self._track_sub_layout.addWidget(cb)
                self._sub_checks.append((cb, stream.index))
            self._track_sub_container.setVisible(True)
        else:
            self._track_sub_container.setVisible(False)

        if not has_tracks:
            self._track_no_hint.setText("此文件未检测到音频或字幕轨道。")
            self._track_no_hint.setVisible(True)
        else:
            self._track_no_hint.setText(
                "勾选需要保留的轨道 (音频默认全选，字幕默认不选)"
            )
            set_label_kind(self._track_no_hint, "muted")
            self._track_no_hint.setVisible(True)

        self._probe_btn.setVisible(True)
        self._update_static_track_visibility(False)

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

        return ArgsNamespace(
            command=self.command_name,
            input=self.input_edit.text(),
            output=self.output_edit.text(),
            subtitle=self.subtitle_edit.text(),
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
