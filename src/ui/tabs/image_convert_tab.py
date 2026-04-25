# -*- coding: utf-8 -*-
"""图片转换标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import IMAGE_FORMATS


class ImageConvertTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("图片转换", parent)

        io = self.add_group("输入/输出设置")
        self.img_input_edit = self.add_multi_file_chooser(
            io, "输入图片 (可多选)",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff);;所有文件 (*.*)",
            "选择要转换的图片文件 (可批量选择多个)",
        )
        self.img_output_dir_edit = self.add_dir_chooser(
            io, "输出目录 (可选)",
            "留空则在原文件位置生成转换后的图片",
        )
        self.img_overwrite_cb = self.add_checkbox(
            io, "覆盖原文件", False,
            "⚠️ 危险: 转换后删除原文件，仅保留新文件",
        )

        fmt = self.add_group("输出格式")
        self.img_format_combo = self.add_combo(
            fmt, "目标格式",
            list(IMAGE_FORMATS.keys()), "PNG (无损)",
            "选择目标图片格式，或选择 '自定义' 手动输入",
        )
        self.img_format_custom_edit = self.add_text_input(
            fmt, "自定义格式", "",
            "当上方选择 '自定义' 时，在此输入扩展名 (如 ico, tga)",
        )
        self.img_quality_spin = self.add_spinbox(
            fmt, "质量 (JPG/WEBP)", 1, 100, 95,
            "JPEG/WEBP 格式的压缩质量 (1-100)，其他格式忽略",
        )
        self.img_skip_same_cb = self.add_checkbox(
            fmt, "忽略同格式文件", True,
            "跳过与目标转换格式相同的图片",
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
            img_input=self.get_multi_paths(self.img_input_edit),
            img_output_dir=self.img_output_dir_edit.text(),
            img_overwrite=self.img_overwrite_cb.isChecked(),
            img_format=self.img_format_combo.currentText(),
            img_format_custom=self.img_format_custom_edit.text(),
            img_quality=self.img_quality_spin.value(),
            img_skip_same_format=self.img_skip_same_cb.isChecked(),
        )
