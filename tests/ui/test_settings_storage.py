# -*- coding: utf-8 -*-
"""设置页「存储位置」+「自动更新」可用性测试 (M4.4)。

覆盖:
* 配置/数据/缓存/日志四行只读展示 platform_paths() 结果 (含 tooltip);
* 「打开目录」走 QDesktopServices.openUrl(QUrl.fromLocalFile(...)), 失败静默;
* 「自动更新」行与提示文案随 platform_capabilities().self_update_available 变化。

路径与能力均由 tests/ui/conftest.py 的 platform_state_stub 注入, 不触碰
真实目录, 也不做真实平台探测。
"""

import pytest
from PyQt6.QtCore import QUrl

from pathlib import Path

import src.ui.settings_page as settings_module
from src.ui.settings_page import (
    SELF_UPDATE_AVAILABLE_TEXT,
    SELF_UPDATE_CHECK_ONLY_TEXT,
    SettingsPage,
)


class _DesktopServicesStub:
    """QDesktopServices 替身: 记录 openUrl 调用, 可模拟失败/异常。"""

    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.urls = []

    def openUrl(self, url):  # noqa: N802 - 模拟 Qt 静态 API
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def desktop_services(monkeypatch):
    stub = _DesktopServicesStub()
    monkeypatch.setattr(settings_module, "QDesktopServices", stub)
    return stub


@pytest.fixture
def page(qapp, platform_state_stub):
    return SettingsPage()


# ----------------------------------------------------------------
# 存储位置
# ----------------------------------------------------------------

def test_storage_rows_show_platform_paths(page, platform_state_stub):
    for key, _label in settings_module._STORAGE_ROWS:
        expected = str(getattr(platform_state_stub, key))
        edit = page.storage_edits[key]
        assert edit.text() == expected
        assert edit.isReadOnly() is True
        assert edit.toolTip() == expected


def test_storage_rows_cover_config_data_cache_log(page):
    assert set(page.storage_edits) == {
        "config_dir", "data_dir", "cache_dir", "log_dir"}
    assert set(page.storage_open_buttons) == set(page.storage_edits)
    # 每行都有「打开目录」按钮, 且光标为手型
    for button in page.storage_open_buttons.values():
        assert button.text() == "打开目录"
        assert button.isEnabled() is True


def test_open_storage_dir_uses_desktop_services(page, platform_state_stub,
                                                desktop_services):
    page.storage_open_buttons["config_dir"].click()

    assert len(desktop_services.urls) == 1
    url = desktop_services.urls[0]
    assert isinstance(url, QUrl)
    assert url.isLocalFile() is True
    # QUrl.toLocalFile() 在 Windows 上用正斜杠, 统一按 Path 比较
    assert Path(url.toLocalFile()) == platform_state_stub.config_dir


def test_open_storage_dir_targets_each_row(page, platform_state_stub,
                                           desktop_services):
    for key in ("data_dir", "cache_dir", "log_dir"):
        page.storage_open_buttons[key].click()

    opened = [Path(url.toLocalFile()) for url in desktop_services.urls]
    assert opened == [
        platform_state_stub.data_dir,
        platform_state_stub.cache_dir,
        platform_state_stub.log_dir,
    ]


def test_open_storage_dir_failure_is_silent(page, monkeypatch,
                                            platform_state_stub):
    """openUrl 返回 False 或抛异常都不得冒泡到 UI。"""
    monkeypatch.setattr(settings_module, "QDesktopServices",
                        _DesktopServicesStub(result=False))
    page.storage_open_buttons["log_dir"].click()  # 不抛异常

    monkeypatch.setattr(
        settings_module, "QDesktopServices",
        _DesktopServicesStub(error=RuntimeError("没有文件管理器")))
    page.storage_open_buttons["log_dir"].click()  # 依然静默


def test_open_directory_empty_path_is_noop(monkeypatch, platform_state_stub):
    stub = _DesktopServicesStub()
    monkeypatch.setattr(settings_module, "QDesktopServices", stub)

    assert settings_module.open_directory("") is False
    assert settings_module.open_directory(None) is False
    assert stub.urls == []


def test_open_directory_returns_desktop_services_result(monkeypatch,
                                                        platform_state_stub):
    monkeypatch.setattr(settings_module, "QDesktopServices",
                        _DesktopServicesStub(result=True))
    assert settings_module.open_directory(
        platform_state_stub.log_dir) is True


# ----------------------------------------------------------------
# 自动更新可用性
# ----------------------------------------------------------------

def test_auto_update_row_reports_self_update_available(page):
    # conftest 默认快照: Windows, self_update_available=True
    assert page.self_update_available is True
    assert page.auto_update_label.text() == SELF_UPDATE_AVAILABLE_TEXT == "可用"


def test_auto_update_row_check_only_on_macos(qapp, monkeypatch):
    from src.platform import capabilities as platform_caps

    monkeypatch.setattr(
        platform_caps, "detect",
        lambda: platform_caps.PlatformCapabilities(
            os_name="darwin", self_update_available=False))
    platform_caps.reset_platform_capabilities()

    page = SettingsPage()

    assert page.self_update_available is False
    assert page.auto_update_label.text() == SELF_UPDATE_CHECK_ONLY_TEXT
    assert page.auto_update_label.text() == "仅提示新版本"
    assert "Release 页面" in page.auto_update_label.toolTip()


def test_update_hint_differs_for_check_only(qapp, monkeypatch):
    from PyQt6.QtWidgets import QLabel

    from src.platform import capabilities as platform_caps

    def _hints(page):
        return " ".join(
            label.text() for label in page.findChildren(QLabel)
            if label.objectName().startswith("hint_"))

    windows_page = SettingsPage()
    assert "安装完成后程序会自动重启" in _hints(windows_page)

    monkeypatch.setattr(
        platform_caps, "detect",
        lambda: platform_caps.PlatformCapabilities(
            os_name="darwin", self_update_available=False))
    platform_caps.reset_platform_capabilities()

    macos_page = SettingsPage()
    assert "安装完成后程序会自动重启" not in _hints(macos_page)
    assert "Release 页面手动下载安装包" in _hints(macos_page)


def test_check_btn_still_emits_update_request_in_check_only(qapp, monkeypatch):
    """check-only 平台按钮文案不变, 仍走同一信号 (由主窗口分流)。"""
    from src.platform import capabilities as platform_caps

    monkeypatch.setattr(
        platform_caps, "detect",
        lambda: platform_caps.PlatformCapabilities(
            os_name="darwin", self_update_available=False))
    platform_caps.reset_platform_capabilities()

    page = SettingsPage()
    emitted = []
    page.update_check_requested.connect(lambda: emitted.append(1))
    page.check_btn.click()

    assert page.check_btn.text() == "检查更新"
    assert emitted == [1]
