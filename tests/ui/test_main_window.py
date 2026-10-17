# -*- coding: utf-8 -*-
"""main_window.py 与 main.py 入口测试。"""

import pytest
from PyQt6.QtWidgets import QDialog

import src.ui.main_window as mw
from src.task.result import TaskResult
from src.ui import theme
from src.ui.main_window import MainWindow, _CenteredColumnWidget
from src.ui.task_runner import TaskRunner


@pytest.fixture
def win(qapp):
    w = MainWindow()
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
    # 5 个分组平铺 11 页: 首页 + 9 个功能页 + 设置
    assert win._stack.count() == 11
    assert len(win._tabs) == 11
    # 9 个功能页注册了 executor (首页/设置不可执行, 使用说明已移除)
    assert len(win._handlers) == 9
    assert win._sidebar.count() == 11
    assert win.windowTitle() == "小雪工具箱"
    assert win.minimumSize().width() == 960


def test_flat_grouped_navigation(win):
    """导航为 5 个分组平铺 11 页 (无二级 Tab 容器, 无使用说明)。"""
    rows = win._sidebar._page_of_row
    section_titles = [
        win._sidebar._list.item(row).text()
        for row, page in enumerate(rows) if page is None
    ]
    item_titles = [
        win._sidebar._list.item(row).text()
        for row, page in enumerate(rows) if page is not None
    ]
    assert section_titles == [
        "常用", "视频处理", "格式与媒体", "质量与批量", "系统",
    ]
    assert item_titles == [
        "首页",
        "视频压制", "音频替换", "音视频抽取",
        "封装转换", "媒体元数据检测", "图片转换",
        "素材质量检测", "文件夹创建", "批量重命名",
        "设置",
    ]
    assert win._sidebar._list.count() == len(section_titles) + len(item_titles)
    assert win._sidebar.count() == len(item_titles)
    assert "首页" in item_titles and "设置" in item_titles
    assert "使用说明" not in item_titles


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
    win._handlers["视频压制"] = lambda args: TaskResult.ok("完成")
    # 首页执行按钮禁用, 切到「视频压制」(索引 1) 才能执行
    win._sidebar.setCurrentRow(1)
    win._on_execute()
    _pump_until(qapp, lambda: "完成" in win.statusBar().currentMessage())
    assert win._execute_btn.isEnabled()
    assert not win._stop_btn.isEnabled()


def test_execute_failure_flow(win, qapp, monkeypatch):
    def boom(args):
        raise ValueError("运行失败")
    win._handlers["视频压制"] = boom
    win._sidebar.setCurrentRow(1)
    win._on_execute()
    _pump_until(qapp, lambda: "失败" in win.statusBar().currentMessage())
    assert "执行失败" in "\n".join(win._log_panel._chunks)


def test_execute_invalid_command_logs_error(win):
    win._sidebar.setCurrentRow(1)  # 首页执行按钮禁用, 需先进入功能页
    win._handlers.clear()
    win._on_execute()
    assert any("未知命令" in c for c in win._log_panel._chunks)


def test_execute_empty_stack_noop(win, qapp):
    win._stack.setCurrentIndex(-1)
    win._on_execute()  # 不应崩溃
    qapp.processEvents()


def test_build_args_error_logged(win, monkeypatch):
    win._sidebar.setCurrentRow(1)
    monkeypatch.setattr(win._tabs[1], "build_args",
                        lambda: (_ for _ in ()).throw(RuntimeError("坏参数")))
    win._on_execute()
    assert any("坏参数" in c for c in win._log_panel._chunks)


def test_stop_without_runner_noop(win):
    win._sidebar.setCurrentRow(1)
    win._on_stop()
    assert win._execute_btn.isEnabled()


def test_stop_running_task(win, qapp):
    # 假 runner: 断言走协作式取消 (request_cancel), 不再 terminate QThread
    class FakeRunner:
        def __init__(self):
            self.cancelled = False

        def isRunning(self):
            return True

        def request_cancel(self):
            self.cancelled = True

    fake = FakeRunner()
    win._runner = fake
    win._sidebar.setCurrentRow(1)
    win._set_running(True)
    win._on_stop()
    assert fake.cancelled is True
    # 运行态等 result_signal 到达后恢复, 停止按钮先禁用防二连点
    assert win._stop_btn.isEnabled() is False
    assert win._execute_btn.isEnabled() is False
    assert any("正在停止" in c for c in win._log_panel._chunks)


def test_running_button_icons_branch(win, qapp):
    runner = TaskRunner(lambda a: None, None, "x")
    win._runner = runner
    qapp.processEvents()
    win._update_run_button_icons()
    win._set_running(True)
    win._set_running(False)
    win._runner = None
    win._update_run_button_icons()


def test_stop_button_uses_circle_outline_icon(win, monkeypatch):
    """停止按钮图标改为圆形描边 (不再用实心 stop-fill 黑方块)。"""
    captured_names = []
    real_icon = mw.icons.icon

    def spy(name, token="icon_color"):
        captured_names.append(name)
        return real_icon(name, token)

    monkeypatch.setattr(mw.icons, "icon", spy)
    win._update_run_button_icons()

    assert "ri.stop-circle-line" in captured_names
    assert "ri.stop-fill" not in captured_names
    from PyQt6.QtCore import QSize
    assert win._stop_btn.iconSize() == QSize(16, 16)


def test_stop_icon_color_follows_state(win, monkeypatch):
    """停止图标: 运行中白色 (危险色底), 禁用时用 muted 文本色。"""
    captured = []
    real_icon = mw.icons.icon

    def spy(name, token="icon_color"):
        captured.append((name, token))
        return real_icon(name, token)

    monkeypatch.setattr(mw.icons, "icon", spy)
    win._update_run_button_icons()
    idle_tokens = [token for name, token in captured
                   if name == "ri.stop-circle-line"]
    assert idle_tokens and idle_tokens[0] == theme.color("text_disabled")

    class _RunningRunner:
        def isRunning(self):
            return True

    captured.clear()
    win._runner = _RunningRunner()
    win._update_run_button_icons()
    win._runner = None
    running_tokens = [token for name, token in captured
                      if name == "ri.stop-circle-line"]
    assert running_tokens and running_tokens[0] == "#ffffff"


def test_on_duration_ready_updates_parser(win):
    """M2.4: 时长由 worker 线程预取后经信号写入解析器, 不再 GUI 线程同步 probe。"""
    win._on_duration_ready(120.0)
    assert win._ffmpeg_parser.duration == pytest.approx(120.0)
    # 非法值静默忽略, 不改动已有 duration
    win._on_duration_ready(-5)
    win._on_duration_ready("bad")
    win._on_duration_ready(None)
    assert win._ffmpeg_parser.duration == pytest.approx(120.0)


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
    w = MainWindow()
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
    w1 = MainWindow()
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
    w2 = MainWindow()
    assert calls and calls[0] == saved
    w2.close()


def test_close_cancels_running_runner(qapp):
    """关闭窗口: 先 request_cancel, 再有限等待 (不再 terminate QThread)。"""
    class FakeRunner:
        def __init__(self):
            self.calls = []

        def isRunning(self):
            return True

        def request_cancel(self):
            self.calls.append("cancel")

        def wait(self, ms):
            self.calls.append(("wait", ms))
            return False

    w = MainWindow()
    fake = FakeRunner()
    w._runner = fake
    w.close()
    assert fake.calls[0] == "cancel"
    assert any(
        isinstance(call, tuple) and call[0] == "wait" and call[1] == 5000
        for call in fake.calls)


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

    import src.ui.theme as theme_mod
    monkeypatch.setattr(theme_mod, "apply_theme", lambda *a, **k: None)
    monkeypatch.setattr(theme_mod, "get_theme", lambda: "light")

    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0
    assert created["exec"] is True


def test_execute_button_compact_and_fits_min_window(win, qapp):
    """执行/停止按钮紧凑, 且最小窗口宽度下不重叠 (回归)。"""
    assert win._execute_btn.text() == "开始执行"
    assert win._stop_btn.text() == "停止"
    win.show()
    win.resize(960, 700)  # 窗口最小宽度
    qapp.processEvents()
    bottom = win.findChild(_CenteredColumnWidget).column()
    usable = bottom.width() - 48  # 底部列左右边距
    pair = (win._execute_btn.minimumSizeHint().width()
            + win._stop_btn.minimumSizeHint().width() + 10)
    assert pair <= usable, f"执行区按钮 {pair}px 超出可用宽度 {usable}px"
    assert win._execute_btn.minimumSizeHint().width() <= 160


def test_main_exits_to_apply_pending_update(monkeypatch):
    """回归: 启动时有待应用更新, 应拉起更新器并退出 (不清空下载)。"""
    import main as entry

    launched = []
    monkeypatch.setattr(mw.updater, "has_pending_update",
                        lambda d: True)
    monkeypatch.setattr(mw.updater, "launch_updater",
                        lambda d, pid: launched.append((d, pid)))

    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0
    assert len(launched) == 1


def test_main_normal_start_no_pending(monkeypatch):
    import main as entry

    monkeypatch.setattr(mw.updater, "has_pending_update",
                        lambda d: False)
    launched = []
    monkeypatch.setattr(mw.updater, "launch_updater",
                        lambda d, pid: launched.append(1))

    class FakeApp:
        def __init__(self, argv):
            pass

        def exec(self):
            return 0

    import PyQt6.QtWidgets as QtW
    monkeypatch.setattr(QtW, "QApplication", FakeApp)
    monkeypatch.setattr(mw, "MainWindow",
                        lambda **k: type("W", (), {"show": lambda s: None})())

    import src.ui.theme as theme_mod
    monkeypatch.setattr(theme_mod, "apply_theme", lambda *a, **k: None)
    monkeypatch.setattr(theme_mod, "get_theme", lambda: "light")

    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 0
    assert launched == []
