# -*- coding: utf-8 -*-
"""主题与样式表管理 —— Fluent Design 风格，令牌化亮/暗双主题。

所有颜色、字体、圆角均定义在 PALETTES 设计令牌表中，
QSS 由单一模板 (TEMPLATE) + 令牌渲染生成，保证两套主题结构一致。

对外接口:
    get_theme() / set_theme(name)   当前主题 (持久化到 QSettings)
    get_stylesheet(theme=None)      渲染后的完整样式表
    color(token, theme=None)        代码侧取色 (药丸指示器、图标、状态闪烁等)
    palette(theme=None)             整套令牌字典
    logo_path(theme=None)           与主题匹配的品牌 Logo 路径
    apply_theme(app, theme=None)    一键应用: QPalette + QSS
    reduced_motion() / set_reduced_motion()  减少动画开关 (持久化)
"""

import os
from string import Template

from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPalette
from PyQt6.QtCore import QSettings

from ..utils import get_base_dir

# ================================================================
# 设计令牌
# ================================================================

_FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'
_MONO_FAMILY = '"Cascadia Mono", "Cascadia Code", "Consolas", "Courier New", monospace'
_LOGO_FILES = {
    "light": "小雪工具箱亮色.png",
    "dark": "小雪工具箱暗色.png",
}

_LIGHT = dict(
    font_family=_FONT_FAMILY,
    mono_family=_MONO_FAMILY,
    # 画布与卡片
    window_bg="#f3f3f3",
    card_bg="#ffffff",
    card_border="#e8e8e8",
    card_title="#1a1a1a",
    # 侧边栏
    sidebar_item_text="#1a1a1a",
    sidebar_item_bg_selected="#ffffff",
    sidebar_item_text_selected="#005fb8",
    sidebar_hover="rgba(0, 0, 0, 0.045)",
    hover_overlay="rgba(0, 0, 0, 0.04)",
    pressed_overlay="rgba(0, 0, 0, 0.08)",
    # 菜单
    menu_bg="rgba(255, 255, 255, 0.92)",
    menu_popup_bg="#ffffff",
    menu_border="#e5e5e5",
    menu_text="#1a1a1a",
    menu_selected="rgba(0, 95, 184, 0.08)",
    divider="#e5e5e5",
    # 输入控件
    input_bg="#fafafa",
    input_bg_focus="#ffffff",
    input_border="#d6d6d6",
    input_border_bottom="#a0a0a0",
    input_border_focus="#005fb8",
    input_text="#1a1a1a",
    input_placeholder="#8f8f8f",
    input_disabled_bg="#f0f0f0",
    input_disabled_text="#999999",
    input_disabled_border="#e0e0e0",
    # 文本
    text_primary="#1a1a1a",
    text_secondary="#5a5a5a",
    text_tertiary="#8a8a8a",
    text_disabled="#9d9d9d",
    error_text="#c42b1c",
    # 强调色
    accent="#005fb8",
    accent_hover="#1a6fc4",
    accent_pressed="#004c99",
    accent_disabled="#a0c4e8",
    on_accent="#ffffff",
    accent_text_disabled="rgba(255, 255, 255, 0.62)",
    accent_tint="rgba(0, 95, 184, 0.08)",
    accent_tint_hover="rgba(0, 95, 184, 0.13)",
    # 危险/成功/警告
    danger="#c42b1c",
    danger_hover="#d4382b",
    danger_pressed="#a31d10",
    danger_disabled="#e0a8a3",
    success="#0f7b0f",
    # 进度条
    progress_grad_start="#005fb8",
    progress_grad_mid="#0078d4",
    progress_grad_end="#00a2ed",
    progress_track="#e5e5e5",
    # 滚动条
    scrollbar="rgba(0, 0, 0, 0.22)",
    scrollbar_hover="rgba(0, 0, 0, 0.38)",
    # 日志终端 (亮色主题下保持深色终端观感)
    log_bg="#1e1e1e",
    log_border="#333333",
    log_text="#cccccc",
    log_scrollbar="rgba(255, 255, 255, 0.15)",
    log_scrollbar_hover="rgba(255, 255, 255, 0.30)",
    log_selection="rgba(38, 79, 120, 0.8)",
    # 工具提示
    tooltip_bg="#333333",
    tooltip_text="#ffffff",
    tooltip_border="#333333",
    # 提示条
    hint_info_bg="#e9f3fb",
    hint_info_border="#005fb8",
    hint_info_text="#0f5aa5",
    hint_warn_bg="#fdf5e3",
    hint_warn_border="#c87c00",
    hint_warn_text="#8a5300",
    hint_tip_bg="#ecf6ee",
    hint_tip_border="#218a4b",
    hint_tip_text="#0f6a2f",
    # 复选框
    checkbox_border="#6b6b6b",
    checkbox_bg="#fafafa",
    checkbox_checked="#005fb8",
    checkbox_hover_border="#005fb8",
    # 代码侧取色 (图标 / 药丸指示器)
    icon_color="#1a1a1a",
    icon_color_secondary="#5a5a5a",
    icon_color_accent="#005fb8",
)

_DARK = dict(
    font_family=_FONT_FAMILY,
    mono_family=_MONO_FAMILY,
    window_bg="#202020",
    card_bg="#2b2b2b",
    card_border="#383838",
    card_title="#f5f5f5",
    sidebar_item_text="#e8e8e8",
    sidebar_item_bg_selected="rgba(255, 255, 255, 0.055)",
    sidebar_item_text_selected="#4cc2ff",
    sidebar_hover="rgba(255, 255, 255, 0.06)",
    hover_overlay="rgba(255, 255, 255, 0.06)",
    pressed_overlay="rgba(0, 0, 0, 0.22)",
    menu_bg="rgba(32, 32, 32, 0.92)",
    menu_popup_bg="#2b2b2b",
    menu_border="#3d3d3d",
    menu_text="#f0f0f0",
    menu_selected="rgba(255, 255, 255, 0.08)",
    divider="#3d3d3d",
    input_bg="#333333",
    input_bg_focus="#383838",
    input_border="#3d3d3d",
    input_border_bottom="#6b6b6b",
    input_border_focus="#4cc2ff",
    input_text="#f5f5f5",
    input_placeholder="#7a7a7a",
    input_disabled_bg="#2a2a2a",
    input_disabled_text="#727272",
    input_disabled_border="#333333",
    text_primary="#f5f5f5",
    text_secondary="#c0c0c0",
    text_tertiary="#8a8a8a",
    text_disabled="#6e6e6e",
    error_text="#ff99a4",
    accent="#4cc2ff",
    accent_hover="#63cdff",
    accent_pressed="#3aa8e0",
    accent_disabled="rgba(76, 194, 255, 0.35)",
    on_accent="#000000",
    accent_text_disabled="rgba(0, 0, 0, 0.5)",
    accent_tint="rgba(76, 194, 255, 0.10)",
    accent_tint_hover="rgba(76, 194, 255, 0.16)",
    danger="#d13438",
    danger_hover="#dd5759",
    danger_pressed="#a32226",
    danger_disabled="rgba(209, 52, 56, 0.40)",
    success="#6ccb5f",
    progress_grad_start="#0f6cbd",
    progress_grad_mid="#4cc2ff",
    progress_grad_end="#79d5ff",
    progress_track="#3a3a3a",
    scrollbar="rgba(255, 255, 255, 0.20)",
    scrollbar_hover="rgba(255, 255, 255, 0.38)",
    log_bg="#161616",
    log_border="#2f2f2f",
    log_text="#c8c8c8",
    log_scrollbar="rgba(255, 255, 255, 0.12)",
    log_scrollbar_hover="rgba(255, 255, 255, 0.25)",
    log_selection="rgba(38, 79, 120, 0.9)",
    tooltip_bg="#3d3d3d",
    tooltip_text="#f5f5f5",
    tooltip_border="#4a4a4a",
    hint_info_bg="rgba(76, 194, 255, 0.10)",
    hint_info_border="#4cc2ff",
    hint_info_text="#79c0ff",
    hint_warn_bg="rgba(255, 200, 61, 0.10)",
    hint_warn_border="#ffc83d",
    hint_warn_text="#f0c453",
    hint_tip_bg="rgba(108, 203, 95, 0.10)",
    hint_tip_border="#6ccb5f",
    hint_tip_text="#8bd583",
    checkbox_border="#8a8a8a",
    checkbox_bg="#333333",
    checkbox_checked="#4cc2ff",
    checkbox_hover_border="#4cc2ff",
    icon_color="#e8e8e8",
    icon_color_secondary="#c0c0c0",
    icon_color_accent="#4cc2ff",
)

PALETTES = {
    "light": _LIGHT,
    "dark": _DARK,
}

THEMES = list(PALETTES.keys())


# ================================================================
# QSS 模板 ($TOKEN 由令牌表替换)
# ================================================================

TEMPLATE = Template("""
/* ================================================================
   全局
   ================================================================ */
QMainWindow {
    background-color: $window_bg;
}
QWidget {
    font-family: $font_family;
    font-size: 13px;
    color: $text_primary;
}
QWidget:disabled {
    color: $text_disabled;
}
QToolTip {
    background-color: $tooltip_bg;
    color: $tooltip_text;
    border: 1px solid $tooltip_border;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}

/* ================================================================
   菜单栏  —— 亚克力风格
   ================================================================ */
QMenuBar {
    background-color: $menu_bg;
    border-bottom: 1px solid $divider;
    padding: 2px 4px;
    font-size: 13px;
    color: $menu_text;
}
QMenuBar::item {
    padding: 5px 14px;
    border-radius: 6px;
    margin: 1px 2px;
}
QMenuBar::item:selected {
    background-color: $hover_overlay;
}
QMenuBar::item:pressed {
    background-color: $pressed_overlay;
}
QMenu {
    background-color: $menu_popup_bg;
    border: 1px solid $menu_border;
    border-radius: 8px;
    padding: 4px;
    color: $menu_text;
}
QMenu::item {
    padding: 8px 28px 8px 12px;
    border-radius: 6px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: $menu_selected;
}
QMenu::item:disabled {
    color: $text_disabled;
}
QMenu::separator {
    height: 1px;
    background-color: $divider;
    margin: 4px 12px;
}
QMenu::icon {
    padding-left: 8px;
}

/* ================================================================
   侧边栏  —— WinUI NavigationView 风格
   ================================================================ */
QListWidget#sidebar {
    background-color: $window_bg;
    border: none;
    border-right: 1px solid $divider;
    font-size: 13px;
    outline: none;
    padding: 4px 4px;
    color: $sidebar_item_text;
}
QListWidget#sidebar::item {
    padding: 10px 14px;
    border-radius: 8px;
    margin: 1px 4px;
    border: none;
    color: $sidebar_item_text;
}
QListWidget#sidebar::item:selected {
    background-color: $sidebar_item_bg_selected;
    color: $sidebar_item_text_selected;
    font-weight: bold;
}
QListWidget#sidebar::item:hover:!selected {
    background-color: $sidebar_hover;
}

/* 品牌区与底部按钮 */
QWidget#sidebar_root {
    background-color: $window_bg;
    border-right: 1px solid $divider;
}
QLabel#brand_title {
    font-size: 14px;
    font-weight: bold;
    color: $text_primary;
}
QLabel#brand_version {
    font-size: 11px;
    color: $text_tertiary;
}
QPushButton#sidebar_footer_btn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 7px 10px;
    color: $text_secondary;
    text-align: left;
    font-size: 12px;
}
QPushButton#sidebar_footer_btn:hover {
    background-color: $hover_overlay;
    color: $text_primary;
}

/* ================================================================
   分组框  —— 卡片式 (统一细描边, 无装饰条, 标题内嵌)
   ================================================================ */
QGroupBox {
    font-weight: 600;
    font-size: 13px;
    border: 1px solid $card_border;
    border-radius: 10px;
    margin-top: 10px;
    padding: 36px 18px 16px 18px;
    background-color: $card_bg;
    color: $text_primary;
}
QGroupBox::title {
    subcontrol-origin: border;
    subcontrol-position: top left;
    left: 16px;
    top: 12px;
    padding: 0 4px;
    color: $card_title;
}
/* 表单标签统一用次要色, 让字段值成为视觉主角 (ID 选择器的语义样式可覆盖) */
QGroupBox QLabel {
    color: $text_secondary;
}

/* ================================================================
   输入控件  —— Fluent TextBox 风格 (底部重点线)
   ================================================================ */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    padding: 6px 10px;
    border: 1px solid $input_border;
    border-bottom: 2px solid $input_border_bottom;
    border-radius: 6px;
    background-color: $input_bg;
    font-size: 13px;
    color: $input_text;
    selection-background-color: $menu_selected;
    selection-color: $text_primary;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: $input_border;
    border-bottom: 2px solid $input_border_focus;
    background-color: $input_bg_focus;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled {
    background-color: $input_disabled_bg;
    color: $input_disabled_text;
    border-color: $input_disabled_border;
    border-bottom-color: $input_disabled_border;
}
QLineEdit[dragOver="true"] {
    border: 1px solid $input_border_focus;
    border-bottom: 2px solid $input_border_focus;
    background-color: $input_bg_focus;
}
QLineEdit::placeholder {
    color: $input_placeholder;
}

/* 下拉框箭头 —— 纯 CSS 三角 */
QComboBox::drop-down {
    border: none;
    width: 28px;
    padding-right: 8px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid $text_secondary;
}
QComboBox::down-arrow:hover,
QComboBox::down-arrow:on {
    border-top-color: $accent;
}
QComboBox QAbstractItemView {
    border: 1px solid $menu_border;
    border-radius: 8px;
    background-color: $menu_popup_bg;
    padding: 4px;
    color: $menu_text;
    selection-background-color: $menu_selected;
    selection-color: $menu_text;
    outline: none;
}

/* 数字微调框按钮 */
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    border: none;
    width: 20px;
    background: transparent;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: $hover_overlay;
    border-radius: 4px;
}
QSpinBox::up-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid $text_secondary;
}
QSpinBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid $text_secondary;
}
QSpinBox::up-arrow:hover, QSpinBox::down-arrow:hover {
    border-bottom-color: $accent;
    border-top-color: $accent;
}

/* ================================================================
   按钮  —— Fluent Button 风格
   ================================================================ */
QPushButton {
    padding: 6px 16px;
    border: 1px solid $input_border;
    border-radius: 6px;
    background-color: $card_bg;
    font-size: 13px;
    color: $text_primary;
}
QPushButton:hover {
    background-color: $hover_overlay;
    border-color: $input_border_bottom;
    color: $text_primary;
}
QPushButton:pressed {
    background-color: $pressed_overlay;
}
QPushButton:disabled {
    background-color: $input_disabled_bg;
    border-color: $input_disabled_border;
    color: $text_disabled;
}
QPushButton:checked {
    background-color: $accent_tint;
    border-color: $accent;
    color: $accent;
}
QPushButton:hover:checked {
    background-color: $accent_tint_hover;
}

/* 主操作按钮 — Accent */
QPushButton#execute_btn {
    background-color: $accent;
    color: $on_accent;
    border: none;
    font-weight: bold;
    font-size: 14px;
    padding: 9px 28px;
    min-width: 132px;
    border-radius: 8px;
}
QPushButton#execute_btn:hover {
    background-color: $accent_hover;
    color: $on_accent;
}
QPushButton#execute_btn:pressed {
    background-color: $accent_pressed;
    color: $on_accent;
}
QPushButton#execute_btn:disabled {
    background-color: $accent_disabled;
    color: $accent_text_disabled;
}

/* 停止按钮 — Danger */
QPushButton#stop_btn {
    background-color: $danger;
    color: #ffffff;
    border: none;
    font-size: 14px;
    padding: 9px 28px;
    min-width: 96px;
    border-radius: 8px;
}
QPushButton#stop_btn:hover {
    background-color: $danger_hover;
    color: #ffffff;
}
QPushButton#stop_btn:pressed {
    background-color: $danger_pressed;
    color: #ffffff;
}
QPushButton#stop_btn:disabled {
    background-color: $danger_disabled;
    color: rgba(255, 255, 255, 0.6);
}

/* 次要按钮 (清空日志等) */
QPushButton#clear_btn {
    background-color: transparent;
    border: 1px solid $input_border;
    color: $text_secondary;
    padding: 6px 18px;
    border-radius: 6px;
}
QPushButton#clear_btn:hover {
    background-color: $hover_overlay;
    color: $text_primary;
}

/* 图标小按钮 (日志工具条) */
QPushButton#icon_btn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px;
    margin: 0;
}
QPushButton#icon_btn:hover {
    background-color: $hover_overlay;
}
QPushButton#icon_btn:pressed {
    background-color: $pressed_overlay;
}
QPushButton#icon_btn:checked {
    background-color: $accent_tint;
}

/* Tab 内行内动作按钮 (浏览 / 重新检测) —— 统一宽度由代码侧固定 */
QPushButton[text="浏览"] {
    padding: 6px 0;
    font-size: 12px;
    border-radius: 6px;
}
QPushButton[text="重新检测"] {
    padding: 6px 0;
    font-size: 12px;
    border-radius: 6px;
}

/* ================================================================
   日志面板  —— 深色终端 (Windows Terminal 风格)
   ================================================================ */
QTextEdit#log_panel {
    background-color: $log_bg;
    color: $log_text;
    border: 1px solid $log_border;
    border-radius: 10px;
    font-family: $mono_family;
    font-size: 12px;
    padding: 10px;
    selection-background-color: $log_selection;
    selection-color: $log_text;
}
QLineEdit#log_filter {
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 6px;
}

/* ================================================================
   滚动条  —— 极细风格，hover 展开
   ================================================================ */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollArea > QWidget > QWidget {
    background-color: transparent;
}
QStackedWidget {
    background-color: $window_bg;
}
QScrollBar:vertical {
    width: 6px;
    background: transparent;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: $scrollbar;
    border-radius: 3px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: $scrollbar_hover;
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
    background: $scrollbar;
    border-radius: 3px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background: $scrollbar_hover;
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
    background: $log_scrollbar;
    border-radius: 3px;
}
QTextEdit#log_panel QScrollBar::handle:vertical:hover {
    background: $log_scrollbar_hover;
}

/* ================================================================
   状态栏
   ================================================================ */
QStatusBar {
    background-color: $window_bg;
    border-top: 1px solid $divider;
    color: $text_secondary;
    font-size: 12px;
    padding: 3px 10px;
}

/* ================================================================
   复选框
   ================================================================ */
QCheckBox {
    spacing: 8px;
    font-size: 13px;
    color: $text_primary;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $checkbox_border;
    border-radius: 4px;
    background-color: $checkbox_bg;
}
QCheckBox::indicator:hover {
    border-color: $checkbox_hover_border;
}
QCheckBox::indicator:checked {
    background-color: $checkbox_checked;
    border-color: $checkbox_checked;
}
QCheckBox::indicator:disabled {
    border-color: $input_disabled_border;
    background-color: $input_disabled_bg;
}

/* ================================================================
   进度条  —— 渐变色
   ================================================================ */
QProgressBar {
    border: none;
    border-radius: 4px;
    background-color: $progress_track;
    text-align: center;
    min-height: 6px;
    max-height: 6px;
    color: transparent;
}
QProgressBar::chunk {
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $progress_grad_start, stop:1 $progress_grad_mid);
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
    background-color: $hover_overlay;
}

/* ================================================================
   进度仪表盘  —— MetricCard 样式
   ================================================================ */
QWidget#progress_dashboard {
    background-color: transparent;
}
QFrame#metric_card {
    background-color: $card_bg;
    border: 1px solid $card_border;
    border-radius: 10px;
    padding: 8px;
}
QLabel#metric_value {
    font-family: $mono_family;
    font-size: 19px;
    font-weight: bold;
    color: $accent;
}
QLabel#metric_label {
    font-size: 11px;
    color: $text_tertiary;
}
QProgressBar#dashboard_progress {
    border: none;
    border-radius: 5px;
    background-color: $progress_track;
    min-height: 10px;
    max-height: 10px;
    color: transparent;
}
QProgressBar#dashboard_progress::chunk {
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $progress_grad_start, stop:0.5 $progress_grad_mid, stop:1 $progress_grad_end);
}

/* ================================================================
   语义化文本  —— 供代码侧以 objectName 引用 (随主题联动)
   ================================================================ */
QLabel#group_desc {
    color: $text_tertiary;
    font-size: 12px;
    margin-bottom: 4px;
}
QLabel#hint_info {
    color: $text_tertiary;
    font-size: 12px;
    line-height: 150%;
    padding: 1px 0;
    margin: 2px 0;
    background: transparent;
    border: none;
}
QLabel#hint_warning {
    background-color: $hint_warn_bg;
    border: 1px solid $hint_warn_border;
    border-radius: 6px;
    padding: 8px 12px;
    color: $hint_warn_text;
    font-size: 12px;
    margin: 4px 0;
}
QLabel#hint_tip {
    background-color: $hint_tip_bg;
    border: 1px solid $hint_tip_border;
    border-radius: 6px;
    padding: 8px 12px;
    color: $hint_tip_text;
    font-size: 12px;
    margin: 4px 0;
}
QLabel#muted_label {
    color: $text_tertiary;
    font-size: 12px;
}
QLabel#muted_label[italic="true"] {
    font-style: italic;
}
QLabel#error_label {
    color: $error_text;
    font-size: 12px;
}
QLabel#strong_label {
    color: $text_primary;
    font-weight: bold;
    font-size: 12px;
}
QLabel#accent_label {
    color: $accent;
    font-weight: bold;
    font-size: 12px;
}
QTextEdit#help_view {
    background-color: $input_bg;
    border: 1px solid $input_border;
    border-radius: 6px;
    padding: 8px;
}

/* 可折叠分组标题 */
QToolButton#fold_header {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 8px;
    font-weight: bold;
    font-size: 13px;
    color: $text_primary;
    text-align: left;
}
QToolButton#fold_header:hover {
    background-color: $hover_overlay;
}
QToolButton#fold_header:checked {
    background-color: transparent;
    color: $accent;
}
""")


# ================================================================
# 主题存取
# ================================================================

_KEY_THEME = "ui/theme"
_KEY_REDUCED_MOTION = "ui/reduced_motion"


def _settings() -> QSettings:
    from ..gui_config import get_qsettings
    return get_qsettings()


def get_theme() -> str:
    """读取当前主题名，缺省 light。"""
    name = _settings().value(_KEY_THEME, "light")
    return name if name in PALETTES else "light"


def set_theme(name: str):
    """持久化主题选择。"""
    if name in PALETTES:
        _settings().setValue(_KEY_THEME, name)


def reduced_motion() -> bool:
    """是否开启「减少动画」。"""
    return _settings().value(_KEY_REDUCED_MOTION, "false") in (True, "true", "1")


def set_reduced_motion(enabled: bool):
    """持久化「减少动画」开关。"""
    _settings().setValue(_KEY_REDUCED_MOTION, bool(enabled))


def palette(theme: str = None) -> dict:
    """获取整套设计令牌。"""
    return PALETTES[theme or get_theme()]


def color(token: str, theme: str = None) -> str:
    """代码侧取色 (药丸指示器、图标、状态闪烁等)。"""
    return palette(theme)[token]


def get_stylesheet(theme: str = None) -> str:
    """由令牌渲染完整 QSS。"""
    return TEMPLATE.safe_substitute(palette(theme))


def logo_path(theme: str = None):
    """与主题匹配的品牌 Logo 绝对路径；找不到返回 None。"""
    name = _LOGO_FILES[theme or get_theme()]
    base = get_base_dir()
    for sub in ("image", os.path.join("src", "image"), "."):
        path = os.path.join(base, sub, name)
        if os.path.exists(path):
            return path
    return None


def apply_theme(app, theme: str = None):
    """应用主题: QPalette (兜底) + QSS。切换主题时重复调用即可。"""
    p = palette(theme)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p["window_bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p["text_primary"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(p["input_bg"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p["window_bg"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(p["input_text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(p["card_bg"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p["text_primary"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p["on_accent"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["tooltip_bg"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p["tooltip_text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["input_placeholder"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(p["accent"]))
    pal.setColor(QPalette.ColorRole.LinkVisited, QColor(p["accent"]))
    pal.setColor(QPalette.ColorGroup.Disabled,
                 QPalette.ColorRole.WindowText, QColor(p["text_disabled"]))
    pal.setColor(QPalette.ColorGroup.Disabled,
                 QPalette.ColorRole.Text, QColor(p["text_disabled"]))
    pal.setColor(QPalette.ColorGroup.Disabled,
                 QPalette.ColorRole.ButtonText, QColor(p["text_disabled"]))
    app.setPalette(pal)
    app.setStyleSheet(get_stylesheet(theme or get_theme()))


def toggle_theme():
    """切换主题并返回新主题名。"""
    new_theme = "dark" if get_theme() == "light" else "light"
    set_theme(new_theme)
    return new_theme
