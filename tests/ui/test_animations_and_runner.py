# -*- coding: utf-8 -*-
"""animations.py 与 task_runner.py 测试。"""

import time

from PyQt6.QtWidgets import QLabel, QWidget

from src.ui import theme
from src.ui.animations import (
    AnimatedStackedWidget, button_press_anim, status_flash,
)
from src.ui.task_runner import TaskRunner, _StreamRedirect


def _make_pages(stack):
    for name in ("a", "b", "c"):
        w = QWidget()
        w.setWindowTitle(name)
        stack.addWidget(w)


def test_slide_to_immediate_when_reduced_motion(qapp):
    theme.set_reduced_motion(True)
    stack = AnimatedStackedWidget()
    _make_pages(stack)
    stack.slide_to(2)
    assert stack.currentIndex() == 2


def test_slide_to_animates(qapp, pump_fn):
    theme.set_reduced_motion(False)
    stack = AnimatedStackedWidget()
    _make_pages(stack)
    stack.slide_to(1)
    pump_fn(400)
    assert stack.currentIndex() == 1
    assert not stack._is_animating


def test_slide_to_same_and_out_of_range(qapp):
    stack = AnimatedStackedWidget()
    _make_pages(stack)
    stack.slide_to(0)
    stack.slide_to(-1)
    stack.slide_to(99)
    assert stack.currentIndex() == 0


def test_slide_to_empty_stack(qapp):
    stack = AnimatedStackedWidget()
    stack.slide_to(0)
    assert stack.currentIndex() == -1


def test_button_press_anim(qapp, pump_fn):
    btn = QLabel("x")
    btn.resize(50, 20)
    btn.move(10, 10)
    theme.set_reduced_motion(False)
    anim = button_press_anim(btn)
    assert anim is not None
    pump_fn(300)


def test_button_press_anim_reduced_motion_no_start(qapp):
    theme.set_reduced_motion(True)
    btn = QLabel("x")
    btn.resize(50, 20)
    anim = button_press_anim(btn)
    assert anim.state() != anim.State.Running


def test_status_flash_restores(qapp, pump_fn):
    bar = QWidget()
    bar.setStyleSheet("QStatusBar {}")
    status_flash(bar, "#ff0000", 80)
    assert "#ff0000" in bar.styleSheet()
    pump_fn(300)
    assert "#ff0000" not in bar.styleSheet()


# ----------------------------------------------------------------
# TaskRunner
# ----------------------------------------------------------------

def _run_and_wait(runner, app, timeout_ms=5000):
    import time
    result = {}
    runner.finished_signal.connect(lambda ok, name: result.update(ok=ok, name=name))
    runner.start()
    deadline = time.time() + timeout_ms / 1000
    while not result and time.time() < deadline:
        app.processEvents()
    return result


def test_task_runner_success(qapp):
    logs = []
    runner = TaskRunner(lambda args: print("working"), None, "任务")
    runner.log_signal.connect(logs.append)
    result = _run_and_wait(runner, qapp)
    assert result == {"ok": True, "name": "任务"}
    assert any("working" in s for s in logs)


def test_task_runner_failure(qapp):
    def boom(args):
        raise ValueError("炸了")
    logs = []
    runner = TaskRunner(boom, None, "任务")
    runner.log_signal.connect(logs.append)
    result = _run_and_wait(runner, qapp)
    assert result["ok"] is False
    assert any("炸了" in s for s in logs)
    assert any("Traceback" in s for s in logs)


def test_stream_redirect_flush_noop(qapp):
    from PyQt6.QtCore import pyqtSignal, QObject

    class Holder(QObject):
        sig = pyqtSignal(str)

    h = Holder()
    r = _StreamRedirect(h.sig)
    r.flush()
    r.write("")
    assert True


def test_stream_redirect_write(qapp):
    from PyQt6.QtCore import pyqtSignal, QObject

    got = []

    class Holder(QObject):
        sig = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.sig.connect(got.append)

    h = Holder()
    r = _StreamRedirect(h.sig)
    r.write("hello")
    assert got == ["hello"]
