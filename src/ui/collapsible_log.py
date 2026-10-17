# -*- coding: utf-8 -*-
"""可折叠日志区 —— 标题行 (复用 fold_header 样式) + 内层 LogPanel，默认折叠。

主窗口接入 (PR-06) 时:
    * 用 ``collapsible.panel`` 赋给 ``self._log_panel``，即可让既有测试
      继续访问内层 LogPanel 的 ``_chunks`` / ``_view``；
    * append_log / clear_log / on_theme_changed 全部委托给内层面板，
      折叠状态下日志仍照常写入 (只是不显示)。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from .log_panel import LogPanel

_COLLAPSED_MARK = "▸"
_EXPANDED_MARK = "▾"


class CollapsibleLog(QWidget):
    """默认折叠的日志面板容器，保持 LogPanel 的对外 API。"""

    def __init__(self, title: str = "执行日志", parent=None):
        super().__init__(parent)
        self.setObjectName("collapsible_log_root")
        self._title = title

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # 标题行: 复用 theme.py 里的 QToolButton#fold_header 样式
        self._toggle = QToolButton()
        self._toggle.setObjectName("fold_header")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setText(f"{_COLLAPSED_MARK}  {title}")
        self._toggle.setToolTip("展开 / 折叠执行日志")
        self._toggle.toggled.connect(self._on_toggled)
        root.addWidget(self._toggle, 0)

        self._panel = LogPanel()
        self._panel.hide()
        root.addWidget(self._panel, 1)

    # ----------------------------------------------------------------
    # 对外属性 / 折叠控制
    # ----------------------------------------------------------------

    @property
    def panel(self) -> LogPanel:
        """内层 LogPanel (供主窗口保留 ``_log_panel`` 兼容)。"""
        return self._panel

    @property
    def title(self) -> str:
        """标题文案。"""
        return self._title

    def is_expanded(self) -> bool:
        """当前是否展开。"""
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool):
        """设置展开/折叠状态 (会同步内层面板可见性)。"""
        self._toggle.setChecked(bool(expanded))

    def expand(self):
        """展开日志。"""
        self.set_expanded(True)

    def collapse(self):
        """折叠日志。"""
        self.set_expanded(False)

    # ----------------------------------------------------------------
    # LogPanel 委托
    # ----------------------------------------------------------------

    def append_log(self, text):
        """追加日志 (折叠状态下仍写入内层面板)。"""
        self._panel.append_log(text)

    def clear_log(self):
        """清空日志。"""
        self._panel.clear_log()

    def on_theme_changed(self):
        """主题切换后刷新内层工具条图标。"""
        self._panel.on_theme_changed()

    # ----------------------------------------------------------------
    # 内部
    # ----------------------------------------------------------------

    def _on_toggled(self, checked: bool):
        self._panel.setVisible(checked)
        mark = _EXPANDED_MARK if checked else _COLLAPSED_MARK
        self._toggle.setText(f"{mark}  {self._title}")
