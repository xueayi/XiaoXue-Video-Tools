# -*- coding: utf-8 -*-
"""首页/设置页 FFmpeg 能力展示 + 主窗口后台探测接线 (M3.1)。

探测本身由 tests/capabilities 覆盖; 这里全部使用 tests/ui/conftest.py 的
``capability_probe_stub`` 替身, 不启动真实 QThread, 只验证:
* 首页/设置页在「探测中 / 成功 / 失败」三态下的展示文案;
* 设置页「重新检测」信号与按钮禁用/恢复;
* 主窗口 show 后启动一次探测、防重复、完成后刷新两处展示。
"""

import pytest

from src.capabilities.ffmpeg_probe import (
    KEY_ENCODERS,
    FfmpegCaps,
    set_capabilities,
)
from src.ui.home_page import HomePage
from src.ui.main_window import MainWindow
from src.ui.settings_page import SettingsPage


def _caps(encoders=None, probe_error=None, version="7.1"):
    names = set(KEY_ENCODERS) if encoders is None else set(encoders)
    return FfmpegCaps(
        ffmpeg_path="C:/bin/ffmpeg.exe",
        version=version,
        encoders=frozenset(names),
        filters=frozenset({"scale", "subtitles"}),
        hwaccels=frozenset({"cuda"}),
        probe_error=probe_error,
        probed_at=123.0,
    )


@pytest.fixture
def win(qapp):
    w = MainWindow()
    yield w
    w.close()


# ----------------------------------------------------------------
# 首页展示
# ----------------------------------------------------------------

def test_home_shows_probing_before_caps(qapp):
    home = HomePage()
    assert "正在检测" in home._capability_label.text()
    assert home._encoder_label.text() == "待检测"
    assert home._nvenc_label.text() == "未检测到"


def test_home_update_capabilities_success(qapp):
    home = HomePage()
    home.update_capabilities(_caps())

    assert "检测完成" in home._capability_label.text()
    assert "7.1" in home._capability_label.text()
    assert home._encoder_label.text() == "6/6 可用"
    assert home._nvenc_label.text() == "可用"


def test_home_update_capabilities_partial_encoders(qapp):
    home = HomePage()
    home.update_capabilities(_caps(encoders={"libx264", "h264_nvenc"}))

    assert home._encoder_label.text() == "2/6 可用"
    assert home._nvenc_label.text() == "可用"
    assert "h264_qsv" in home._encoder_label.toolTip()


def test_home_update_capabilities_without_nvenc(qapp):
    home = HomePage()
    home.update_capabilities(
        _caps(encoders={"libx264", "libx265", "h264_qsv", "h264_amf"}))

    assert home._encoder_label.text() == "4/6 可用"
    assert home._nvenc_label.text() == "不可用"


def test_home_update_capabilities_failure_is_truncated(qapp):
    long_error = "探测失败原因" + "x" * 400
    home = HomePage()
    home.update_capabilities(_caps(encoders=set(), probe_error=long_error))

    text = home._capability_label.text()
    assert text.startswith("检测失败: ")
    assert len(text) < 200  # 状态行只放截断后的短文本
    assert home._capability_label.toolTip() == long_error  # 完整原因在 tooltip
    assert home._encoder_label.text() == "未知"
    assert home._nvenc_label.text() == "未检测到"


def test_home_set_probing_resets_display(qapp):
    home = HomePage()
    home.update_capabilities(_caps())
    home.set_probing()

    assert "正在检测" in home._capability_label.text()
    assert home._encoder_label.text() == "待检测"
    assert home._nvenc_label.text() == "未检测到"


def test_home_uses_cached_caps_at_construction(qapp):
    set_capabilities(_caps())
    home = HomePage()
    assert "检测完成" in home._capability_label.text()
    assert home._encoder_label.text() == "6/6 可用"


# ----------------------------------------------------------------
# 设置页展示
# ----------------------------------------------------------------

def test_settings_shows_probing_and_disabled_recheck(qapp):
    page = SettingsPage()
    assert "正在检测" in page._cap_status_label.text()
    assert page.recheck_btn.isEnabled() is False


def test_settings_uses_cached_caps_at_construction(qapp):
    set_capabilities(_caps())
    page = SettingsPage()

    assert "检测完成" in page._cap_status_label.text()
    assert "6/6" in page._cap_detail_label.text()
    assert "NVENC 可用" in page._cap_detail_label.text()
    assert page.recheck_btn.isEnabled() is True


def test_settings_recheck_emits_refresh_request(qapp):
    page = SettingsPage()
    page.update_capabilities(_caps())  # 先恢复按钮

    emitted = []
    page.capability_refresh_requested.connect(lambda: emitted.append(1))
    page.recheck_btn.click()

    assert emitted == [1]


def test_settings_probing_disables_button_until_result(qapp):
    page = SettingsPage()
    page.update_capabilities(_caps())
    assert page.recheck_btn.isEnabled() is True

    page.set_probing()
    assert page.recheck_btn.isEnabled() is False
    assert "正在检测" in page._cap_status_label.text()

    page.update_capabilities(_caps(encoders={"libx264"}))
    assert page.recheck_btn.isEnabled() is True
    assert "1/6" in page._cap_detail_label.text()


def test_settings_failure_is_truncated(qapp):
    long_error = "y" * 500
    page = SettingsPage()
    page.update_capabilities(_caps(encoders=set(), probe_error=long_error))

    assert page._cap_status_label.text().startswith("检测失败: ")
    assert len(page._cap_status_label.text()) < 200
    assert page._cap_status_label.toolTip() == long_error
    assert page.recheck_btn.isEnabled() is True
    assert "未知" in page._cap_detail_label.text()


# ----------------------------------------------------------------
# 主窗口后台探测接线
# ----------------------------------------------------------------

def test_main_window_starts_probe_after_show(win, qapp, capability_probe_stub):
    assert capability_probe_stub.calls == 0  # 未 show 不探测

    win.show()
    qapp.processEvents()

    assert capability_probe_stub.calls == 1
    worker = capability_probe_stub.workers[0]
    assert worker.refresh is False
    assert win._caps_worker is worker
    assert "正在检测" in win._home_page._capability_label.text()


def test_main_window_show_twice_starts_probe_once(win, qapp,
                                                  capability_probe_stub):
    win.show()
    qapp.processEvents()
    win.show()
    qapp.processEvents()
    assert capability_probe_stub.calls == 1


def test_main_window_no_concurrent_probe(win, qapp, capability_probe_stub):
    win.show()
    qapp.processEvents()

    same = win._start_capability_probe()
    assert same is capability_probe_stub.workers[0]
    assert capability_probe_stub.calls == 1  # 已有 worker 在跑, 不重复创建


def test_main_window_refreshes_both_pages_on_result(win, qapp,
                                                    capability_probe_stub):
    win.show()
    qapp.processEvents()

    capability_probe_stub.emit_latest(_caps())

    assert win._caps_worker is None  # 完成后释放, 允许再次检测
    assert win._home_page._encoder_label.text() == "6/6 可用"
    assert "检测完成" in win._settings_page._cap_status_label.text()
    assert win._settings_page.recheck_btn.isEnabled() is True


def test_main_window_refreshes_pages_on_failure(win, qapp,
                                                capability_probe_stub):
    win.show()
    qapp.processEvents()

    capability_probe_stub.emit_latest(
        _caps(encoders=set(), probe_error="ffmpeg 不存在"))

    assert win._home_page._capability_label.text().startswith("检测失败")
    assert win._settings_page._cap_status_label.text().startswith("检测失败")


def test_settings_recheck_triggers_second_probe(win, qapp,
                                                capability_probe_stub):
    win.show()
    qapp.processEvents()
    capability_probe_stub.emit_latest(_caps())

    settings = win._settings_page
    assert settings.recheck_btn.isEnabled() is True
    settings.recheck_btn.click()

    assert capability_probe_stub.calls == 2
    assert capability_probe_stub.workers[-1].refresh is True
    # 探测中按钮禁用, 完成后恢复
    assert settings.recheck_btn.isEnabled() is False
    capability_probe_stub.emit_latest(_caps(encoders={"libx264"}))
    assert settings.recheck_btn.isEnabled() is True
    assert "1/6" in settings._cap_detail_label.text()


def test_main_window_uses_cached_caps_at_construction(qapp,
                                                      capability_probe_stub):
    set_capabilities(_caps())
    win = MainWindow()
    try:
        assert win._home_page._encoder_label.text() == "6/6 可用"
        assert "检测完成" in win._settings_page._cap_status_label.text()
        # 已有缓存时 show 仍会启动一次后台刷新 (refresh=False 命中单例),
        # 但页面先前的展示不应退回「正在检测…」
        win.show()
        qapp.processEvents()
        assert capability_probe_stub.calls == 1
        assert win._home_page._encoder_label.text() == "6/6 可用"
    finally:
        win.close()


def test_main_window_close_waits_probe_worker(win, qapp,
                                             capability_probe_stub):
    win.show()
    qapp.processEvents()
    worker = capability_probe_stub.workers[0]
    assert worker.isRunning() is True

    win.close()

    assert worker.isRunning() is False
    assert win._caps_worker is None
