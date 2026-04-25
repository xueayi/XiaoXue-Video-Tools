# -*- coding: utf-8 -*-
"""主题与样式表管理。"""

LIGHT_STYLESHEET = """
/* ---- 全局 ---- */
QMainWindow {
    background-color: #f5f5f5;
}

/* ---- 菜单栏 ---- */
QMenuBar {
    background-color: #00AEEC;
    color: white;
    padding: 2px;
    font-size: 13px;
}
QMenuBar::item {
    padding: 4px 12px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #0098d4;
}
QMenu {
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    padding: 4px 0;
}
QMenu::item {
    padding: 6px 28px;
}
QMenu::item:selected {
    background-color: #e3f2fd;
}

/* ---- 侧边栏 ---- */
QListWidget#sidebar {
    background-color: #ffffff;
    border: none;
    border-right: 1px solid #e0e0e0;
    font-size: 14px;
    outline: none;
}
QListWidget#sidebar::item {
    padding: 12px 18px;
    border-bottom: 1px solid #f0f0f0;
}
QListWidget#sidebar::item:selected {
    background-color: #e3f2fd;
    color: #1976d2;
    border-left: 3px solid #1976d2;
}
QListWidget#sidebar::item:hover:!selected {
    background-color: #fafafa;
}

/* ---- 分组框 ---- */
QGroupBox {
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    margin-top: 14px;
    padding: 20px 12px 12px 12px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #333333;
}

/* ---- 输入控件 ---- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    padding: 5px 8px;
    border: 1px solid #cccccc;
    border-radius: 4px;
    background-color: #ffffff;
    font-size: 13px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: #1976d2;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
}

/* ---- 按钮 ---- */
QPushButton {
    padding: 5px 14px;
    border: 1px solid #cccccc;
    border-radius: 4px;
    background-color: #ffffff;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #e3f2fd;
    border-color: #1976d2;
}
QPushButton#execute_btn {
    background-color: #00AEEC;
    color: white;
    border: none;
    font-weight: bold;
    font-size: 14px;
    padding: 8px 32px;
    border-radius: 5px;
}
QPushButton#execute_btn:hover {
    background-color: #0098d4;
}
QPushButton#execute_btn:disabled {
    background-color: #90caf9;
}
QPushButton#stop_btn {
    background-color: #d32f2f;
    color: white;
    border: none;
    font-size: 14px;
    padding: 8px 24px;
    border-radius: 5px;
}
QPushButton#stop_btn:hover {
    background-color: #c62828;
}
QPushButton#stop_btn:disabled {
    background-color: #ef9a9a;
}

/* ---- 日志面板 ---- */
QTextEdit#log_panel {
    background-color: #fafafa;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    padding: 6px;
}

/* ---- 滚动区域 ---- */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    width: 8px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: #c0c0c0;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #a0a0a0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* ---- 状态栏 ---- */
QStatusBar {
    background-color: #e8e8e8;
    color: #555555;
    font-size: 12px;
    padding: 2px 8px;
}

/* ---- 复选框 ---- */
QCheckBox {
    spacing: 8px;
    font-size: 13px;
}

/* ---- 进度条 ---- */
QProgressBar {
    border: 1px solid #cccccc;
    border-radius: 4px;
    text-align: center;
    min-height: 18px;
    font-size: 12px;
}
QProgressBar::chunk {
    background-color: #00AEEC;
    border-radius: 3px;
}

/* ---- 分割器 ---- */
QSplitter::handle {
    background-color: #e0e0e0;
}
QSplitter::handle:vertical {
    height: 2px;
}
"""


def get_stylesheet():
    """获取当前主题样式表。"""
    return LIGHT_STYLESHEET
