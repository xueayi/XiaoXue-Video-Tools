# -*- coding: utf-8 -*-
"""tests/process 公共设施: 离屏 QApplication (QProcess 后端测试用)。"""

import os

# 必须在 QApplication 创建前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XIAOXUE_NO_UPDATE_CHECK", "1")

import pytest


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication (离屏, 不显示窗口)。"""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        import sys

        app = QApplication(sys.argv)
    yield app
