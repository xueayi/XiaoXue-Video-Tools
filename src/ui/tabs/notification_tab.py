# -*- coding: utf-8 -*-
"""通知设置标签页。"""

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...notify import FEISHU_COLORS


class NotificationTab(BaseTab):

    def __init__(self, config=None, parent=None):
        super().__init__("通知设置", parent)
        if config is None:
            config = {}

        auto = self.add_group(
            "自动通知设置",
            "配置文件保存在程序目录下的 notify_config.json",
        )
        self.enable_auto_cb = self.add_checkbox(
            auto, "启用自动通知",
            config.get("enabled", False),
            "勾选后，其他任务完成时会自动发送通知",
        )
        self.save_config_cb = self.add_checkbox(
            auto, "保存配置(运行后生效)", False,
            "保存当前通知配置，下次启动时自动加载",
        )
        self.delete_config_cb = self.add_checkbox(
            auto, "删除已保存配置", False,
            "勾选后运行将删除已保存的配置文件",
        )

        feishu = self.add_group("飞书通知")
        self.feishu_webhook_edit = self.add_text_input(
            feishu, "飞书 Webhook URL",
            config.get("feishu_webhook", ""),
            "飞书机器人 Webhook 地址 (留空则跳过飞书通知)",
        )
        self.feishu_title_edit = self.add_text_input(
            feishu, "卡片标题",
            config.get("feishu_title", "任务完成通知"),
        )
        self.feishu_content_edit = self.add_text_area(
            feishu, "消息内容",
            config.get("feishu_content", "您的视频处理任务已完成！"),
            80,
            "飞书消息内容 (支持 lark_md 格式)",
        )

        saved_color = config.get("feishu_color", "blue")
        color_display = "蓝色 (Blue)"
        for name, code in FEISHU_COLORS.items():
            if code == saved_color:
                color_display = name
                break

        self.feishu_color_combo = self.add_combo(
            feishu, "卡片颜色",
            list(FEISHU_COLORS.keys()), color_display,
        )

        webhook = self.add_group("自定义 Webhook")
        self.webhook_url_edit = self.add_text_input(
            webhook, "Webhook URL",
            config.get("webhook_url", ""),
            "自定义 POST 请求 URL (留空则跳过)",
        )
        self.webhook_headers_edit = self.add_text_input(
            webhook, "请求头 (JSON)",
            config.get("webhook_headers", '{"Content-Type": "application/json"}'),
        )
        self.webhook_body_edit = self.add_text_area(
            webhook, "请求体 (JSON)",
            config.get("webhook_body", '{"message": "任务完成"}'),
            80,
        )

        docs = self.add_group("在线文档")
        self.add_link(
            docs,
            "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Notification",
        )
        self.add_stretch()

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            enable_auto_notify=self.enable_auto_cb.isChecked(),
            save_notify_config=self.save_config_cb.isChecked(),
            delete_notify_config=self.delete_config_cb.isChecked(),
            feishu_webhook=self.feishu_webhook_edit.text(),
            feishu_title=self.feishu_title_edit.text(),
            feishu_content=self.feishu_content_edit.toPlainText(),
            feishu_color=self.feishu_color_combo.currentText(),
            webhook_url=self.webhook_url_edit.text(),
            webhook_headers=self.webhook_headers_edit.text(),
            webhook_body=self.webhook_body_edit.toPlainText(),
        )
