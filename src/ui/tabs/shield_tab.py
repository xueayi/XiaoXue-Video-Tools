# -*- coding: utf-8 -*-
"""露骨图片识别 (Shield) 标签页。"""

from PyQt6.QtWidgets import QLabel

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import (
    SHIELD_THRESHOLDS, SHIELD_CENSOR_TYPES,
    SHIELD_MOSAIC_SIZES, SHIELD_EXPAND_OPTIONS,
)


class ShieldTab(BaseTab):

    def __init__(self, shield_available=True, parent=None):
        super().__init__("露骨图片识别", parent)
        self.shield_available = shield_available

        if not shield_available:
            self._build_unavailable_ui()
            return

        self._build_full_ui()

    # ----------------------------------------------------------------
    # Shield 不可用时显示版本提示
    # ----------------------------------------------------------------

    def _build_unavailable_ui(self):
        notice = self.add_group(
            "您目前的软件版本不支持该功能",
            "当前为 标准版，不包含 AI 露骨图片识别模块。\n\n"
            "【标准版】体积小，适合日常视频压制和批量处理。\n"
            "【Shield 增强版】额外包含基于 AI 的 NSFW 识别功能。\n\n"
            "前往 GitHub Releases 页面下载带 shield 标识的版本即可。",
        )
        self.add_link(
            notice,
            "https://github.com/xueayi/XiaoXue-Video-Tools/releases",
            "下载 Shield 增强版",
        )
        self.add_stretch()

    # ----------------------------------------------------------------
    # 完整功能表单
    # ----------------------------------------------------------------

    def _build_full_ui(self):
        io = self.add_group("输入设置", "选择要扫描的文件夹或图片文件")
        self.input_dir_edit = self.add_dir_chooser(
            io, "扫描目录",
            "选择要扫描的文件夹 (递归扫描所有图片)",
        )
        self.input_files_edit = self.add_multi_file_chooser(
            io, "或选择图片 (可多选)",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;所有文件 (*.*)",
            "直接选择多个图片文件，与上方二选一",
        )

        output = self.add_group("输出设置")
        self.output_dir_edit = self.add_dir_chooser(
            output, "输出目录 (可选)",
            "打码图片和报告的输出目录。留空则在输入目录下创建 shield_output 子目录",
        )
        self.report_edit = self.add_file_saver(
            output, "报告路径 (可选)",
            "文本文件 (*.txt);;所有文件 (*.*)",
            "留空则自动生成: [输出目录]/shield_report.txt",
        )

        detect = self.add_group("检测设置")
        self.threshold_combo = self.add_combo(
            detect, "风险阈值",
            list(SHIELD_THRESHOLDS.keys()), "Questionable 及以上 (推荐)",
            "达到此级别及以上将被标记为风险图片",
        )
        self.recursive_cb = self.add_checkbox(
            detect, "递归扫描子目录", True,
            "勾选后将扫描所有子目录中的图片",
        )

        censor = self.add_group("打码设置 (可选)")
        self.enable_censor_cb = self.add_checkbox(
            censor, "启用自动打码", False,
            "对风险图片的敏感区域自动打码",
        )
        self.censor_type_combo = self.add_combo(
            censor, "打码类型",
            list(SHIELD_CENSOR_TYPES.keys()), "马赛克 (Pixelate)",
        )
        self.mosaic_size_combo = self.add_combo(
            censor, "处理强度/大小",
            SHIELD_MOSAIC_SIZES, "16",
            "马赛克=方块大小，模糊=半径，黑色=圆角，表情=元素比例",
        )
        self.overlay_image_edit = self.add_file_chooser(
            censor, "覆盖图片 (自定义模式)",
            "图片文件 (*.png *.jpg *.jpeg);;所有文件 (*.*)",
            '当打码类型选择「自定义图片」时使用',
        )
        self.expand_pixels_combo = self.add_combo(
            censor, "打码范围扩展 (像素)",
            SHIELD_EXPAND_OPTIONS, "0",
            "向外扩展打码区域的像素数",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Shield",
        )
        self.add_stretch()

        # 控件联动
        self.enable_censor_cb.toggled.connect(self._on_censor_toggled)
        self.censor_type_combo.currentTextChanged.connect(self._on_censor_type_changed)
        self._on_censor_toggled(self.enable_censor_cb.isChecked())

    def _on_censor_toggled(self, enabled):
        self.censor_type_combo.setEnabled(enabled)
        self.mosaic_size_combo.setEnabled(enabled)
        self.expand_pixels_combo.setEnabled(enabled)
        if enabled:
            self._on_censor_type_changed(self.censor_type_combo.currentText())
        else:
            self.overlay_image_edit.setEnabled(False)

    def _on_censor_type_changed(self, text):
        self.overlay_image_edit.setEnabled("自定义" in text)

    def build_args(self):
        if not self.shield_available:
            return ArgsNamespace(command=self.command_name)

        files = self.get_multi_paths(self.input_files_edit)
        return ArgsNamespace(
            command=self.command_name,
            shield_input_dir=self.input_dir_edit.text(),
            shield_input_files=files if files else None,
            shield_output_dir=self.output_dir_edit.text(),
            shield_report=self.report_edit.text(),
            shield_threshold=self.threshold_combo.currentText(),
            shield_recursive=self.recursive_cb.isChecked(),
            shield_enable_censor=self.enable_censor_cb.isChecked(),
            shield_censor_type=self.censor_type_combo.currentText(),
            shield_mosaic_size=self.mosaic_size_combo.currentText(),
            shield_overlay_image=self.overlay_image_edit.text(),
            shield_expand_pixels=self.expand_pixels_combo.currentText(),
        )
