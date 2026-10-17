# -*- coding: utf-8 -*-
"""TaskResult 测试：构造器、不可变、legacy_success、字段归一。"""

import dataclasses

import pytest

from src.task.result import TaskResult
from src.task.status import TaskStatus


def test_ok_defaults():
    result = TaskResult.ok()
    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    assert result.message == ""
    assert result.warnings == ()
    assert result.outputs == ()
    assert result.details == {}
    assert result.is_ok is True
    assert result.legacy_success is True


def test_failed_keeps_exit_code_and_message():
    result = TaskResult.failed("FFmpeg 退出码 1", exit_code=1)
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 1
    assert result.message == "FFmpeg 退出码 1"
    assert result.is_ok is False
    assert result.legacy_success is False


def test_cancelled_result():
    result = TaskResult.cancelled()
    assert result.status is TaskStatus.CANCELLED
    assert result.message == "用户取消"
    assert result.legacy_success is False
    assert result.is_ok is False

    custom = TaskResult.cancelled("窗口关闭，已取消", exit_code=-9)
    assert custom.message == "窗口关闭，已取消"
    assert custom.exit_code == -9


def test_partial_result():
    result = TaskResult.partial("成功 2 个, 失败 1 个",
                                outputs=["a.mp4", "b.mp4"],
                                warnings=["第 3 个失败"])
    assert result.status is TaskStatus.PARTIAL
    assert result.is_ok is True
    # PARTIAL 不算“完全成功”，旧 bool 信号必须为 False
    assert result.legacy_success is False


def test_warnings_and_outputs_accept_iterables_and_single_string():
    result = TaskResult.failed(
        "x", warnings=["a", "b"], outputs=("o1.mp4", "o2.mp4"))
    assert result.warnings == ("a", "b")
    assert result.outputs == ("o1.mp4", "o2.mp4")

    single = TaskResult.ok(outputs="only.mp4", warnings="单个警告")
    assert single.outputs == ("only.mp4",)
    assert single.warnings == ("单个警告",)

    none_like = TaskResult.ok(outputs=None, warnings=None)
    assert none_like.outputs == ()
    assert none_like.warnings == ()


def test_status_coerced_from_string():
    result = TaskResult("success")  # 允许字符串，构造时归一
    assert result.status is TaskStatus.SUCCESS


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        TaskResult("not-a-status")


def test_details_is_copied_into_plain_dict():
    source = {"dry_run": True}
    result = TaskResult.ok(details=source)
    assert result.details == {"dry_run": True}
    assert result.details is not source


def test_result_is_frozen():
    result = TaskResult.ok()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.message = "改不了"  # type: ignore[misc]


def test_results_compare_by_value():
    assert TaskResult.ok(outputs=["a"]) == TaskResult.ok(outputs=["a"])
    assert TaskResult.ok() != TaskResult.failed()
