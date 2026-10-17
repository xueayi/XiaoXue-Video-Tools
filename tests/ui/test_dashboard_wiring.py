# -*- coding: utf-8 -*-
"""PR-06 组件接入测试: 底部任务卡 / 折叠日志 / 错误卡 + 首页 mock 最近任务。

全部 offscreen 运行: 不跑真实 ffmpeg、不弹真实窗口、不调用 QDialog.exec。
"""

import time
from pathlib import Path

import pytest

from src.ui.collapsible_log import CollapsibleLog
from src.ui.error_card import ErrorCategory, ErrorInfo
from src.ui.home_page import HomePage
from src.ui.main_window import MainWindow
from src.ui.task_card import CURRENT_TASK_ID, TaskArea
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
    """M2.4: -progress 行经新解析器 -> 适配层 -> TaskArea.update_metrics。"""
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.set_duration(100.0)
    # 一个完整进度块 (stdout key=value)
    for line in (
        "frame=100\n",
        "fps=25.0\n",
        "out_time_us=50000000\n",
        "speed=2.0x\n",
        "progress=continue\n",
    ):
        win._on_progress_line(line)
    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.RUNNING
    assert state.progress == 50.0
    assert state.speed == 2.0
    assert state.eta_sec == 25.0
    # 块结束标记 -> 进度 100%
    win._on_progress_line("progress=end\n")
    assert win._dashboard._states[CURRENT_TASK_ID].progress == 100.0

    # duration 未知时只走不确定态, 不产生伪 0% 完成度
    win._ffmpeg_parser.reset()
    win._dashboard.show_indeterminate()
    win._on_progress_line("out_time_us=5000000\n")
    win._on_progress_line("progress=continue\n")
    assert win._dashboard._states[CURRENT_TASK_ID].progress is None


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
    """真实执行失败链路: TaskResult.details 中的 stderr_tail 被归类并展示。"""
    def boom(args):
        return TaskResult.failed(
            "FFmpeg 退出码 1",
            exit_code=1,
            details={"stderr_tail": (
                "[h264_nvenc @ 0000] No NVENC capable devices found\n")},
        )

    win._handlers["视频压制"] = boom
    win._sidebar.setCurrentRow(1)  # 视频压制
    win._on_execute()
    _pump_until(qapp, lambda: "失败" in win.statusBar().currentMessage())

    assert win._error_card.isHidden() is False
    assert win._error_card.error.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert "硬件编码器" in win._error_card._title_label.text()


def test_success_hides_error_card(win):
    win._error_card.show(ErrorInfo(title="旧错误", causes=["原因"]))
    assert win._error_card.isHidden() is False

    win._on_task_finished(True, "视频压制")
    assert win._error_card.isHidden() is True


def test_stop_requests_cancel_and_hides_error_card(win):
    class FakeRunner:
        def __init__(self):
            self.cancelled = False

        def isRunning(self):
            return True

        def request_cancel(self):
            self.cancelled = True

    win._error_card.show(ErrorInfo(title="旧错误", causes=["原因"]))
    fake = FakeRunner()
    win._runner = fake
    win._on_stop()

    assert fake.cancelled is True
    assert win._error_card.isHidden() is True
    assert win._stop_btn.isEnabled() is False
    assert any("正在停止" in chunk for chunk in win._log_panel._chunks)
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
# 取消链路 (M2.3: 协作式取消, 不再 terminate QThread)
# ----------------------------------------------------------------

def test_task_area_cancel_requested_reaches_stop(win):
    class FakeRunner:
        def __init__(self):
            self.cancelled = False

        def isRunning(self):
            return True

        def request_cancel(self):
            self.cancelled = True

    fake = FakeRunner()
    win._runner = fake
    win._set_running(True)
    win._dashboard.show_indeterminate()

    card = win._dashboard._cards[CURRENT_TASK_ID]
    assert card._cancel_btn.isEnabled() is True
    card._cancel_btn.click()

    assert fake.cancelled is True
    assert any("正在停止" in chunk for chunk in win._log_panel._chunks)
    assert win._stop_btn.isEnabled() is False
    assert win._execute_btn.isEnabled() is False  # 等 result_signal 到达后再恢复
    win._runner = None


def test_no_thread_terminate_call_sites():
    """守护: 停止/关闭不再使用 QThread.terminate() (M2.3 可靠取消)。"""
    source_path = (
        Path(__file__).resolve().parents[2] / "src" / "ui" / "main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert source.count(".terminate()") == 0
    assert "QThread.terminate" not in source
    assert "self._runner.terminate" not in source
    assert source.count("request_cancel") >= 2


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
    win._on_task_result(TaskResult.failed(
        "FFmpeg 退出码 1",
        exit_code=1,
        details={"stderr_tail": (
            "[h264_nvenc @ 000001f4] No NVENC capable devices found\n")},
    ))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.FAILED
    assert state.progress is None
    assert win._error_card.isHidden() is False
    assert win._error_card.error.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert "硬件编码器" in win._error_card._title_label.text()
    assert win._error_card._action_buttons  # 建议操作按钮
    assert "失败" in win.statusBar().currentMessage()
    assert any("FFmpeg 退出码 1" in chunk for chunk in win._log_panel._chunks)


def test_show_error_card_passes_stderr_tail_exit_code_and_cancelled(win, monkeypatch):
    """M2.5 接线: classify(stderr_tail, exit_code, cancelled) 由 TaskResult 驱动。"""
    calls = []
    real_classify = mw.classify_ffmpeg_error

    def spy(stderr_tail="", exit_code=None, cancelled=False):
        calls.append((stderr_tail, exit_code, cancelled))
        return real_classify(stderr_tail, exit_code, cancelled)

    monkeypatch.setattr(mw, "classify_ffmpeg_error", spy)
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    stderr_tail = ("[out#0/mp4 @ 0000] Error opening output out.mp4: "
                   "Permission denied\n")
    win._on_task_result(TaskResult.failed(
        "FFmpeg 退出码 2",
        exit_code=2,
        details={"stderr_tail": stderr_tail, "cancelled": False},
    ))

    assert calls == [(stderr_tail, 2, False)]
    info = win._error_card.error
    assert info.category is ErrorCategory.OUTPUT_PERMISSION_DENIED
    assert info.title == "没有文件写入权限"
    assert info.actions
    assert "Permission denied" in info.log_tail


def test_cancelled_result_with_cancelled_detail_does_not_show_error_card(win):
    """CANCELLED 不显示错误卡 (即使 details 带 cancelled=True / stderr 文本)。"""
    win._sidebar.setCurrentRow(1)
    win._dashboard.show_indeterminate()
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.cancelled(
        "用户取消",
        details={"cancelled": True,
                 "stderr_tail": "Exiting normally, received signal 2.\n"},
    ))
    assert win._error_card.isHidden() is True
    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.CANCELLED


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
            self.progress_signal = _Signal("progress")
            self.duration_signal = _Signal("duration")
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
    # M2.4: 进度与时长信号必须接线到主窗口
    assert "progress" in names
    assert "duration" in names
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
# 首页真实记录 (替代 mock 示例)
# ----------------------------------------------------------------

def test_home_starts_without_mock_examples(win):
    home = win._tabs[0]
    assert isinstance(home, HomePage)
    assert home.task_records == []
    assert home.recent_outputs == []
    assert home._recent_tasks_area.task_ids == []
    assert home._recent_tasks_placeholder.text() == "暂无任务记录"
    assert home._recent_outputs_placeholder.text() == "暂无输出文件"
    assert home._clear_records_btn.isEnabled() is False


def test_on_task_result_appends_home_record_and_outputs(win):
    home = win._tabs[0]
    win._sidebar.setCurrentRow(1)
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.ok("完成", outputs=("C:/out/a.mp4",)))

    assert len(home.task_records) == 1
    record = home.task_records[0]
    assert record.title == "视频压制"
    assert record.status is TaskStatus.SUCCESS
    assert record.message == "完成"
    assert home.recent_outputs == ["C:/out/a.mp4"]
    assert home._clear_records_btn.isEnabled() is True
    # 任务卡渲染在首页任务区
    assert home._recent_tasks_area.task_ids == [record.task_id]


def test_on_task_result_failed_records_without_outputs(win):
    home = win._tabs[0]
    win._sidebar.setCurrentRow(1)
    win._task_caption = "封装转换"
    win._on_task_result(TaskResult.failed("FFmpeg 退出码 1"))

    assert home.task_records[0].status is TaskStatus.FAILED
    assert home.task_records[0].title == "封装转换"
    assert home.task_records[0].message == "FFmpeg 退出码 1"
    assert home.recent_outputs == []
    assert home._clear_records_btn.isEnabled() is True


def test_on_task_result_partial_and_cancelled_recorded(win):
    home = win._tabs[0]
    win._sidebar.setCurrentRow(1)
    win._task_caption = "图片转换"
    win._on_task_result(TaskResult.partial("成功 2 个，失败 1 个"))
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.cancelled("用户取消"))

    assert [record.status for record in home.task_records] == [
        TaskStatus.CANCELLED, TaskStatus.PARTIAL]


def test_home_clear_button_clears_tasks_and_outputs(win):
    home = win._tabs[0]
    home.add_task_record("视频压制", TaskStatus.SUCCESS, "完成")
    home.add_recent_outputs(["C:/out/a.mp4", "C:/out/b.mp4"])
    assert home._clear_records_btn.isEnabled() is True

    home._clear_records_btn.click()

    assert home.task_records == []
    assert home.recent_outputs == []
    assert home._recent_tasks_area.isHidden() is True
    assert home._recent_tasks_placeholder.isHidden() is False
    assert home._recent_outputs_placeholder.isHidden() is False
    assert home._clear_records_btn.isEnabled() is False


def test_home_recent_outputs_deduped_and_capped(win):
    home = win._tabs[0]
    home.add_recent_outputs(["C:/out/a.mp4", "C:/out/b.mp4"])
    home.add_recent_outputs(["C:/out/b.mp4", "C:/out/c.mp4"])
    assert home.recent_outputs == [
        "C:/out/c.mp4", "C:/out/b.mp4", "C:/out/a.mp4"]

    for index in range(12):
        home.add_recent_outputs([f"C:/out/extra-{index}.mp4"])
    assert len(home.recent_outputs) == 10


def test_home_outputs_alone_enable_clear_button(win):
    home = win._tabs[0]
    home.add_recent_outputs(["C:/out/only.mp4"])
    assert home.task_records == []
    assert home.recent_outputs == ["C:/out/only.mp4"]
    assert home._clear_records_btn.isEnabled() is True
    home._clear_records_btn.click()
    assert home._clear_records_btn.isEnabled() is False


def test_home_records_newest_first_and_card_count(win):
    home = win._tabs[0]
    home.add_task_record("视频压制", TaskStatus.SUCCESS, "第一条")
    home.add_task_record("封装转换", TaskStatus.FAILED, "第二条")
    assert [record.title for record in home.task_records] == [
        "封装转换", "视频压制"]
    assert len(home._recent_tasks_area.task_ids) == 2


def test_on_task_result_uses_runner_command_when_caption_empty(win):
    class _FakeRunner:
        command_name = "图片转换"

        def isRunning(self):
            return False

    home = win._tabs[0]
    win._runner = _FakeRunner()
    win._task_caption = ""
    win._on_task_result(TaskResult.ok())
    win._runner = None

    assert home.task_records[0].title == "图片转换"


def test_on_task_result_records_once_per_result(win):
    home = win._tabs[0]
    win._sidebar.setCurrentRow(1)
    win._task_caption = "视频压制"
    win._on_task_result(TaskResult.ok(outputs=("C:/out/one.mp4",)))
    assert len(home.task_records) == 1
    assert home.recent_outputs == ["C:/out/one.mp4"]


def test_home_task_area_cards_reflect_records(win):
    from src.ui.task_card import TaskCard

    home = win._tabs[0]
    home.add_task_record("视频压制", TaskStatus.SUCCESS)
    home.add_task_record("封装转换", TaskStatus.FAILED)
    assert len(home._recent_tasks_area.findChildren(TaskCard)) == 2
    home.clear_records()
    assert home._recent_tasks_area.findChildren(TaskCard) == []
