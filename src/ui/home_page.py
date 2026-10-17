# -*- coding: utf-8 -*-
"""首页 —— 快速压制 / 最近任务 / 最近输出 / 环境能力概览的骨架。

导航重做后首页成为「常用」分组的第一个入口:

- 快速压制入口通过 ``navigate_requested`` 通知主窗口跳转到视频压制页;
- 最近任务区占位, PR-06 接入 TaskCard 后替换;
- 最近输出占位, 后续接入真实输出记录;
- 环境能力概览展示 FFmpeg 路径与「待能力检测」占位 (真实探测后续接入)。

首页不参与执行 (``is_executable()`` 恒为 False), 底部「开始执行」禁用。
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from .._version import __version__
from ..utils import get_ffmpeg_path
from . import icons
from .base_tab import BaseTab


class HomePage(BaseTab):
    """首页: 骨架占位 + 快速入口。"""

    #: 请求跳转到功能页 (参数为页面名, 如 "视频压制")
    navigate_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("home_page")

        title = QLabel("小雪工具箱")
        title.setObjectName("brand_title")
        self._main_layout.addWidget(title)

        subtitle = QLabel(
            f"v{__version__} · 视频压制、媒体工具与素材检测的一站式工具箱")
        subtitle.setObjectName("muted_label")
        self._main_layout.addWidget(subtitle)

        self._build_quick_actions()
        self._build_recent_tasks()
        self._build_recent_outputs()
        self._build_environment()
        self.add_stretch()

    # ----------------------------------------------------------------
    # 分区
    # ----------------------------------------------------------------

    def _build_quick_actions(self):
        quick = self.add_group("快速开始")
        self._quick_encode_btn = QPushButton("快速压制")
        self._quick_encode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quick_encode_btn.setIcon(icons.icon("ri.play-fill"))
        self._quick_encode_btn.clicked.connect(
            lambda: self.navigate_requested.emit("视频压制"))
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._quick_encode_btn)
        row.addStretch(1)
        quick.addRow(row)
        self.add_hint(
            quick,
            "选择视频后进入「视频处理 → 视频压制」配置输出方案与压缩参数。",
            "info",
        )

    def _build_recent_tasks(self):
        recent = self.add_group(
            "最近任务", "任务卡片后续接入 (PR-06), 当前为占位区域")
        self._recent_tasks_placeholder = QLabel("暂无任务记录")
        self._recent_tasks_placeholder.setObjectName("muted_label")
        recent.addRow(self._recent_tasks_placeholder)
        self.add_hint(
            recent,
            "后续版本将在此展示最近任务的状态、进度与结果。",
            "info",
        )

    def _build_recent_outputs(self):
        outputs = self.add_group("最近输出", "后续接入真实输出记录")
        self._recent_outputs_placeholder = QLabel("暂无输出文件")
        self._recent_outputs_placeholder.setObjectName("muted_label")
        outputs.addRow(self._recent_outputs_placeholder)

    def _build_environment(self):
        env = self.add_group("环境与能力", "FFmpeg 自动定位, 硬件能力待检测")
        self._ffmpeg_path_label = QLabel(get_ffmpeg_path())
        self._ffmpeg_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._ffmpeg_path_label.setWordWrap(True)
        env.addRow("FFmpeg 路径", self._ffmpeg_path_label)

        self._capability_label = QLabel("待能力检测")
        self._capability_label.setObjectName("muted_label")
        env.addRow("硬件编码能力", self._capability_label)
        self.add_hint(
            env,
            "硬件编码器 (NVENC / QSV / AMF) 真实可用性将在后续版本启动时探测。",
            "info",
        )

    # ----------------------------------------------------------------
    # 主题联动 / 执行能力
    # ----------------------------------------------------------------

    def on_theme_changed(self):
        """主题切换后刷新快速入口图标颜色。"""
        self._quick_encode_btn.setIcon(icons.icon("ri.play-fill"))

    def is_executable(self) -> bool:
        """首页不参与执行。"""
        return False
