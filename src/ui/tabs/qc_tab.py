# -*- coding: utf-8 -*-
"""素材质量检测标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...presets import RESOLUTION_PRESETS


class QcTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("素材质量检测", parent)

        io = self.add_group("扫描设置")
        self.scan_dir_edit = self.add_dir_chooser(
            io, "扫描目录",
            "选择要扫描的文件夹 (将递归扫描)",
        )
        self.report_output_edit = self.add_file_saver(
            io, "报告输出路径 (可选)",
            "文本文件 (*.txt);;所有文件 (*.*)",
            "留空则自动生成: [扫描目录内]/QC_报告.txt",
        )

        thresh = self.add_group("阈值设置 (可选)")
        self.max_bitrate_spin = self.add_spinbox(
            thresh, "最大码率 (kbps)", 0, 999999, 0,
            "超过此码率将警告 (0 表示不检查)",
        )
        self.min_bitrate_spin = self.add_spinbox(
            thresh, "最小码率 (kbps)", 0, 999999, 0,
            "低于此码率将警告 (0 表示不检查)",
        )
        self.max_res_combo = self.add_combo(
            thresh, "最大分辨率 (预设)",
            list(RESOLUTION_PRESETS.keys()), "不限制",
        )
        self.max_res_custom_edit = self.add_text_input(
            thresh, "最大分辨率 (自定义)", "",
            "如果上方选择 '自定义'，请在此输入 (如 1920x1080)",
        )
        self.min_res_combo = self.add_combo(
            thresh, "最小分辨率 (预设)",
            list(RESOLUTION_PRESETS.keys()), "不限制",
        )
        self.min_res_custom_edit = self.add_text_input(
            thresh, "最小分辨率 (自定义)", "",
            "如果上方选择 '自定义'，请在此输入 (如 1280x720)",
        )

        pr = self.add_group("Premiere Pro 兼容性检测")
        self.check_pr_video_cb = self.add_checkbox(
            pr, "PR 视频兼容性", True,
            "检测可能会导致 PR 导入问题的视频格式 (如 MKV, VFR)",
        )
        self.check_pr_image_cb = self.add_checkbox(
            pr, "PR 图片兼容性", True,
            "检测可能会导致 PR 导入问题的图片格式 (可检测图片和后缀是否匹配)",
        )
        self.add_hint(
            pr,
            "检测内容: 容器兼容性 (MKV/WEBM/FLV)、编码兼容性 (VP9/AV1)\n"
            "图片格式检测 (WEBP 等)、扫描完成后生成 TXT 报告",
            "info",
        )

        custom = self.add_group("自定义兼容性规则 (高级)")
        self.add_hint(
            custom,
            "用逗号分隔格式，不含点号\n"
            "容器示例: mkv,webm,flv  |  编码示例: vp9,av1,theora  |  图片示例: webp,jxl",
            "info",
        )
        self.custom_containers_edit = self.add_text_input(
            custom, "不兼容容器", "mkv,webm,ogv,ogg,flv",
            "逗号分隔的不兼容容器扩展名 (不含点号)",
        )
        self.custom_codecs_edit = self.add_text_input(
            custom, "不兼容编码", "vp8,vp9,av1,theora",
            "逗号分隔的不兼容视频编码名称",
        )
        self.custom_images_edit = self.add_text_input(
            custom, "不兼容图片", "webp,heic,avif",
            "逗号分隔的不兼容图片扩展名 (不含点号)",
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Quality-Control",
        )
        self.add_stretch()

        # 控件联动
        self.max_res_combo.currentTextChanged.connect(self._on_max_res_changed)
        self.min_res_combo.currentTextChanged.connect(self._on_min_res_changed)
        self._on_max_res_changed(self.max_res_combo.currentText())
        self._on_min_res_changed(self.min_res_combo.currentText())

    def _on_max_res_changed(self, text):
        self.max_res_custom_edit.setEnabled("自定义" in text)

    def _on_min_res_changed(self, text):
        self.min_res_custom_edit.setEnabled("自定义" in text)

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            scan_dir=self.scan_dir_edit.text(),
            report_output=self.report_output_edit.text(),
            max_bitrate=self.max_bitrate_spin.value(),
            min_bitrate=self.min_bitrate_spin.value(),
            max_res_preset=self.max_res_combo.currentText(),
            max_res_custom=self.max_res_custom_edit.text(),
            min_res_preset=self.min_res_combo.currentText(),
            min_res_custom=self.min_res_custom_edit.text(),
            check_pr_video=self.check_pr_video_cb.isChecked(),
            check_pr_image=self.check_pr_image_cb.isChecked(),
            custom_containers=self.custom_containers_edit.text(),
            custom_codecs=self.custom_codecs_edit.text(),
            custom_images=self.custom_images_edit.text(),
        )
