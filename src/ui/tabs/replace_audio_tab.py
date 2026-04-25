# -*- coding: utf-8 -*-
"""音频替换标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import AUDIO_ENCODERS, AUDIO_BITRATES


class ReplaceAudioTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("音频替换", parent)

        io = self.add_group("输入/输出设置")
        self.video_input_edit = self.add_file_chooser(
            io, "原始视频",
            "视频文件 (*.mp4 *.mov *.avi *.mkv);;所有文件 (*.*)",
            "选择原始视频文件",
        )
        self.audio_input_edit = self.add_file_chooser(
            io, "新音频文件",
            "音频文件 (*.mp3 *.aac *.wav *.flac *.m4a);;所有文件 (*.*)",
            "选择要替换的新音频文件",
        )
        self.audio_output_edit = self.add_file_saver(
            io, "输出路径 (可选)",
            "MP4 文件 (*.mp4);;所有文件 (*.*)",
            "留空则自动生成: [原视频名]_replaced.mp4",
        )

        audio = self.add_group("音频设置")
        self.audio_enc_combo = self.add_combo(
            audio, "音频编码器",
            list(AUDIO_ENCODERS.keys()), "AAC (推荐)",
        )
        self.audio_br_combo = self.add_combo(
            audio, "音频码率", AUDIO_BITRATES, "192k",
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
            video_input=self.video_input_edit.text(),
            audio_input=self.audio_input_edit.text(),
            audio_output=self.audio_output_edit.text(),
            audio_enc=self.audio_enc_combo.currentText(),
            audio_br=self.audio_br_combo.currentText(),
        )
