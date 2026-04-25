# -*- coding: utf-8 -*-
"""音视频抽取标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import AUDIO_ENCODERS, AUDIO_BITRATES, EXTRACT_MODES


class ExtractAvTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("音视频抽取", parent)

        io = self.add_group("输入/输出设置")
        self.extract_input_edit = self.add_file_chooser(
            io, "输入视频",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm);;所有文件 (*.*)",
            "选择要处理的视频文件",
        )
        self.extract_output_edit = self.add_file_saver(
            io, "音频输出路径 (可选)",
            "MP3 文件 (*.mp3);;AAC 文件 (*.aac);;WAV 文件 (*.wav);;FLAC 文件 (*.flac);;所有文件 (*.*)",
            "留空则自动生成: [原视频名]_extract.[ext]",
        )
        self.extract_video_output_edit = self.add_file_saver(
            io, "视频输出路径 (可选)",
            "MP4 文件 (*.mp4);;MKV 文件 (*.mkv);;所有文件 (*.*)",
            "留空则自动生成: [原视频名]_noaudio.[ext]",
        )

        mode = self.add_group("抽取模式")
        self.extract_mode_combo = self.add_combo(
            mode, "抽取模式",
            list(EXTRACT_MODES.keys()), "仅音频",
            "仅音频 / 仅视频 / 同时输出两个文件",
        )
        self.add_hint(
            mode,
            "仅音频: 从视频中提取纯音频文件\n"
            "仅视频: 输出无音频的纯视频文件\n"
            "音频+视频: 同时输出纯音频和纯视频两个文件",
            "info",
        )

        audio = self.add_group("音频设置")
        self.extract_encoder_combo = self.add_combo(
            audio, "音频编码器",
            list(AUDIO_ENCODERS.keys()), "AAC (推荐)",
            "选择音频编码器 (选 '复制' 可直接提取原始音频)",
        )
        self.extract_bitrate_combo = self.add_combo(
            audio, "音频码率", AUDIO_BITRATES, "192k",
            "音频码率 (仅转码时生效)",
        )
        self.add_hint(
            audio,
            "选择「复制 (不重新编码)」可无损提取原始音频，输出格式取决于原始编码\n"
            "视频抽取不重新编码，速度极快",
            "tip",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Audio-Video-Tools",
        )
        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            extract_input=self.extract_input_edit.text(),
            extract_output=self.extract_output_edit.text(),
            extract_video_output=self.extract_video_output_edit.text(),
            extract_mode=self.extract_mode_combo.currentText(),
            extract_encoder=self.extract_encoder_combo.currentText(),
            extract_bitrate=self.extract_bitrate_combo.currentText(),
        )
