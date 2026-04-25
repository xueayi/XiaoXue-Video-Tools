# -*- coding: utf-8 -*-
"""封装转换标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import (
    REMUX_PRESETS, AUDIO_TRACK_OPTIONS, SUBTITLE_TRACK_OPTIONS,
)


class RemuxTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("封装转换", parent)

        io = self.add_group("输入/输出设置")
        self.remux_input_edit = self.add_multi_file_chooser(
            io, "输入文件 (可多选)",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm *.ts *.mxf);;所有文件 (*.*)",
            "选择要转换的文件 (可批量选择多个)",
        )

        fmt = self.add_group(
            "输出格式",
            "选择封装预设，或选择「自定义」并在下方填写目标后缀名。",
        )
        self.remux_preset_combo = self.add_combo(
            fmt, "封装预设",
            list(REMUX_PRESETS.keys()), "MP4 (H.264 兼容)",
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

        stream = self.add_group(
            "流选择",
            "控制保留哪些音轨和字幕流。默认全部保留。",
        )
        self.remux_audio_tracks_combo = self.add_combo(
            stream, "保留音轨",
            list(AUDIO_TRACK_OPTIONS.keys()), "全部保留",
        )
        self.remux_audio_custom_edit = self.add_text_input(
            stream, "音轨编号 (自定义)", "",
            "填写要保留的音轨编号，如: 0,2。仅当上方选择「自定义选择」时生效。",
        )
        self.remux_subtitle_tracks_combo = self.add_combo(
            stream, "保留字幕",
            list(SUBTITLE_TRACK_OPTIONS.keys()), "全部保留",
        )
        self.remux_subtitle_custom_edit = self.add_text_input(
            stream, "字幕编号 (自定义)", "",
            "填写要保留的字幕编号，如: 0,1。仅当上方选择「自定义选择」时生效。",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Remux-Image",
        )
        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            remux_input=self.get_multi_paths(self.remux_input_edit),
            remux_preset=self.remux_preset_combo.currentText(),
            remux_format_custom=self.remux_format_custom_edit.text(),
            remux_output=self.remux_output_edit.text(),
            remux_overwrite=self.remux_overwrite_cb.isChecked(),
            remux_audio_tracks=self.remux_audio_tracks_combo.currentText(),
            remux_audio_tracks_custom=self.remux_audio_custom_edit.text(),
            remux_subtitle_tracks=self.remux_subtitle_tracks_combo.currentText(),
            remux_subtitle_tracks_custom=self.remux_subtitle_custom_edit.text(),
        )
