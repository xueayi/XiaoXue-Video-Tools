# -*- coding: utf-8 -*-
"""update_dialog.py 与主窗口更新入口测试 (worker 同步执行, 全程无网络)。"""

import os

import pytest
from PyQt6.QtWidgets import QLabel, QProgressBar, QPushButton

import src.ui.main_window as mw
import src.ui.update_dialog as ud
from src.ui.main_window import MainWindow
from src.ui.update_dialog import UpdateDialog, UpdateWorker
from src.updater import download


class ReleaseStub:
    def __init__(self, version="2.2.0", size=10 << 20):
        import src.updater as updater
        self.version = version
        self.asset_name = "XiaoXueToolbox_v2.2.0_Windows_x64.zip"
        self.asset_url = "https://dl/x.zip"
        self.asset_size = size
        self.sha256_url = "https://dl/x.zip.sha256"
        self.notes = "- 修复若干问题"
        self.published_at = "2026-09-12"
        self.html_url = "https://github.com/xueayi/XiaoXue-Video-Tools/releases/tag/v2.2.0"
        self._updater = updater


@pytest.fixture(autouse=True)
def sync_worker_start(monkeypatch):
    """worker.start() 直接同步执行 run(), 信号同步送达。"""
    monkeypatch.setattr(UpdateWorker, "start", lambda self: self.run())


@pytest.fixture
def dlg(qapp, monkeypatch, tmp_path):
    """检查结果=发现新版本的对话框 (跳过构造时的网络检查)。"""
    return UpdateDialog(str(tmp_path), shield=False,
                        release=ReleaseStub())


# ----------------------------------------------------------------
# Worker
# ----------------------------------------------------------------

def test_worker_check_has_update(qapp, monkeypatch):
    rel = ReleaseStub()
    monkeypatch.setattr(ud.updater, "fetch_latest", lambda *a, **k: rel)
    worker = UpdateWorker("check", "C:/app", shield=False)
    got = []
    worker.checked.connect(got.append)
    worker.run()
    assert got == [rel]


def test_worker_check_uptodate(qapp, monkeypatch):
    monkeypatch.setattr(ud.updater, "fetch_latest", lambda *a, **k: None)
    worker = UpdateWorker("check", "C:/app")
    got = []
    worker.checked.connect(got.append)
    worker.run()
    assert got == [None]


def test_worker_check_update_error(qapp, monkeypatch):
    monkeypatch.setattr(ud.updater, "fetch_latest",
                        lambda *a, **k: (_ for _ in ()).throw(
                            ud.updater.UpdateError("断网")))
    worker = UpdateWorker("check", "C:/app")
    got = []
    worker.failed.connect(got.append)
    worker.run()
    assert got == ["断网"]


def test_worker_generic_exception(qapp, monkeypatch):
    monkeypatch.setattr(ud.updater, "fetch_latest",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    worker = UpdateWorker("check", "C:/app")
    got = []
    worker.failed.connect(got.append)
    worker.run()
    assert got and got[0].startswith("更新失败")


def test_worker_full_pipeline(qapp, monkeypatch, tmp_path):
    calls = {"progress": [], "stages": []}

    def fake_download(url, dest, progress_cb=None, check_cancel=None):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        progress_cb(5 << 20, 10 << 20)
        open(dest, "wb").write(b"zipdata")

    monkeypatch.setattr(ud.updater, "ensure_disk_space", lambda *a: None)
    monkeypatch.setattr(ud.updater, "download", fake_download)
    monkeypatch.setattr(ud.updater, "fetch_checksum", lambda url: "a" * 64)
    monkeypatch.setattr(ud.updater, "verify_sha256", lambda p, e: True)
    monkeypatch.setattr(ud.updater, "prepare",
                        lambda z, d, v: "C:/app/_update/updater.ps1")

    worker = UpdateWorker("full", str(tmp_path), release=ReleaseStub())
    worker.progress.connect(lambda d, t: calls["progress"].append((d, t)))
    worker.stage.connect(calls["stages"].append)
    ready = []
    worker.ready.connect(ready.append)
    worker.run()
    assert ready == ["C:/app/_update/updater.ps1"]
    assert calls["progress"] == [(5 << 20, 10 << 20)]
    assert any("下载" in s for s in calls["stages"])


def test_worker_full_cancel(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(ud.updater, "ensure_disk_space", lambda *a: None)

    def fake_download(url, dest, progress_cb=None, check_cancel=None):
        assert check_cancel() is True
        raise ud.updater.UpdateError("已取消")
    monkeypatch.setattr(ud.updater, "download", fake_download)

    worker = UpdateWorker("full", str(tmp_path), release=ReleaseStub())
    worker.cancel = True
    got = []
    worker.failed.connect(got.append)
    worker.run()
    assert got == ["已取消"]


def test_worker_full_checksum_mismatch(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(ud.updater, "ensure_disk_space", lambda *a: None)
    def fake_download(url, dest, **k):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(b"x")
    monkeypatch.setattr(ud.updater, "download", fake_download)
    monkeypatch.setattr(ud.updater, "fetch_checksum", lambda url: "a" * 64)
    monkeypatch.setattr(ud.updater, "verify_sha256", lambda p, e: False)
    worker = UpdateWorker("full", str(tmp_path), release=ReleaseStub())
    got = []
    worker.failed.connect(got.append)
    worker.run()
    assert "SHA256" in got[0]


# ----------------------------------------------------------------
# 对话框状态机
# ----------------------------------------------------------------

def test_dialog_initial_available_state(dlg):
    assert dlg._state == "available"
    assert "发现新版本" in dlg._status_label.text()
    assert not dlg._progress.isVisibleTo(dlg)
    assert dlg._action_btn.text() == "立即更新"
    assert dlg._skip_btn.isVisibleTo(dlg)
    assert "修复若干问题" in dlg._notes_view.toPlainText()


def test_dialog_uptodate_state(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(ud.updater, "fetch_latest", lambda *a, **k: None)
    d = UpdateDialog(str(tmp_path))
    assert d._state == "uptodate"
    assert not d._action_btn.isVisibleTo(d)


def test_dialog_check_error_shows_uptodate_text(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(ud.updater, "fetch_latest",
                        lambda *a, **k: (_ for _ in ()).throw(
                            ud.updater.UpdateError("断网")))
    d = UpdateDialog(str(tmp_path))
    assert "断网" in d._status_label.text()


def test_dialog_action_starts_download(dlg, monkeypatch):
    started = []
    monkeypatch.setattr(dlg, "_start_download", lambda: started.append(1))
    dlg._on_action()  # available -> download
    assert started == [1]


def test_dialog_action_cancel_while_downloading(dlg):
    dlg._apply_state("downloading")
    dlg._worker = UpdateWorker("full", dlg._install_dir)
    dlg._worker.deleteLater()
    dlg._worker = None

    class W:
        cancel = False
    dlg._worker = W()
    dlg._on_action()
    assert dlg._worker.cancel is True


def test_dialog_action_install_when_ready(dlg, monkeypatch):
    dlg._apply_state("ready")
    launched = []
    monkeypatch.setattr(ud.updater, "launch_updater",
                        lambda d, pid: launched.append((d, pid)))
    emitted = []
    dlg.install_requested.connect(lambda: emitted.append(1))
    dlg._on_action()
    assert launched and launched[0][0] == dlg._install_dir
    assert emitted == [1]


def test_dialog_error_retry_starts_download(dlg, monkeypatch):
    started = []
    monkeypatch.setattr(dlg, "_start_download", lambda: started.append(1))
    dlg._on_failed("网络断开")
    assert dlg._state == "error"
    dlg._on_action()
    assert started == [1]


def test_dialog_progress_with_total(dlg):
    dlg._apply_state("downloading")
    bar = dlg.findChild(QProgressBar)
    dlg._on_progress(5 << 20, 10 << 20)
    assert bar.value() == 500
    assert "5 / 10 MB" in dlg._status_label.text()


def test_dialog_progress_unknown_total(dlg):
    dlg._apply_state("downloading")
    bar = dlg.findChild(QProgressBar)
    dlg._on_progress(3 << 20, 0)
    assert bar.minimum() == 0 and bar.maximum() == 0  # 忙指示
    assert "已下载 3 MB" in dlg._status_label.text()


def test_dialog_ready_state(dlg):
    dlg._on_ready("C:/ps1")
    assert dlg._state == "ready"
    assert dlg._action_btn.text() == "重启并安装"
    assert "重启并安装" in dlg._status_label.text()


def test_dialog_failed_without_release_keeps_uptodate(qapp, monkeypatch,
                                                      tmp_path):
    monkeypatch.setattr(ud.updater, "fetch_latest", lambda *a, **k: None)
    d = UpdateDialog(str(tmp_path))
    d._on_failed("某错误")
    assert d._state == "uptodate"


def test_dialog_skip_version(dlg, monkeypatch):
    saved = []
    monkeypatch.setattr(ud.updater, "set_skip_version",
                        lambda v: saved.append(v))
    dlg._on_skip()
    assert saved == ["2.2.0"]


def test_dialog_open_browser(dlg, monkeypatch):
    opened = []
    monkeypatch.setattr(ud.webbrowser, "open", lambda u: opened.append(u))
    dlg._on_open_browser()
    assert opened == [dlg._release.html_url]
    dlg._release = None
    dlg._on_open_browser()
    assert "releases/latest" in opened[-1]


def test_dialog_reject_cancels_worker(dlg):
    class W:
        cancel = False
    dlg._worker = W()
    dlg.reject()
    assert dlg._worker.cancel is True


def test_dialog_labels_exist(dlg):
    assert dlg.findChild(QLabel) is not None
    assert dlg.windowTitle() == "检查更新"


# ----------------------------------------------------------------
# 主窗口集成
# ----------------------------------------------------------------

@pytest.fixture
def win(qapp):
    w = MainWindow(shield_available=True, notify_config=None)
    yield w
    w.close()


def test_sidebar_has_update_button(win):
    btn = win._sidebar._update_btn
    assert btn.text() == "检查更新"
    assert btn.objectName() == "sidebar_footer_btn"
    assert not btn.icon().isNull()


def test_sidebar_update_button_signal(win, monkeypatch):
    fired = []
    win._sidebar.update_check_requested.connect(lambda: fired.append(1))
    monkeypatch.setattr(mw, "UpdateDialog", lambda *a, **k: None)
    monkeypatch.setattr(type(win), "exec", lambda self: None, raising=False)
    win._sidebar._update_btn.click()
    assert fired == [1]


def test_silent_check_skipped_in_test_env(win):
    # conftest 设置了 XIAOXUE_NO_UPDATE_CHECK, 不应创建 worker
    win._silent_update_check()
    assert win._check_worker is None


def test_silent_check_skipped_for_dev_version(win, monkeypatch):
    monkeypatch.delenv("XIAOXUE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(mw.updater, "is_dev_version", lambda v: True)
    win._silent_update_check()
    assert win._check_worker is None


def test_silent_check_runs_without_guard(win, monkeypatch):
    monkeypatch.delenv("XIAOXUE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(mw.updater, "is_dev_version", lambda v: False)

    inst = []
    from PyQt6.QtCore import pyqtSignal, QObject

    class RealFake(QObject):
        checked = pyqtSignal(object)

        def __init__(self, mode, install_dir, shield=False):
            super().__init__()
            inst.append((mode, install_dir, shield))

        def start(self):
            self.started = True

    monkeypatch.setattr(mw, "UpdateWorker", RealFake)
    win._silent_update_check()
    assert inst and inst[0][0] == "check"


def test_on_silent_checked_none_no_dialog(win):
    win._on_silent_checked(None)
    assert win._update_dialog is None


def test_on_silent_checked_skipped_version(win, monkeypatch):
    monkeypatch.setattr(mw.updater, "get_skip_version", lambda: "2.2.0")
    win._on_silent_checked(ReleaseStub(version="2.2.0"))
    assert win._update_dialog is None


def test_on_silent_checked_shows_dialog(win, monkeypatch):
    shown = []
    created = []

    class FakeDialog:
        def __init__(self, install_dir, shield=False, release=None,
                     parent=None):
            created.append(release)
            self.install_requested = type("S", (), {"connect": staticmethod(
                lambda cb: None)})()

        def show(self):
            shown.append(True)

    monkeypatch.setattr(mw, "UpdateDialog", FakeDialog)
    win._on_silent_checked(ReleaseStub())
    assert shown == [True] and created and created[0].version == "2.2.0"
    assert win._update_dialog is not None


def test_show_update_dialog_manual_uses_exec(win, monkeypatch):
    executed = []

    class FakeDialog:
        def __init__(self, install_dir, shield=False, release=None,
                     parent=None):
            self.install_requested = type("S", (), {"connect": staticmethod(
                lambda cb: None)})()

        def exec(self):
            executed.append("exec")

    monkeypatch.setattr(mw, "UpdateDialog", FakeDialog)
    win._show_update_dialog(manual=True)
    assert executed == ["exec"]


def test_apply_update_and_quit_closes(win, monkeypatch):
    closed = []
    monkeypatch.setattr(win, "close", lambda: closed.append(1))
    win._apply_update_and_quit()
    assert closed == [1]


def test_show_update_dialog_non_modal_uses_show(win, monkeypatch):
    shown = []

    class FakeDialog:
        def __init__(self, install_dir, shield=False, release=None,
                     parent=None):
            self.install_requested = type("S", (), {"connect": staticmethod(
                lambda cb: None)})()

        def show(self):
            shown.append(True)

    monkeypatch.setattr(mw, "UpdateDialog", FakeDialog)
    win._show_update_dialog(manual=False)
    assert shown == [True]
    assert win._update_dialog is not None


def test_dialog_real_start_download_pipeline(dlg, monkeypatch, tmp_path):
    """_start_download 真实执行 (updater 全部 mock), 走完 ready 状态。"""
    import os as _os

    def fake_download(url, dest, progress_cb=None, check_cancel=None):
        _os.makedirs(_os.path.dirname(dest), exist_ok=True)
        progress_cb(10 << 20, 10 << 20)
        open(dest, "wb").write(b"zip")

    monkeypatch.setattr(ud.updater, "ensure_disk_space", lambda *a: None)
    monkeypatch.setattr(ud.updater, "download", fake_download)
    monkeypatch.setattr(ud.updater, "fetch_checksum", lambda url: None)
    monkeypatch.setattr(ud.updater, "prepare",
                        lambda z, d, v: "C:/ps1")
    dlg._start_download()
    assert dlg._state == "ready"
    assert dlg._action_btn.text() == "重启并安装"
    assert "已就绪" in dlg._status_label.text()


def test_dialog_cleanup_worker_releases(dlg):
    worker = UpdateWorker("check", dlg._install_dir)
    dlg._worker = worker
    dlg._cleanup_worker()
    assert dlg._worker is None
    dlg._cleanup_worker()  # None 分支
    assert dlg._worker is None


def test_download_bad_content_length_header(monkeypatch, tmp_path):
    import src.updater as m

    class Resp:
        status_code = 200
        headers = {"Content-Length": "not-a-number"}

        def iter_content(self, chunk_size):
            yield b"data"

    monkeypatch.setattr(m.requests, "get", lambda *a, **k: Resp())
    dest = str(tmp_path / "u.zip")
    download("https://dl/x.zip", dest)
    assert open(dest, "rb").read() == b"data"  # total 未知, 不影响落盘
