# -*- coding: utf-8 -*-
"""首页 —— 快速压制 / 最近任务 / 最近输出 / 环境能力概览。

首页是「常用」分组的第一个入口:

- 快速压制入口通过 ``navigate_requested`` 通知主窗口跳转到视频压制页;
- 「最近任务」记录真实任务结果: 主窗口 ``_on_task_result`` 通过
  :meth:`add_task_record` 转发 command / status / message / outputs,
  最多保留 :data:`MAX_RECENT_RECORDS` 条, 用任务卡渲染;
- 「最近输出」记录真实产出路径, 通过 :meth:`add_recent_outputs` 追加;
- 「一键清空」同时清空最近任务与最近输出, 两个列表都空时按钮禁用;
- 环境能力概览展示 FFmpeg 路径与后台能力探测结果 (M3.1)。

首页不参与执行 (``is_executable()`` 恒为 False), 底部「开始执行」禁用。
首页也不发起探测: 探测由主窗口在窗口显示后启动, 结果通过
:meth:`update_capabilities` 推送过来, 首页只做展示。
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

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
from .task_card import TaskArea
from .task_state import TaskStatus, TaskViewState

#: 首页「最近任务 / 最近输出」各自最多保留的条数
MAX_RECENT_RECORDS = 10


class HomePage(BaseTab):
    """首页: 快速入口 + 真实任务/输出记录 + 环境能力概览。"""

    #: 请求跳转到功能页 (参数为页面名, 如 "视频压制")
    navigate_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("home_page")

        #: 真实任务记录 (最新在前, TaskViewState)
        self._task_records = []
        #: 真实输出路径 (最新在前, 去重)
        self._output_paths = []
        self._record_seq = 0

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
        self._refresh_records()

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
            "最近任务", f"完成的任务会记录在这里, 最多保留 {MAX_RECENT_RECORDS} 条")

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._clear_records_btn = QPushButton("一键清空")
        self._clear_records_btn.setObjectName("clear_btn")
        self._clear_records_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_records_btn.setIcon(
            icons.secondary("ri.delete-bin-7-line"))
        self._clear_records_btn.setToolTip(
            "清空首页的「最近任务」与「最近输出」记录")
        self._clear_records_btn.clicked.connect(self.clear_records)
        toolbar.addWidget(self._clear_records_btn)
        toolbar.addStretch(1)
        recent.addRow(toolbar)

        self._recent_tasks_placeholder = QLabel("暂无任务记录")
        self._recent_tasks_placeholder.setObjectName("muted_label")
        recent.addRow(self._recent_tasks_placeholder)

        # 首页独立任务区, 与主窗口底部执行区互不影响
        self._recent_tasks_area = TaskArea()
        recent.addRow(self._recent_tasks_area)

    def _build_recent_outputs(self):
        outputs = self.add_group(
            "最近输出", f"任务产出的文件会记录在这里, 最多保留 {MAX_RECENT_RECORDS} 条")
        self._recent_outputs_placeholder = QLabel("暂无输出文件")
        self._recent_outputs_placeholder.setObjectName("muted_label")
        outputs.addRow(self._recent_outputs_placeholder)

        # 每行一个输出路径, 动态重建
        self._recent_outputs_box = QVBoxLayout()
        self._recent_outputs_box.setSpacing(4)
        outputs.addRow(self._recent_outputs_box)

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
    # 最近任务 / 最近输出记录 (真实任务结果, 由主窗口转发)
    # ----------------------------------------------------------------

    @property
    def task_records(self):
        """最近任务记录 (TaskViewState 列表, 最新在前)。"""
        return list(self._task_records)

    @property
    def recent_outputs(self):
        """最近输出路径 (最新在前, 已去重)。"""
        return list(self._output_paths)

    def add_task_record(self, command, status, message="", outputs=()):
        """追加一条真实任务记录 (最新在前, 最多 MAX_RECENT_RECORDS 条)。"""
        view_status = TaskStatus.coerce(getattr(status, "value", status))
        output_list = [str(path) for path in (outputs or ()) if path]
        self._record_seq += 1
        record = TaskViewState(
            task_id=f"recent-task-{self._record_seq}",
            title=str(command or "任务"),
            status=view_status,
            message=str(message or ""),
            output_path=output_list[0] if output_list else "",
        )
        self._task_records.insert(0, record)
        self._task_records = self._task_records[:MAX_RECENT_RECORDS]
        self._refresh_records()
        return record

    def add_recent_outputs(self, paths):
        """追加真实产出路径 (最新在前, 去重, 最多 MAX_RECENT_RECORDS 条)。"""
        new_paths = [str(path) for path in (paths or ()) if path]
        if not new_paths:
            return
        merged = []
        for path in list(reversed(new_paths)) + self._output_paths:
            if path not in merged:
                merged.append(path)
        self._output_paths = merged[:MAX_RECENT_RECORDS]
        self._refresh_records()

    def clear_records(self):
        """一键清空「最近任务」与「最近输出」两个列表。"""
        self._task_records = []
        self._output_paths = []
        self._refresh_records()

    def _refresh_records(self):
        """按当前记录刷新任务卡区/输出行/空态与清空按钮可用性。"""
        self._recent_tasks_area.set_tasks(list(self._task_records))
        self._recent_tasks_area.setVisible(bool(self._task_records))
        self._recent_tasks_placeholder.setVisible(not self._task_records)

        while self._recent_outputs_box.count():
            item = self._recent_outputs_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for path in self._output_paths:
            label = QLabel(path)
            label.setObjectName("muted_label")
            label.setWordWrap(True)
            label.setToolTip(path)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._recent_outputs_box.addWidget(label)
        self._recent_outputs_placeholder.setVisible(not self._output_paths)

        self._clear_records_btn.setEnabled(
            bool(self._task_records or self._output_paths))

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
    # 主题联动 / 执行能力
    # ----------------------------------------------------------------

    def on_theme_changed(self):
        """主题切换后刷新快速入口与清空按钮图标颜色。"""
        self._quick_encode_btn.setIcon(icons.icon("ri.play-fill"))
        self._clear_records_btn.setIcon(
            icons.secondary("ri.delete-bin-7-line"))

    def is_executable(self) -> bool:
        """首页不参与执行。"""
        return False
