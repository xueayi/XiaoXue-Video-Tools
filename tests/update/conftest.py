# -*- coding: utf-8 -*-
"""tests/update 公共 fixtures (M4.2)。"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def cache_paths(tmp_path, monkeypatch):
    """把 Windows 更新暂存目录重定向到临时 cache_dir (不写真实 _cache)。"""
    import src.update.windows as windows

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        windows, "platform_paths",
        lambda: SimpleNamespace(cache_dir=cache_dir))
    return cache_dir


@pytest.fixture
def isolated_qsettings(tmp_path, monkeypatch):
    """把 QSettings 重定向到临时 config.ini (跳过版本测试用)。"""
    from PyQt6.QtCore import QSettings

    ini = tmp_path / "config.ini"

    def fake_qsettings():
        return QSettings(str(ini), QSettings.Format.IniFormat)

    import src.gui_config as gc
    monkeypatch.setattr(gc, "get_qsettings", fake_qsettings)
