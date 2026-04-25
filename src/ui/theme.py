# -*- coding: utf-8 -*-
"""主题与样式表管理 —— Fluent Design 风格。"""

LIGHT_STYLESHEET = """
/* ================================================================
   全局
   ================================================================ */
QMainWindow {
    background-color: #f3f3f3;
}
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
}

/* ================================================================
   菜单栏  —— 亚克力风格 (白底 + 底部细线)
   ================================================================ */
QMenuBar {
    background-color: rgba(255, 255, 255, 0.92);
    border-bottom: 1px solid #e5e5e5;
    padding: 2px 4px;
    font-size: 13px;
    color: #1a1a1a;
}
QMenuBar::item {
    padding: 5px 14px;
    border-radius: 6px;
    margin: 1px 2px;
}
QMenuBar::item:selected {
    background-color: rgba(0, 0, 0, 0.05);
}
QMenuBar::item:pressed {
    background-color: rgba(0, 0, 0, 0.08);
}
QMenu {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 8px 28px 8px 16px;
    border-radius: 6px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: rgba(0, 120, 212, 0.08);
}
QMenu::separator {
    height: 1px;
    background-color: #e5e5e5;
    margin: 4px 12px;
}

/* ================================================================
   侧边栏  —— WinUI NavigationView 风格
   ================================================================ */
QListWidget#sidebar {
    background-color: #f3f3f3;
    border: none;
    border-right: 1px solid #e5e5e5;
    font-size: 13px;
    outline: none;
    padding: 6px 4px;
}
QListWidget#sidebar::item {
    padding: 10px 16px;
    border-radius: 8px;
    margin: 1px 4px;
    border: none;
    color: #1a1a1a;
}
QListWidget#sidebar::item:selected {
    background-color: #ffffff;
    color: #005fb8;
    font-weight: bold;
}
QListWidget#sidebar::item:hover:!selected {
    background-color: rgba(0, 0, 0, 0.04);
}

/* ================================================================
   分组框  —— 卡片式 (左侧色条 + 轻阴影)
   ================================================================ */
QGroupBox {
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #e8e8e8;
    border-left: 3px solid #005fb8;
    border-radius: 8px;
    margin-top: 16px;
    padding: 22px 14px 14px 14px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 8px;
    color: #1a1a1a;
}

/* ================================================================
   输入控件  —— Fluent TextBox 风格 (底部重点线)
   ================================================================ */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    padding: 6px 10px;
    border: 1px solid #d6d6d6;
    border-bottom: 2px solid #a0a0a0;
    border-radius: 6px;
    background-color: #fafafa;
    font-size: 13px;
    color: #1a1a1a;
    selection-background-color: rgba(0, 95, 184, 0.3);
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: #d6d6d6;
    border-bottom: 2px solid #005fb8;
    background-color: #ffffff;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled {
    background-color: #f0f0f0;
    color: #999999;
    border-color: #e5e5e5;
    border-bottom-color: #d0d0d0;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
    padding-right: 6px;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    background-color: #ffffff;
    padding: 4px;
    selection-background-color: rgba(0, 120, 212, 0.08);
    outline: none;
}

/* ================================================================
   按钮  —— Fluent Button 风格
   ================================================================ */
QPushButton {
    padding: 6px 16px;
    border: 1px solid #d6d6d6;
    border-radius: 6px;
    background-color: #ffffff;
    font-size: 13px;
    color: #1a1a1a;
}
QPushButton:hover {
    background-color: #f0f0f0;
    border-color: #c0c0c0;
}
QPushButton:pressed {
    background-color: #e8e8e8;
}

/* 主操作按钮 — Accent (蓝色) */
QPushButton#execute_btn {
    background-color: #005fb8;
    color: white;
    border: none;
    font-weight: bold;
    font-size: 14px;
    padding: 9px 36px;
    border-radius: 8px;
}
QPushButton#execute_btn:hover {
    background-color: #1a6fc4;
}
QPushButton#execute_btn:pressed {
    background-color: #004c99;
}
QPushButton#execute_btn:disabled {
    background-color: #a0c4e8;
    color: rgba(255, 255, 255, 0.6);
}

/* 停止按钮 — Danger */
QPushButton#stop_btn {
    background-color: #c42b1c;
    color: white;
    border: none;
    font-size: 14px;
    padding: 9px 28px;
    border-radius: 8px;
}
QPushButton#stop_btn:hover {
    background-color: #d4382b;
}
QPushButton#stop_btn:pressed {
    background-color: #a31d10;
}
QPushButton#stop_btn:disabled {
    background-color: #e0a8a3;
    color: rgba(255, 255, 255, 0.6);
}

/* 清空日志 — 次要按钮 */
QPushButton#clear_btn {
    background-color: transparent;
    border: 1px solid #d6d6d6;
    color: #5a5a5a;
    padding: 6px 18px;
    border-radius: 6px;
}
QPushButton#clear_btn:hover {
    background-color: #f0f0f0;
    color: #1a1a1a;
}

/* ================================================================
   日志面板  —— 深色终端 (Windows Terminal 风格)
   ================================================================ */
QTextEdit#log_panel {
    background-color: #1e1e1e;
    color: #cccccc;
    border: 1px solid #333333;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 10px;
    selection-background-color: rgba(38, 79, 120, 0.8);
}

/* ================================================================
   滚动条  —— 极细风格，hover 展开
   ================================================================ */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 3px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(0, 0, 0, 0.35);
    width: 8px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 6px;
    background: transparent;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 3px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(0, 0, 0, 0.35);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* 深色终端内的滚动条 */
QTextEdit#log_panel QScrollBar:vertical {
    width: 6px;
    background: transparent;
}
QTextEdit#log_panel QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 3px;
}
QTextEdit#log_panel QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.3);
}

/* ================================================================
   状态栏
   ================================================================ */
QStatusBar {
    background-color: #f3f3f3;
    border-top: 1px solid #e5e5e5;
    color: #5a5a5a;
    font-size: 12px;
    padding: 3px 10px;
}

/* ================================================================
   复选框
   ================================================================ */
QCheckBox {
    spacing: 8px;
    font-size: 13px;
    color: #1a1a1a;
}

/* ================================================================
   进度条  —— 渐变色
   ================================================================ */
QProgressBar {
    border: none;
    border-radius: 4px;
    background-color: #e5e5e5;
    text-align: center;
    min-height: 6px;
    max-height: 6px;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005fb8, stop:1 #0078d4);
}

/* ================================================================
   分割器
   ================================================================ */
QSplitter::handle {
    background-color: transparent;
}
QSplitter::handle:vertical {
    height: 6px;
}
QSplitter::handle:hover {
    background-color: rgba(0, 0, 0, 0.06);
}

/* ================================================================
   Tab 内按钮 (浏览...)
   ================================================================ */
QPushButton[text="浏览..."] {
    padding: 5px 12px;
    font-size: 12px;
    border-radius: 6px;
}

/* ================================================================
   进度仪表盘  —— MetricCard 样式
   ================================================================ */
QWidget#progress_dashboard {
    background-color: transparent;
}
QFrame#metric_card {
    background-color: #ffffff;
    border: 1px solid #e8e8e8;
    border-radius: 10px;
    padding: 8px;
}
QLabel#metric_value {
    font-size: 22px;
    font-weight: bold;
    color: #005fb8;
}
QLabel#metric_label {
    font-size: 11px;
    color: #888888;
}
QProgressBar#dashboard_progress {
    border: none;
    border-radius: 5px;
    background-color: #e5e5e5;
    min-height: 10px;
    max-height: 10px;
    color: transparent;
}
QProgressBar#dashboard_progress::chunk {
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005fb8, stop:0.5 #0078d4, stop:1 #00a2ed);
}
"""


def get_stylesheet():
    """获取当前主题样式表。"""
    return LIGHT_STYLESHEET
