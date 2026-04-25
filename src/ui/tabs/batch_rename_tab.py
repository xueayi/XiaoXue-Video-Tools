# -*- coding: utf-8 -*-
"""批量重命名标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import (
    RENAME_MODES, RENAME_TARGETS, RENAME_BEHAVIORS,
    RENAME_SORT_METHODS, RENAME_SORT_ORDERS,
)


class BatchRenameTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("批量重命名", parent)

        io = self.add_group("输入设置")
        self.input_dir_edit = self.add_dir_chooser(
            io, "输入目录",
            "选择要重命名的文件所在目录",
        )

        mode = self.add_group("重命名模式")
        self.mode_combo = self.add_combo(
            mode, "模式",
            list(RENAME_MODES.keys()), "原地重命名",
            "原地: 直接重命名; 复制: 保留原文件; 移动: 移动到新位置",
        )
        self.output_dir_edit = self.add_dir_chooser(
            mode, "安全输出路径 (可选)",
            "复制/移动模式: 留空则在输入目录创建 'rename_output' 文件夹",
        )

        sort_group = self.add_group(
            "排序设置",
            "控制文件的排序规则，影响重命名后的序号分配。",
        )
        self.sort_method_combo = self.add_combo(
            sort_group, "排序方式",
            list(RENAME_SORT_METHODS.keys()), "按文件名排序",
        )
        self.sort_order_combo = self.add_combo(
            sort_group, "排序方向",
            list(RENAME_SORT_ORDERS.keys()), "升序（从小到大）",
        )
        self.priority_keyword_edit = self.add_text_input(
            sort_group, "关键词提前排序 (可选)", "",
            "文件名包含此关键词的文件会优先排在序列前面，如:主视觉图",
        )

        target = self.add_group("重命名对象")
        self.target_combo = self.add_combo(
            target, "目标类型",
            list(RENAME_TARGETS.keys()), "图片和视频",
        )
        self.image_exts_edit = self.add_text_input(
            target, "图片格式", "png,jpg",
            "逗号分隔的图片扩展名 (不含点号)",
        )
        self.video_exts_edit = self.add_text_input(
            target, "视频格式", "mp4,mov",
            "逗号分隔的视频扩展名 (不含点号)",
        )

        behavior = self.add_group(
            "重命名行为",
            "递归模式: 包含子目录并在文件名中带上目录前缀；非递归模式: 仅处理当前目录。",
        )
        self.recursive_combo = self.add_combo(
            behavior, "行为模式",
            list(RENAME_BEHAVIORS.keys()), "递归模式（保持目录结构）",
        )

        advanced = self.add_group("高级选项")
        self.exclude_underscore_cb = self.add_checkbox(
            advanced, "排除下划线后文字", True,
            "递归模式下，忽略文件夹名中第一个下划线后的内容",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools",
        )
        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            rename_input_dir=self.input_dir_edit.text(),
            rename_mode=self.mode_combo.currentText(),
            rename_output_dir=self.output_dir_edit.text(),
            rename_sort_method=self.sort_method_combo.currentText(),
            rename_sort_order=self.sort_order_combo.currentText(),
            rename_priority_keyword=self.priority_keyword_edit.text(),
            rename_target=self.target_combo.currentText(),
            rename_image_exts=self.image_exts_edit.text(),
            rename_video_exts=self.video_exts_edit.text(),
            rename_recursive=self.recursive_combo.currentText(),
            rename_exclude_underscore=self.exclude_underscore_cb.isChecked(),
        )
