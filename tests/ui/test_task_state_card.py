# -*- coding: utf-8 -*-
"""task_state.py / task_card.py 测试: 6 态渲染、取消可用性、TaskArea API 与旧仪表盘适配。"""

from types import SimpleNamespace

import pytest

from PyQt6.QtWidgets import QProgressBar

from src.ui import theme
from src.ui.task_card import (
    CURRENT_TASK_ID,
    TaskArea,
    TaskCard,
    status_color,
)
from src.ui.task_state import ALL_STATUSES, TaskStatus, TaskViewState


# ----------------------------------------------------------------
# TaskStatus / TaskViewState (纯 Python)
# ----------------------------------------------------------------

def test_status_has_six_members():
    assert [status.value for status in TaskStatus] == [
        "queued", "running", "success", "partial", "failed", "cancelled",
    ]
    assert len(ALL_STATUSES) == 6


def test_status_convenience_properties():
    assert TaskStatus.QUEUED.is_terminal is False
    assert TaskStatus.RUNNING.is_terminal is False
    assert TaskStatus.RUNNING.is_active is True
    for status in (TaskStatus.SUCCESS, TaskStatus.PARTIAL,
                   TaskStatus.FAILED, TaskStatus.CANCELLED):
        assert status.is_terminal is True
        assert status.is_active is False

    assert TaskStatus.SUCCESS.is_ok is True
    assert TaskStatus.PARTIAL.is_ok is True
    assert TaskStatus.FAILED.is_ok is False
    assert TaskStatus.CANCELLED.is_ok is False

    assert TaskStatus.QUEUED.can_cancel is True
    assert TaskStatus.RUNNING.can_cancel is True
    assert TaskStatus.SUCCESS.can_cancel is False
    assert TaskStatus.PARTIAL.can_cancel is False
    assert TaskStatus.FAILED.can_cancel is False
    assert TaskStatus.CANCELLED.can_cancel is False

    assert all(status.label for status in TaskStatus)


def test_status_coerce():
    assert TaskStatus.coerce("running") is TaskStatus.RUNNING
    assert TaskStatus.coerce(" SUCCESS ") is TaskStatus.SUCCESS
    assert TaskStatus.coerce(TaskStatus.FAILED) is TaskStatus.FAILED
    assert TaskStatus.coerce(None) is TaskStatus.QUEUED
    with pytest.raises(ValueError):
        TaskStatus.coerce("not-a-status")


def test_task_state_normalizes_progress_and_eta():
    state = TaskViewState("t1", status="running", progress=123.0, eta_sec=-5)
    assert state.status is TaskStatus.RUNNING
    assert state.progress == 100.0
    assert state.eta_sec is None
    assert state.is_terminal is False
    assert state.can_cancel is True

    assert TaskViewState("t2", progress=float("nan")).progress is None
    assert TaskViewState("t3", progress=-5).progress == 0.0
    assert TaskViewState("t4", progress=42.5).progress == 42.5
    assert TaskViewState("t5", eta_sec=12.5).eta_sec == 12.5
    assert TaskViewState("t6", status=TaskStatus.PARTIAL).is_ok is True


# ----------------------------------------------------------------
# TaskCard 渲染
# ----------------------------------------------------------------

@pytest.mark.parametrize("status", ALL_STATUSES, ids=lambda s: s.value)
def test_task_card_renders_status(qapp, status):
    state = TaskViewState(
        task_id=f"task-{status.value}",
        title=f"任务 {status.label}",
        status=status,
        encoder="x264",
        progress=40.0,
        message="说明文字",
    )
    card = TaskCard(state)

    assert card.property("status") == status.value
    assert card._title_label.text() == f"任务 {status.label}"
    assert card._status_label.text() == status.label
    assert card._status_label.property("status") == status.value

    bar = card.findChild(QProgressBar, "dashboard_progress")
    assert bar is card._progress_bar
    assert bar.maximum() == 1000
    assert bar.value() == 400
    assert card._percent_label.text() == "40.0%"

    # 取消按钮仅在 QUEUED / RUNNING 可用
    assert card._cancel_btn.isEnabled() == status.can_cancel
    assert card._cancel_btn.isHidden() == status.is_terminal


def test_task_card_indeterminate_progress(qapp):
    card = TaskCard(TaskViewState("t", status=TaskStatus.RUNNING))
    assert card._progress_bar.maximum() == 0  # 不确定进度 (忙碌态)
    assert card._progress_bar.isHidden() is False
    assert card._percent_label.text() == "--"


def test_task_card_terminal_without_progress_hides_bar(qapp):
    card = TaskCard(TaskViewState("t", status=TaskStatus.FAILED))
    assert card._progress_bar.isHidden() is True


def test_task_card_unknown_title_placeholder(qapp):
    card = TaskCard(TaskViewState("t"))
    assert card._title_label.text() == "（未命名任务）"


def test_task_card_meta_shows_encoder_speed_eta(qapp):
    state = TaskViewState(
        "t", status=TaskStatus.RUNNING, encoder="NVENC H.264",
        progress=10.0, speed=1.85, eta_sec=38.0, elapsed_sec=42.0,
        output_path=r"D:\输出\成片.mp4",
    )
    card = TaskCard(state)
    text = card._meta_label.text()
    assert "NVENC H.264" in text
    assert "1.85x" in text
    assert "剩余 00:38" in text
    assert "耗时 00:00:42" in text
    assert "输出 成片.mp4" in text
    assert card._meta_label.toolTip() == r"D:\输出\成片.mp4"


def test_task_card_set_state_rejects_non_state(qapp):
    card = TaskCard()
    with pytest.raises(TypeError):
        card.set_state("not-a-state")


def test_task_card_set_state_updates_cancel_availability(qapp):
    card = TaskCard(TaskViewState("t", status=TaskStatus.QUEUED))
    assert card._cancel_btn.isEnabled() is True
    assert card._cancel_btn.isHidden() is False

    card.set_state(TaskViewState("t", status=TaskStatus.CANCELLED))
    assert card._cancel_btn.isEnabled() is False
    assert card._cancel_btn.isHidden() is True


def test_task_card_cancel_signal(qapp):
    card = TaskCard(TaskViewState("task-1", status=TaskStatus.RUNNING))
    received = []
    card.cancel_requested.connect(received.append)

    card._cancel_btn.click()
    assert received == ["task-1"]


def test_task_card_terminal_does_not_emit_cancel(qapp):
    card = TaskCard(TaskViewState("task-1", status=TaskStatus.SUCCESS))
    received = []
    card.cancel_requested.connect(received.append)

    card._cancel_btn.click()  # 已被禁用/隐藏，点击不发信号
    assert received == []


def test_task_card_details_signal(qapp):
    card = TaskCard(TaskViewState("task-2", status=TaskStatus.FAILED))
    received = []
    card.details_requested.connect(received.append)

    card._details_btn.click()
    assert received == ["task-2"]


def test_status_color_uses_theme_tokens(qapp):
    assert status_color(TaskStatus.RUNNING) == theme.color("accent", "light")
    assert status_color(TaskStatus.SUCCESS) == theme.color("success", "light")
    assert status_color(TaskStatus.PARTIAL) == theme.color("warning", "light")
    assert status_color(TaskStatus.FAILED) == theme.color("danger", "light")


# ----------------------------------------------------------------
# TaskArea
# ----------------------------------------------------------------

def _running_states(count=3):
    return [
        TaskViewState(f"t{i}", title=f"任务 {i}", status=TaskStatus.RUNNING)
        for i in range(count)
    ]


def test_task_area_set_tasks(qapp):
    area = TaskArea()
    area.set_tasks(_running_states())
    assert area.task_ids == ["t0", "t1", "t2"]
    assert len(area.findChildren(TaskCard)) == 3
    assert area._placeholder.isHidden() is True


def test_task_area_update_task(qapp):
    area = TaskArea()
    area.set_tasks([TaskViewState("t0", status=TaskStatus.RUNNING)])
    card = area.update_task(
        TaskViewState("t0", status=TaskStatus.SUCCESS, progress=100.0)
    )
    assert card.state.status is TaskStatus.SUCCESS
    assert len(area.task_ids) == 1


def test_task_area_update_task_adds_unknown(qapp):
    area = TaskArea()
    area.set_tasks([])
    area.update_task(TaskViewState("new", status=TaskStatus.QUEUED))
    assert area.task_ids == ["new"]
    assert len(area.findChildren(TaskCard)) == 1


def test_task_area_clear(qapp):
    area = TaskArea()
    area.set_tasks(_running_states(2))
    area.clear()
    assert area.task_ids == []
    assert area.findChildren(TaskCard) == []
    assert area._placeholder.isHidden() is False


def test_task_area_forwards_signals(qapp):
    area = TaskArea()
    area.set_tasks([TaskViewState("a", status=TaskStatus.RUNNING)])
    cancels, details = [], []
    area.cancel_requested.connect(cancels.append)
    area.details_requested.connect(details.append)

    card = area._cards["a"]
    card._cancel_btn.click()
    card._details_btn.click()
    assert cancels == ["a"]
    assert details == ["a"]


# ----------------------------------------------------------------
# 旧 ProgressDashboard API 适配
# ----------------------------------------------------------------

def _progress_info(percent=42.5, speed=1.5, eta_sec=30.0, frame=100):
    return SimpleNamespace(percent=percent, speed=speed, eta_sec=eta_sec, frame=frame)


def test_task_area_show_indeterminate(qapp):
    area = TaskArea()
    area.show_indeterminate()
    assert area.task_ids == [CURRENT_TASK_ID]
    state = area._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.RUNNING
    assert state.progress is None
    assert area._cards[CURRENT_TASK_ID]._progress_bar.maximum() == 0


def test_task_area_update_metrics(qapp):
    area = TaskArea()
    area.show_indeterminate()
    area.update_metrics(_progress_info())
    state = area._states[CURRENT_TASK_ID]
    assert state.progress == 42.5
    assert state.speed == 1.5
    assert state.eta_sec == 30.0
    assert area._cards[CURRENT_TASK_ID]._progress_bar.value() == 425


def test_task_area_update_metrics_without_show(qapp):
    area = TaskArea()
    area.update_metrics(_progress_info(percent=0.0, speed=0.0, eta_sec=-1.0))
    state = area._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.RUNNING
    assert state.progress == 0.0
    assert state.eta_sec is None
    assert area.isHidden() is False


def test_task_area_finish_success(qapp):
    area = TaskArea()
    area.show_indeterminate()
    area.update_metrics(_progress_info())
    area.finish(True)
    state = area._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.SUCCESS
    assert state.progress == 100.0
    assert area._cards[CURRENT_TASK_ID]._cancel_btn.isEnabled() is False


def test_task_area_finish_failure(qapp):
    area = TaskArea()
    area.show_indeterminate()
    area.finish(False)
    state = area._states[CURRENT_TASK_ID]
    assert state.status is TaskStatus.FAILED
    assert state.message


def test_task_area_reset(qapp):
    area = TaskArea()
    area.show_indeterminate()
    area.reset()
    assert area.task_ids == []
    assert area.findChildren(TaskCard) == []
    assert area.isHidden() is True


# ----------------------------------------------------------------
# 主题 QSS 新增规则
# ----------------------------------------------------------------

def test_theme_qss_contains_task_component_selectors(qapp):
    selectors = [
        'QFrame#task_card[status="running"]',
        "QFrame#error_card",
        "QFrame#execution_summary",
        "QLabel#summary_line",
        "QLabel#media_field_value",
        "QPushButton#plan_card:checked",
        "QFrame#plan_card[selected=\"true\"]",
    ]
    for name in ("light", "dark"):
        qss = theme.get_stylesheet(name)
        for selector in selectors:
            assert selector in qss, f"{name} 缺少 QSS: {selector}"
        # 全部令牌必须替换成功 (safe_substitute 不会因缺令牌报错)
        assert "$" not in qss


def test_new_warning_token_in_both_palettes():
    assert "warning" in theme.PALETTES["light"]
    assert "warning" in theme.PALETTES["dark"]
    assert theme.PALETTES["light"]["warning"] != theme.PALETTES["dark"]["warning"]
