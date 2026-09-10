# -*- coding: utf-8 -*-
"""日志输出面板 —— 深色终端风格，ANSI 颜色渲染 + 工具条 (过滤/自动滚动/换行/复制)。"""

import re
import html as html_module

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from . import icons

_ANSI_RE = re.compile(r'\033\[([0-9;]*)m')

# 深色终端适配的 ANSI 前景色 (比浅色主题下更鲜艳)
_ANSI_FG = {
    '30': '#555555', '31': '#f44747', '32': '#6a9955', '33': '#dcdcaa',
    '34': '#569cd6', '35': '#c586c0', '36': '#4ec9b0', '37': '#d4d4d4',
    '90': '#808080', '91': '#f14c4c', '92': '#89d185', '93': '#e2e210',
    '94': '#6cb6ff', '95': '#d670d6', '96': '#4fe0c0', '97': '#e5e5e5',
}


class _LogView(QTextEdit):
    """终端视图: Ctrl+滚轮调整字号。"""

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoomIn(1)
            else:
                self.zoomOut(1)
            event.accept()
            return
        super().wheelEvent(event)


class LogPanel(QWidget):
    """日志面板外观组件: 工具条 + 终端视图。保持 append_log/clear_log API。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("log_panel_root")
        self._chunks = []          # 原始日志块 (用于过滤后重渲染)
        self._scroll_anim = None
        self._tool_icon_names = {}  # 工具条按钮 -> 图标名 (主题切换时刷新)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        # ---- 工具条 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._filter_edit = QLineEdit()
        self._filter_edit.setObjectName("log_filter")
        self._filter_edit.setPlaceholderText("过滤关键字...")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.setFixedWidth(220)
        self._filter_edit.addAction(
            icons.secondary("ri.search-line"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._filter_edit.textChanged.connect(self._rerender)
        toolbar.addWidget(self._filter_edit)

        toolbar.addStretch()

        self._autoscroll_btn = self._make_tool_btn(
            "ri.arrow-down-line", "自动滚动到最新日志", checkable=True, checked=True)
        self._wrap_btn = self._make_tool_btn(
            "ri.text-wrap", "自动换行", checkable=True, checked=True)
        copy_btn = self._make_tool_btn("ri.file-copy-line", "复制全部日志")
        clear_btn = self._make_tool_btn("ri.delete-bin-7-line", "清空日志")

        self._autoscroll_btn.toggled.connect(self._scroll_to_bottom)
        self._wrap_btn.toggled.connect(self._toggle_wrap)
        copy_btn.clicked.connect(self._copy_all)
        clear_btn.clicked.connect(self.clear_log)

        for b in (self._autoscroll_btn, self._wrap_btn, copy_btn, clear_btn):
            toolbar.addWidget(b)

        root.addLayout(toolbar)

        # ---- 终端视图 ----
        self._view = _LogView()
        self._view.setObjectName("log_panel")
        self._view.setReadOnly(True)
        self._view.setFont(QFont("Cascadia Code", 10))
        self._view.setMinimumHeight(180)
        self._view.setPlaceholderText("任务日志将在这里输出…  (支持彩色输出, Ctrl+滚轮调整字号)")
        root.addWidget(self._view, 1)

    # ----------------------------------------------------------------
    # 公开 API (与旧版 LogPanel 兼容)
    # ----------------------------------------------------------------

    def append_log(self, text):
        """追加日志，自动将 ANSI 颜色转换为 HTML。"""
        if not text:
            return
        self._chunks.append(text)
        if self._filter_edit.text().strip():
            return  # 有过滤时由 _rerender 统一处理
        html_text = _ansi_to_html(text)
        self._insert_html(html_text)

    def clear_log(self):
        """清空日志。"""
        self._chunks.clear()
        self._view.clear()

    # ----------------------------------------------------------------
    # 工具条行为
    # ----------------------------------------------------------------

    def _make_tool_btn(self, icon_name, tooltip, checkable=False, checked=False):
        btn = QPushButton()
        btn.setObjectName("icon_btn")
        btn.setIcon(icons.secondary(icon_name))
        btn.setFixedSize(30, 28)
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        btn.setChecked(checked)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tool_icon_names[btn] = icon_name
        return btn

    def on_theme_changed(self):
        """主题切换后刷新工具条图标颜色。"""
        for btn, icon_name in self._tool_icon_names.items():
            btn.setIcon(icons.secondary(icon_name))

    def _toggle_wrap(self, checked):
        from PyQt6.QtGui import QTextOption
        mode = (QTextOption.WrapMode.WordWrap if checked
                else QTextOption.WrapMode.NoWrap)
        self._view.setWordWrapMode(mode)
        self._wrap_btn.setToolTip("自动换行 (当前: 开)" if checked else "自动换行 (当前: 关)")

    def _copy_all(self):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self._view.toPlainText())

    def _scroll_to_bottom(self, *_):
        sb = self._view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ----------------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------------

    def _insert_html(self, html_text):
        self._view.moveCursor(QTextCursor.MoveOperation.End)
        self._view.insertHtml(html_text)
        if self._autoscroll_btn.isChecked():
            self._smooth_scroll_to_bottom()

    def _rerender(self):
        """按过滤关键字重渲染全部日志 (逐行包含匹配, 不区分大小写)。"""
        keyword = self._filter_edit.text().strip().lower()
        self._view.clear()
        if not keyword:
            for chunk in self._chunks:
                self._insert_html(_ansi_to_html(chunk))
            return

        for chunk in self._chunks:
            html_text = _ansi_to_html(chunk)
            html_lines = html_text.split("<br/>")
            plain_lines = chunk.split("\n")
            kept = [
                h for h, plain in zip(html_lines, plain_lines)
                if keyword in plain.lower()
            ]
            if kept:
                self._insert_html("<br/>".join(kept) + "<br/>")

    def _smooth_scroll_to_bottom(self):
        """平滑滚动到底部。"""
        sb = self._view.verticalScrollBar()
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
        self._scroll_anim.finished.connect(
            lambda: setattr(self, "_scroll_anim", None))
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
