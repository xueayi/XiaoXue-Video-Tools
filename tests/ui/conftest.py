# -*- coding: utf-8 -*-
"""UI 测试公共设施: 离屏 QApplication + QSettings 重定向到临时目录。"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 必须在 QApplication 创建前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication (离屏平台, 不显示任何窗口)。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    """把 QSettings 重定向到每测试独立的临时目录 (Ini 格式)。

    避免测试读写真实用户注册表/配置 (主题、窗口几何等)。
    """
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path / "settings"),
    )
    yield


@pytest.fixture(scope="session", autouse=True)
def _slot_exception_guard():
    """把 PyQt6 的槽异常从 qFatal-abort 转为可见的日志失败。

    PyQt6 在槽内出现未处理异常且 sys.excepthook 为默认值时会直接
    qFatal 杀死进程 (exit 127), 导致整个测试会话崩溃且丢失输出。
    安装自定义 excepthook 后异常只会被打印, 对应测试按断言失败处理。
    """
    import sys
    import traceback

    def hook(tp, val, tb):
        print("\n--- Qt 槽内未处理异常 ---")
        traceback.print_exception(tp, val, tb)
        print("--- 测试可能因此未完成预期操作 ---")

    sys.excepthook = hook
    yield
    sys.excepthook = sys.__excepthook__


@pytest.fixture(autouse=True)
def _drain_deferred_deletes(qapp):
    """每个测试结束后立即处理 deleteLater 与挂起事件。

    跨测试延迟析构 C++ 对象会引发随机原生崩溃 (access violation)。
    """
    from PyQt6.QtCore import QEvent
    yield
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def pump(app, ms: int):
    """跑事件循环 ms 毫秒, 让信号/动画/线程回调得到处理。"""
    import time

    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()


@pytest.fixture
def pump_fn(qapp):
    return lambda ms=100: pump(qapp, ms)
