# -*- coding: utf-8 -*-
"""日志输出面板：支持 ANSI 颜色渲染的只读终端。"""

import re
import html as html_module

from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtCore import Qt

_ANSI_RE = re.compile(r'\033\[([0-9;]*)m')
_ANSI_FG = {
    '30': '#000', '31': '#cc0000', '32': '#4e9a06', '33': '#c4a000',
    '34': '#3465a4', '35': '#75507b', '36': '#06989a', '37': '#d3d7cf',
    '90': '#555', '91': '#ef2929', '92': '#8ae234', '93': '#fce94f',
    '94': '#729fcf', '95': '#ad7fa8', '96': '#34e2e2', '97': '#eeeeec',
}


class LogPanel(QTextEdit):
    """日志输出面板，支持 ANSI 转义码着色。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log_panel")
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 10))
        self.setMinimumHeight(100)
        self.setPlaceholderText("日志输出...")

    def append_log(self, text):
        """追加日志，自动将 ANSI 颜色转换为 HTML。"""
        if not text:
            return
        html_text = _ansi_to_html(text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertHtml(html_text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()

    def clear_log(self):
        """清空日志。"""
        self.clear()


def _ansi_to_html(text):
    """将 ANSI 转义码转换为 HTML <span> 标签。"""
    parts = []
    last = 0
    open_span = False

    for m in _ANSI_RE.finditer(text):
        before = text[last:m.start()]
        if before:
            parts.append(html_module.escape(before))
        last = m.end()

        codes = m.group(1).split(';') if m.group(1) else ['0']
        for code in codes:
            if code in ('0', ''):
                if open_span:
                    parts.append('</span>')
                    open_span = False
            elif code == '1':
                if open_span:
                    parts.append('</span>')
                parts.append('<span style="font-weight:bold;">')
                open_span = True
            elif code in _ANSI_FG:
                if open_span:
                    parts.append('</span>')
                parts.append(f'<span style="color:{_ANSI_FG[code]};">')
                open_span = True

    remaining = text[last:]
    if remaining:
        parts.append(html_module.escape(remaining))
    if open_span:
        parts.append('</span>')

    return ''.join(parts).replace('\n', '<br/>')
