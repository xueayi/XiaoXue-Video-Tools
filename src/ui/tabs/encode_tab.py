# -*- coding: utf-8 -*-
"""视频压制标签页 —— 最复杂的功能页面。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import (
    ENCODERS, QUALITY_PRESETS, CPU_PRESETS, NVENC_PRESETS,
    AUDIO_ENCODERS, AUDIO_BITRATES, RATE_CONTROL_MODES,
    VIDEO_BITRATES, AUDIO_TRACK_OPTIONS, SUBTITLE_TRACK_OPTIONS,
    POST_TRANSFER_MODES,
)


class EncodeTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("视频压制", parent)

        # ---- 输入/输出 ----
        io = self.add_group("输入/输出设置")
        self.input_edit = self.add_file_chooser(
            io, "输入视频",
            "视频文件 (*.mp4 *.mov *.avi *.mkv);;所有文件 (*.*)",
            "选择要处理的视频文件（支持将文件直接拖动到输入框）",
        )
        self.output_edit = self.add_file_saver(
            io, "输出路径 (可选)",
            "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*.*)",
            "留空则自动生成: 输入文件名_编码器.mp4",
        )
        self.subtitle_edit = self.add_file_chooser(
            io, "字幕文件 (可选)",
            "字幕文件 (*.srt *.ass *.ssa);;所有文件 (*.*)",
            "选择要烧录的字幕文件 (留空则不烧录)",
        )
        self.compat_mode_cb = self.add_checkbox(
            io, "兼容模式 (字幕)", False,
            "开启：使用 AviSynth+VSFilter 渲染字幕。\n"
            "关闭 (默认)：使用 FFmpeg 内置 libass 渲染。",
        )
        self.add_hint(
            io,
            "推荐开启: ASS 字幕特效显示错乱、无法调用 TTC/OTF 字体特定字重时\n"
            "默认关闭 (libass): 速度更快，适合 SRT 及大多数 ASS\n"
            "注意: 兼容模式需要程序在非中文路径下运行",
            "info",
        )

        # ---- 预设 ----
        preset = self.add_group("预设选择")
        self.preset_combo = self.add_combo(
            preset, "质量预设",
            list(QUALITY_PRESETS.keys()),
            "【均衡画质】x264常用导出(CRF18)",
            "选择预设配置，或选择 '自定义' 手动配置参数",
        )

        # ---- 编码器 ----
        encode_only = {k: v for k, v in ENCODERS.items() if v != "copy"}
        encoder = self.add_group("编码器设置", "选择自定义模式时生效")
        self.encoder_combo = self.add_combo(
            encoder, "视频编码器",
            list(encode_only.keys()), "H.264 (CPU - libx264)",
            "选择视频编码器 (CPU/NVIDIA/Intel/AMD)",
        )
        self.speed_preset_combo = self.add_combo(
            encoder, "编码速度", CPU_PRESETS, "medium",
            "编码速度预设 (越慢画质越好)",
        )
        self.nvenc_preset_combo = self.add_combo(
            encoder, "N卡速度档位",
            ["使用预设默认"] + NVENC_PRESETS, "使用预设默认",
            "NVENC 速度档位 (p1最快/p7最慢)",
        )

        # ---- 质量与码率 ----
        quality = self.add_group(
            "质量与码率",
            "CRF/CQ 模式由质量值控制；VBR/CBR 模式需设置目标码率",
        )
        self.rate_control_combo = self.add_combo(
            quality, "码率控制模式",
            list(RATE_CONTROL_MODES.keys()), "CRF/CQ (恒定质量)",
        )
        self.crf_spin = self.add_spinbox(
            quality, "质量值 (CRF/CQ)", 0, 51, 18,
            "0-51，越低画质越好，推荐 18-23",
        )
        self.video_bitrate_combo = self.add_combo(
            quality, "目标码率", VIDEO_BITRATES, "",
            "CRF/CQ 模式留空；VBR/CBR/2-Pass 模式设置码率",
        )
        self.add_hint(
            quality,
            "CRF/CQ: 恒定质量 (推荐)，由上方质量值控制\n"
            "VBR: 可变码率，设置平均码率  |  CBR: 恒定码率，适合推流\n"
            "2-Pass: 两遍编码，精确控制目标码率",
            "info",
        )

        # ---- 视频输出 ----
        vid_out = self.add_group("视频输出")
        self.resolution_edit = self.add_text_input(
            vid_out, "分辨率", "",
            "如 1920x1080，留空保持原分辨率",
        )
        self.fps_spin = self.add_spinbox(
            vid_out, "帧率", 0, 240, 0,
            "如 30、60，填 0 保持原帧率",
        )

        # ---- 音频设置 ----
        audio = self.add_group("音频设置")
        self.audio_encoder_combo = self.add_combo(
            audio, "音频编码器",
            list(AUDIO_ENCODERS.keys()), "复制 (不重新编码)",
        )
        self.audio_bitrate_combo = self.add_combo(
            audio, "音频码率", AUDIO_BITRATES, "192k",
        )
        self.audio_tracks_combo = self.add_combo(
            audio, "保留音轨",
            list(AUDIO_TRACK_OPTIONS.keys()), "仅保留第 1 条 (#0)",
            "快捷选择保留的音轨。注意：MP4 不支持多音轨。",
        )
        self.audio_tracks_custom_edit = self.add_text_input(
            audio, "音轨编号 (自定义)", "",
            "填写要保留的音轨编号，多条用逗号分隔，如: 0,1",
        )
        self.add_hint(
            audio,
            "编号从 #0 开始，可通过「媒体元数据检测」查看各音轨详情\n"
            "注意: MP4 格式不支持多音轨，需保留多轨请输出 MKV 格式",
            "warning",
        )

        # ---- 字幕流设置 ----
        sub = self.add_group("字幕流设置")
        self.add_hint(
            sub,
            "「字幕烧录」= 硬编码到画面中，不可关闭\n"
            "「保留字幕流」= 保留在容器中可切换的字幕轨\n"
            "两者是不同概念，可同时使用",
            "info",
        )
        self.subtitle_tracks_combo = self.add_combo(
            sub, "保留字幕",
            list(SUBTITLE_TRACK_OPTIONS.keys()), "不保留字幕",
            "注意：MP4 不支持 ASS 字幕。",
        )
        self.subtitle_tracks_custom_edit = self.add_text_input(
            sub, "字幕编号 (自定义)", "",
            "填写要保留的字幕编号，如: 0,2",
        )
        self.add_hint(
            sub,
            "MP4 格式不支持 ASS 等字幕，若源字幕为 ASS 格式，\n"
            "请选择「不保留字幕」或手动指定输出格式为 MKV",
            "warning",
        )

        # ---- 压制后分发 ----
        transfer = self.add_group(
            "压制后分发",
            "压制完成后自动将成品复制或移动到指定目录。",
        )
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

        # ---- 高级选项 ----
        extra = self.add_group("高级选项")
        self.extra_args_edit = self.add_text_input(
            extra, "额外 FFmpeg 参数", "",
            "多个参数用空格分隔",
        )
        self.add_hint(
            extra,
            "填写示例: -ss 00:01:00 -t 30 -tune animation\n"
            "参数会追加到 FFmpeg 命令末尾，多个参数用空格分隔",
            "info",
        )
        self.debug_mode_cb = self.add_checkbox(
            extra, "Debug 模式", False,
            "勾选后仅打印 FFmpeg 命令，不执行实际编码",
        )

        # ---- 在线文档 ----
        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Video-Encode",
        )
        self.add_stretch()

        # ---- 控件联动 ----
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.rate_control_combo.currentTextChanged.connect(self._on_rate_control_changed)
        self.encoder_combo.currentTextChanged.connect(self._on_encoder_changed)
        self.audio_tracks_combo.currentTextChanged.connect(self._on_audio_tracks_changed)
        self.subtitle_tracks_combo.currentTextChanged.connect(self._on_subtitle_tracks_changed)
        self.post_transfer_mode_combo.currentTextChanged.connect(self._on_transfer_changed)

        self._on_preset_changed(self.preset_combo.currentText())
        self._on_audio_tracks_changed(self.audio_tracks_combo.currentText())
        self._on_subtitle_tracks_changed(self.subtitle_tracks_combo.currentText())
        self._on_transfer_changed(self.post_transfer_mode_combo.currentText())

    # ----------------------------------------------------------------
    # 控件联动
    # ----------------------------------------------------------------

    def _on_preset_changed(self, preset_name):
        """当质量预设切换时，自动填充关联参数并控制可编辑状态。"""
        is_custom = "自定义" in preset_name or "Custom" in preset_name

        self.encoder_combo.setEnabled(is_custom)
        self.speed_preset_combo.setEnabled(is_custom)
        self.nvenc_preset_combo.setEnabled(is_custom)
        self.rate_control_combo.setEnabled(is_custom)
        self.crf_spin.setEnabled(is_custom)
        self.video_bitrate_combo.setEnabled(is_custom)

        preset = QUALITY_PRESETS.get(preset_name)
        if not preset or preset.get("encoder") is None:
            if is_custom:
                self._on_rate_control_changed(self.rate_control_combo.currentText())
                self._on_encoder_changed(self.encoder_combo.currentText())
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

    def _on_rate_control_changed(self, mode_name):
        """当码率控制模式切换时，调整质量值/码率控件的可用状态。"""
        is_crf = "CRF" in mode_name or "CQ" in mode_name
        self.crf_spin.setEnabled(is_crf)
        self.video_bitrate_combo.setEnabled(not is_crf)

    def _on_encoder_changed(self, encoder_name):
        """当编码器切换时，控制 NVENC 档位可用状态。"""
        is_nvenc = "NVENC" in encoder_name or "nvenc" in encoder_name
        self.nvenc_preset_combo.setEnabled(is_nvenc)

    def _on_audio_tracks_changed(self, text):
        self.audio_tracks_custom_edit.setEnabled("自定义" in text)

    def _on_subtitle_tracks_changed(self, text):
        self.subtitle_tracks_custom_edit.setEnabled("自定义" in text)

    def _on_transfer_changed(self, mode):
        self.post_transfer_dir_edit.setEnabled("不分发" not in mode)

    def build_args(self):
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
            resolution=self.resolution_edit.text(),
            fps=self.fps_spin.value(),
            audio_encoder=self.audio_encoder_combo.currentText(),
            audio_bitrate=self.audio_bitrate_combo.currentText(),
            audio_tracks=self.audio_tracks_combo.currentText(),
            audio_tracks_custom=self.audio_tracks_custom_edit.text(),
            subtitle_tracks=self.subtitle_tracks_combo.currentText(),
            subtitle_tracks_custom=self.subtitle_tracks_custom_edit.text(),
            post_transfer_mode=self.post_transfer_mode_combo.currentText(),
            post_transfer_dir=self.post_transfer_dir_edit.text(),
            extra_args=self.extra_args_edit.text(),
            debug_mode=self.debug_mode_cb.isChecked(),
        )
