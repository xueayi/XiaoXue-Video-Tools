# -*- coding: utf-8 -*-
"""TaskStatus 测试：4 种终态、is_ok/is_terminal/label、coerce。"""

import pytest

from src.task.status import ALL_STATUSES, TaskStatus


def test_status_has_four_members():
    assert [status.value for status in TaskStatus] == [
        "success", "failed", "cancelled", "partial",
    ]
    assert len(ALL_STATUSES) == 4


def test_status_is_terminal_always_true():
    for status in TaskStatus:
        assert status.is_terminal is True


def test_status_is_ok():
    assert TaskStatus.SUCCESS.is_ok is True
    assert TaskStatus.PARTIAL.is_ok is True
    assert TaskStatus.FAILED.is_ok is False
    assert TaskStatus.CANCELLED.is_ok is False


def test_status_labels():
    assert TaskStatus.SUCCESS.label == "成功"
    assert TaskStatus.FAILED.label == "失败"
    assert TaskStatus.CANCELLED.label == "已取消"
    assert TaskStatus.PARTIAL.label == "部分完成"


def test_status_is_str_enum():
    # (str, Enum): 可直接与字符串比较，便于持久化/日志
    assert TaskStatus.SUCCESS == "success"
    assert isinstance(TaskStatus.FAILED, str)


def test_status_coerce_accepts_member_and_strings():
    assert TaskStatus.coerce(TaskStatus.PARTIAL) is TaskStatus.PARTIAL
    assert TaskStatus.coerce("failed") is TaskStatus.FAILED
    assert TaskStatus.coerce(" FAILED ") is TaskStatus.FAILED
    assert TaskStatus.coerce("CANCELLED") is TaskStatus.CANCELLED
    assert TaskStatus.coerce("partial") is TaskStatus.PARTIAL


@pytest.mark.parametrize("value", [None, "", "  ", "queued", "running", 1, object()])
def test_status_coerce_rejects_invalid(value):
    with pytest.raises(ValueError):
        TaskStatus.coerce(value)
