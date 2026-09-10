# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 功能页面 + 进度仪表盘 + 日志面板。"""

import webbrowser

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QApplication, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QStatusBar,
    QDialog, QLabel, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QIcon, QShortcut, QKeySequence, QPixmap

from ..gui_config import get_icon_path

from . import theme
from . import icons
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

_REPO_URL = "https://github.com/xueayi/XiaoXue-Video-Tools"


def _tab_defs(shield_available: bool, notify_config):
    """功能页注册表: (分组标题, [(页面名, 图标名, Tab工厂, executor), ...])"""

    def shield():
        return ShieldTab(shield_available=shield_available)

    def notification():
        return NotificationTab(config=notify_config)

    return [
        ("视频处理", [
            ("视频压制", "ri.film-line", EncodeTab, execute_encode),
            ("音频替换", "ri.music-2-line", ReplaceAudioTab, execute_replace_audio),
            ("音视频抽取", "ri.file-transfer-line", ExtractAvTab, execute_extract_av),
        ]),
        ("格式与媒体", [
            ("封装转换", "ri.exchange-line", RemuxTab, execute_remux),
            ("媒体元数据检测", "ri.file-info-line", MediaProbeTab, execute_media_probe),
            ("图片转换", "ri.image-line", ImageConvertTab, execute_image_convert),
        ]),
        ("质量与批量", [
            ("素材质量检测", "ri.file-search-line", QcTab, execute_qc),
            ("文件夹创建", "ri.folder-add-line", FolderCreatorTab, execute_folder_creator),
            ("批量重命名", "ri.file-edit-line", BatchRenameTab, execute_batch_rename),
        ]),
        ("特色与辅助", [
            ("露骨图片识别", "ri.shield-check-line", shield, execute_shield),
            ("通知设置", "ri.notification-3-line", notification, execute_notification),
        ]),
        ("帮助", [
            ("使用说明", "ri.question-line", HelpTab, execute_help),
        ]),
    ]


class MainWindow(QMainWindow):
    """应用程序主窗口。"""

    def __init__(self, shield_available=True, notify_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("小雪工具箱")
        self.setMinimumSize(960, 640)
        self.resize(1080, 760)

        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self._runner = None
        self._btn_anim = None

        self._build_menu_bar()
        self._build_central(shield_available, notify_config)
        self._build_status_bar()
        self._build_shortcuts()
        self._restore_geometry()

        self._ffmpeg_parser = FFmpegProgressParser(self)
        self._ffmpeg_parser.progress_updated.connect(self._dashboard.update_metrics)

        self._sidebar.setCurrentRow(0)

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
        motion_action.setCheckable(True)
        motion_action.setChecked(theme.reduced_motion())
        motion_action.triggered.connect(
            lambda checked: theme.set_reduced_motion(checked))
        view_menu.addAction(motion_action)

        about_menu = menu_bar.addMenu("关于")
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
            ("通知设置", f"{_REPO_URL}/wiki/Features-Notification"),
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

    def _build_central(self, shield_available, notify_config):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 侧边栏
        self._sidebar = Sidebar()
        self._sidebar.theme_button().clicked.connect(self._on_theme_toggle)
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

        self._execute_btn = QPushButton("  开始执行")
        self._execute_btn.setObjectName("execute_btn")
        self._execute_btn.clicked.connect(self._on_execute)

        self._stop_btn = QPushButton("  停止")
        self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)

        btn_row.addWidget(self._execute_btn)
        btn_row.addWidget(self._stop_btn)
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

        for section_title, items in _tab_defs(shield_available, notify_config):
            self._sidebar.add_section(section_title)
            for name, icon_name, tab_factory, handler in items:
                self._sidebar.add_item(name, icon_name)
                tab_widget = tab_factory()
                self._stack.addWidget(tab_widget)
                self._tabs.append(tab_widget)
                self._handlers[name] = handler

        self._sidebar.tab_changed.connect(self._stack.slide_to)
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

    def _on_theme_toggle(self):
        new_theme = "dark" if theme.get_theme() == "light" else "light"
        theme.set_theme(new_theme)
        theme.apply_theme(QApplication.instance(), new_theme)
        self._refresh_theme_dependent_ui()
        self.statusBar().showMessage(f"就绪  |  v{_VERSION}")

    def _refresh_theme_dependent_ui(self):
        """主题切换后刷新图标、Logo、按钮文案、勾选状态。"""
        self._theme_action.setChecked(theme.get_theme() == "dark")
        self._sidebar.set_theme_icons()
        self._update_run_button_icons()
        for tab in self._tabs:
            tab.on_theme_changed()
        self._log_panel.on_theme_changed()

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
        self._log_panel.append_log(f"▶ 开始执行: {command}\n")
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
            self._log_panel.append_log("\n⏹ 任务已停止\n")
            self._dashboard.reset()
            self._set_running(False)

    def _on_task_finished(self, success, command_name):
        if success:
            self._log_panel.append_log(f"\n✔ {command_name} 执行完成\n")
            self._dashboard.finish(True)
            status_flash(self.statusBar(), theme.color("success"), 2000)
            if command_name in _AUTO_NOTIFY_COMMANDS:
                try:
                    send_auto_notification(command_name)
                except Exception:
                    pass
        else:
            self._log_panel.append_log(f"\n✘ {command_name} 执行失败\n")
            self._dashboard.finish(False)
            status_flash(self.statusBar(), theme.color("danger"), 2000)

        self._set_running(False)
        self.statusBar().showMessage(
            f"{'完成' if success else '失败'}  |  v{_VERSION}"
        )

    def _set_running(self, running):
        self._execute_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._sidebar.setEnabled(not running)
        self._update_run_button_icons()
        if running:
            self.statusBar().showMessage(f"执行中...  |  v{_VERSION}")

    # ================================================================
    # 窗口几何持久化
    # ================================================================

    def _restore_geometry(self):
        settings = QSettings("XiaoXue", "XiaoXueToolbox")
        geo = settings.value("ui/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            # 首次启动居中显示
            center = self.screen().availableGeometry().center()
            self.move(center.x() - self.width() // 2,
                      center.y() - self.height() // 2)

    def closeEvent(self, event):
        settings = QSettings("XiaoXue", "XiaoXueToolbox")
        settings.setValue("ui/geometry", self.saveGeometry())
        if self._runner and self._runner.isRunning():
            self._runner.terminate()
            self._runner.wait(2000)
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
