# -*- coding: utf-8 -*-
"""main_window.py 与 main.py 入口测试。"""

import pytest
from PyQt6.QtWidgets import QDialog

import src.ui.main_window as mw
from src.ui import theme
from src.ui.main_window import MainWindow, _CenteredColumnWidget
from src.ui.task_runner import TaskRunner


@pytest.fixture
def win(qapp):
    w = MainWindow(shield_available=True, notify_config=None)
    yield w
    w.close()


def _pump_until(qapp, cond, timeout_ms=5000):
    import time
    deadline = time.time() + timeout_ms / 1000
    while not cond():
        assert time.time() < deadline, "等待条件超时"
        qapp.processEvents()


# ----------------------------------------------------------------
# 构建与导航
# ----------------------------------------------------------------

def test_window_builds_all_pages(win):
    assert win._stack.count() == 12
    assert len(win._tabs) == 12
    assert len(win._handlers) == 12
    assert win._sidebar.count() == 12
    assert win.windowTitle() == "小雪工具箱"
    assert win.minimumSize().width() == 960


def test_navigation_switches_stack(win, qapp):
    win._sidebar.setCurrentRow(3)
    _pump_until(qapp, lambda: win._stack.currentIndex() == 3)
    win._sidebar.setCurrentRow(0)


def test_centered_bottom_column_tracks_width(win, qapp):
    bottom = win.findChild(_CenteredColumnWidget)
    assert bottom is not None
    win.show()  # 布局计算需要真实 show (离屏下不可见)
    qapp.processEvents()
    win.resize(1400, 800)  # 离屏屏幕较小时会被钳制, 用动态断言
    qapp.processEvents()
    assert bottom.column().width() == min(860, bottom.width() - 8)
    win.resize(960, 800)
    qapp.processEvents()
    assert bottom.column().width() == min(860, bottom.width() - 8)


def test_status_bar_ready(win):
    assert "就绪" in win.statusBar().currentMessage()


# ----------------------------------------------------------------
# 执行 / 停止流
# ----------------------------------------------------------------

def test_execute_success_flow(win, qapp, monkeypatch):
    notified = []
    monkeypatch.setattr(mw, "send_auto_notification",
                        lambda name: notified.append(name))
    win._handlers["视频压制"] = lambda args: print("fake encode")
    win._sidebar.setCurrentRow(0)
    win._on_execute()
    _pump_until(qapp, lambda: "完成" in win.statusBar().currentMessage())
    assert notified == ["视频压制"]
    assert win._execute_btn.isEnabled()
    assert not win._stop_btn.isEnabled()


def test_execute_failure_flow(win, qapp, monkeypatch):
    def boom(args):
        raise ValueError("运行失败")
    win._handlers["视频压制"] = boom
    win._sidebar.setCurrentRow(0)
    win._on_execute()
    _pump_until(qapp, lambda: "失败" in win.statusBar().currentMessage())
    assert "执行失败" in "\n".join(win._log_panel._chunks)


def test_execute_invalid_command_logs_error(win):
    win._handlers.clear()
    win._on_execute()
    assert any("未知命令" in c for c in win._log_panel._chunks)


def test_execute_empty_stack_noop(win, qapp):
    win._stack.setCurrentIndex(-1)
    win._on_execute()  # 不应崩溃
    qapp.processEvents()


def test_build_args_error_logged(win, monkeypatch):
    monkeypatch.setattr(win._tabs[0], "build_args",
                        lambda: (_ for _ in ()).throw(RuntimeError("坏参数")))
    win._on_execute()
    assert any("坏参数" in c for c in win._log_panel._chunks)


def test_stop_without_runner_noop(win):
    win._on_stop()
    assert win._execute_btn.isEnabled()


def test_stop_running_task(win, qapp):
    # 用假 runner 覆盖停止分支, 避免 terminate 真线程在 Windows 上死锁
    class FakeRunner:
        def isRunning(self):
            return True

        def terminate(self):
            self.terminated = True

        def wait(self, ms):
            return True

    fake = FakeRunner()
    win._runner = fake
    win._stop_btn.setEnabled(True)
    win._on_stop()
    assert fake.terminated
    assert win._execute_btn.isEnabled()
    assert any("已停止" in c for c in win._log_panel._chunks)


def test_running_button_icons_branch(win, qapp):
    runner = TaskRunner(lambda a: None, None, "x")
    win._runner = runner
    qapp.processEvents()
    win._update_run_button_icons()
    win._set_running(True)
    win._set_running(False)
    win._runner = None
    win._update_run_button_icons()


def test_try_set_duration_invalid_path(win):
    class A:
        input = "Z:/nope.mp4"
    win._try_set_duration(A())  # 文件不存在 -> 静默返回
    class B:
        input = ""
    win._try_set_duration(B())


# ----------------------------------------------------------------
# 主题切换 / 视图菜单
# ----------------------------------------------------------------

def test_theme_toggle_roundtrip(win, qapp):
    before = theme.get_theme()
    win._theme_action.setChecked(before != "dark")
    win._on_theme_toggle()
    assert theme.get_theme() != before
    win._on_theme_toggle()
    assert theme.get_theme() == before


def test_reduce_motion_action(win):
    from PyQt6.QtGui import QAction
    win._theme_action.setChecked(False)
    # 减少动画开关直接写设置
    theme.set_reduced_motion(True)
    assert theme.reduced_motion() is True
    theme.set_reduced_motion(False)


# ----------------------------------------------------------------
# 关于对话框
# ----------------------------------------------------------------

def test_about_dialog_opens_and_links(win, qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(mw.webbrowser, "open",
                        lambda u, **k: opened.append(u))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    win._show_about()
    gh_btn = [w for w in win.findChildren(type(win._execute_btn))
              if w.text() == "GitHub 仓库"]
    assert gh_btn
    gh_btn[0].click()
    assert opened and "github.com" in opened[0]


# ----------------------------------------------------------------
# 窗口几何持久化
# ----------------------------------------------------------------

def test_geometry_persisted_on_close(qapp):
    from src.gui_config import get_qsettings
    w = MainWindow(shield_available=True, notify_config=None)
    w.resize(1000, 700)
    w.close()
    geo = get_qsettings().value("ui/geometry")
    assert geo is not None


def test_geometry_restored_on_reopen(qapp, monkeypatch):
    """关闭保存几何 -> 重新打开时调用 restoreGeometry 恢复。

    离屏平台屏幕过小会钳制恢复后的尺寸, 因此断言「以保存值调用了
    restoreGeometry」而非最终尺寸。
    """
    from src.gui_config import get_qsettings
    w1 = MainWindow(shield_available=True, notify_config=None)
    w1.resize(1010, 705)
    w1.close()
    saved = get_qsettings().value("ui/geometry")
    assert saved is not None

    calls = []
    real_restore = MainWindow.restoreGeometry

    def spy(self, geo):
        calls.append(geo)
        return real_restore(self, geo)
    monkeypatch.setattr(MainWindow, "restoreGeometry", spy)
    w2 = MainWindow(shield_available=True, notify_config=None)
    assert calls and calls[0] == saved
    w2.close()


def test_close_terminates_running_runner(qapp):
    class FakeRunner:
        def __init__(self):
            self.calls = []

        def isRunning(self):
            return not self.calls

        def terminate(self):
            self.calls.append("terminate")

        def wait(self, ms):
            self.calls.append("wait")
            return True

    w = MainWindow(shield_available=True, notify_config=None)
    fake = FakeRunner()
    w._runner = fake
    w.close()
    assert "terminate" in fake.calls


# ----------------------------------------------------------------
# main.py 入口
# ----------------------------------------------------------------

def test_main_entrypoint(monkeypatch, qapp):
    import main as entry

    class FakeWindow:
        def __init__(self, **kwargs):
            self.shown = False

        def show(self):
            self.shown = True

    created = {}

    def fake_mainwindow(**kwargs):
        created["w"] = FakeWindow(**kwargs)
        return created["w"]

    class FakeApp:
        def __init__(self, argv):
            pass

        def exec(self):
            created["exec"] = True
            return 0

    import PyQt6.QtWidgets as QtW
    monkeypatch.setattr(QtW, "QApplication", FakeApp)
    monkeypatch.setattr(mw, "MainWindow", fake_mainwindow)
    monkeypatch.setattr(entry, "load_notify_config", lambda: None)
    monkeypatch.setattr(entry, "get_notify_config", lambda: {})
    monkeypatch.setattr(entry, "SHIELD_AVAILABLE", True, raising=False)

    import src.ui.theme as theme_mod
    monkeypatch.setattr(theme_mod, "apply_theme", lambda *a, **k: None)
    monkeypatch.setattr(theme_mod, "get_theme", lambda: "light")

    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0
    assert created["exec"] is True
