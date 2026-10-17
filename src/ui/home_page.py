# -*- coding: utf-8 -*-
"""首页 —— 快速压制 / 最近任务 / 最近输出 / 环境能力概览。

首页是「常用」分组的第一个入口; PR-06 把「最近任务」占位替换为
由 ``MOCK_TASKS`` 渲染的 TaskArea (示例数据):

- 最近任务区展示 5 种状态的任务卡片, 取消只在本地把卡片置为「已取消」,
  不接后端、不创建 TaskRunner;
- 快速压制入口通过 ``navigate_requested`` 通知主窗口跳转到视频压制页;
- 最近输出占位, 后续接入真实输出记录;
- 环境能力概览展示 FFmpeg 路径, 以及后台能力探测的结果 (M3.1):
  检测中 / 关键编码器可用数 / NVENC 可用性 / 失败原因。

首页不参与执行 (``is_executable()`` 恒为 False), 底部「开始执行」禁用。
首页也不发起探测: 探测由主窗口在窗口显示后启动, 结果通过
:meth:`update_capabilities` 推送过来, 首页只做展示。
"""

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from .._version import __version__
from ..capabilities import (
    KEY_ENCODERS,
    available_key_encoders,
    caps_ready,
    get_capabilities,
    nvenc_available,
    short_probe_error,
)
from ..utils import get_ffmpeg_path
from . import icons
from .base_tab import BaseTab
from .mock_data import MOCK_TASKS
from .task_card import TaskArea
from .task_state import TaskStatus


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
            "最近任务",
            "示例数据: 展示任务卡片的 5 种状态 "
            "(执行中 / 成功 / 部分完成 / 失败 / 已取消)",
        )
        self._recent_tasks_placeholder = QLabel(
            "示例数据 · 仅用于演示任务卡样式, 不接入真实任务")
        self._recent_tasks_placeholder.setObjectName("muted_label")
        recent.addRow(self._recent_tasks_placeholder)

        # 首页独立任务区, 与主窗口底部执行区互不影响
        self._mock_tasks = [replace(task) for task in MOCK_TASKS]
        self._recent_tasks_area = TaskArea()
        self._recent_tasks_area.set_tasks(self._mock_tasks)
        self._recent_tasks_area.cancel_requested.connect(
            self._on_mock_task_cancel)
        recent.addRow(self._recent_tasks_area)

        self.add_hint(
            recent,
            "以上为演示任务: 点击「取消」只在本地把该卡置为「已取消」, "
            "不会影响真实任务。",
            "info",
        )

    def _build_recent_outputs(self):
        outputs = self.add_group("最近输出", "后续接入真实输出记录")
        self._recent_outputs_placeholder = QLabel("暂无输出文件")
        self._recent_outputs_placeholder.setObjectName("muted_label")
        outputs.addRow(self._recent_outputs_placeholder)

    def _build_environment(self):
        env = self.add_group(
            "环境与能力", "启动后后台探测, 不阻塞使用, 也不影响已有功能")
        self._ffmpeg_path_label = QLabel(get_ffmpeg_path())
        self._ffmpeg_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._ffmpeg_path_label.setWordWrap(True)
        env.addRow("FFmpeg 路径", self._ffmpeg_path_label)

        self._capability_label = QLabel()
        self._capability_label.setObjectName("muted_label")
        self._capability_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._capability_label.setWordWrap(True)
        env.addRow("检测状态", self._capability_label)

        self._encoder_label = QLabel()
        self._encoder_label.setObjectName("muted_label")
        env.addRow("编码器", self._encoder_label)

        self._nvenc_label = QLabel()
        self._nvenc_label.setObjectName("muted_label")
        env.addRow("NVENC", self._nvenc_label)

        self.set_probing()
        self.add_hint(
            env,
            "关键编码器指压制页可选的 CPU / NVENC / QSV / AMF 共 "
            f"{len(KEY_ENCODERS)} 项; 真实可用性以本次检测结果为准, "
            "其它编码器仍可在「自定义」中使用。",
            "info",
        )
        # 若本次进程已有探测结果 (例如从设置页返回后重建首页), 直接展示
        if caps_ready():
            caps = get_capabilities()
            if caps is not None:
                self.update_capabilities(caps)

    # ----------------------------------------------------------------
    # 环境与能力展示 (M3.1)
    # ----------------------------------------------------------------

    def set_probing(self):
        """探测进行中: 只改展示文案, 不禁用任何功能。"""
        self._capability_label.setText("正在检测…")
        self._capability_label.setToolTip("")
        self._encoder_label.setText("待检测")
        self._encoder_label.setToolTip("")
        self._nvenc_label.setText("未检测到")
        self._nvenc_label.setToolTip("")

    def update_capabilities(self, caps):
        """接收主窗口推送的探测结果并刷新「环境与能力」区。"""
        if caps is None:
            self.set_probing()
            return

        if getattr(caps, "probe_error", None):
            self._capability_label.setText(
                f"检测失败: {short_probe_error(caps)}")
            # 完整原因放 tooltip, 状态行只展示截断后的短文本
            self._capability_label.setToolTip(str(caps.probe_error))
            self._encoder_label.setText("未知")
            self._encoder_label.setToolTip("能力探测失败, 无法确定编码器可用性")
            self._nvenc_label.setText("未检测到")
            self._nvenc_label.setToolTip("能力探测失败, 无法确定 NVENC 可用性")
            return

        version = getattr(caps, "version", "") or "未知版本"
        self._capability_label.setText(f"检测完成 · FFmpeg {version}")
        self._capability_label.setToolTip(str(getattr(caps, "ffmpeg_path", "")))

        available = available_key_encoders(caps)
        self._encoder_label.setText(
            f"{len(available)}/{len(KEY_ENCODERS)} 可用")
        missing = [name for name in KEY_ENCODERS if name not in available]
        self._encoder_label.setToolTip(
            ("不可用: " + ", ".join(missing)) if missing else "全部可用")

        if nvenc_available(caps):
            self._nvenc_label.setText("可用")
            self._nvenc_label.setToolTip("检测到 h264_nvenc / hevc_nvenc 等 NVENC 编码器")
        else:
            self._nvenc_label.setText("不可用")
            self._nvenc_label.setToolTip("FFmpeg 未提供 NVENC 编码器 (无 N 卡或构建未启用)")

    # ----------------------------------------------------------------
    # 示例任务交互 / 主题联动 / 执行能力
    # ----------------------------------------------------------------

    def _on_mock_task_cancel(self, task_id: str):
        """示例任务取消: 只在本地保留结果, 不接后端、不启动 TaskRunner。"""
        for index, task in enumerate(self._mock_tasks):
            if task.task_id != task_id:
                continue
            updated = replace(
                task,
                status=TaskStatus.CANCELLED,
                message="已取消（示例数据）",
                speed=0.0,
                eta_sec=None,
            )
            self._mock_tasks[index] = updated
            self._recent_tasks_area.update_task(updated)
            return

    def on_theme_changed(self):
        """主题切换后刷新快速入口图标颜色。"""
        self._quick_encode_btn.setIcon(icons.icon("ri.play-fill"))

    def is_executable(self) -> bool:
        """首页不参与执行。"""
        return False
