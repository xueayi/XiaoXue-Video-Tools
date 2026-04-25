# -*- coding: utf-8 -*-
"""日志输出面板 —— 深色终端风格，支持 ANSI 颜色渲染和平滑滚动。"""

import re
import html as html_module

from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve

_ANSI_RE = re.compile(r'\033\[([0-9;]*)m')

# 深色终端适配的 ANSI 前景色 (比浅色主题下更鲜艳)
_ANSI_FG = {
    '30': '#555555', '31': '#f44747', '32': '#6a9955', '33': '#dcdcaa',
    '34': '#569cd6', '35': '#c586c0', '36': '#4ec9b0', '37': '#d4d4d4',
    '90': '#808080', '91': '#f14c4c', '92': '#89d185', '93': '#e2e210',
    '94': '#6cb6ff', '95': '#d670d6', '96': '#4fe0c0', '97': '#e5e5e5',
}


class LogPanel(QTextEdit):
    """日志输出面板，深色终端风格，支持 ANSI 转义码着色和平滑滚动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log_panel")
        self.setReadOnly(True)
        self.setFont(QFont("Cascadia Code", 10))
        self.setMinimumHeight(180)
        self.setPlaceholderText("日志输出...")
        self._scroll_anim = None

    def _on_scroll_anim_finished(self):
        """动画结束后清空引用，避免悬空指针。"""
        self._scroll_anim = None

    def append_log(self, text):
        """追加日志，自动将 ANSI 颜色转换为 HTML。"""
        if not text:
            return
        html_text = _ansi_to_html(text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertHtml(html_text)
        self._smooth_scroll_to_bottom()

    def clear_log(self):
        """清空日志。"""
        self.clear()

    def _smooth_scroll_to_bottom(self):
        """平滑滚动到底部。"""
        sb = self.verticalScrollBar()
        target = sb.maximum()
        current = sb.value()

        if abs(target - current) < 20:
            sb.setValue(target)
            return

        if self._scroll_anim is not None:
            self._scroll_anim.stop()
            self._scroll_anim.deleteLater()

        self._scroll_anim = QPropertyAnimation(sb, b"value", self)
        self._scroll_anim.setStartValue(current)
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.setDuration(120)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_anim.finished.connect(self._on_scroll_anim_finished)
        self._scroll_anim.start()


def _ansi_to_html(text):
    """将 ANSI 转义码转换为 HTML <span> 标签 (深色终端色值)。"""
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
