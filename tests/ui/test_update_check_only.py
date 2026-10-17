# -*- coding: utf-8 -*-
"""check-only 更新流程测试 (M4.4, 全程无网络/无下载)。

覆盖:
* :class:`CheckOnlyWorker` 调用后端 ``check`` 并把 ReleaseInfo/异常转成信号;
* :class:`UpdateCheckOnlyDialog` 的「发现新版本 / 已是最新 / 检查失败」三态,
  「打开 Release 页面」走后端 ``open_release_page``, 且**从不**下载或安装;
* 主窗口按 platform_capabilities().self_update_available 分流:
  check-only → UpdateCheckOnlyDialog, Windows → 既有 UpdateDialog (行为不变);
* check-only 平台的启动静默检查走 CheckOnlyWorker。

后端用替身注入, 因此不触发 requests / 子进程; 平台能力由 conftest 的
platform_state_stub 提供, 需要 check-only 场景时在用例内覆盖。
"""

from types import SimpleNamespace

import pytest

import src.ui.main_window as mw
import src.ui.update_dialog as ud
from src.ui.main_window import MainWindow
from src.ui.update_dialog import (
    CheckOnlyWorker,
    UpdateCheckOnlyDialog,
    UpdateDialog,
    _current_version,
)

RELEASE_VERSION = "9.9.9"


class ReleaseStub:
    """ReleaseInfo 替身 (只需对话框用到的字段)。"""

    def __init__(self, version=RELEASE_VERSION):
        self.version = version
        self.html_url = (
            "https://github.com/xueayi/XiaoXue-Video-Tools/releases/tag/v9.9.9")
        self.notes = "- 新版本说明"


class BackendStub:
    """check-only 后端替身: 记录调用, 写盘方法一律断言失败。"""

    name = "check-only"
    supports_self_update = False

    def __init__(self, release=None, error=None, open_error=None):
        self.release = release
        self.error = error
        self.open_error = open_error
        self.checked_versions = []
        self.opened_releases = []
        self.write_calls = []

    def check(self, current_version, timeout=10.0):
        self.checked_versions.append(current_version)
        if self.error is not None:
            raise self.error
        return self.release

    def open_release_page(self, release=None):
        self.opened_releases.append(release)
        if self.open_error is not None:
            raise self.open_error
        return (getattr(release, "html_url", "") or
                "https://github.com/xueayi/XiaoXue-Video-Tools/releases/latest")

    # ---- 以下方法在 check-only 流程里绝不能被调用 ----

    def download_and_prepare(self, *args, **kwargs):
        self.write_calls.append("download_and_prepare")
        raise AssertionError("check-only 流程不应下载更新包")

    def install(self, *args, **kwargs):
        self.write_calls.append("install")
        raise AssertionError("check-only 流程不应安装/重启")


@pytest.fixture(autouse=True)
def sync_check_worker(monkeypatch):
    """CheckOnlyWorker.start() 直接同步执行 run(), 信号同步送达。"""
    monkeypatch.setattr(CheckOnlyWorker, "start", lambda self: self.run())


@pytest.fixture
def check_only_platform(monkeypatch):
    """把主窗口看到的平台能力切换为 check-only (macOS 语义)。"""
    state = SimpleNamespace(
        os_name="darwin", is_macos=True, is_windows=False, is_linux=False,
        avisynth_available=False, self_update_available=False,
        videotoolbox_available=True, ffmpeg_caps=None)
    monkeypatch.setattr(mw, "platform_capabilities", lambda refresh=False: state)
    return state


@pytest.fixture
def win(qapp):
    w = MainWindow()
    yield w
    w.close()


# ----------------------------------------------------------------
# Worker
# ----------------------------------------------------------------

def test_worker_calls_backend_check_with_current_version(qapp):
    backend = BackendStub(release=ReleaseStub())
    worker = CheckOnlyWorker(backend)
    got = []
    worker.checked.connect(got.append)

    worker.run()

    assert backend.checked_versions == [_current_version()]
    assert got and got[0].version == RELEASE_VERSION
    assert backend.write_calls == []


def test_worker_reports_uptodate_as_none(qapp):
    backend = BackendStub(release=None)
    worker = CheckOnlyWorker(backend)
    got = []
    worker.checked.connect(got.append)

    worker.run()

    assert got == [None]


def test_worker_update_error_becomes_failed_signal(qapp):
    backend = BackendStub(error=ud.UpdateError("断网了"))
    worker = CheckOnlyWorker(backend)
    failed = []
    worker.failed.connect(failed.append)
    checked = []
    worker.checked.connect(checked.append)

    worker.run()

    assert failed == ["断网了"]
    assert checked == []


def test_worker_generic_exception_is_wrapped(qapp):
    backend = BackendStub(error=RuntimeError("boom"))
    worker = CheckOnlyWorker(backend)
    failed = []
    worker.failed.connect(failed.append)

    worker.run()

    assert failed and failed[0].startswith("检查更新失败")
    assert "boom" in failed[0]


def test_worker_resolves_backend_from_factory(qapp, monkeypatch):
    backend = BackendStub(release=None)
    called = []
    monkeypatch.setattr(ud, "get_update_backend",
                        lambda: (called.append(1), backend)[1])

    worker = CheckOnlyWorker()
    worker.run()

    assert called == [1]
    assert backend.checked_versions == [_current_version()]


# ----------------------------------------------------------------
# 对话框
# ----------------------------------------------------------------

def _dialog(backend, release=None, qapp=None):
    dlg = UpdateCheckOnlyDialog(backend=backend, release=release)
    dlg.show()  # 让 isVisible() 可用 (offscreen)
    if qapp is not None:
        qapp.processEvents()
    return dlg


def test_dialog_reports_new_version(qapp):
    backend = BackendStub(release=ReleaseStub())
    dlg = _dialog(backend, qapp=qapp)

    assert f"发现新版本 v{RELEASE_VERSION}" in dlg._status_label.text()
    assert dlg._open_btn.isVisible() is True
    assert dlg._open_btn.text() == "打开 Release 页面"
    assert dlg.windowTitle() == "检查更新"
    assert backend.write_calls == []


def test_dialog_open_release_page_uses_backend(qapp):
    release = ReleaseStub()
    backend = BackendStub(release=release)
    dlg = _dialog(backend, qapp=qapp)

    dlg._open_btn.click()

    assert backend.opened_releases == [release]
    assert backend.write_calls == []


def test_dialog_open_release_page_failure_is_silent(qapp):
    backend = BackendStub(release=ReleaseStub(),
                          open_error=RuntimeError("没有浏览器"))
    dlg = _dialog(backend, qapp=qapp)

    dlg._open_btn.click()  # 不抛异常

    assert backend.opened_releases  # 后端确实被调用过


def test_dialog_uptodate_hides_release_button(qapp):
    backend = BackendStub(release=None)
    dlg = _dialog(backend, qapp=qapp)

    assert "已是最新版本" in dlg._status_label.text()
    assert dlg._open_btn.isVisible() is False
    assert backend.write_calls == []


def test_dialog_failure_offers_release_page(qapp):
    backend = BackendStub(error=ud.UpdateError("无法访问 GitHub"))
    dlg = _dialog(backend, qapp=qapp)

    assert dlg._status_label.text().startswith("更新失败")
    assert "无法访问 GitHub" in dlg._status_label.text()
    assert dlg._open_btn.isVisible() is True

    dlg._open_btn.click()
    assert backend.opened_releases == [None]  # 无具体版本 → 最新发行页


def test_dialog_with_release_skips_check(qapp):
    backend = BackendStub(release=None)
    dlg = _dialog(backend, release=ReleaseStub(), qapp=qapp)

    assert backend.checked_versions == []  # 静默检查已给出结果, 不再查询
    assert f"发现新版本 v{RELEASE_VERSION}" in dlg._status_label.text()


def test_dialog_never_downloads_or_installs(qapp):
    """三个状态走完都不允许触碰写盘方法。"""
    for backend in (BackendStub(release=ReleaseStub()),
                    BackendStub(release=None),
                    BackendStub(error=ud.UpdateError("x"))):
        dlg = _dialog(backend, qapp=qapp)
        assert backend.write_calls == []
        dlg.close()


# ----------------------------------------------------------------
# 主窗口分流
# ----------------------------------------------------------------

class FakeDialog:
    """记录构造/exec/show 的对话框替身。"""

    instances = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.args = args
        self.exec_called = False
        self.show_called = False
        self.install_requested = SimpleNamespace(connect=lambda cb: None)
        FakeDialog.instances.append(self)

    def exec(self):
        self.exec_called = True
        return 0

    def show(self):
        self.show_called = True


@pytest.fixture
def fake_dialogs(monkeypatch):
    FakeDialog.instances = []
    monkeypatch.setattr(mw, "UpdateCheckOnlyDialog", FakeDialog)
    monkeypatch.setattr(mw, "UpdateDialog", FakeDialog)
    return FakeDialog


def test_manual_entry_uses_check_only_dialog(win, check_only_platform,
                                             fake_dialogs):
    win._show_update_dialog(manual=True)

    assert len(fake_dialogs.instances) == 1
    dlg = fake_dialogs.instances[0]
    assert dlg.exec_called is True
    assert dlg.kwargs.get("release") is None
    # 不下载/不安装: 没有 install_requested 接线到退出流程
    assert win._update_dialog is None


def test_non_manual_entry_shows_check_only_dialog(win, check_only_platform,
                                                  fake_dialogs):
    win._show_update_dialog(manual=False)

    dlg = fake_dialogs.instances[0]
    assert dlg.show_called is True
    assert win._update_dialog is dlg


def test_windows_entry_still_uses_self_update_dialog(win, fake_dialogs):
    """Windows (self_update_available=True) 行为不变。"""
    win._show_update_dialog(manual=True)

    dlg = fake_dialogs.instances[0]
    assert dlg.exec_called is True
    # 自更新对话框需要 install_dir (check-only 对话框不需要)
    assert dlg.args and isinstance(dlg.args[0], str)


def test_silent_check_uses_check_only_worker(win, check_only_platform,
                                             monkeypatch):
    monkeypatch.delenv("XIAOXUE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(mw.updater, "is_dev_version", lambda v: False)
    created = []

    class FakeWorker:
        def __init__(self, *args, **kwargs):
            self.checked = SimpleNamespace(connect=lambda cb: None)
            created.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(mw, "CheckOnlyWorker", FakeWorker)
    monkeypatch.setattr(mw, "UpdateWorker",
                        lambda *a, **k: pytest.fail("不应使用 Windows 更新 worker"))

    win._silent_update_check()

    assert len(created) == 1
    assert win._check_worker is created[0]


def test_silent_check_windows_keeps_update_worker(win, monkeypatch):
    monkeypatch.delenv("XIAOXUE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(mw.updater, "is_dev_version", lambda v: False)
    created = []

    class FakeWorker:
        def __init__(self, mode, install_dir):
            self.mode = mode
            self.checked = SimpleNamespace(connect=lambda cb: None)
            created.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(mw, "UpdateWorker", FakeWorker)
    monkeypatch.setattr(mw, "CheckOnlyWorker",
                        lambda *a, **k: pytest.fail("Windows 不应走 check-only"))

    win._silent_update_check()

    assert created and created[0].mode == "check"


def test_on_silent_checked_check_only_shows_dialog(win, check_only_platform,
                                                   fake_dialogs, monkeypatch):
    win._on_silent_checked_check_only(ReleaseStub())

    dlg = fake_dialogs.instances[0]
    assert dlg.show_called is True
    assert dlg.kwargs.get("release") is not None
    assert win._update_dialog is dlg


def test_on_silent_checked_check_only_ignores_uptodate_and_skipped(
        win, check_only_platform, fake_dialogs, monkeypatch):
    win._on_silent_checked_check_only(None)
    assert fake_dialogs.instances == []

    monkeypatch.setattr(mw.updater, "get_skip_version",
                        lambda: RELEASE_VERSION)
    win._on_silent_checked_check_only(ReleaseStub())
    assert fake_dialogs.instances == []


def test_self_update_available_follows_platform_capabilities(win,
                                                             check_only_platform):
    assert win._self_update_available() is False
