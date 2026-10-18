# -*- coding: utf-8 -*-
"""首页 —— 快速压制 / 最近任务 / 最近输出 / 环境能力概览。

首页是「常用」分组的第一个入口:

- 快速压制入口通过 ``navigate_requested`` 通知主窗口跳转到视频压制页;
- 「最近任务」记录真实任务结果: 主窗口 ``_on_task_result`` 通过
  :meth:`add_task_record` 转发 command / status / message / outputs,
  最多保留 :data:`MAX_RECENT_RECORDS` 条, 用任务卡渲染;
- 「最近输出」记录真实产出路径, 通过 :meth:`add_recent_outputs` 追加;
- 「一键清空」同时清空最近任务与最近输出, 两个列表都空时按钮禁用;
- 环境能力概览展示 FFmpeg 路径与后台能力探测结果 (M3.1), 以及平台能力
  三行: AviSynth 兼容字幕 / 自动更新 / VideoToolbox (M4.4)。

首页不参与执行 (``is_executable()`` 恒为 False), 底部「开始执行」禁用。
首页也不发起探测: 探测由主窗口在窗口显示后启动, 结果通过
:meth:`update_capabilities` 推送过来, 首页只做展示; 平台能力三行同样
只读 :func:`src.platform.capabilities.platform_capabilities` 的快照,
不在 UI 层直接判断运行平台。
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

import json

from .._version import __version__
from ..capabilities import (
    KEY_ENCODERS,
    available_key_encoders,
    caps_ready,
    get_capabilities,
    nvenc_available,
    short_probe_error,
)
from ..platform import platform_paths
from ..platform.capabilities import platform_capabilities
from ..utils import get_ffmpeg_path
from . import icons
from .base_tab import BaseTab
from .task_card import TaskArea
from .task_details import TaskDetailsDialog, open_path_in_file_manager
from .task_state import TaskStatus, TaskViewState

#: 首页「最近任务 / 最近输出」各自最多保留的条数
MAX_RECENT_RECORDS = 10

#: 最近记录持久化文件名 (存于 PlatformPaths.data_dir)
RECORDS_FILENAME = "recent_records.json"

#: 平台能力三行文案 (M4.4)
PENDING_TEXT = "待检测"
AVISYNTH_AVAILABLE_TEXT = "可用"
AVISYNTH_UNAVAILABLE_TEXT = "不可用"
SELF_UPDATE_AVAILABLE_TEXT = "可用"
SELF_UPDATE_CHECK_ONLY_TEXT = "仅检查更新"
VIDEOTOOLBOX_AVAILABLE_TEXT = "可用"
VIDEOTOOLBOX_UNAVAILABLE_TEXT = "不可用"
VIDEOTOOLBOX_NOT_MACOS_TEXT = "非 macOS"


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
        self._wire_record_actions()
        self._load_records()
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

        # M4.4: 平台能力三行 (平台/探测两路来源, 文案见 _refresh_platform_rows)
        self._avisynth_label = QLabel()
        self._avisynth_label.setObjectName("muted_label")
        env.addRow("AviSynth 兼容字幕", self._avisynth_label)

        self._self_update_label = QLabel()
        self._self_update_label.setObjectName("muted_label")
        env.addRow("自动更新", self._self_update_label)

        self._videotoolbox_label = QLabel()
        self._videotoolbox_label.setObjectName("muted_label")
        env.addRow("VideoToolbox", self._videotoolbox_label)

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
        self._save_records()
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
        self._save_records()

    def clear_records(self):
        """一键清空「最近任务」与「最近输出」两个列表。"""
        self._task_records = []
        self._output_paths = []
        self._refresh_records()
        self._save_records()

    def _wire_record_actions(self):
        """接通任务卡的详情 / 打开文件夹 (修复「详情点击无效」)。"""
        self._recent_tasks_area.details_requested.connect(
            self._show_task_details)
        self._recent_tasks_area.open_folder_requested.connect(
            self._open_containing_folder)

    def _show_task_details(self, task_id: str):
        state = self._recent_tasks_area.state_for(task_id)
        if state is None:
            for record in self._task_records:
                if record.task_id == task_id:
                    state = record
                    break
        dialog = TaskDetailsDialog(state, self)
        dialog.exec()

    def _open_containing_folder(self, path: str):
        open_path_in_file_manager(path)

    # ----------------------------------------------------------------
    # 持久化 (重启后保留最近任务/输出)
    # ----------------------------------------------------------------

    def records_file(self):
        """最近记录的持久化文件路径 (data_dir 不可用时返回 None)。"""
        try:
            return platform_paths().data_dir / RECORDS_FILENAME
        except Exception:  # pragma: no cover - 路径解析极端失败
            return None

    def _load_records(self):
        """启动时恢复最近任务与输出 (损坏/缺失时静默忽略)。"""
        path = self.records_file()
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        records = []
        for item in list(payload.get("tasks") or [])[:MAX_RECENT_RECORDS]:
            try:
                status = TaskStatus.coerce(item.get("status"))
            except (ValueError, AttributeError):
                continue
            records.append(TaskViewState(
                task_id=str(item.get("task_id") or f"recent-task-{len(records) + 1}"),
                title=str(item.get("title") or "任务"),
                status=status,
                message=str(item.get("message") or ""),
                output_path=str(item.get("output_path") or ""),
            ))
        self._task_records = records
        self._output_paths = [
            str(item) for item in (payload.get("outputs") or []) if item
        ][:MAX_RECENT_RECORDS]
        self._record_seq = max(self._record_seq, len(records))

    def _save_records(self):
        """把最近任务/输出写入 data_dir (失败静默, 不影响主流程)。"""
        path = self.records_file()
        if path is None:
            return
        payload = {
            "tasks": [
                {
                    "task_id": record.task_id,
                    "title": record.title,
                    "status": record.status.value,
                    "message": record.message,
                    "output_path": record.output_path,
                }
                for record in self._task_records
            ],
            "outputs": list(self._output_paths),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

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
                continue
            child = item.layout()
            if child is not None:
                while child.count():
                    sub_item = child.takeAt(0)
                    sub_widget = sub_item.widget()
                    if sub_widget is not None:
                        sub_widget.deleteLater()
                child.deleteLater()
        for path in self._output_paths:
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(path)
            label.setObjectName("muted_label")
            label.setWordWrap(True)
            label.setToolTip(path)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(label, 1)

            open_btn = QPushButton("打开文件夹")
            open_btn.setObjectName("output_folder_btn")
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.setIcon(icons.secondary("ri.folder-open-line"))
            open_btn.setToolTip("打开该产出所在目录")
            open_btn.clicked.connect(
                lambda _checked=False, p=path: self._open_containing_folder(p))
            row.addWidget(open_btn, 0)
            self._recent_outputs_box.addLayout(row)
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
        self._set_platform_rows_pending()

    def _set_platform_rows_pending(self):
        """平台能力三行统一显示「待检测」(探测完成前不臆断可用性)。"""
        for label in (self._avisynth_label, self._self_update_label,
                      self._videotoolbox_label):
            label.setText(PENDING_TEXT)
            label.setToolTip("能力探测完成后显示实际可用性")

    def _refresh_platform_rows(self):
        """按平台能力快照刷新三行 (M4.4)。

        * AviSynth 兼容字幕: 可用 / 不可用 (Windows + 依赖 DLL);
        * 自动更新: 可用 / 仅检查更新 (非 Windows 只能在浏览器下载);
        * VideoToolbox: 可用 / 不可用 / 非 macOS (macOS 专属硬件编码)。
        """
        state = platform_capabilities()

        avisynth = bool(getattr(state, "avisynth_available", False))
        self._avisynth_label.setText(
            AVISYNTH_AVAILABLE_TEXT if avisynth else AVISYNTH_UNAVAILABLE_TEXT)
        self._avisynth_label.setToolTip(
            "已检测到 AviSynth + VSFilter, 压制页可使用「兼容模式 (字幕)」"
            if avisynth else
            "当前平台不使用 AviSynth 渲染字幕, 压制页不显示兼容模式选项; "
            "普通字幕烧录走 FFmpeg 内置 libass")

        self_update = bool(getattr(state, "self_update_available", False))
        self._self_update_label.setText(
            SELF_UPDATE_AVAILABLE_TEXT if self_update
            else SELF_UPDATE_CHECK_ONLY_TEXT)
        self._self_update_label.setToolTip(
            "支持在程序内下载并安装新版本"
            if self_update else
            "仅提示新版本, 需到 Release 页面手动下载安装")

        if not getattr(state, "is_macos", False):
            self._videotoolbox_label.setText(VIDEOTOOLBOX_NOT_MACOS_TEXT)
            self._videotoolbox_label.setToolTip(
                "VideoToolbox 是 macOS 专属硬件编码, 当前平台不适用")
        elif getattr(state, "videotoolbox_available", False):
            self._videotoolbox_label.setText(VIDEOTOOLBOX_AVAILABLE_TEXT)
            self._videotoolbox_label.setToolTip(
                "已探测到 h264_videotoolbox / hevc_videotoolbox 硬件编码器")
        else:
            self._videotoolbox_label.setText(VIDEOTOOLBOX_UNAVAILABLE_TEXT)
            self._videotoolbox_label.setToolTip(
                "macOS 但未探测到 VideoToolbox 编码器")

    def update_capabilities(self, caps):
        """接收主窗口推送的探测结果并刷新「环境与能力」区。"""
        if caps is None:
            self.set_probing()
            return

        # M4.4: 平台能力三行与 FFmpeg 探测解耦, 有探测结果就一并刷新
        self._refresh_platform_rows()

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
