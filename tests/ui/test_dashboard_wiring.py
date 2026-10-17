# -*- coding: utf-8 -*-
"""PR-06 组件接入测试: 底部任务卡 / 折叠日志 / 错误卡 + 首页 mock 最近任务。

全部 offscreen 运行: 不跑真实 ffmpeg、不弹真实窗口、不调用 QDialog.exec。
"""

import time
from pathlib import Path

import pytest

from src.ui.collapsible_log import CollapsibleLog
from src.ui.error_card import ErrorCategory, ErrorInfo
from src.ui.ffmpeg_progress import ProgressInfo
from src.ui.home_page import HomePage
from src.ui.main_window import MainWindow
from src.ui.mock_data import MOCK_TASKS
from src.ui.task_card import CURRENT_TASK_ID, TaskArea, TaskCard
from src.ui.task_state import TaskStatus
from src.task.result import TaskResult

import src.ui.main_window as mw


@pytest.fixture
def win(qapp):
    w = MainWindow()
    yield w
    w.close()


def _pump_until(qapp, cond, timeout_ms=5000):
    deadline = time.time() + timeout_ms / 1000
    while not cond():
        assert time.time() < deadline, "等待条件超时"
        qapp.processEvents()


# ----------------------------------------------------------------
# 底部执行区接线
# ----------------------------------------------------------------

def test_bottom_dashboard_is_task_area(win):
    assert isinstance(win._dashboard, TaskArea)
    assert win._dashboard.objectName() == "task_area"
    assert isinstance(win._log_box, CollapsibleLog)
    assert win._error_card.isHidden() is True


def test_ffmpeg_parser_still_feeds_task_area(win):
    """_ffmpeg_parser.progress_updated 接线保留, 驱动 TaskArea 的旧 API。"""
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.progress_updated.emit(
        ProgressInfo(percent=33.0, speed=1.5, eta_sec=12.0, frame=100))
    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.RUNNING
    assert state.progress == 33.0
    assert state.speed == 1.5
    assert state.eta_sec == 12.0


# ----------------------------------------------------------------
# 折叠日志
# ----------------------------------------------------------------

def test_log_box_default_collapsed(win):
    assert win._log_box.is_expanded() is False
    assert win._log_box.panel.isHidden() is True
    assert win._log_box._toggle.objectName() == "fold_header"


def test_log_panel_compat_while_collapsed(win):
    """旧 API 兼容: _log_panel 指向内层 LogPanel, 折叠时仍可写入。"""
    assert win._log_panel is win._log_box.panel
    assert win._log_panel.isHidden() is True

    win._log_panel.append_log("折叠日志\n")
    assert win._log_panel._chunks == ["折叠日志\n"]
    assert "折叠日志" in win._log_panel._view.toPlainText()

    win._log_box.append_log("经由折叠容器写入\n")
    assert win._log_box.panel._chunks[-1] == "经由折叠容器写入\n"

    win._log_panel.on_theme_changed()  # 旧调用方式仍可用
    assert win._log_panel._tool_icon_names


def test_error_log_request_expands_collapsed_log(win):
    assert win._log_box.is_expanded() is False
    win._error_card.show(ErrorInfo(title="t", causes=["原因"], actions=["操作"]))
    win._error_card._log_btn.click()
    assert win._log_box.is_expanded() is True
    assert win._log_box.panel.isHidden() is False


# ----------------------------------------------------------------
# 错误卡片
# ----------------------------------------------------------------

def test_failure_shows_error_card_with_category(win):
    win._log_panel.append_log(
        "[h264_nvenc @ 000001f4] No NVENC capable devices found\n")
    win._on_task_finished(False, "视频压制")

    card = win._error_card
    assert card.isHidden() is False
    assert card.error is not None
    assert card.error.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert "硬件编码器" in card._title_label.text()
    assert card._action_buttons  # 建议操作按钮可见

    # 任务卡也切到失败终态
    assert (win._dashboard._cards[CURRENT_TASK_ID].state.status
            is TaskStatus.FAILED)


def test_execute_failure_flow_shows_error_card(win, qapp):
    """真实执行失败链路: 日志中的 NVENC 关键词被归类为编码器不可用。"""
    def boom(args):
        print("[h264_nvenc @ 0000] No NVENC capable devices found")
        raise RuntimeError("编码失败")

    win._handlers["视频压制"] = boom
    win._sidebar.setCurrentRow(1)  # 视频压制
    win._on_execute()
    _pump_until(qapp, lambda: "失败" in win.statusBar().currentMessage())

    assert win._error_card.isHidden() is False
    assert win._error_card.error.category is ErrorCategory.ENCODER_UNAVAILABLE


def test_success_hides_error_card(win):
    win._error_card.show(ErrorInfo(title="旧错误", causes=["原因"]))
    assert win._error_card.isHidden() is False

    win._on_task_finished(True, "视频压制")
    assert win._error_card.isHidden() is True


def test_stop_hides_error_card(win):
    class FakeRunner:
        def __init__(self):
            self.terminated = False

        def isRunning(self):
            return True

        def terminate(self):
            self.terminated = True

        def wait(self, ms):
            return True

    win._error_card.show(ErrorInfo(title="旧错误", causes=["原因"]))
    fake = FakeRunner()
    win._runner = fake
    win._on_stop()

    assert fake.terminated is True
    assert win._error_card.isHidden() is True
    assert win._dashboard.isHidden() is True
    win._runner = None


def test_new_task_hides_previous_error_card(win, qapp):
    win._error_card.show(ErrorInfo(title="旧错误", causes=["原因"]))
    win._handlers["视频压制"] = lambda args: TaskResult.ok()
    win._sidebar.setCurrentRow(1)  # 视频压制

    win._on_execute()
    assert win._error_card.isHidden() is True
    # 等后台线程正常结束, 避免关闭窗口时悬挂
    _pump_until(qapp, lambda: "完成" in win.statusBar().currentMessage())


def test_error_action_requested_logs_hint(win):
    win._error_card.show(
        ErrorInfo(title="t", actions=["改用 CPU 编码 (H.264 / H.265)"]))
    win._error_card._action_buttons[0].click()

    assert any("改用 CPU 编码" in chunk for chunk in win._log_panel._chunks)
    assert "改用 CPU 编码" in win.statusBar().currentMessage()


# ----------------------------------------------------------------
# 取消链路 (复用既有停止路径, 不新增 terminate 调用点)
# ----------------------------------------------------------------

def test_task_area_cancel_requested_reaches_stop(win):
    class FakeRunner:
        def __init__(self):
            self.terminated = False

        def isRunning(self):
            return True

        def terminate(self):
            self.terminated = True

        def wait(self, ms):
            return True

    fake = FakeRunner()
    win._runner = fake
    win._set_running(True)
    win._dashboard.show_indeterminate()

    card = win._dashboard._cards[CURRENT_TASK_ID]
    assert card._cancel_btn.isEnabled() is True
    card._cancel_btn.click()

    assert fake.terminated is True
    assert any("已停止" in chunk for chunk in win._log_panel._chunks)
    assert win._stop_btn.isEnabled() is False
    win._runner = None


def test_no_new_terminate_call_sites():
    """守护: PR-06 未新增 QThread.terminate() 调用点 (仅既有 2 处)。"""
    source_path = (
        Path(__file__).resolve().parents[2] / "src" / "ui" / "main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert source.count(".terminate()") == 2


# ----------------------------------------------------------------
# TaskResult -> 视图状态映射 (M2.1)
# ----------------------------------------------------------------

def test_on_task_result_success_updates_card_and_status(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.ok(outputs=("out.mp4",)))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.SUCCESS
    assert state.progress == 100.0
    assert "完成" in win.statusBar().currentMessage()
    assert win._error_card.isHidden() is True
    assert win._execute_btn.isEnabled()
    assert win._stop_btn.isEnabled() is False
    assert any("执行完成" in chunk for chunk in win._log_panel._chunks)


def test_on_task_result_failed_shows_error_card(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    win._log_panel.append_log(
        "[h264_nvenc @ 000001f4] No NVENC capable devices found\n")
    win._on_task_result(TaskResult.failed("FFmpeg 退出码 1", exit_code=1))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.FAILED
    assert state.progress is None
    assert win._error_card.isHidden() is False
    assert win._error_card.error.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert "失败" in win.statusBar().currentMessage()
    assert any("FFmpeg 退出码 1" in chunk for chunk in win._log_panel._chunks)


def test_on_task_result_cancelled_not_treated_as_failure(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.cancelled("用户点了停止"))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.CANCELLED
    assert state.progress is None
    assert "已取消" in win.statusBar().currentMessage()
    assert win._error_card.isHidden() is True
    assert any("已取消" in chunk for chunk in win._log_panel._chunks)


def test_on_task_result_partial_shows_warning_status(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "封装转换"
    win._on_task_result(TaskResult.partial("成功 2 个, 失败 1 个"))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.PARTIAL
    assert state.progress == 100.0
    assert "成功 2 个" in state.message
    assert "部分完成" in win.statusBar().currentMessage()
    assert win._error_card.isHidden() is True
    assert any("部分完成" in chunk for chunk in win._log_panel._chunks)


def test_on_task_result_warnings_are_logged(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.ok(warnings=("分发失败: 目录不可写",)))
    assert any("分发失败: 目录不可写" in chunk
               for chunk in win._log_panel._chunks)


def test_on_task_result_non_result_payload_is_failed(win):
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._on_task_result(object())
    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.FAILED
    assert win._error_card.isHidden() is False


def test_execute_connects_result_signal_not_finished(win, monkeypatch):
    """主路径只接 result_signal; finished_signal 不再连接。"""
    connected = []

    class _Signal:
        def __init__(self, name):
            self.name = name

        def connect(self, slot):
            connected.append((self.name, slot))

    class FakeRunner:
        def __init__(self, handler, args, command, parent=None):
            self.log_signal = _Signal("log")
            self.result_signal = _Signal("result")
            self.finished_signal = _Signal("finished")

        def isRunning(self):
            return False

        def start(self):
            connected.append(("start", None))

    monkeypatch.setattr(mw, "TaskRunner", FakeRunner)
    win._sidebar.setCurrentRow(1)
    win._on_execute()

    names = [name for name, _ in connected]
    assert "result" in names
    assert "finished" not in names
    assert "start" in names


# ----------------------------------------------------------------
# 底部区域高度 (任务卡/错误卡/展开日志不被挤压)
# ----------------------------------------------------------------

def test_bottom_area_reserves_height_for_visible_content(win):
    base = win._bottom.minimumHeight()
    assert base == 100  # _CenteredColumnWidget 基线

    # 运行中的任务卡需要额外高度
    win._dashboard.show_indeterminate()
    win._refresh_bottom_minimum()
    running_min = win._bottom.minimumHeight()
    assert running_min > base

    # 失败时任务卡 + 错误卡需要更多高度
    win._log_panel.append_log("No NVENC capable devices found\n")
    win._on_task_finished(False, "视频压制")
    error_min = win._bottom.minimumHeight()
    assert error_min > running_min
    assert win._error_card.isHidden() is False
    assert win._error_card.sizeHint().height() > 0

    # 展开折叠日志时再为日志留出空间
    win._on_error_log_requested()
    assert win._bottom.minimumHeight() > error_min

    # 停止/重置后回落到基线
    win._dashboard.reset()
    win._error_card.hide()
    win._log_box.collapse()
    win._refresh_bottom_minimum()
    assert win._bottom.minimumHeight() == base


# ----------------------------------------------------------------
# 首页 mock 最近任务
# ----------------------------------------------------------------

def test_home_recent_tasks_use_mock_data(win):
    home = win._tabs[0]
    assert isinstance(home, HomePage)
    area = home._recent_tasks_area
    assert isinstance(area, TaskArea)
    assert area.task_ids == [task.task_id for task in MOCK_TASKS]
    assert len(area.task_ids) == 5
    assert len(area.findChildren(TaskCard)) == 5

    statuses = {card.state.status for card in area._cards.values()}
    assert statuses == {
        TaskStatus.RUNNING,
        TaskStatus.SUCCESS,
        TaskStatus.PARTIAL,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
    # 保留「示例数据」说明标签
    assert home._recent_tasks_placeholder.text()
    assert "示例数据" in home._recent_tasks_placeholder.text()


def test_home_mock_cancel_is_local_only(win):
    home = win._tabs[0]
    area = home._recent_tasks_area
    card = area._cards["mock-running-001"]
    assert card.state.status is TaskStatus.RUNNING

    card._cancel_btn.click()

    # 只在本地把该卡置为已取消, 其余卡不变
    assert area._cards["mock-running-001"].state.status is TaskStatus.CANCELLED
    assert area._cards["mock-success-001"].state.status is TaskStatus.SUCCESS
    assert "已取消" in area._cards["mock-running-001"]._status_label.text()

    # 不接后端: 没有 TaskRunner, 底部执行区不受影响
    assert win._runner is None
    assert win._dashboard.isHidden() is True
    assert win._execute_btn.isEnabled() is False  # 首页不参与执行
    assert not any("已停止" in chunk for chunk in win._log_panel._chunks)


def test_home_mock_cards_are_not_bound_to_execution(win):
    """首页示例卡片的信号只落在首页本地, 不连到主窗口停止路径。"""
    home = win._tabs[0]
    received = []
    home._recent_tasks_area.cancel_requested.connect(received.append)

    home._recent_tasks_area._cards["mock-running-001"]._cancel_btn.click()
    assert received == ["mock-running-001"]
    assert win._error_card.isHidden() is True
