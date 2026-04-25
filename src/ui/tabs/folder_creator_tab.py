# -*- coding: utf-8 -*-
"""文件夹创建标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace


class FolderCreatorTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("文件夹创建", parent)

        io = self.add_group("输入/输出设置")
        self.txt_edit = self.add_file_chooser(
            io, "TXT 文件",
            "文本文件 (*.txt);;所有文件 (*.*)",
            "选择包含文件夹名称的 TXT 文件，每行一个名称",
        )
        self.output_dir_edit = self.add_dir_chooser(
            io, "输出目录 (可选)",
            "留空则在 TXT 文件所在目录创建",
        )

        self.add_hint(
            io,
            "TXT 文件每行一个文件夹名称，支持 UTF-8/GBK/UTF-16 编码\n"
            "名称中的非法字符 ( \\ / : * ? \" < > | ) 会自动替换",
            "info",
        )

        options = self.add_group("选项设置")
        self.auto_number_cb = self.add_checkbox(
            options, "自动排序", True,
            "开启后自动在文件夹名前添加序号 (如 1_文件夹名)",
        )

        docs = self.add_group("在线文档")
        self.add_link(docs, "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools")

        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            folder_txt=self.txt_edit.text(),
            folder_output_dir=self.output_dir_edit.text(),
            folder_auto_number=self.auto_number_cb.isChecked(),
        )
