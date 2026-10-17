# -*- coding: utf-8 -*-
"""M2.4 UI 侧进度接入测试：fake ffmpeg -progress 数据流 -> TaskArea 指标。

覆盖:
    * 主窗口 _on_progress_line / _on_duration_ready -> TaskArea.update_metrics；
    * ProgressEvent -> ProgressInfo 形状适配层；
    * TaskRunner 的 progress_signal / duration_signal (worker 线程) 接线；
    * 进度行不进入日志面板（只走 stderr 日志）。
全部 offscreen，不跑真实 ffmpeg。
"""

import types

import pytest

from src.process import CompletedProcess
from src.process.progress import ProgressEvent
from src.task.result import TaskResult
from src.task.status import TaskStatus
from src.ui.main_window import MainWindow, _ProgressView
from src.ui.task_card import CURRENT_TASK_ID
from src.ui.task_runner import TaskRunner


@pytest.fixture
def win(qapp):
    w = MainWindow()
    yield w
    w.close()


def _block(*, frame=100, out_time_us=30_000_000, speed=2.0,
           progress="continue"):
    return [
        f"frame={frame}\n",
        "fps=25.0\n",
        f"out_time_us={out_time_us}\n",
        f"out_time_ms={out_time_us}\n",
        f"speed={speed}x\n",
        f"progress={progress}\n",
    ]


def _feed(win, lines):
    for line in lines:
        win._on_progress_line(line)


# ----------------------------------------------------------------
# 主窗口适配层
# ----------------------------------------------------------------

def test_progress_view_adapter_shape():
    event = ProgressEvent(frame=12, speed=1.5, percent=33.0, eta_seconds=9.0)
    view = _ProgressView.from_event(event)
    assert view.percent == 33.0
    assert view.speed == 1.5
    assert view.eta_sec == 9.0
    assert view.frame == 12
    # 未知 duration 时 percent/eta 保持 None (任务卡显示不确定态/--)
    unknown = _ProgressView.from_event(ProgressEvent(speed=1.0))
    assert unknown.percent is None
    assert unknown.eta_sec is None


def test_fake_progress_stream_updates_task_area(win):
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.reset()
    win._on_duration_ready(120.0)

    _feed(win, _block(frame=60, out_time_us=30_000_000, speed=2.0))

    state = win._dashboard._states[CURRENT_TASK_ID]
    assert state.status.value == "running"
    assert state.progress == pytest.approx(25.0)   # 30/120
    assert state.speed == pytest.approx(2.0)
    assert state.eta_sec == pytest.approx(45.0)    # (120-30)/2


def test_progress_end_closes_at_100(win):
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.reset()
    win._on_duration_ready(120.0)
    _feed(win, _block(out_time_us=120_000_000, progress="end"))
    assert win._dashboard._states[CURRENT_TASK_ID].progress == 100.0


def test_unknown_duration_keeps_indeterminate(win):
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.reset()
    _feed(win, _block())
    assert win._dashboard._states[CURRENT_TASK_ID].progress is None


def test_garbage_lines_do_not_touch_task_area(win):
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.reset()
    before = win._dashboard._states[CURRENT_TASK_ID].progress
    for line in ("", "\n", "hello\n", "frame=\n", "speed=N/A\n"):
        win._on_progress_line(line)
    assert win._dashboard._states[CURRENT_TASK_ID].progress == before
    # 非字符串防御分支
    win._on_progress_line(None)


# ----------------------------------------------------------------
# TaskRunner: duration 预取 / 进度信号 (worker 线程)
# ----------------------------------------------------------------

def test_task_runner_emits_duration_from_worker_probe(qapp, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    args = types.SimpleNamespace(input=str(video))
    probed = []

    def probe(path):
        probed.append(path)
        return 120.0

    runner = TaskRunner(lambda a: TaskResult.ok(), args, "c",
                        duration_probe=probe)
    durations, results = [], []
    runner.duration_signal.connect(durations.append)
    runner.result_signal.connect(results.append)
    runner.run()

    assert probed == [str(video)]
    assert durations == [120.0]
    assert results[0].status is TaskStatus.SUCCESS


def test_task_runner_skips_probe_without_input(qapp):
    def failed_probe(path):  # pragma: no cover - 不应被调用
        raise AssertionError("无输入路径时不应探测时长")

    runner = TaskRunner(lambda a: TaskResult.ok(), None, "c",
                        duration_probe=failed_probe)
    durations, results = [], []
    runner.duration_signal.connect(durations.append)
    runner.result_signal.connect(results.append)
    runner.run()
    assert durations == []
    assert results[0].status is TaskStatus.SUCCESS


# ----------------------------------------------------------------
# 各页面输入路径解析 (duration 预取)
# ----------------------------------------------------------------

@pytest.mark.parametrize("args_kwargs,expected", [
    ({"input": "a.mp4"}, "a.mp4"),
    ({"video_input": "v.mp4"}, "v.mp4"),
    ({"extract_input": "e.mp4"}, "e.mp4"),
    ({"remux_input": ["r.mp4"]}, "r.mp4"),
    ({"remux_input": ["r1.mp4", "r2.mp4"]}, ""),
    ({"input": "a.mp4; b.mp4"}, ""),
    ({}, ""),
])
def test_resolve_input_path_for_duration_probe(args_kwargs, expected):
    from src.ui.task_runner import resolve_input_path

    assert resolve_input_path(types.SimpleNamespace(**args_kwargs)) == expected


def test_resolve_input_path_none_or_invalid():
    from src.ui.task_runner import resolve_input_path

    assert resolve_input_path(None) == ""
    assert resolve_input_path(types.SimpleNamespace(input="   ")) == ""
    assert resolve_input_path(types.SimpleNamespace(input=42)) == ""
    assert resolve_input_path(types.SimpleNamespace(remux_input=[])) == ""


def test_duration_probe_works_for_replace_audio_page(qapp, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    args = types.SimpleNamespace(video_input=str(video))
    probed = []

    def probe(path):
        probed.append(path)
        return 90.0

    runner = TaskRunner(lambda a: TaskResult.ok(), args, "音频替换",
                        duration_probe=probe)
    durations = []
    runner.duration_signal.connect(durations.append)
    runner.run()
    assert probed == [str(video)]
    assert durations == [90.0]


def test_duration_probe_skips_batch_remux(qapp, tmp_path):
    videos = [tmp_path / f"{index}.mp4" for index in range(2)]
    for video in videos:
        video.write_bytes(b"x")
    args = types.SimpleNamespace(remux_input=[str(v) for v in videos])

    def failed_probe(path):  # pragma: no cover - 不应被调用
        raise AssertionError("批量输入不应预取单文件时长")

    runner = TaskRunner(lambda a: TaskResult.ok(), args, "封装转换",
                        duration_probe=failed_probe)
    durations = []
    runner.duration_signal.connect(durations.append)
    runner.run()
    assert durations == []


def test_task_runner_progress_signal_from_context_callback(qapp):
    def handler(args):
        from src.task.context import current_task

        context = current_task()
        assert context is not None
        assert context.progress_callback is not None
        for line in _block():
            context.progress_callback(line)
        return TaskResult.ok()

    runner = TaskRunner(handler, None, "c")
    lines, results = [], []
    runner.progress_signal.connect(lines.append)
    runner.result_signal.connect(results.append)
    runner.run()

    assert lines == _block()
    assert results[0].status is TaskStatus.SUCCESS


def test_worker_pipeline_routes_progress_and_stderr_log(qapp, monkeypatch):
    """worker 内 core.run_ffmpeg_command: 进度 -> progress_signal, stderr -> 日志。"""
    import src.core as core

    def fake_streaming(cmd, *, on_line=None, on_progress=None, on_log=None,
                       env=None):
        from src.task.context import current_task

        # 等价于真实实现的接线: 未显式传 on_progress 时用 TaskContext 回调
        sink = on_progress
        if sink is None:
            context = current_task()
            sink = getattr(context, "progress_callback", None)
        for line in _block()[:-1]:
            if sink is not None:
                sink(line)
        on_log("stderr-only log line\n")
        if sink is not None:
            sink("progress=continue\n")
        return CompletedProcess(exit_code=0)

    monkeypatch.setattr(core, "run_ffmpeg_streaming", fake_streaming)

    def handler(args):
        rc = core.run_ffmpeg_command(["ffmpeg", "-y", "in.mp4", "out.mp4"])
        return TaskResult.ok() if rc == 0 else TaskResult.failed("失败")

    runner = TaskRunner(handler, None, "c")
    progress_lines, log_chunks, results = [], [], []
    runner.progress_signal.connect(progress_lines.append)
    runner.log_signal.connect(log_chunks.append)
    runner.result_signal.connect(results.append)
    runner.run()

    assert results[0].status is TaskStatus.SUCCESS
    assert "progress=continue\n" in progress_lines
    joined_log = "".join(log_chunks)
    assert "stderr-only log line" in joined_log
    # 进度行不得刷进日志面板
    assert "progress=continue" not in joined_log
    assert "out_time_us=" not in joined_log


def test_parser_feed_via_main_window_keeps_log_clean(win):
    """主窗口进度接入不写日志面板 (只更新任务卡)。"""
    win._dashboard.show_indeterminate()
    win._ffmpeg_parser.reset()
    before = len(win._log_panel._chunks)
    _feed(win, _block())
    assert len(win._log_panel._chunks) == before
