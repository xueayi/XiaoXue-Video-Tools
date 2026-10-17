# -*- coding: utf-8 -*-
"""设置页 —— FFmpeg / 外观 / 更新 / 高级 四个分组 (单个平铺页面)。

设置页只做配置, 不通过底部「开始执行」触发任务 (``is_executable()``
恒为 False); 主题切换、减少动画与检查更新通过信号交给主窗口复用既有
能力 (theme.apply_theme / UpdateDialog), 不重复实现一套。

FFmpeg 分组 (M3.1): 展示自动定位到的 ffmpeg/ffprobe 路径与后台能力探测
状态; 「重新检测」只发出 :attr:`capability_refresh_requested` 请求, 由
主窗口统一创建后台探测线程并刷新首页/设置页两处展示, 本页不直接跑探测。
"""

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton

from .._version import __version__
from ..capabilities import (
    KEY_ENCODERS,
    available_key_encoders,
    caps_ready,
    get_capabilities,
    nvenc_available,
    short_probe_error,
)
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
    #: 请求重新探测 FFmpeg 能力 (主窗口创建后台线程, 刷新首页/设置页)
    capability_refresh_requested = pyqtSignal()

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

        # 能力检测 (M3.1): 状态行 + 重新检测按钮, 探测在后台线程执行
        self._cap_status_label = QLabel()
        self._cap_status_label.setObjectName("muted_label")
        self._cap_status_label.setWordWrap(True)
        group.addRow("检测状态", self._cap_status_label)

        self._cap_detail_label = QLabel()
        self._cap_detail_label.setObjectName("muted_label")
        self._cap_detail_label.setWordWrap(True)
        group.addRow("检测结果", self._cap_detail_label)

        self.recheck_btn = QPushButton("重新检测")
        self.recheck_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recheck_btn.setIcon(icons.icon("ri.refresh-line"))
        self.recheck_btn.clicked.connect(
            self.capability_refresh_requested.emit)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.recheck_btn)
        row.addStretch(1)
        group.addRow(row)

        self.set_probing()
        self.add_hint(
            group,
            "路径来自 utils.get_ffmpeg_path / get_ffprobe_path; "
            "能力检测在后台执行, 不阻塞程序使用。",
            "info",
        )
        # 本次进程已探测过 (例如设置页在后台探测完成后才被切换到) 时直接展示
        if caps_ready():
            caps = get_capabilities()
            if caps is not None:
                self.update_capabilities(caps)

    # ----------------------------------------------------------------
    # FFmpeg 能力检测展示 (M3.1)
    # ----------------------------------------------------------------

    def set_probing(self):
        """探测进行中: 状态文案 + 禁用「重新检测」, 不影响其他功能。"""
        self._cap_status_label.setText("正在检测…")
        self._cap_status_label.setToolTip("")
        self._cap_detail_label.setText("后台探测 FFmpeg 能力, 不阻塞使用")
        self._cap_detail_label.setToolTip("")
        self.recheck_btn.setEnabled(False)

    def update_capabilities(self, caps):
        """接收主窗口推送的探测结果并刷新 FFmpeg 分组 (并恢复按钮)。"""
        self.recheck_btn.setEnabled(True)
        if caps is None:
            self.set_probing()
            return

        path = str(getattr(caps, "ffmpeg_path", "") or "")
        if path:
            self.ffmpeg_path_edit.setText(path)
            self.ffmpeg_path_edit.setCursorPosition(0)

        if getattr(caps, "probe_error", None):
            self._cap_status_label.setText(
                f"检测失败: {short_probe_error(caps)}")
            self._cap_status_label.setToolTip(str(caps.probe_error))
            self._cap_detail_label.setText("编码器与 NVENC 可用性未知")
            self._cap_detail_label.setToolTip(str(caps.probe_error))
            return

        version = getattr(caps, "version", "") or "未知版本"
        self._cap_status_label.setText(f"检测完成 · FFmpeg {version}")
        self._cap_status_label.setToolTip(path)
        available = available_key_encoders(caps)
        nvenc = "可用" if nvenc_available(caps) else "不可用"
        self._cap_detail_label.setText(
            f"关键编码器 {len(available)}/{len(KEY_ENCODERS)} 可用 · "
            f"NVENC {nvenc}")
        self._cap_detail_label.setToolTip(
            ("编码器: " + ", ".join(sorted(caps.encoders)))
            if caps.encoders else "未解析到编码器列表")

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
        self.recheck_btn.setIcon(icons.icon("ri.refresh-line"))
        self._sync_from_theme()

    # ----------------------------------------------------------------
    # 执行能力
    # ----------------------------------------------------------------

    def is_executable(self) -> bool:
        """设置页只做配置, 不通过底部「开始执行」触发任务。"""
        return False

    def build_args(self):
        raise NotImplementedError("设置页不参与执行")
