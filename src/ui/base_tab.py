# -*- coding: utf-8 -*-
"""Tab 页面基类：提供通用控件创建辅助方法。"""

from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QSpinBox, QPlainTextEdit, QFileDialog, QToolButton,
)
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from .args_builder import ArgsNamespace

# 表单内容列的最大宽度: 避免宽窗口下输入框被无限拉长
CONTENT_MAX_WIDTH = 860

_STATUS_KINDS = {
    "muted": ("muted_label", True),
    "error": ("error_label", False),
    "strong": ("strong_label", False),
}


def repolish(widget: QWidget):
    """让 objectName/动态属性变更后的 QSS 重新生效。"""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_label_kind(label: QLabel, kind: str):
    """将状态标签切换为 muted(灰斜体)/error(红)/strong(粗体) 语义样式。"""
    object_name, italic = _STATUS_KINDS.get(kind, _STATUS_KINDS["muted"])
    label.setObjectName(object_name)
    label.setProperty("italic", italic)
    repolish(label)


def _set_drag_over(widget, over: bool):
    """切换拖放高亮态 (QSS QLineEdit[dragOver="true"])。"""
    if widget.property("dragOver") != over:
        widget.setProperty("dragOver", over)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


class FileDropLineEdit(QLineEdit):
    """支持文件拖放的 QLineEdit。拖入文件时自动填入路径，拖悬时高亮。"""

    def __init__(self, multi=False, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._multi = multi
        if multi:
            self._paths = []

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            _set_drag_over(self, True)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        _set_drag_over(self, False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        _set_drag_over(self, False)
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if not paths:
            return
        if self._multi:
            self._paths = paths
            if len(paths) <= 3:
                self.setText("; ".join(paths))
            else:
                self.setText(f"已选择 {len(paths)} 个文件")
        else:
            self.setText(paths[0])
        event.acceptProposedAction()


class BaseTab(QScrollArea):
    """所有功能页面的基类。子类需实现 build_args()。"""

    def __init__(self, command_name, parent=None):
        super().__init__(parent)
        self.command_name = command_name
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        self._container = QWidget()
        self._container.setMaximumWidth(CONTENT_MAX_WIDTH)
        self._main_layout = QVBoxLayout(self._container)
        self._main_layout.setContentsMargins(20, 16, 20, 16)
        self._main_layout.setSpacing(10)
        self.setWidget(self._container)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    # ----------------------------------------------------------------
    # 分组
    # ----------------------------------------------------------------

    def add_group(self, title, description=None):
        """创建一个 QGroupBox 分组并追加到主布局，返回内部 QFormLayout。"""
        group = QGroupBox(title)
        layout = QFormLayout()
        layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        group.setLayout(layout)

        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setObjectName("group_desc")
            layout.addRow(desc)

        self._main_layout.addWidget(group)
        return layout

    # ----------------------------------------------------------------
    # 控件辅助方法 —— 每个方法返回值承载控件以供 build_args 读取
    # ----------------------------------------------------------------

    def add_file_chooser(self, layout, label, filter_str="所有文件 (*.*)", tooltip=""):
        """单文件选择器 (打开)，支持拖放。"""
        row = QHBoxLayout()
        edit = FileDropLineEdit()
        if tooltip:
            edit.setToolTip(tooltip)
        btn = QPushButton("浏览...")
        btn.setFixedWidth(70)
        row.addWidget(edit, 1)
        row.addWidget(btn, 0)

        def _browse():
            path, _ = QFileDialog.getOpenFileName(self, f"选择 - {label}", "", filter_str)
            if path:
                edit.setText(path)

        btn.clicked.connect(_browse)
        layout.addRow(label, row)
        return edit

    def add_file_saver(self, layout, label, filter_str="所有文件 (*.*)", tooltip=""):
        """文件保存路径选择器，支持拖放。"""
        row = QHBoxLayout()
        edit = FileDropLineEdit()
        if tooltip:
            edit.setToolTip(tooltip)
        btn = QPushButton("浏览...")
        btn.setFixedWidth(70)
        row.addWidget(edit, 1)
        row.addWidget(btn, 0)

        def _browse():
            path, _ = QFileDialog.getSaveFileName(self, f"保存 - {label}", "", filter_str)
            if path:
                edit.setText(path)

        btn.clicked.connect(_browse)
        layout.addRow(label, row)
        return edit

    def add_dir_chooser(self, layout, label, tooltip=""):
        """目录选择器，支持拖放目录。"""
        row = QHBoxLayout()
        edit = FileDropLineEdit()
        if tooltip:
            edit.setToolTip(tooltip)
        btn = QPushButton("浏览...")
        btn.setFixedWidth(70)
        row.addWidget(edit, 1)
        row.addWidget(btn, 0)

        def _browse():
            path = QFileDialog.getExistingDirectory(self, f"选择目录 - {label}")
            if path:
                edit.setText(path)

        btn.clicked.connect(_browse)
        layout.addRow(label, row)
        return edit

    def add_multi_file_chooser(self, layout, label, filter_str="所有文件 (*.*)", tooltip=""):
        """多文件选择器，支持拖放多个文件。"""
        row = QHBoxLayout()
        edit = FileDropLineEdit(multi=True)
        if tooltip:
            edit.setToolTip(tooltip)
        btn = QPushButton("浏览...")
        btn.setFixedWidth(70)
        row.addWidget(edit, 1)
        row.addWidget(btn, 0)

        def _browse():
            paths, _ = QFileDialog.getOpenFileNames(self, f"选择 - {label}", "", filter_str)
            if paths:
                edit._paths = paths
                if len(paths) <= 3:
                    edit.setText("; ".join(paths))
                else:
                    edit.setText(f"已选择 {len(paths)} 个文件")

        btn.clicked.connect(_browse)
        layout.addRow(label, row)
        return edit

    def add_combo(self, layout, label, choices, default="", tooltip=""):
        """下拉选择框。"""
        combo = QComboBox()
        combo.addItems(choices)
        if default in choices:
            combo.setCurrentText(default)
        if tooltip:
            combo.setToolTip(tooltip)
        layout.addRow(label, combo)
        return combo

    def add_checkbox(self, layout, label, default=False, tooltip=""):
        """复选框。"""
        cb = QCheckBox()
        cb.setChecked(default)
        if tooltip:
            cb.setToolTip(tooltip)
        layout.addRow(label, cb)
        return cb

    def add_spinbox(self, layout, label, min_val=0, max_val=100, default=0, tooltip=""):
        """整数微调框。"""
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        if tooltip:
            spin.setToolTip(tooltip)
        layout.addRow(label, spin)
        return spin

    def add_text_input(self, layout, label, default="", tooltip=""):
        """单行文本输入。"""
        edit = QLineEdit(default)
        if tooltip:
            edit.setToolTip(tooltip)
        layout.addRow(label, edit)
        return edit

    def add_text_area(self, layout, label, default="", height=80, tooltip=""):
        """多行文本输入。"""
        edit = QPlainTextEdit()
        edit.setPlainText(default)
        edit.setMaximumHeight(height)
        if tooltip:
            edit.setToolTip(tooltip)
        layout.addRow(label, edit)
        return edit

    def add_link(self, layout, url, text="查看在线文档"):
        """添加可点击的超链接。"""
        link = QLabel(f'<a href="{url}">{text}</a>')
        link.setOpenExternalLinks(True)
        layout.addRow("", link)

    def add_hint(self, layout, text, hint_type="info"):
        """添加带样式的内联提示标签。

        hint_type 可选 "info"(蓝), "warning"(橙), "tip"(绿)。
        颜色由主题 QSS 中的 QLabel#hint_* 规则提供，随亮暗主题联动。
        """
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName(f"hint_{hint_type}" if hint_type in ("info", "warning", "tip")
                           else "hint_info")
        label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addRow("", label)
        return label

    def add_stretch(self):
        """在底部添加弹性空间。"""
        self._main_layout.addStretch(1)

    def add_collapsible_group(self, title, description=None, expanded=False):
        """创建可折叠分组 (Win11 展开器风格)，返回内部 QFormLayout。"""
        header = QToolButton()
        header.setObjectName("fold_header")
        header.setCheckable(True)
        header.setChecked(expanded)
        header.setText(("▾  " if expanded else "▸  ") + title)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        content = QWidget()
        content.setObjectName("fold_content")
        layout = QFormLayout(content)
        layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setContentsMargins(14, 0, 0, 4)

        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setObjectName("group_desc")
            layout.addRow(desc)

        def _toggle(checked):
            header.setText(("▾  " if checked else "▸  ") + title)
            content.setVisible(checked)

        header.toggled.connect(_toggle)
        content.setVisible(expanded)

        self._main_layout.addWidget(header)
        self._main_layout.addWidget(content)
        return layout

    # ----------------------------------------------------------------
    # 主题联动钩子
    # ----------------------------------------------------------------

    def on_theme_changed(self):
        """主题切换后的刷新钩子，子类可覆盖 (如重渲染内嵌 HTML)。"""

    # ----------------------------------------------------------------
    # 工具方法
    # ----------------------------------------------------------------

    def get_multi_paths(self, edit):
        """从 MultiFileChooser 控件获取路径列表。"""
        if hasattr(edit, '_paths') and edit._paths:
            return list(edit._paths)
        text = edit.text().strip()
        if not text or text.startswith("已选择"):
            return []
        return [p.strip() for p in text.split(";") if p.strip()]

    # ----------------------------------------------------------------
    # 子类必须实现
    # ----------------------------------------------------------------

    def build_args(self):
        """从表单控件收集参数，返回 ArgsNamespace 对象。"""
        raise NotImplementedError(f"{type(self).__name__} 必须实现 build_args()")
