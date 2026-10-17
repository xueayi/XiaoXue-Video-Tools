# -*- coding: utf-8 -*-
"""设置页 —— FFmpeg / 外观 / 更新 / 高级 四个分组 (单个平铺页面)。

设置页只做配置, 不通过底部「开始执行」触发任务 (``is_executable()``
恒为 False); 主题切换、减少动画与检查更新通过信号交给主窗口复用既有
能力 (theme.apply_theme / UpdateDialog), 不重复实现一套。
"""

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

from .._version import __version__
from ..utils import get_ffmpeg_path, get_ffprobe_path
from . import icons, theme
from .base_tab import BaseTab

#: (显示文案, theme 模块主题名)
_THEME_CHOICES = [("浅色", "light"), ("深色", "dark")]


class SettingsPage(BaseTab):
    """设置页: FFmpeg / 外观 / 更新 / 高级。"""

    #: 请求切换主题 (参数为 theme 模块主题名)
    theme_change_requested = pyqtSignal(str)
    #: 减少动画勾选变化
    reduced_motion_changed = pyqtSignal(bool)
    #: 请求检查更新 (主窗口打开既有 UpdateDialog)
    update_check_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("settings_page")

        self._build_ffmpeg_group()
        self._build_appearance_group()
        self._build_update_group()
        self._build_advanced_group()
        self.add_stretch()
        self._sync_from_theme()

    # ----------------------------------------------------------------
    # 分组
    # ----------------------------------------------------------------

    def _build_ffmpeg_group(self):
        group = self.add_group(
            "FFmpeg", "只读展示, 由程序自动定位内置或系统 FFmpeg")

        self.ffmpeg_path_edit = QLineEdit(get_ffmpeg_path())
        self.ffmpeg_path_edit.setReadOnly(True)
        self.ffmpeg_path_edit.setCursorPosition(0)
        group.addRow("ffmpeg", self.ffmpeg_path_edit)

        self.ffprobe_path_edit = QLineEdit(get_ffprobe_path())
        self.ffprobe_path_edit.setReadOnly(True)
        self.ffprobe_path_edit.setCursorPosition(0)
        group.addRow("ffprobe", self.ffprobe_path_edit)
        self.add_hint(
            group,
            "路径来自 utils.get_ffmpeg_path / get_ffprobe_path; "
            "如需更换 FFmpeg, 请替换 bin 目录下的可执行文件。",
            "info",
        )

    def _build_appearance_group(self):
        group = self.add_group("外观", "切换后立即生效, 并保存到本地配置")
        self.theme_combo = self.add_combo(
            group,
            "主题",
            [label for label, _name in _THEME_CHOICES],
            self._theme_label(theme.get_theme()),
            "亮色 / 深色主题",
        )
        self.reduced_motion_cb = self.add_checkbox(
            group,
            "减少动画",
            theme.reduced_motion(),
            "关闭页面切换与按钮按下动画, 降低低配设备占用",
        )
        self.add_hint(
            group,
            "主题与减少动画选择会写入本地配置, 下次启动自动恢复。",
            "info",
        )
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selected)
        self.reduced_motion_cb.toggled.connect(self._on_reduced_motion_toggled)

    def _build_update_group(self):
        group = self.add_group("更新", "从 GitHub Release 检查并安装新版本")
        self.version_label = QLabel(f"当前版本: v{__version__}")
        group.addRow("版本", self.version_label)

        self.check_btn = QPushButton("检查更新")
        self.check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_btn.setIcon(icons.icon("ri.download-2-line"))
        self.check_btn.clicked.connect(self.update_check_requested.emit)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        group.addRow(row)
        self.add_hint(
            group,
            "更新过程中请勿关闭程序; 安装完成后程序会自动重启。",
            "info",
        )

    def _build_advanced_group(self):
        group = self.add_group("高级", "占位: 后续版本提供高级配置")
        self.placeholder_label = QLabel("暂无可配置的高级选项")
        self.placeholder_label.setObjectName("muted_label")
        group.addRow(self.placeholder_label)
        self.add_hint(
            group,
            "日志级别、并发任务数等高级设置将在后续版本接入。",
            "tip",
        )

    # ----------------------------------------------------------------
    # 外观联动
    # ----------------------------------------------------------------

    @staticmethod
    def _theme_label(name: str) -> str:
        for label, theme_name in _THEME_CHOICES:
            if theme_name == name:
                return label
        return _THEME_CHOICES[0][0]

    def _sync_from_theme(self):
        """按当前主题 / 减少动画设置同步控件, 避免反向触发信号。"""
        blockers = (
            QSignalBlocker(self.theme_combo),
            QSignalBlocker(self.reduced_motion_cb),
        )
        self.theme_combo.setCurrentText(self._theme_label(theme.get_theme()))
        self.reduced_motion_cb.setChecked(theme.reduced_motion())
        del blockers

    def _on_theme_selected(self, index: int):
        if not 0 <= index < len(_THEME_CHOICES):
            return
        name = _THEME_CHOICES[index][1]
        if name != theme.get_theme():
            self.theme_change_requested.emit(name)

    def _on_reduced_motion_toggled(self, checked: bool):
        self.reduced_motion_changed.emit(checked)

    def on_theme_changed(self):
        """主题切换后同步图标颜色与外观控件勾选状态。"""
        self.check_btn.setIcon(icons.icon("ri.download-2-line"))
        self._sync_from_theme()

    # ----------------------------------------------------------------
    # 执行能力
    # ----------------------------------------------------------------

    def is_executable(self) -> bool:
        """设置页只做配置, 不通过底部「开始执行」触发任务。"""
        return False

    def build_args(self):
        raise NotImplementedError("设置页不参与执行")
