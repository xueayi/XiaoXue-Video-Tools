# -*- coding: utf-8 -*-
"""collapsible_log.py 测试: 默认折叠、展开/折叠、折叠状态下写入、LogPanel 委托。"""

from src.ui.collapsible_log import CollapsibleLog
from src.ui.log_panel import LogPanel


def test_default_collapsed(qapp):
    widget = CollapsibleLog()
    assert widget.is_expanded() is False
    assert widget.panel.isHidden() is True
    assert widget._toggle.objectName() == "fold_header"
    assert widget._toggle.text().startswith("▸")
    assert "执行日志" in widget._toggle.text()


def test_expand_and_collapse(qapp):
    widget = CollapsibleLog("运行日志")
    widget.expand()
    assert widget.is_expanded() is True
    assert widget.panel.isHidden() is False
    assert widget._toggle.text().startswith("▾")
    assert "运行日志" in widget._toggle.text()

    widget.collapse()
    assert widget.is_expanded() is False
    assert widget.panel.isHidden() is True
    assert widget._toggle.text().startswith("▸")

    widget.set_expanded(True)
    assert widget.is_expanded() is True


def test_append_while_collapsed_writes_inner_panel(qapp):
    widget = CollapsibleLog()
    assert widget.panel.isHidden() is True

    widget.append_log("collapsed line\n")
    # 折叠时日志仍写入内层 LogPanel (只是不可见)
    assert "collapsed line" in widget.panel._view.toPlainText()
    assert widget.panel._chunks == ["collapsed line\n"]

    widget.append_log("second line\n")
    assert "second line" in widget.panel._view.toPlainText()


def test_clear_log(qapp):
    widget = CollapsibleLog()
    widget.append_log("hello\n")
    widget.clear_log()
    assert widget.panel._chunks == []
    assert widget.panel._view.toPlainText() == ""


def test_panel_property_exposes_inner_log_panel(qapp):
    widget = CollapsibleLog()
    assert isinstance(widget.panel, LogPanel)
    assert widget.panel is widget._panel
    # 主窗口兼容: 外层持有 panel 后仍可访问 _chunks
    assert hasattr(widget.panel, "_chunks")


def test_delegates_use_inner_panel(qapp, monkeypatch):
    widget = CollapsibleLog()
    calls = []

    class _FakePanel:
        def append_log(self, text):
            calls.append(("append", text))

        def clear_log(self):
            calls.append(("clear", None))

        def on_theme_changed(self):
            calls.append(("theme", None))

    monkeypatch.setattr(widget, "_panel", _FakePanel())
    widget.append_log("x")
    widget.clear_log()
    widget.on_theme_changed()
    assert calls == [("append", "x"), ("clear", None), ("theme", None)]


def test_on_theme_changed_refreshes_real_panel_icons(qapp):
    widget = CollapsibleLog()
    widget.on_theme_changed()
    assert widget.panel._tool_icon_names
