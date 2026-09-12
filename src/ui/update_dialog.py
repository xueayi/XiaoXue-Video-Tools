# -*- coding: utf-8 -*-
"""更新对话框 —— 检查 / 下载 / 校验 / 待重启 的状态机 UI。

后台工作在 QThread 中执行 (检查与下载共用一个 Worker, 按 mode 区分),
UI 只响应信号; 下载中点击主按钮 = 取消 (保留 .part 供续传)。
"""

import os
import webbrowser

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit,
    QVBoxLayout,
)

from .. import updater
from . import icons

_STATE_LABELS = {
    "checking": "正在检查更新…",
    "uptodate": "当前已是最新版本 ✓",
    "available": "发现新版本",
    "downloading": "正在下载更新…",
    "verifying": "正在校验安装包…",
    "ready": "更新已就绪",
    "error": "更新失败",
}


class UpdateWorker(QThread):
    """更新后台工作线程。mode: "check" 只查询; "full" 下载并准备。"""

    checked = pyqtSignal(object)        # ReleaseInfo | None (已是最新)
    failed = pyqtSignal(str)
    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int)     # (已下载, 总量, 0 表示未知)
    ready = pyqtSignal(str)             # updater.ps1 路径

    def __init__(self, mode, install_dir, release=None, shield=False,
                 parent=None):
        super().__init__(parent)
        self._mode = mode
        self._install_dir = install_dir
        self._release = release
        self._shield = shield
        self.cancel = False

    def run(self):
        try:
            if self._mode == "check":
                self.checked.emit(updater.fetch_latest(
                    self._local_version(), shield=self._shield))
            else:
                self._download_and_prepare()
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:  # 兜底: 任何意外都不允许崩掉调用方
            self.failed.emit(f"更新失败: {e}")

    def _local_version(self):
        from .._version import __version__
        return __version__

    def _download_and_prepare(self):
        r = self._release
        updater.ensure_disk_space(self._install_dir, r.asset_size)

        zip_path = os.path.join(self._install_dir, updater.STAGING_DIR,
                                "update.zip")
        self.stage.emit("正在下载更新包…")
        updater.download(
            r.asset_url, zip_path,
            progress_cb=lambda done, total: self.progress.emit(done, total),
            check_cancel=lambda: self.cancel)

        self.stage.emit("正在校验安装包完整性…")
        expected = updater.fetch_checksum(r.sha256_url) if r.sha256_url else None
        if expected and not updater.verify_sha256(zip_path, expected):
            raise updater.UpdateError(
                "SHA256 校验失败, 安装包可能已损坏, 请重试或到发布页手动下载")

        self.stage.emit("正在准备更新文件…")
        ps1 = updater.prepare(zip_path, self._install_dir, r.version)
        self.ready.emit(ps1)


class UpdateDialog(QDialog):
    """检查更新对话框。

    install_requested: 用户点击「重启并安装」后发出 (更新器已拉起),
    主窗口接收后退出自身, 由更新器完成收尾并重启。
    """

    install_requested = pyqtSignal()

    def __init__(self, install_dir, shield=False, release=None, parent=None):
        super().__init__(parent)
        self._install_dir = install_dir
        self._shield = shield
        self._release = release
        self._worker = None
        self._state = "checking"
        self.setMinimumWidth(480)
        self.setWindowTitle("检查更新")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setObjectName("dashboard_progress")
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._notes_view = QTextEdit()
        self._notes_view.setObjectName("help_view")
        self._notes_view.setReadOnly(True)
        self._notes_view.setMaximumHeight(180)
        layout.addWidget(self._notes_view, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._action_btn = QPushButton()
        self._action_btn.setObjectName("execute_btn")
        self._action_btn.clicked.connect(self._on_action)
        btn_row.addWidget(self._action_btn)

        self._skip_btn = QPushButton("跳过此版本")
        self._skip_btn.setObjectName("clear_btn")
        self._skip_btn.clicked.connect(self._on_skip)
        btn_row.addWidget(self._skip_btn)

        self._browser_btn = QPushButton("在浏览器打开下载页")
        self._browser_btn.setObjectName("clear_btn")
        self._browser_btn.clicked.connect(self._on_open_browser)
        btn_row.addWidget(self._browser_btn)
        btn_row.addStretch()

        self._close_btn = QPushButton("关闭")
        self._close_btn.setObjectName("clear_btn")
        self._close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        if release is not None:
            self._on_checked(release)
        else:
            self._start_check()

    # ----------------------------------------------------------------
    # 状态机
    # ----------------------------------------------------------------

    def _apply_state(self, state):
        self._state = state
        self._status_label.setText(_STATE_LABELS.get(state, ""))
        downloading = state == "downloading"
        self._progress.setVisible(downloading)
        self._action_btn.setVisible(state in ("available", "downloading",
                                              "ready", "error"))
        self._action_btn.setText({
            "available": "立即更新",
            "downloading": "取消下载",
            "ready": "重启并安装",
            "error": "重试",
        }.get(state, ""))
        self._skip_btn.setVisible(state == "available")
        self._browser_btn.setVisible(state in ("available", "ready", "error"))
        self._notes_view.setVisible(state in ("available", "ready", "error"))
        if state == "available":
            self._action_btn.setIcon(icons.icon("ri.download-2-line",
                                                "on_accent"))
        elif state == "ready":
            self._action_btn.setIcon(icons.icon("ri.refresh-line",
                                                "on_accent"))

    # ----------------------------------------------------------------
    # 检查
    # ----------------------------------------------------------------

    def _start_check(self):
        self._apply_state("checking")
        self._cleanup_worker()
        self._worker = UpdateWorker("check", self._install_dir,
                                    shield=self._shield)
        self._worker.checked.connect(self._on_checked)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_checked(self, release):
        if release is None:
            self._apply_state("uptodate")
            return
        self._release = release
        self._apply_state("available")
        self._status_label.setText(
            f"发现新版本 v{release.version}  (当前 v{self._local_version()})\n"
            f"安装包大小: {release.asset_size >> 20} MB")
        self._notes_view.setPlainText(release.notes or "（无更新说明）")

    def _local_version(self):
        from .._version import __version__
        return __version__

    # ----------------------------------------------------------------
    # 下载 / 校验 / 就绪
    # ----------------------------------------------------------------

    def _start_download(self):
        self._apply_state("downloading")
        self._progress.setRange(0, 1000)
        self._cleanup_worker()
        self._worker = UpdateWorker("full", self._install_dir,
                                    release=self._release,
                                    shield=self._shield)
        self._worker.stage.connect(lambda s: self._status_label.setText(s))
        self._worker.progress.connect(self._on_progress)
        self._worker.ready.connect(self._on_ready)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done, total):
        if total > 0:
            self._progress.setRange(0, 1000)
            self._progress.setValue(int(done / total * 1000))
            self._status_label.setText(
                f"正在下载更新…  {done >> 20} / {total >> 20} MB")
        else:
            self._progress.setRange(0, 0)  # 未知总量: 走忙指示
            self._status_label.setText(
                f"正在下载更新…  已下载 {done >> 20} MB")

    def _on_ready(self, ps1_path):
        self._apply_state("ready")
        self._status_label.setText(
            "更新已就绪。点击「重启并安装」后程序将自动退出、\n"
            "完成更新并重新启动。")

    def _on_failed(self, message):
        if self._release is not None:
            self._apply_state("error")
        else:
            self._apply_state("uptodate")  # 静默检查失败不该显示错误态
        self._status_label.setText(f"更新失败\n{message}")

    # ----------------------------------------------------------------
    # 按钮
    # ----------------------------------------------------------------

    def _on_action(self):
        if self._state in ("available", "error"):
            self._start_download()
        elif self._state == "downloading":
            if self._worker is not None:
                self._worker.cancel = True
        elif self._state == "ready":
            self._install()

    def _install(self):
        updater.launch_updater(self._install_dir, os.getpid())
        self.install_requested.emit()
        self.accept()

    def _on_skip(self):
        if self._release is not None:
            updater.set_skip_version(self._release.version)
        self.reject()

    def _on_open_browser(self):
        url = (self._release.html_url if self._release
               else updater.REPO_URL + "/releases/latest")
        webbrowser.open(url)

    def _cleanup_worker(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    # ----------------------------------------------------------------
    # 关闭行为
    # ----------------------------------------------------------------

    def reject(self):
        if self._worker is not None:
            self._worker.cancel = True
        super().reject()
