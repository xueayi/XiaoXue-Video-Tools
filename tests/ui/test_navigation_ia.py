# -*- coding: utf-8 -*-
"""平铺分组导航测试: 5 个分组 11 个页面 + 首页/设置页接入。

全部 offscreen 运行: 不弹真实窗口、不跑 ffmpeg、不调用 QDialog.exec。
"""

import pytest

import src.ui.main_window as mw
from src.executors import execute_encode
from src.ui import theme
from src.ui.home_page import HomePage
from src.ui.main_window import MainWindow, _tab_defs
from src.ui.settings_page import SettingsPage
from src.ui.task_card import TaskArea
from src.ui.task_state import TaskStatus
from src.utils import get_ffmpeg_path, get_ffprobe_path

#: 侧边栏期望的 5 个分组与 11 个页面 (顺序即显示顺序)
_EXPECTED_GROUPS = [
    ("常用", ["首页"]),
    ("视频处理", ["视频压制", "音频替换", "音视频抽取"]),
    ("格式与媒体", ["封装转换", "媒体元数据检测", "图片转换"]),
    ("质量与批量", ["素材质量检测", "文件夹创建", "批量重命名"]),
    ("系统", ["设置"]),
]
_EXPECTED_ITEMS = [name for _title, items in _EXPECTED_GROUPS for name in items]

#: 业务键 (Tab.command_name) -> executor; 首页/设置没有命令名
_EXPECTED_HANDLERS = {
    "视频压制", "音频替换", "音视频抽取",
    "封装转换", "媒体元数据检测", "图片转换",
    "素材质量检测", "文件夹创建", "批量重命名",
}


@pytest.fixture
def win(qapp):
    w = MainWindow()
    yield w
    w.close()


def _section_titles(win):
    rows = win._sidebar._page_of_row
    return [win._sidebar._list.item(row).text()
            for row, page in enumerate(rows) if page is None]


def _item_titles(win):
    rows = win._sidebar._page_of_row
    return [win._sidebar._list.item(row).text()
            for row, page in enumerate(rows) if page is not None]


def _pump_until(qapp, cond, timeout_ms=5000):
    import time
    deadline = time.time() + timeout_ms / 1000
    while not cond():
        assert time.time() < deadline, "等待条件超时"
        qapp.processEvents()


# ----------------------------------------------------------------
# 导航结构
# ----------------------------------------------------------------

def test_flat_grouped_navigation_structure(win):
    assert _section_titles(win) == [title for title, _items in _EXPECTED_GROUPS]
    assert _item_titles(win) == _EXPECTED_ITEMS
    assert win._sidebar.count() == 11
    assert win._sidebar._list.count() == 5 + 11
    assert win._stack.count() == 11
    assert len(win._tabs) == 11
    # 首页/设置没有 executor, 其余 9 页保持不变
    assert len(win._handlers) == 9


def test_tab_defs_structure():
    """_tab_defs 为 [(分组标题, [(页面名, 图标名, 页面工厂), ...]), ...]。"""
    defs = _tab_defs()
    assert [title for title, _items in defs] == [
        title for title, _items in _EXPECTED_GROUPS]
    total = 0
    for (title, items), (expected_title, expected_items) in zip(
            defs, _EXPECTED_GROUPS):
        assert title == expected_title
        assert [item[0] for item in items] == expected_items
        for item in items:
            assert len(item) == 3
            assert isinstance(item[0], str) and item[0]
            assert isinstance(item[1], str) and item[1]
            assert callable(item[2])
        total += len(items)
    assert total == 11


def test_page_types(win):
    assert isinstance(win._stack.widget(0), HomePage)
    assert isinstance(win._stack.widget(10), SettingsPage)
    for index in range(1, 10):
        page = win._stack.widget(index)
        assert not isinstance(page, (HomePage, SettingsPage))


def test_page_index_map(win):
    assert win._page_index == {
        name: index for index, name in enumerate(_EXPECTED_ITEMS)
    }


def test_removed_modules_are_gone():
    """使用说明与首页 mock 示例模块已按要求删除。"""
    import importlib.util

    for module in ("src.ui.mock_data", "src.help_texts",
                   "src.ui.tabs.help_tab", "src.executors.misc_executor"):
        assert importlib.util.find_spec(module) is None, module


def test_help_menu_online_links_kept(win):
    """顶部「帮助文档」在线文档菜单保留。"""
    menus = {action.text(): action for action in win.menuBar().actions()}
    assert "帮助文档" in menus
    menu = menus["帮助文档"].menu()
    titles = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert "使用手册首页" in titles
    assert "常见问题" in titles


def test_navigation_switches_stack(win, qapp):
    win._sidebar.setCurrentRow(7)  # 素材质量检测
    _pump_until(qapp, lambda: win._stack.currentIndex() == 7)
    assert win._current_page_index == 7
    assert win._current_tab().command_name == "素材质量检测"
    win._sidebar.setCurrentRow(0)


# ----------------------------------------------------------------
# 执行路由
# ----------------------------------------------------------------

def test_handlers_business_keys_unchanged(win):
    assert set(win._handlers) == _EXPECTED_HANDLERS
    assert win._handlers["视频压制"] is execute_encode
    assert "首页" not in win._handlers
    assert "设置" not in win._handlers
    assert "使用说明" not in win._handlers


def test_execute_button_enabled_per_page(win):
    win._sidebar.setCurrentRow(0)  # 首页
    assert not win._execute_btn.isEnabled()

    win._sidebar.setCurrentRow(1)  # 视频压制
    assert win._execute_btn.isEnabled()

    win._sidebar.setCurrentRow(10)  # 设置
    assert not win._execute_btn.isEnabled()

    win._sidebar.setCurrentRow(0)
    assert not win._execute_btn.isEnabled()


def test_execute_routes_to_current_page_command(win, monkeypatch):
    captured = {}

    class _Signal:
        def connect(self, *args, **kwargs):
            pass

    class FakeRunner:
        def __init__(self, handler, args, command, parent=None):
            captured.update(handler=handler, args=args, command=command)
            self.log_signal = _Signal()
            self.progress_signal = _Signal()
            self.duration_signal = _Signal()
            self.finished_signal = _Signal()
            self.result_signal = _Signal()

        def isRunning(self):
            return False

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(mw, "TaskRunner", FakeRunner)
    sentinel = lambda args: None
    win._handlers["封装转换"] = sentinel

    win._sidebar.setCurrentRow(4)  # 封装转换
    assert win._current_tab().command_name == "封装转换"
    win._on_execute()

    assert captured["command"] == "封装转换"
    assert captured["handler"] is sentinel
    assert captured["started"] is True
    assert captured["args"].command == "封装转换"


def test_execute_noop_on_home_page(win, monkeypatch):
    class _BoomRunner:
        def __init__(self, *args, **kwargs):
            raise AssertionError("首页不应创建执行任务")

    monkeypatch.setattr(mw, "TaskRunner", _BoomRunner)
    win._sidebar.setCurrentRow(0)
    before = list(win._log_panel._chunks)
    win._on_execute()  # 不应崩溃, 也不应触发任务
    assert win._log_panel._chunks == before
    assert win._runner is None


def test_execute_noop_on_settings_page(win, monkeypatch):
    class _BoomRunner:
        def __init__(self, *args, **kwargs):
            raise AssertionError("设置页不应创建执行任务")

    monkeypatch.setattr(mw, "TaskRunner", _BoomRunner)
    win._sidebar.setCurrentRow(10)
    win._on_execute()
    assert win._runner is None


# ----------------------------------------------------------------
# 首页
# ----------------------------------------------------------------

def test_home_page_starts_empty(win):
    """新启动的首页没有示例数据, 两个列表为空且清空按钮禁用。"""
    home = win._tabs[0]
    assert isinstance(home, HomePage)
    assert home.is_executable() is False
    assert home.task_records == []
    assert home.recent_outputs == []
    assert isinstance(home._recent_tasks_area, TaskArea)
    assert home._recent_tasks_area.task_ids == []
    assert home._recent_tasks_area.isHidden() is True
    assert home._recent_tasks_placeholder.text() == "暂无任务记录"
    assert home._recent_outputs_placeholder.text() == "暂无输出文件"
    assert home._clear_records_btn.text() == "一键清空"
    assert home._clear_records_btn.isEnabled() is False
    assert home._ffmpeg_path_label.text() == get_ffmpeg_path()
    # M3.1: 探测完成前展示「正在检测…」; 结果由主窗口后台探测推送
    assert "正在检测" in home._capability_label.text()
    assert home._encoder_label.text() == "待检测"
    assert home._nvenc_label.text() == "未检测到"


def test_home_records_enable_clear_button(win):
    home = win._tabs[0]
    home.add_task_record("视频压制", TaskStatus.SUCCESS, "完成")
    assert len(home.task_records) == 1
    assert home.task_records[0].title == "视频压制"
    assert home.task_records[0].status is TaskStatus.SUCCESS
    assert home._recent_tasks_area.task_ids == [
        home.task_records[0].task_id]
    assert home._clear_records_btn.isEnabled() is True

    home.add_recent_outputs(["C:/out/a.mp4"])
    assert home.recent_outputs == ["C:/out/a.mp4"]
    assert home._recent_outputs_placeholder.isHidden() is True

    home.clear_records()
    assert home.task_records == []
    assert home.recent_outputs == []
    assert home._clear_records_btn.isEnabled() is False


def test_home_records_capped_at_ten(win):
    home = win._tabs[0]
    for index in range(12):
        home.add_task_record(f"任务 {index}", TaskStatus.SUCCESS)
    assert len(home.task_records) == 10
    # 最新在前
    assert home.task_records[0].title == "任务 11"

    for index in range(12):
        home.add_recent_outputs([f"C:/out/{index}.mp4"])
    assert len(home.recent_outputs) == 10
    assert home.recent_outputs[0] == "C:/out/11.mp4"


def test_home_quick_action_emits_navigate_requested(win):
    home = win._tabs[0]
    got = []
    home.navigate_requested.connect(got.append)
    home._quick_encode_btn.click()
    assert got == ["视频压制"]


def test_home_quick_action_navigates_to_video_encode(win, qapp):
    win._sidebar.setCurrentRow(0)
    win._tabs[0]._quick_encode_btn.click()

    assert win._current_page_index == 1
    assert win._current_tab().command_name == "视频压制"
    assert win._execute_btn.isEnabled()
    _pump_until(qapp, lambda: win._stack.currentIndex() == 1)


# ----------------------------------------------------------------
# 设置页
# ----------------------------------------------------------------

def test_settings_page_groups(win):
    from PyQt6.QtWidgets import QGroupBox

    settings = win._tabs[10]
    assert isinstance(settings, SettingsPage)
    assert settings.is_executable() is False
    titles = [group.title() for group in settings.findChildren(QGroupBox)]
    assert titles == ["FFmpeg", "外观", "更新", "高级"]
    # 通知面板已随功能下线, 设置页不包含
    assert "通知" not in " ".join(titles)


def test_settings_ffmpeg_group_readonly(win):
    settings = win._tabs[10]
    assert settings.ffmpeg_path_edit.isReadOnly()
    assert settings.ffmpeg_path_edit.text() == get_ffmpeg_path()
    assert settings.ffprobe_path_edit.isReadOnly()
    assert settings.ffprobe_path_edit.text() == get_ffprobe_path()


def test_settings_update_button_reuses_dialog(win, monkeypatch):
    calls = []

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            calls.append("created")
            self.install_requested = type(
                "S", (), {"connect": staticmethod(lambda cb: None)})()

        def exec(self):
            calls.append("exec")

    monkeypatch.setattr(mw, "UpdateDialog", FakeDialog)
    win._sidebar.setCurrentRow(10)
    settings = win._tabs[10]

    emitted = []
    settings.update_check_requested.connect(lambda: emitted.append(1))
    settings.check_btn.click()

    assert emitted == [1]
    assert calls == ["created", "exec"]


def test_settings_appearance_switches_theme(win):
    win._sidebar.setCurrentRow(10)
    settings = win._tabs[10]

    before = theme.get_theme()
    target = "dark" if before == "light" else "light"
    settings.theme_combo.setCurrentText(settings._theme_label(target))

    assert theme.get_theme() == target
    assert win._theme_action.isChecked() == (target == "dark")

    settings.theme_combo.setCurrentText(settings._theme_label(before))
    assert theme.get_theme() == before
    assert win._theme_action.isChecked() == (before == "dark")


def test_settings_reduced_motion_syncs_menu_action(win):
    win._sidebar.setCurrentRow(10)
    settings = win._tabs[10]

    before = theme.reduced_motion()
    settings.reduced_motion_cb.setChecked(not before)
    assert theme.reduced_motion() is (not before)
    assert win._motion_action.isChecked() is (not before)

    settings.reduced_motion_cb.setChecked(before)
    assert theme.reduced_motion() is before
    assert win._motion_action.isChecked() is before


def test_theme_toggle_syncs_settings_appearance(win):
    win._sidebar.setCurrentRow(10)
    settings = win._tabs[10]

    before = theme.get_theme()
    win._on_theme_toggle()
    assert theme.get_theme() != before
    assert settings.theme_combo.currentText() == settings._theme_label(
        theme.get_theme())

    win._on_theme_toggle()
    assert theme.get_theme() == before


def test_motion_menu_action_syncs_settings_checkbox(win):
    win._sidebar.setCurrentRow(10)
    settings = win._tabs[10]

    before = theme.reduced_motion()
    win._motion_action.trigger()
    assert theme.reduced_motion() is (not before)
    assert settings.reduced_motion_cb.isChecked() is (not before)

    win._motion_action.trigger()
    assert theme.reduced_motion() is before
    assert settings.reduced_motion_cb.isChecked() is before
