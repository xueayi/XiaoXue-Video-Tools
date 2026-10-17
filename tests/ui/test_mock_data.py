# -*- coding: utf-8 -*-
"""mock_data.py 测试: mock 状态齐全、错误/媒体假值、DemoTaskPlayer 确定性推进。"""

import re
from pathlib import Path

from src.media_probe import DetailedMediaInfo
from src.ui.error_card import ErrorCategory
from src.ui.mock_data import (
    MOCK_ERROR,
    MOCK_MEDIA,
    MOCK_TASKS,
    DemoTaskPlayer,
)
from src.ui.task_card import TaskArea, TaskCard
from src.ui.task_state import TaskStatus, TaskViewState


def test_mock_tasks_cover_required_statuses():
    statuses = {task.status for task in MOCK_TASKS}
    assert {
        TaskStatus.RUNNING,
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    } <= statuses
    assert TaskStatus.PARTIAL in statuses  # 额外提供部分完成态
    assert all(isinstance(task, TaskViewState) for task in MOCK_TASKS)
    assert all(task.title for task in MOCK_TASKS)


def test_mock_tasks_unique_ids():
    ids = [task.task_id for task in MOCK_TASKS]
    assert len(ids) == len(set(ids))


def test_mock_running_task_has_progress():
    running = next(task for task in MOCK_TASKS if task.status is TaskStatus.RUNNING)
    assert running.progress is not None
    assert 0.0 < running.progress < 100.0
    assert running.encoder


def test_mock_error_shape():
    assert MOCK_ERROR.category is ErrorCategory.ENCODER_UNAVAILABLE
    assert len(MOCK_ERROR.causes) == 3
    assert len(MOCK_ERROR.actions) == 2
    assert MOCK_ERROR.log_tail


def test_mock_media_is_fake_detailed_info():
    assert isinstance(MOCK_MEDIA, DetailedMediaInfo)
    assert MOCK_MEDIA.filename == "示例影片.mkv"
    assert MOCK_MEDIA.duration_sec > 0
    assert MOCK_MEDIA.file_size_bytes > 0
    assert len(MOCK_MEDIA.video_streams) == 1
    assert MOCK_MEDIA.video_streams[0].codec_type == "video"
    assert len(MOCK_MEDIA.audio_streams) >= 1
    assert len(MOCK_MEDIA.subtitle_streams) >= 1
    assert MOCK_MEDIA.errors == []
    assert MOCK_MEDIA.chapters


def test_mock_tasks_render_in_task_area(qapp):
    area = TaskArea()
    area.set_tasks(MOCK_TASKS)
    assert area.task_ids == [task.task_id for task in MOCK_TASKS]
    assert len(area.findChildren(TaskCard)) == len(MOCK_TASKS)


# ----------------------------------------------------------------
# DemoTaskPlayer
# ----------------------------------------------------------------

def test_demo_player_default_state(qapp):
    player = DemoTaskPlayer()
    assert player.state.status is TaskStatus.RUNNING
    assert player.state.progress == 0.0
    assert player.is_running is False


def test_demo_player_deterministic_steps(qapp):
    player = DemoTaskPlayer(steps=4)
    states, finished = [], []
    player.state_changed.connect(states.append)
    player.finished.connect(finished.append)

    first = player.step()
    assert first.status is TaskStatus.RUNNING
    assert first.progress == 25.0

    second = player.step()
    assert second.progress == 50.0

    third = player.step()
    assert third.progress == 75.0

    final = player.step()
    assert final.status is TaskStatus.SUCCESS
    assert final.progress == 100.0
    assert final.is_terminal is True
    assert len(states) == 4
    assert finished == [final.task_id]

    # 到终态后再 step 幂等: 状态不变、不重复发信号
    again = player.step()
    assert again is final
    assert len(states) == 4
    assert len(finished) == 1


def test_demo_player_timer_start_stop(qapp):
    player = DemoTaskPlayer(steps=100, interval_ms=10)
    player.start()
    assert player.is_running is True
    player.stop()
    assert player.is_running is False


def test_demo_player_does_not_restart_after_terminal(qapp):
    player = DemoTaskPlayer(steps=1)
    player.step()
    assert player.state.is_terminal is True
    player.start()
    assert player.is_running is False


# ----------------------------------------------------------------
# 依赖约束
# ----------------------------------------------------------------

def test_mock_data_has_no_forbidden_imports():
    source_path = Path(__file__).resolve().parents[2] / "src" / "ui" / "mock_data.py"
    source = source_path.read_text(encoding="utf-8")
    # 只检查 import 行，允许文档里出现关键词
    forbidden = re.findall(
        r"^\s*(?:from|import)\s+[^\n]*(?:executors|task_runner|ffmpeg)",
        source,
        re.MULTILINE,
    )
    assert forbidden == []
