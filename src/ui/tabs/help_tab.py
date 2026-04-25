# -*- coding: utf-8 -*-
"""使用说明标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace


class HelpTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("使用说明", parent)

        group = self.add_group("功能说明")
        self.topic_combo = self.add_combo(
            group, "选择功能",
            [
                "视频压制", "音频替换", "封装转换", "素材质量检测",
                "媒体元数据检测", "音视频抽取", "图片转换", "文件夹创建",
                "批量重命名", "通知设置", "常见问题",
            ],
            default="视频压制",
            tooltip="选择要查看说明的功能模块",
        )

        docs = self.add_group("在线文档")
        self.add_link(docs, "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Home")

        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            help_topic=self.topic_combo.currentText(),
        )
