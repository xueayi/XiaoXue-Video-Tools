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

        # ---- 字幕流设置 ----
        sub = self.add_group(
            "字幕流设置",
            "控制保留哪些内封字幕流 (与上方字幕烧录是不同概念)。",
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

        # ---- 高级选项 ----
        extra = self.add_group(
            "高级选项",
            "额外参数会追加到 FFmpeg 命令末尾。\n示例: -ss 00:01:00 -t 30 -tune animation",
        )
        self.extra_args_edit = self.add_text_input(
            extra, "额外 FFmpeg 参数", "",
            "多个参数用空格分隔",
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

    # ----------------------------------------------------------------
    # 预设联动
    # ----------------------------------------------------------------

    def _on_preset_changed(self, preset_name):
        """当质量预设切换时，自动填充关联参数。"""
        preset = QUALITY_PRESETS.get(preset_name)
        if not preset or preset.get("encoder") is None:
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
