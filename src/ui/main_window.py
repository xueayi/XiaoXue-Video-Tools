# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 功能页面 + 任务卡执行区 + 可折叠日志。"""

import os
import webbrowser
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QApplication, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QStatusBar,
    QDialog, QLabel, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QIcon, QShortcut, QKeySequence, QPixmap

from .. import updater
from ..gui_config import get_icon_path
from ..utils import get_base_dir
from ..process.progress import FFmpegProgressParser, ProgressEvent

from . import theme
from . import icons
from .base_tab import CONTENT_MAX_WIDTH
from .sidebar import Sidebar
from .collapsible_log import CollapsibleLog
from .error_card import ErrorCard, error_info_from_user
from .task_card import TaskArea
from .task_state import TaskStatus as ViewTaskStatus
from .update_dialog import UpdateDialog, UpdateWorker
from .task_runner import TaskRunner
from .animations import AnimatedStackedWidget, button_press_anim, status_flash
from .home_page import HomePage
from .settings_page import SettingsPage
from ..ffmpeg.errors import classify as classify_ffmpeg_error
from ..task.result import TaskResult
from ..task.status import TaskStatus as ResultStatus
from .tabs import (
    EncodeTab, ReplaceAudioTab, RemuxTab, QcTab,
    MediaProbeTab, ExtractAvTab, ImageConvertTab,
    FolderCreatorTab, BatchRenameTab, HelpTab,
)

from ..executors import (
    execute_encode, execute_replace_audio, execute_extract_av,
    execute_remux, execute_image_convert, execute_folder_creator,
    execute_batch_rename, execute_qc,
    execute_help, execute_media_probe,
)
from .._version import __version__ as _VERSION

_REPO_URL = "https://github.com/xueayi/XiaoXue-Video-Tools"


@dataclass(frozen=True)
class _ProgressView:
    """把进程层 :class:`ProgressEvent` 适配为任务卡接受的 ProgressInfo 形状。

    任务卡 ``TaskArea.update_metrics`` 只读取 ``percent`` / ``speed`` /
    ``eta_sec`` / ``frame`` 字段；``percent`` 与 ``eta_sec`` 允许 None
    （分别表示不确定进度 / 未知剩余时间）。
    """

    percent: Optional[float] = None
    speed: float = 0.0
    eta_sec: Optional[float] = None
    frame: int = 0

    @classmethod
    def from_event(cls, event: ProgressEvent) -> "_ProgressView":
        return cls(
            percent=event.percent,
            speed=event.speed,
            eta_sec=event.eta_seconds,
            frame=event.frame,
        )


#: deprecated 旧 bool 通道兜底: 交给错误分类的最近日志块数量
_ERROR_CONTEXT_CHUNKS = 40

#: 执行层 4 态结果 -> UI 视图层 6 态中的终态。
#: 两个枚举刻意分离 (执行层没有 QUEUED/RUNNING), 只在此处做一次映射。
_RESULT_TO_VIEW_STATUS = {
    ResultStatus.SUCCESS: ViewTaskStatus.SUCCESS,
    ResultStatus.FAILED: ViewTaskStatus.FAILED,
    ResultStatus.CANCELLED: ViewTaskStatus.CANCELLED,
    ResultStatus.PARTIAL: ViewTaskStatus.PARTIAL,
}

#: 业务键 (Tab.command_name) -> executor 的映射。
#: 首页/设置页没有命令名, 因此不在其中 (执行按钮对它们禁用)。
_EXECUTORS = {
    "视频压制": execute_encode,
    "音频替换": execute_replace_audio,
    "音视频抽取": execute_extract_av,
    "封装转换": execute_remux,
    "媒体元数据检测": execute_media_probe,
    "图片转换": execute_image_convert,
    "素材质量检测": execute_qc,
    "文件夹创建": execute_folder_creator,
    "批量重命名": execute_batch_rename,
    "使用说明": execute_help,
}


class _CenteredColumnWidget(QWidget):
    """宽度上限受限的内容列容器: 列宽 = min(max_width, 可用宽度), 水平居中。

    用于让底部按钮区/仪表盘/日志区与上方页面内容列保持同宽对齐。
    """

    def __init__(self, max_width: int, margins, spacing: int, parent=None):
        super().__init__(parent)
        self._max_width = max_width

        outer = QHBoxLayout(self)
        # 右侧预留 8px (与页面滚动区常驻滚动条同宽), 居中基准一致
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(0)

        self._column = QWidget()
        self._column_layout = QVBoxLayout(self._column)
        self._column_layout.setContentsMargins(*margins)
        self._column_layout.setSpacing(spacing)

        outer.addStretch(1)
        outer.addWidget(self._column)
        outer.addStretch(1)

        # 列的定宽会经布局抬高容器最小宽度导致窗口无法收窄,
        # 显式给出较小的最小尺寸打断该反馈, 列宽在 resizeEvent 中重算
        self.setMinimumSize(240, 100)

    def column(self) -> QWidget:
        return self._column

    def column_layout(self) -> QVBoxLayout:
        return self._column_layout

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 列宽确定性计算, 两侧 stretch 均分剩余空间实现居中
        available = max(self.width() - 8, 100)
        self._column.setFixedWidth(min(self._max_width, available))



def _tab_defs():
    """功能页注册表: (分组标题, [(页面名, 图标名, 页面工厂), ...])。

    侧边栏按分组平铺渲染 (无二级 Tab 容器); 首页/设置页为新增入口,
    其中首页与设置页不参与执行。
    """
    return [
        ("常用", [
            ("首页", "ri.home-line", HomePage),
        ]),
        ("视频处理", [
            ("视频压制", "ri.film-line", EncodeTab),
            ("音频替换", "ri.music-2-line", ReplaceAudioTab),
            ("音视频抽取", "ri.file-transfer-line", ExtractAvTab),
        ]),
        ("格式与媒体", [
            ("封装转换", "ri.exchange-line", RemuxTab),
            ("媒体元数据检测", "ri.file-info-line", MediaProbeTab),
            ("图片转换", "ri.image-line", ImageConvertTab),
        ]),
        ("质量与批量", [
            ("素材质量检测", "ri.file-search-line", QcTab),
            ("文件夹创建", "ri.folder-add-line", FolderCreatorTab),
            ("批量重命名", "ri.file-edit-line", BatchRenameTab),
        ]),
        ("系统", [
            ("设置", "ri.settings-3-line", SettingsPage),
            ("使用说明", "ri.question-line", HelpTab),
        ]),
    ]


class MainWindow(QMainWindow):
    """应用程序主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小雪工具箱")
        self.setMinimumSize(960, 640)
        self.resize(1080, 760)

        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self._runner = None
        self._btn_anim = None
        self._update_dialog = None
        self._check_worker = None
        # 当前任务标题 (结果日志用, _on_execute 时写入)
        self._task_caption = ""
        # 当前选中页索引 (点击即生效, 不等切换动画播完)
        self._current_page_index = -1

        self._build_menu_bar()
        self._build_central()
        self._build_status_bar()
        self._build_shortcuts()
        self._restore_geometry()

        # M2.4: 结构化进度解析器 (src/process/progress) —— 喂 ffmpeg -progress
        # 的 stdout 行, 块结束事件经 _on_progress_line 适配后驱动任务卡。
        self._ffmpeg_parser = FFmpegProgressParser()

        self._sidebar.setCurrentRow(0)

        updater.cleanup_staging(get_base_dir())
        QTimer.singleShot(2500, self._silent_update_check)

    # ================================================================
    # 检查更新
    # ================================================================

    def _show_update_dialog(self, manual: bool):
        """打开更新对话框; manual=True 时模态 (用户主动), 否则非模态。"""
        dlg = UpdateDialog(get_base_dir(), release=None, parent=self)
        dlg.install_requested.connect(self._apply_update_and_quit)
        if manual:
            dlg.exec()
        else:
            dlg.show()
            self._update_dialog = dlg

    def _silent_update_check(self):
        """启动后静默检查一次; 开发版/已跳过的版本不提示。

        设置环境变量 XIAOXUE_NO_UPDATE_CHECK=1 可完全禁用 (测试/调试用)。
        """
        if os.environ.get("XIAOXUE_NO_UPDATE_CHECK"):
            return
        if updater.is_dev_version(_VERSION):
            return
        self._check_worker = UpdateWorker("check", get_base_dir())
        self._check_worker.checked.connect(self._on_silent_checked)
        self._check_worker.start()

    def _on_silent_checked(self, release):
        if release is None:
            return
        if release.version == updater.get_skip_version():
            return
        dlg = UpdateDialog(get_base_dir(), release=release, parent=self)
        dlg.install_requested.connect(self._apply_update_and_quit)
        dlg.show()
        self._update_dialog = dlg

    def _apply_update_and_quit(self):
        """更新器已拉起, 主窗口退出交由其完成替换与重启。"""
        self.close()

    # ================================================================
    # 菜单栏
    # ================================================================

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        view_menu = menu_bar.addMenu("视图")
        self._theme_action = QAction("深色模式", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(theme.get_theme() == "dark")
        self._theme_action.triggered.connect(self._on_theme_toggle)
        view_menu.addAction(self._theme_action)

        motion_action = QAction("减少动画", self)
        self._motion_action = motion_action
        motion_action.setCheckable(True)
        motion_action.setChecked(theme.reduced_motion())
        motion_action.triggered.connect(self._on_motion_action_triggered)
        view_menu.addAction(motion_action)

        about_menu = menu_bar.addMenu("关于")
        update_act = QAction("检查更新", self)
        update_act.setIcon(icons.secondary("ri.download-2-line"))
        update_act.triggered.connect(
            lambda: self._show_update_dialog(manual=True))
        about_menu.addAction(update_act)
        about_act = QAction("关于小雪工具箱", self)
        about_act.triggered.connect(self._show_about)
        about_menu.addAction(about_act)

        help_menu = menu_bar.addMenu("帮助文档")
        _links = [
            ("使用手册首页", f"{_REPO_URL}/wiki/Home"),
            ("安装与环境", f"{_REPO_URL}/wiki/Installation"),
            ("视频压制", f"{_REPO_URL}/wiki/Features-Video-Encode"),
            ("音视频工具", f"{_REPO_URL}/wiki/Features-Audio-Video-Tools"),
            ("封装与图片", f"{_REPO_URL}/wiki/Features-Remux-Image"),
            ("素材质量检测", f"{_REPO_URL}/wiki/Features-Quality-Control"),
            ("批量与效率工具", f"{_REPO_URL}/wiki/Features-Batch-Tools"),
            ("常见问题", f"{_REPO_URL}/wiki/FAQ"),
        ]
        for title, url in _links:
            act = QAction(title, self)
            act.triggered.connect(lambda checked, u=url: webbrowser.open(u))
            help_menu.addAction(act)

        ext_menu = menu_bar.addMenu("主页链接")
        for title, url in [
            ("GitHub 仓库", _REPO_URL),
            ("B站主页", "https://space.bilibili.com/107936977"),
        ]:
            act = QAction(title, self)
            act.triggered.connect(lambda checked, u=url: webbrowser.open(u))
            ext_menu.addAction(act)

    # ================================================================
    # 中央区域
    # ================================================================

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 侧边栏
        self._sidebar = Sidebar()
        self._sidebar.theme_button().clicked.connect(self._on_theme_toggle)
        self._sidebar.update_check_requested.connect(
            lambda: self._show_update_dialog(manual=True))
        root_layout.addWidget(self._sidebar)

        # 右侧
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)

        # 功能页面 (带动画切换)
        self._stack = AnimatedStackedWidget()
        right_splitter.addWidget(self._stack)

        # 底部：按钮行 + 任务卡区 + 错误卡 + 折叠日志 (与页面内容列同宽居中)
        bottom = _CenteredColumnWidget(
            CONTENT_MAX_WIDTH, (24, 6, 24, 10), 6)
        bottom_layout = bottom.column_layout()
        self._bottom = bottom

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._execute_btn = QPushButton("开始执行")
        self._execute_btn.setObjectName("execute_btn")
        self._execute_btn.clicked.connect(self._on_execute)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        btn_row.addWidget(self._execute_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        bottom_layout.addLayout(btn_row)

        # 任务卡执行区 (替换旧进度仪表盘; 属性名 _dashboard 保持兼容)
        self._dashboard = TaskArea()
        self._dashboard.cancel_requested.connect(self._on_stop)
        bottom_layout.addWidget(self._dashboard)

        # 错误卡片 (失败时显示在任务区与日志之间, 默认隐藏)
        self._error_card = ErrorCard()
        self._error_card.log_requested.connect(self._on_error_log_requested)
        self._error_card.action_requested.connect(self._on_error_action_requested)
        bottom_layout.addWidget(self._error_card)

        # 可折叠日志 (默认收起; _log_panel 指向内层 LogPanel 保持旧 API 兼容)
        self._log_box = CollapsibleLog()
        self._log_panel = self._log_box.panel
        bottom_layout.addWidget(self._log_box, 1)
        # 折叠/展开变化时重算底部最小高度 (展开后需为日志留出空间)
        self._log_box._toggle.toggled.connect(
            lambda _checked: self._refresh_bottom_minimum())

        right_splitter.addWidget(bottom)
        right_splitter.setStretchFactor(0, 5)
        right_splitter.setStretchFactor(1, 4)

        root_layout.addWidget(right_splitter, 1)

        # ---- 注册导航页面 (分组平铺, 无二级容器) ----
        self._tabs = []
        # 业务键 (Tab.command_name) -> executor, 不随导航结构变化
        self._handlers = dict(_EXECUTORS)
        # 页面名 -> 页面栈索引 (首页快捷入口跳转用)
        self._page_index = {}

        for section_title, items in _tab_defs():
            self._sidebar.add_section(section_title)
            for name, icon_name, page_factory in items:
                self._sidebar.add_item(name, icon_name)
                page = page_factory()
                if isinstance(page, HomePage):
                    page.navigate_requested.connect(self._on_home_navigate)
                elif isinstance(page, SettingsPage):
                    page.theme_change_requested.connect(self._apply_theme_choice)
                    page.reduced_motion_changed.connect(
                        self._on_reduced_motion_changed)
                    page.update_check_requested.connect(
                        lambda: self._show_update_dialog(manual=True))
                self._stack.addWidget(page)
                self._tabs.append(page)
                self._page_index[name] = len(self._tabs) - 1

        self._sidebar.tab_changed.connect(self._on_sidebar_tab_changed)
        self._refresh_theme_dependent_ui()

    # ================================================================
    # 快捷键
    # ================================================================

    def _build_shortcuts(self):
        exec_sc = QShortcut(QKeySequence("Ctrl+Return"), self)
        exec_sc.activated.connect(self._on_execute)

    # ================================================================
    # 状态栏
    # ================================================================

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.showMessage(f"就绪  |  v{_VERSION}")
        self.setStatusBar(sb)

    # ================================================================
    # 主题切换
    # ================================================================

    def _apply_theme_choice(self, name: str):
        """应用指定主题 (菜单 / 侧边栏按钮 / 设置页外观共用)。"""
        if name not in theme.THEMES:
            return
        theme.set_theme(name)
        theme.apply_theme(QApplication.instance(), name)
        self._refresh_theme_dependent_ui()
        self.statusBar().showMessage(f"就绪  |  v{_VERSION}")

    def _on_theme_toggle(self):
        new_theme = "dark" if theme.get_theme() == "light" else "light"
        self._apply_theme_choice(new_theme)

    def _on_motion_action_triggered(self, checked: bool):
        """菜单栏「减少动画」开关: 持久化并同步设置页勾选状态。"""
        theme.set_reduced_motion(checked)
        self._sync_settings_appearance()

    def _on_reduced_motion_changed(self, enabled: bool):
        """设置页「减少动画」勾选: 持久化并同步菜单栏勾选状态。"""
        theme.set_reduced_motion(enabled)
        self._motion_action.setChecked(enabled)

    def _sync_settings_appearance(self):
        for page in self._tabs:
            if isinstance(page, SettingsPage):
                page.on_theme_changed()

    def _refresh_theme_dependent_ui(self):
        """主题切换后刷新图标、Logo、按钮文案、勾选状态。"""
        self._theme_action.setChecked(theme.get_theme() == "dark")
        self._motion_action.setChecked(theme.reduced_motion())
        self._sidebar.set_theme_icons()
        self._update_run_button_icons()
        for tab in self._tabs:
            tab.on_theme_changed()
        self._log_box.on_theme_changed()

    def _update_run_button_icons(self):
        running = self._runner is not None and self._runner.isRunning()
        if running:
            self._execute_btn.setIcon(
                icons.icon("ri.loader-4-line", "accent_text_disabled"))
            self._stop_btn.setIcon(icons.icon("ri.stop-fill", "#ffffff"))
        else:
            self._execute_btn.setIcon(icons.icon("ri.play-fill", "on_accent"))
            self._stop_btn.setIcon(icons.icon("ri.stop-fill", "#ffffff"))

    # ================================================================
    # 页面路由
    # ================================================================

    def _current_tab(self):
        """当前选中的一级页面。

        以侧边栏选中索引为准 (点击即生效), 避免等页面切换动画播完才能
        读到执行目标; 首页/设置页因此也能立刻反映「执行按钮禁用」。
        """
        index = self._current_page_index
        if 0 <= index < len(self._tabs):
            return self._tabs[index]
        return None

    @staticmethod
    def _tab_supports_execution(tab) -> bool:
        """页面是否允许交给底部「开始执行」(首页/设置页显式返回 False)。"""
        if tab is None:
            return False
        hook = getattr(tab, "is_executable", None)
        return True if not callable(hook) else bool(hook())

    def _is_executable_tab(self, tab) -> bool:
        """可执行 = 页面允许执行 且 command_name 已注册 executor。"""
        return (
            tab is not None
            and self._tab_supports_execution(tab)
            and getattr(tab, "command_name", "") in self._handlers
        )

    def _update_execute_enabled(self):
        """按当前页面是否可执行刷新「开始执行」按钮。"""
        self._execute_btn.setEnabled(
            self._is_executable_tab(self._current_tab()))

    def _on_sidebar_tab_changed(self, index: int):
        self._current_page_index = index
        self._stack.slide_to(index)
        self._update_execute_enabled()

    def _on_home_navigate(self, target: str):
        """首页快捷入口跳转: target 为页面名 (如 "视频压制")。"""
        index = self._page_index.get(target)
        if index is not None:
            self._sidebar.setCurrentRow(index)

    # ================================================================
    # 执行与停止
    # ================================================================

    def _on_execute(self):
        idx = self._stack.currentIndex()
        if idx < 0:
            return
        tab = self._current_tab()
        if not self._tab_supports_execution(tab):
            return
        try:
            args = tab.build_args()
        except Exception as e:
            self._log_panel.append_log(f"参数构建失败: {e}\n")
            return

        command = tab.command_name
        handler = self._handlers.get(command)
        if handler is None:
            self._log_panel.append_log(f"未知命令: {command}\n")
            return

        # 按钮点击动画
        self._btn_anim = button_press_anim(self._execute_btn)

        self._set_running(True)
        self._error_card.hide()
        self._ffmpeg_parser.reset()
        self._dashboard.show_indeterminate()
        self._refresh_bottom_minimum()

        self._log_panel.append_log(f"{'=' * 50}\n")
        self._log_panel.append_log(f"▶ 开始执行: {command}\n")
        self._log_panel.append_log(f"{'=' * 50}\n")

        self._task_caption = command
        self._runner = TaskRunner(handler, args, command, parent=self)
        self._runner.log_signal.connect(self._log_panel.append_log)
        # M2.4 进度通道: stdout(key=value) -> 解析器 -> 任务卡;
        # duration_signal 由 worker 线程预取, 用于计算 percent/ETA。
        self._runner.progress_signal.connect(self._on_progress_line)
        self._runner.duration_signal.connect(self._on_duration_ready)
        # 主路径: 接收 TaskResult; finished_signal 只保留给旧槽/旧测试, 不再连接
        self._runner.result_signal.connect(self._on_task_result)
        self._runner.start()

    # ----------------------------------------------------------------
    # 任务进度 (M2.4: ffmpeg -progress -> percent/ETA)
    # ----------------------------------------------------------------

    def _on_progress_line(self, line):
        """收到一行 ffmpeg -progress 输出：解析成事件后更新任务卡指标。"""
        if not isinstance(line, str):
            return
        event = self._ffmpeg_parser.feed_line(line)
        if event is None:
            return
        self._dashboard.update_metrics(_ProgressView.from_event(event))

    def _on_duration_ready(self, duration):
        """worker 线程预取到输入时长：交给解析器计算 percent/ETA。"""
        try:
            seconds = float(duration)
        except (TypeError, ValueError):
            return
        if seconds > 0:
            self._ffmpeg_parser.set_duration(seconds)

    def _on_stop(self):
        """协作式取消：请求 TaskRunner 取消（内部触发 runner.cancel()）。

        不再调用 QThread 的强制终止接口；子进程终止由 runner.wait() 在后台线程
        推进，UI 状态等 result_signal(CANCELLED) 到达后再恢复。
        """
        if self._runner and self._runner.isRunning():
            self._stop_btn.setEnabled(False)  # 防二连点
            self._runner.request_cancel()
            self._error_card.hide()
            self._log_panel.append_log("\n⏹ 正在停止任务…\n")
            self.statusBar().showMessage(f"正在停止...  |  v{_VERSION}")
            self._refresh_bottom_minimum()

    def _on_task_finished(self, success, command_name):
        """deprecated: 旧 bool 结果槽 (保留一版兼容)。

        新路径使用 :meth:`_on_task_result`；这里把 bool 包成 TaskResult 后转发，
        让旧测试/旧信号在本轮迁移中保持可用。失败时用最近日志近似 stderr
        尾部，保证旧通道也能归类 (新通道由 runner 提供精确 stderr_tail)。
        下个版本删除。
        """
        self._task_caption = command_name or self._task_caption
        if success:
            self._on_task_result(TaskResult.ok(message="任务完成"))
        else:
            self._on_task_result(TaskResult.failed(
                "任务失败",
                details={"stderr_tail": self._recent_log_text()},
            ))

    def _on_task_result(self, result):
        """按 TaskResult 更新任务卡 / 错误卡 / 状态栏 (M2.1 主路径)。

        result -> view 映射只在这里发生；FAILED 才展示错误卡片，
        CANCELLED / PARTIAL 不显示错误卡片。
        """
        if not isinstance(result, TaskResult):
            result = TaskResult.failed(
                f"未知任务结果: {type(result).__name__}")
        caption = (
            self._task_caption
            or getattr(self._runner, "command_name", "")
            or "任务"
        )
        view_status = _RESULT_TO_VIEW_STATUS[result.status]

        for warning in result.warnings:
            self._log_panel.append_log(f"\n⚠ {warning}\n")

        if result.status is ResultStatus.SUCCESS:
            self._log_panel.append_log(f"\n✔ {caption} 执行完成\n")
            self._dashboard.finish_status(
                view_status, result.message or "任务完成")
            self._error_card.hide()
            status_flash(self.statusBar(), theme.color("success"), 2000)
            status_text = "完成"
        elif result.status is ResultStatus.FAILED:
            detail = f"：{result.message}" if result.message else ""
            self._log_panel.append_log(f"\n✘ {caption} 执行失败{detail}\n")
            self._dashboard.finish_status(
                view_status, result.message or "任务失败")
            self._show_error_card(result)
            status_flash(self.statusBar(), theme.color("danger"), 2000)
            status_text = "失败"
        elif result.status is ResultStatus.CANCELLED:
            self._log_panel.append_log(f"\n⏹ {caption} 已取消\n")
            self._dashboard.finish_status(
                view_status, result.message or "已取消")
            self._error_card.hide()
            status_text = "已取消"
        else:  # PARTIAL: 有成功也有失败, 不算失败也不发成功通知
            detail = f"：{result.message}" if result.message else ""
            self._log_panel.append_log(f"\n⚠ {caption} 部分完成{detail}\n")
            self._dashboard.finish_status(
                view_status, result.message or "部分完成")
            self._error_card.hide()
            status_flash(self.statusBar(), theme.color("warning"), 2000)
            status_text = "部分完成"

        self._task_caption = ""
        self._set_running(False)
        self.statusBar().showMessage(f"{status_text}  |  v{_VERSION}")
        self._refresh_bottom_minimum()

    # ----------------------------------------------------------------
    # 错误卡片 (M2.5: TaskResult.stderr_tail + exit_code -> UserFacingError)
    # ----------------------------------------------------------------

    def _recent_log_text(self, max_chunks=_ERROR_CONTEXT_CHUNKS) -> str:
        """最近日志块拼成的文本 (仅 deprecated 旧 bool 通道兜底使用)。"""
        chunks = list(getattr(self._log_panel, "_chunks", []))
        return "".join(chunks[-max_chunks:])

    def _show_error_card(self, result):
        """失败时按 TaskResult 的 stderr 尾部 + exit_code 归类并展示错误卡片。

        分类规则唯一实现在 :mod:`src.ffmpeg.errors`；这里只做
        ``TaskResult -> UserFacingError -> ErrorInfo`` 的展示适配。
        """
        details = result.details if isinstance(result, TaskResult) else {}
        stderr_tail = str(details.get("stderr_tail", "") or "")
        cancelled = bool(details.get("cancelled", False))
        error = classify_ffmpeg_error(
            stderr_tail,
            result.exit_code if isinstance(result, TaskResult) else None,
            cancelled,
        )
        self._error_card.show(error_info_from_user(error))
        self._refresh_bottom_minimum()

    def _on_error_log_requested(self):
        """错误卡片「查看完整日志」: 展开底部折叠日志。"""
        self._log_box.expand()
        self._refresh_bottom_minimum()

    def _on_error_action_requested(self, action: str):
        """错误卡片建议操作的 M1 最小实现: 记录提示, 不真正切换编码器。"""
        self._log_panel.append_log(f"\n💡 建议操作: {action}\n")
        self.statusBar().showMessage(f"建议操作: {action}  |  v{_VERSION}")

    # ----------------------------------------------------------------
    # 底部区域尺寸
    # ----------------------------------------------------------------

    def _refresh_bottom_minimum(self):
        """按底部可见内容抬升最小高度, 避免任务卡/错误卡被挤压成细条。

        _CenteredColumnWidget 显式设置了 100px 的最小高度 (打断宽度反馈),
        QSplitter 因此可以压到 100px; 任务卡/错误卡/展开日志需要额外空间。
        """
        bottom = getattr(self, "_bottom", None)
        if bottom is None:
            return
        minimum = 100  # 按钮行 + 折叠日志标题行 + 边距的基线高度
        for widget in (getattr(self, "_dashboard", None),
                       getattr(self, "_error_card", None)):
            if widget is not None and not widget.isHidden():
                minimum += widget.sizeHint().height()
        log_box = getattr(self, "_log_box", None)
        if log_box is not None and log_box.is_expanded():
            minimum += log_box.panel.sizeHint().height()
        bottom.setMinimumHeight(minimum)

    def _set_running(self, running):
        if running:
            self._execute_btn.setEnabled(False)
        else:
            # 首页 / 设置页仍保持禁用, 其余页面恢复可执行
            self._update_execute_enabled()
        self._stop_btn.setEnabled(running)
        self._sidebar.setEnabled(not running)
        self._update_run_button_icons()
        if running:
            self.statusBar().showMessage(f"执行中...  |  v{_VERSION}")

    # ================================================================
    # 窗口几何持久化
    # ================================================================

    def _restore_geometry(self):
        from ..gui_config import get_qsettings
        settings = get_qsettings()
        geo = settings.value("ui/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            # 首次启动居中显示
            center = self.screen().availableGeometry().center()
            self.move(center.x() - self.width() // 2,
                      center.y() - self.height() // 2)

    def closeEvent(self, event):
        """关闭窗口：先请求取消，有限等待工作线程退出后再接受关闭。

        不再调用 QThread 的强制终止接口（会绕过 finally/清理且不保证杀掉 FFmpeg）；
        取消后由 runner 在工作线程内完成 graceful -> terminate -> kill 时序。
        """
        from ..gui_config import get_qsettings
        settings = get_qsettings()
        settings.setValue("ui/geometry", self.saveGeometry())
        runner = self._runner
        if runner is not None and runner.isRunning():
            cancel_and_wait = getattr(runner, "cancel_and_wait", None)
            if callable(cancel_and_wait):
                cancel_and_wait(5000)
            else:
                runner.request_cancel()
                wait = getattr(runner, "wait", None)
                if callable(wait):
                    wait(5000)
        super().closeEvent(event)

    # ================================================================
    # 关于对话框
    # ================================================================

    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("关于小雪工具箱")
        dlg.setFixedWidth(430)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 26, 28, 18)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(14)
        logo_path = theme.logo_path()
        if logo_path:
            logo = QLabel()
            logo.setPixmap(QPixmap(logo_path).scaled(
                52, 52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            logo.setFixedSize(52, 52)
            logo.setScaledContents(True)
            head.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel(f"小雪工具箱 v{_VERSION}")
        title.setObjectName("brand_title")
        subtitle = QLabel("简洁实用的视频压制与素材管理工具")
        subtitle.setObjectName("muted_label")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        head.addLayout(title_col, 1)
        layout.addLayout(head)
        layout.addSpacing(10)

        desc = QLabel(
            "基于 FFmpeg 和 PyQt6 构建，内置 FFmpeg，开箱即用。\n作者: 雪阿宜"
        )
        desc.setWordWrap(True)
        desc.setObjectName("muted_label")
        layout.addWidget(desc)
        layout.addSpacing(6)

        components = QLabel(
            "开源许可: MIT\n第三方组件: FFmpeg · PyQt6 · AviSynth+ · VSFilter"
        )
        components.setWordWrap(True)
        components.setObjectName("muted_label")
        layout.addWidget(components)
        layout.addSpacing(12)

        btn_row = QHBoxLayout()
        gh_btn = QPushButton("GitHub 仓库")
        gh_btn.setIcon(icons.secondary("ri.github-line"))
        gh_btn.clicked.connect(lambda: webbrowser.open(_REPO_URL))
        btn_row.addWidget(gh_btn)

        bilibili_btn = QPushButton("B站主页")
        bilibili_btn.clicked.connect(
            lambda: webbrowser.open("https://space.bilibili.com/107936977"))
        btn_row.addWidget(bilibili_btn)
        btn_row.addStretch()

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(dlg.reject)
        btn_row.addWidget(close_box)
        layout.addLayout(btn_row)

        dlg.exec()
