# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 功能页面 + 日志面板。"""

import webbrowser

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSplitter, QPushButton, QStatusBar,
    QMenuBar, QProgressBar, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon

from ..gui_config import get_icon_path

from .sidebar import Sidebar
from .log_panel import LogPanel
from .task_runner import TaskRunner
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

_VERSION = "1.9.0"

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
        self.resize(960, 720)

        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self._runner = None

        # ---- 构建 UI ----
        self._build_menu_bar()
        self._build_central(shield_available, notify_config)
        self._build_status_bar()

        # 默认选中第一项
        self._sidebar.setCurrentRow(0)

    # ================================================================
    # 菜单栏
    # ================================================================

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # 关于
        about_menu = menu_bar.addMenu("关于")
        about_act = QAction("关于小雪工具箱", self)
        about_act.triggered.connect(self._show_about)
        about_menu.addAction(about_act)

        # 帮助文档
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

        # 主页链接
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

        # 右侧：功能页面 + 操作按钮 + 日志
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)

        # 功能页面
        self._stack = QStackedWidget()
        right_splitter.addWidget(self._stack)

        # 操作栏 + 日志
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(6)

        # 按钮行
        btn_row = QHBoxLayout()
        self._execute_btn = QPushButton("开始执行")
        self._execute_btn.setObjectName("execute_btn")
        self._execute_btn.clicked.connect(self._on_execute)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        self._clear_btn = QPushButton("清空日志")
        self._clear_btn.clicked.connect(lambda: self._log_panel.clear_log())

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(18)

        btn_row.addWidget(self._execute_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._progress)
        bottom_layout.addLayout(btn_row)

        # 日志面板
        self._log_panel = LogPanel()
        bottom_layout.addWidget(self._log_panel, 1)

        right_splitter.addWidget(bottom)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

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

        self._sidebar.tab_changed.connect(self._stack.setCurrentIndex)

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

        self._set_running(True)
        self._log_panel.append_log(f"{'=' * 50}\n")
        self._log_panel.append_log(f"▶ 开始执行: {command}\n")
        self._log_panel.append_log(f"{'=' * 50}\n")

        self._runner = TaskRunner(handler, args, command, parent=self)
        self._runner.log_signal.connect(self._log_panel.append_log)
        self._runner.finished_signal.connect(self._on_task_finished)
        self._runner.start()

    def _on_stop(self):
        if self._runner and self._runner.isRunning():
            self._runner.terminate()
            self._runner.wait(3000)
            self._log_panel.append_log("\n⏹ 任务已停止\n")
            self._set_running(False)

    def _on_task_finished(self, success, command_name):
        if success:
            self._log_panel.append_log(f"\n✔ {command_name} 执行完成\n")
            if command_name in _AUTO_NOTIFY_COMMANDS:
                try:
                    send_auto_notification(command_name)
                except Exception:
                    pass
        else:
            self._log_panel.append_log(f"\n✘ {command_name} 执行失败\n")

        self._set_running(False)
        self.statusBar().showMessage(
            f"{'完成' if success else '失败'}  |  v{_VERSION}"
        )

    def _set_running(self, running):
        self._execute_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._sidebar.setEnabled(not running)
        self._progress.setVisible(running)
        if running:
            self.statusBar().showMessage(f"执行中...  |  v{_VERSION}")

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
