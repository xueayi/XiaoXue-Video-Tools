# -*- coding: utf-8 -*-
"""媒体元数据检测标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace


class MediaProbeTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("媒体元数据检测", parent)

        io = self.add_group(
            "输入设置",
            "两种输入方式二选一：\n① 直接选择文件 (可多选)\n② 选择目录 (自动扫描媒体文件)",
        )
        self.probe_files_edit = self.add_multi_file_chooser(
            io, "输入文件 (可多选)",
            "媒体文件 (*.mp4 *.mkv *.mov *.avi *.mp3 *.flac *.wav);;所有文件 (*.*)",
            "选择要分析的媒体文件",
        )
        self.probe_dir_edit = self.add_dir_chooser(
            io, "或选择目录",
            "选择要扫描的文件夹",
        )

        output = self.add_group("输出设置")
        self.report_output_edit = self.add_file_saver(
            output, "报告输出路径 (可选)",
            "文本文件 (*.txt);;所有文件 (*.*)",
            "留空则仅在控制台显示，填写则额外保存 TXT 报告",
        )

        options = self.add_group("扫描选项")
        self.recursive_cb = self.add_checkbox(
            options, "递归扫描子目录", True,
            "目录模式下，勾选后将扫描所有子目录",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Media-Probe",
        )
        self.add_stretch()

    def build_args(self):
        files = self.get_multi_paths(self.probe_files_edit)
        return ArgsNamespace(
            command=self.command_name,
            probe_input_files=files if files else None,
            probe_input_dir=self.probe_dir_edit.text(),
            probe_report_output=self.report_output_edit.text(),
            probe_recursive=self.recursive_cb.isChecked(),
        )
