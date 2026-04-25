# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 功能页面 + 进度仪表盘 + 日志面板。"""

import webbrowser

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QStatusBar,
    QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon

from ..gui_config import get_icon_path

from .sidebar import Sidebar
from .log_panel import LogPanel
from .task_runner import TaskRunner
from .animations import AnimatedStackedWidget, button_press_anim, status_flash
from .ffmpeg_progress import FFmpegProgressParser
from .progress_dashboard import ProgressDashboard
from .tabs import (
    EncodeTab, ReplaceAudioTab, RemuxTab, QcTab,
    MediaProbeTab, ExtractAvTab, ImageConvertTab,
    FolderCreatorTab, BatchRenameTab, ShieldTab,
    NotificationTab, HelpTab,
)

from ..executors import (
    execute_encode, execute_replace_audio, execute_extract_av,
    execute_remux, execute_image_convert, execute_folder_creator,
    execute_batch_rename, execute_qc, execute_notification,
    execute_help, execute_shield, execute_media_probe,
)
from ..notify_config import send_auto_notification
from .._version import __version__ as _VERSION

_AUTO_NOTIFY_COMMANDS = {
    "视频压制", "音频替换", "封装转换", "素材质量检测",
    "音视频抽取", "图片转换", "文件夹创建", "批量重命名",
    "媒体元数据检测", "露骨图片识别",
}


class MainWindow(QMainWindow):
    """应用程序主窗口。"""

    def __init__(self, shield_available=True, notify_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小雪工具箱")
        self.resize(1000, 740)

        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self._runner = None
        self._btn_anim = None

        self._build_menu_bar()
        self._build_central(shield_available, notify_config)
        self._build_status_bar()

        self._ffmpeg_parser = FFmpegProgressParser(self)
        self._ffmpeg_parser.progress_updated.connect(self._dashboard.update_metrics)

        self._sidebar.setCurrentRow(0)

    # ================================================================
    # 菜单栏
    # ================================================================

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        about_menu = menu_bar.addMenu("关于")
        about_act = QAction("关于小雪工具箱", self)
        about_act.triggered.connect(self._show_about)
        about_menu.addAction(about_act)

        help_menu = menu_bar.addMenu("帮助文档")
        _links = [
            ("使用手册首页", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Home"),
            ("安装与环境", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Installation"),
            ("视频压制", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Video-Encode"),
            ("音视频工具", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Audio-Video-Tools"),
            ("封装与图片", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Remux-Image"),
            ("素材质量检测", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Quality-Control"),
            ("批量与效率工具", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools"),
            ("通知设置", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Notification"),
            ("常见问题", "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/FAQ"),
        ]
        for title, url in _links:
            act = QAction(title, self)
            act.triggered.connect(lambda checked, u=url: webbrowser.open(u))
            help_menu.addAction(act)

        ext_menu = menu_bar.addMenu("主页链接")
        for title, url in [
            ("GitHub 仓库", "https://github.com/xueayi/XiaoXue-Video-Tools"),
            ("B站主页", "https://space.bilibili.com/107936977"),
        ]:
            act = QAction(title, self)
            act.triggered.connect(lambda checked, u=url: webbrowser.open(u))
            ext_menu.addAction(act)

    # ================================================================
    # 中央区域
    # ================================================================

    def _build_central(self, shield_available, notify_config):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 侧边栏
        self._sidebar = Sidebar()
        root_layout.addWidget(self._sidebar)

        # 右侧
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)

        # 功能页面 (带动画切换)
        self._stack = AnimatedStackedWidget()
        right_splitter.addWidget(self._stack)

        # 底部：按钮行 + 仪表盘 + 日志
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        bottom_layout.setSpacing(6)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._execute_btn = QPushButton("  \u25B6  开始执行")
        self._execute_btn.setObjectName("execute_btn")
        self._execute_btn.clicked.connect(self._on_execute)

        self._stop_btn = QPushButton("  \u25A0  停止")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        self._clear_btn = QPushButton("清空日志")
        self._clear_btn.setObjectName("clear_btn")
        self._clear_btn.clicked.connect(lambda: self._log_panel.clear_log())

        btn_row.addWidget(self._execute_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        bottom_layout.addLayout(btn_row)

        # 进度仪表盘
        self._dashboard = ProgressDashboard()
        bottom_layout.addWidget(self._dashboard)

        # 日志面板
        self._log_panel = LogPanel()
        bottom_layout.addWidget(self._log_panel, 1)

        right_splitter.addWidget(bottom)
        right_splitter.setStretchFactor(0, 5)
        right_splitter.setStretchFactor(1, 4)

        root_layout.addWidget(right_splitter, 1)

        # ---- 注册 Tab 页面 ----
        self._tabs = []
        self._handlers = {}

        tab_defs = [
            ("视频压制", EncodeTab(), execute_encode),
            ("音频替换", ReplaceAudioTab(), execute_replace_audio),
            ("封装转换", RemuxTab(), execute_remux),
            ("素材质量检测", QcTab(), execute_qc),
            ("媒体元数据检测", MediaProbeTab(), execute_media_probe),
            ("音视频抽取", ExtractAvTab(), execute_extract_av),
            ("图片转换", ImageConvertTab(), execute_image_convert),
            ("文件夹创建", FolderCreatorTab(), execute_folder_creator),
            ("批量重命名", BatchRenameTab(), execute_batch_rename),
            ("露骨图片识别", ShieldTab(shield_available=shield_available), execute_shield),
            ("通知设置", NotificationTab(config=notify_config), execute_notification),
            ("使用说明", HelpTab(), execute_help),
        ]

        for name, tab_widget, handler in tab_defs:
            self._sidebar.add_item(name)
            self._stack.addWidget(tab_widget)
            self._tabs.append(tab_widget)
            self._handlers[name] = handler

        self._sidebar.tab_changed.connect(self._stack.slide_to)

    # ================================================================
    # 状态栏
    # ================================================================

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.showMessage(f"就绪  |  v{_VERSION}")
        self.setStatusBar(sb)

    # ================================================================
    # 执行与停止
    # ================================================================

    def _on_execute(self):
        idx = self._stack.currentIndex()
        if idx < 0:
            return
        tab = self._tabs[idx]
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
        self._ffmpeg_parser.reset()
        self._dashboard.show_indeterminate()

        # 尝试从输入参数获取文件时长
        self._try_set_duration(args)

        self._log_panel.append_log(f"{'=' * 50}\n")
        self._log_panel.append_log(f"\u25B6 开始执行: {command}\n")
        self._log_panel.append_log(f"{'=' * 50}\n")

        self._runner = TaskRunner(handler, args, command, parent=self)
        self._runner.log_signal.connect(self._log_panel.append_log)
        self._runner.log_signal.connect(self._ffmpeg_parser.feed_line)
        self._runner.finished_signal.connect(self._on_task_finished)
        self._runner.start()

    def _try_set_duration(self, args):
        """尝试通过 probe 获取输入文件的总时长，传给 parser 计算进度。"""
        input_path = getattr(args, 'input', '') or ''
        if not input_path:
            return
        try:
            from ..media_probe import probe_detailed
            import os
            if os.path.isfile(input_path):
                info = probe_detailed(input_path)
                if info and info.duration_sec > 0:
                    self._ffmpeg_parser.set_duration(info.duration_sec)
        except Exception:
            pass

    def _on_stop(self):
        if self._runner and self._runner.isRunning():
            self._runner.terminate()
            self._runner.wait(3000)
            self._log_panel.append_log("\n\u23F9 任务已停止\n")
            self._dashboard.reset()
            self._set_running(False)

    def _on_task_finished(self, success, command_name):
        if success:
            self._log_panel.append_log(f"\n\u2714 {command_name} 执行完成\n")
            self._dashboard.finish(True)
            status_flash(self.statusBar(), "#4caf50", 2000)
            if command_name in _AUTO_NOTIFY_COMMANDS:
                try:
                    send_auto_notification(command_name)
                except Exception:
                    pass
        else:
            self._log_panel.append_log(f"\n\u2718 {command_name} 执行失败\n")
            self._dashboard.finish(False)
            status_flash(self.statusBar(), "#c42b1c", 2000)

        self._set_running(False)
        self.statusBar().showMessage(
            f"{'完成' if success else '失败'}  |  v{_VERSION}"
        )

    def _set_running(self, running):
        self._execute_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._sidebar.setEnabled(not running)
        if running:
            self.statusBar().showMessage(f"执行中...  |  v{_VERSION}")
        if not running:
            pass

    # ================================================================
    # 关于对话框
    # ================================================================

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于小雪工具箱",
            f"<h3>小雪工具箱 v{_VERSION}</h3>"
            f"<p>一个简单的视频压制与检测工具</p>"
            f"<p>作者: 雪阿宜</p>"
            f'<p><a href="https://github.com/xueayi/XiaoXue-Video-Tools">GitHub</a></p>',
        )
