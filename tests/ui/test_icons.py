# -*- coding: utf-8 -*-
"""icons.py 与 gui_config.py 测试。"""

from src.ui import icons


def test_icon_by_token(qapp):
    assert not icons.icon("ri.play-fill").isNull()


def test_icon_by_raw_hex(qapp):
    # 停止按钮改用圆形描边图标 (原实心 stop-fill 在禁用态显示成黑方块)
    assert not icons.icon("ri.stop-circle-line", "#ffffff").isNull()


def test_accent_and_secondary(qapp):
    assert not icons.accent("ri.moon-line").isNull()
    assert not icons.secondary("ri.search-line").isNull()
