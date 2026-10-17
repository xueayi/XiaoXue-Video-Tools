# -*- coding: utf-8 -*-
"""core.run_ffmpeg_streaming 的 progress/log 双通道分流测试 (M2.4)。

覆盖:
    * stdout -> on_progress / TaskContext.progress_callback, stderr -> on_log;
    * 兼容 on_line 仍收到全部行;
    * run_ffmpeg_command 只把 stderr 打进日志, 进度行不刷屏;
    * 进度行经 TaskContext 流到解析器 (端到端 percent/ETA)。
"""

import pytest

import src.core as core
from src.process import CompletedProcess
from src.process.progress import FFmpegProgressParser
from src.task.context import TaskContext, reset_current_task, set_current_task

STDOUT_PROGRESS = (
    "frame=100\n",
    "fps=25.0\n",
    "out_time_us=1000000\n",
    "out_time_ms=1000000\n",
    "speed=2.0x\n",
    "progress=continue\n",
)
STDERR_LOG = (
    "ffmpeg version 6.1\n",
    "[libx264 @ 0000] frame I:1\n",
)


class FakeRunner:
    """按 start() 时预置的行触发双通道回调的测试 runner。"""

    def __init__(self, stdout_lines=(), stderr_lines=(), exit_code=0,
                 cancelled=False):
        self.on_stdout = None
        self.on_stderr = None
        self.on_finished = None
        self._stdout_lines = tuple(stdout_lines)
        self._stderr_lines = tuple(stderr_lines)
        self._exit_code = exit_code
        self._cancelled = cancelled
        self.started = None
        self.waited = False

    def start(self, cmd, *, cwd=None, env=None, stdin_pipe=False):
        self.started = list(cmd)
        if self.on_stdout is not None:
            for line in self._stdout_lines:
                self.on_stdout(line)
        if self.on_stderr is not None:
            for line in self._stderr_lines:
                self.on_stderr(line)

    def wait(self, timeout=None):
        self.waited = True
        return CompletedProcess(
            exit_code=self._exit_code, cancelled=self._cancelled)

    def cancel(self):
        pass

    def is_running(self):
        return False

    @property
    def exit_code(self):
        return self._exit_code


def _use_context(runner):
    context = TaskContext(runner_factory=lambda: runner)
    token = set_current_task(context)
    return context, token


# ----------------------------------------------------------------
# 双通道分流
# ----------------------------------------------------------------

def test_stdout_goes_to_progress_and_stderr_to_log():
    runner = FakeRunner(STDOUT_PROGRESS, STDERR_LOG)
    progress, logs = [], []
    _context, token = _use_context(runner)
    try:
        completed = core.run_ffmpeg_streaming(
            ["ffmpeg", "-i", "in.mp4", "out.mp4"],
            on_progress=progress.append,
            on_log=logs.append,
        )
    finally:
        reset_current_task(token)

    assert completed.ok
    assert progress == list(STDOUT_PROGRESS)
    assert logs == list(STDERR_LOG)
    assert runner.started == ["ffmpeg", "-i", "in.mp4", "out.mp4"]
    assert runner.waited is True


def test_on_line_legacy_receives_both_channels():
    runner = FakeRunner(STDOUT_PROGRESS, STDERR_LOG)
    lines = []
    _context, token = _use_context(runner)
    try:
        core.run_ffmpeg_streaming(["ffmpeg"], on_line=lines.append)
    finally:
        reset_current_task(token)
    assert lines == list(STDOUT_PROGRESS) + list(STDERR_LOG)


def test_context_progress_callback_used_when_on_progress_absent():
    runner = FakeRunner(stdout_lines=["frame=1\n"])
    context, token = _use_context(runner)
    received = []
    context.progress_callback = received.append
    try:
        core.run_ffmpeg_streaming(["ffmpeg"])
    finally:
        reset_current_task(token)
    assert received == ["frame=1\n"]


def test_explicit_on_progress_wins_over_context():
    runner = FakeRunner(stdout_lines=["frame=1\n"])
    context, token = _use_context(runner)
    context_received, explicit_received = [], []
    context.progress_callback = context_received.append
    try:
        core.run_ffmpeg_streaming(
            ["ffmpeg"], on_progress=explicit_received.append)
    finally:
        reset_current_task(token)
    assert explicit_received == ["frame=1\n"]
    assert context_received == []


def test_no_callbacks_no_crash():
    runner = FakeRunner(stdout_lines=["frame=1\n"], stderr_lines=["log\n"])
    _context, token = _use_context(runner)
    try:
        completed = core.run_ffmpeg_streaming(["ffmpeg"])
    finally:
        reset_current_task(token)
    assert completed.exit_code == 0


def test_runner_states_are_set_for_both_channels():
    runner = FakeRunner()
    _context, token = _use_context(runner)
    try:
        core.run_ffmpeg_streaming(
            ["ffmpeg"], on_progress=lambda line: None,
            on_log=lambda line: None)
    finally:
        reset_current_task(token)
    assert callable(runner.on_stdout)
    assert callable(runner.on_stderr)


# ----------------------------------------------------------------
# run_ffmpeg_command: 日志只收 stderr, 进度只走进度回调
# ----------------------------------------------------------------

def test_run_ffmpeg_command_routes_channels(monkeypatch, capsys):
    def fake_streaming(cmd, *, on_line=None, on_progress=None, on_log=None,
                       env=None):
        for line in STDOUT_PROGRESS:
            if on_progress is not None:
                on_progress(line)
        for line in STDERR_LOG:
            if on_log is not None:
                on_log(line)
        return CompletedProcess(exit_code=0)

    monkeypatch.setattr(core, "run_ffmpeg_streaming", fake_streaming)
    progress = []
    rc = core.run_ffmpeg_command(
        ["ffmpeg", "-i", "in.mp4", "out.mp4"],
        progress_callback=progress.append)

    assert rc == 0
    assert progress == list(STDOUT_PROGRESS)  # 进度回调只收 stdout
    out = capsys.readouterr().out
    for line in STDERR_LOG:
        assert line.strip() in out
    for line in STDOUT_PROGRESS:
        assert line.strip() not in out  # key=value 不进日志


def test_run_ffmpeg_command_uses_context_progress_callback(monkeypatch):
    runner = FakeRunner(stdout_lines=STDOUT_PROGRESS)

    def fake_run_process(cmd, *, runner=None, stdin_pipe=False, env=None):
        # 复用真实 run_ffmpeg_streaming 的接线: 直接在这里触发回调
        for line in STDOUT_PROGRESS:
            if runner.on_stdout is not None:
                runner.on_stdout(line)
        return CompletedProcess(exit_code=0)

    monkeypatch.setattr(core, "run_process", fake_run_process)
    context, token = _use_context(runner)
    received = []
    context.progress_callback = received.append
    try:
        rc = core.run_ffmpeg_command(["ffmpeg"])
    finally:
        reset_current_task(token)

    assert rc == 0
    assert received == list(STDOUT_PROGRESS)


# ----------------------------------------------------------------
# 端到端: 进度行 -> TaskContext -> 解析器 -> percent/ETA
# ----------------------------------------------------------------

def test_progress_lines_flow_to_parser_end_to_end():
    parser = FFmpegProgressParser()
    parser.set_duration(10.0)
    events = []

    def sink(line):
        event = parser.feed_line(line)
        if event is not None:
            events.append(event)

    runner = FakeRunner(stdout_lines=STDOUT_PROGRESS, stderr_lines=STDERR_LOG)
    context, token = _use_context(runner)
    context.progress_callback = sink
    try:
        rc = core.run_ffmpeg_command(["ffmpeg"])
    finally:
        reset_current_task(token)

    assert rc == 0
    assert len(events) == 1
    assert events[0].frame == 100
    assert events[0].percent == pytest.approx(10.0)
    assert events[0].eta_seconds == pytest.approx(4.5)  # (10-1)/2


# ----------------------------------------------------------------
# M2.5: stderr 尾部写入 TaskContext (错误归因)
# ----------------------------------------------------------------

NVENC_LOG = (
    "[h264_nvenc @ 000001f4] No NVENC capable devices found\n",
    "Conversion failed!\n",
)


class FallbackRunner(FakeRunner):
    """wait() 返回带 stderr_tail 的 CompletedProcess (模拟无回调时的兜底)。"""

    def wait(self, timeout=None):
        self.waited = True
        return CompletedProcess(
            exit_code=self._exit_code,
            cancelled=self._cancelled,
            stderr_tail=tuple(self._stderr_lines),
        )


def test_stderr_lines_are_recorded_into_context():
    runner = FakeRunner(stderr_lines=NVENC_LOG, exit_code=1)
    context, token = _use_context(runner)
    try:
        core.run_ffmpeg_streaming(["ffmpeg"], on_log=lambda _line: None)
    finally:
        reset_current_task(token)

    assert context.stderr_lines == NVENC_LOG
    assert "No NVENC capable devices found" in context.stderr_text


def test_completed_process_stderr_tail_fills_context_without_callbacks():
    """没有 on_log/on_line 时由 CompletedProcess.stderr_tail 兜底补齐。"""
    runner = FallbackRunner(stderr_lines=NVENC_LOG, exit_code=1)
    context, token = _use_context(runner)
    try:
        completed = core.run_ffmpeg_streaming(["ffmpeg"])
    finally:
        reset_current_task(token)

    assert completed.stderr_tail == NVENC_LOG
    assert context.stderr_lines == NVENC_LOG


def test_cancelled_streaming_keeps_stderr_buffer():
    from src.task.context import TaskCancelled

    runner = FakeRunner(stderr_lines=NVENC_LOG, cancelled=True)
    context, token = _use_context(runner)
    try:
        with pytest.raises(TaskCancelled):
            core.run_ffmpeg_streaming(["ffmpeg"], on_log=lambda _line: None)
    finally:
        reset_current_task(token)

    # 取消前已产生的 stderr 仍保留, 便于日志/归因
    assert context.stderr_lines == NVENC_LOG
