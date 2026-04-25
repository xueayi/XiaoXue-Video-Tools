# -*- coding: utf-8 -*-
"""使用说明标签页 —— 可视化展示各功能帮助文本。"""

from PyQt6.QtWidgets import QTextEdit, QGroupBox, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..base_tab import BaseTab
from ..args_builder import ArgsNamespace
from ...help_texts import HELP_TEXTS


_HELP_HTML_STYLE = """
<style>
body { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 13px; color: #333; }
h2 { color: #1565c0; margin: 12px 0 6px 0; font-size: 15px; }
.section-title {
    color: #1976d2; font-weight: bold; font-size: 13px;
    border-bottom: 2px solid #bbdefb; padding-bottom: 3px;
    margin: 14px 0 6px 0;
}
.tip { color: #2e7d32; }
.warn { color: #e65100; }
.link { color: #1565c0; }
ul { margin: 2px 0 2px 16px; padding: 0; }
li { margin: 2px 0; }
</style>
"""


def _plain_to_html(text: str) -> str:
    """将 help_texts 中的纯文本转换为带样式的 HTML。"""
    lines = text.strip().split("\n")
    html_parts = [_HELP_HTML_STYLE, "<body>"]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            html_parts.append("<br/>")
            continue

        if stripped.startswith("在线文档:"):
            url = stripped.replace("在线文档:", "").strip()
            html_parts.append(
                f'<p class="link">在线文档: <a href="{url}">{url}</a></p>'
            )
        elif stripped.startswith("【") and "】" in stripped:
            html_parts.append(f"<h2>{_esc(stripped)}</h2>")
        elif "━━" in stripped:
            title = stripped.replace("━", "").strip()
            if title:
                html_parts.append(f'<div class="section-title">{_esc(title)}</div>')
        elif stripped.startswith("•"):
            content = stripped[1:].strip()
            html_parts.append(f"<li>{_esc(content)}</li>")
        elif stripped.startswith("✅"):
            html_parts.append(f'<p class="tip">{_esc(stripped)}</p>')
        elif stripped.startswith("⚠️") or stripped.startswith("❌"):
            html_parts.append(f'<p class="warn">{_esc(stripped)}</p>')
        elif stripped.startswith("❓"):
            html_parts.append(f"<p><b>{_esc(stripped)}</b></p>")
        elif stripped.startswith("→"):
            html_parts.append(f"<p style='margin-left:16px;'>{_esc(stripped)}</p>")
        else:
            html_parts.append(f"<p>{_esc(stripped)}</p>")

    html_parts.append("</body>")
    return "\n".join(html_parts)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class HelpTab(BaseTab):

    def __init__(self, parent=None):
        super().__init__("使用说明", parent)

        group = self.add_group("功能说明")
        self.topic_combo = self.add_combo(
            group, "选择功能",
            list(HELP_TEXTS.keys()),
            default="视频压制",
            tooltip="选择要查看说明的功能模块",
        )

        help_group = QGroupBox("使用指南")
        help_layout = QVBoxLayout()
        help_layout.setContentsMargins(0, 6, 0, 0)
        help_group.setLayout(help_layout)

        self._help_display = QTextEdit()
        self._help_display.setReadOnly(True)
        self._help_display.setMinimumHeight(380)
        self._help_display.setStyleSheet(
            "QTextEdit { background-color: #fafafa; border: 1px solid #e0e0e0; "
            "border-radius: 4px; padding: 8px; }"
        )
        font = QFont("Microsoft YaHei", 10)
        self._help_display.setFont(font)
        help_layout.addWidget(self._help_display)

        self._main_layout.addWidget(help_group)

        docs = self.add_group("在线文档")
        self.add_link(docs, "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Home")

        self.add_stretch()

        self.topic_combo.currentTextChanged.connect(self._on_topic_changed)
        self._on_topic_changed(self.topic_combo.currentText())

    def _on_topic_changed(self, topic):
        text = HELP_TEXTS.get(topic, "暂无此功能的说明。")
        self._help_display.setHtml(_plain_to_html(text))

    def build_args(self):
        return ArgsNamespace(
            command=self.command_name,
            help_topic=self.topic_combo.currentText(),
        )
