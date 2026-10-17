# -*- coding: utf-8 -*-
"""TaskReport 测试：SUCCESS / FAILED / PARTIAL / 无输入的汇总规则。"""

from src.task.report import TaskReport
from src.task.result import TaskResult
from src.task.status import TaskStatus


def test_empty_report_is_failed():
    result = TaskReport().finalize()
    assert result.status is TaskStatus.FAILED
    assert "没有可处理的任务输入" in result.message
    assert result.exit_code is None
    assert result.details["success_count"] == 0
    assert result.details["failure_count"] == 0


def test_all_success_is_success():
    report = TaskReport()
    report.add_success("a.mp4")
    report.add_success("b.mp4")
    result = report.finalize()

    assert result.status is TaskStatus.SUCCESS
    assert result.outputs == ("a.mp4", "b.mp4")
    assert "2" in result.message
    assert result.exit_code == 0
    assert result.legacy_success is True


def test_single_success_has_no_count_message():
    report = TaskReport()
    report.add_success()
    result = report.finalize()
    assert result.status is TaskStatus.SUCCESS
    assert result.message == ""
    assert result.outputs == ()


def test_all_failed_is_failed():
    report = TaskReport()
    report.add_failure("文件不存在", exit_code=1)
    report.add_failure("编码失败", exit_code=2)
    result = report.finalize()

    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 1  # 首个非空退出码
    assert "文件不存在" in result.message
    assert result.details["failure_count"] == 2
    assert result.details["failures"] == ("文件不存在", "编码失败")
    assert result.outputs == ()
    assert result.legacy_success is False


def test_mixed_results_are_partial():
    report = TaskReport()
    report.add_success("ok.mp4")
    report.add_failure("坏文件: 容器不兼容", exit_code=1)
    report.warn("有 1 个文件被跳过")
    result = report.finalize()

    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert result.outputs == ("ok.mp4",)
    assert result.warnings == ("有 1 个文件被跳过",)
    assert result.is_ok is True
    assert result.legacy_success is False
    assert result.details["success_count"] == 1
    assert result.details["failure_count"] == 1


def test_warning_does_not_change_status():
    report = TaskReport()
    report.add_success("a.mp4")
    report.warn("分发失败: 目标目录不可写")
    result = report.finalize()
    assert result.status is TaskStatus.SUCCESS
    assert result.warnings == ("分发失败: 目标目录不可写",)


def test_report_details_are_merged_into_final_result():
    report = TaskReport(details={"mode": "remux"})
    report.add_success("a.mp4")
    result = report.finalize()
    assert result.details["mode"] == "remux"
    assert result.details["success_count"] == 1


def test_report_counters_and_status_property():
    report = TaskReport()
    assert report.success_count == 0 and report.failure_count == 0
    assert report.status is TaskStatus.FAILED
    assert report.has_successes is False and report.has_failures is False

    report.add_success()
    assert report.status is TaskStatus.SUCCESS
    report.add_failure("x")
    assert report.status is TaskStatus.PARTIAL
    assert report.failures == ("x",)


def test_finalize_returns_task_result_instance():
    result = TaskReport().finalize()
    assert isinstance(result, TaskResult)
