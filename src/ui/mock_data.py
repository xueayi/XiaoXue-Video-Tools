# -*- coding: utf-8 -*-
"""UI 演示用 mock 数据 —— 供首页「最近任务（示例）」与组件自测使用。

本模块只构造视图数据，禁止 import executors / task_runner / ffmpeg：
    * ``MOCK_TASKS``  5 条状态齐全的任务视图 (running/success/partial/failed/cancelled)
    * ``MOCK_ERROR``  一条 ENCODER_UNAVAILABLE 错误 (3 原因 + 2 操作)
    * ``MOCK_MEDIA``  一份 DetailedMediaInfo 假值 (不跑 ffprobe)
    * ``DemoTaskPlayer``  QTimer 驱动的演示播放器，running → 终态，
      另暴露出确定性 ``step()`` 便于测试逐步推进。
"""

from dataclasses import replace

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..media_probe import DetailedMediaInfo, StreamInfo
from .error_card import ErrorCategory, ErrorInfo
from .task_state import TaskStatus, TaskViewState

# ----------------------------------------------------------------
# 任务 mock
# ----------------------------------------------------------------

MOCK_TASKS = [
    TaskViewState(
        task_id="mock-running-001",
        title="示例：压制《春日野餐》.mkv",
        status=TaskStatus.RUNNING,
        encoder="NVENC H.264",
        progress=42.5,
        speed=1.85,
        eta_sec=38.0,
        message="",
        elapsed_sec=42.0,
    ),
    TaskViewState(
        task_id="mock-success-001",
        title="示例：压制《城市夜景》.mp4",
        status=TaskStatus.SUCCESS,
        encoder="x265",
        progress=100.0,
        speed=2.4,
        eta_sec=0.0,
        elapsed_sec=96.0,
        output_path=r"D:\输出\城市夜景_压制.mp4",
    ),
    TaskViewState(
        task_id="mock-partial-001",
        title="示例：批量压制 3 个文件",
        status=TaskStatus.PARTIAL,
        encoder="x264",
        progress=100.0,
        message="2 个文件成功，1 个文件失败（部分完成）",
        elapsed_sec=215.0,
        output_path=r"D:\输出\批量压制",
    ),
    TaskViewState(
        task_id="mock-failed-001",
        title="示例：压制《旧动画》.avi",
        status=TaskStatus.FAILED,
        encoder="QSV H.265",
        progress=67.3,
        message="FFmpeg 返回错误 (code=1)",
        elapsed_sec=18.0,
    ),
    TaskViewState(
        task_id="mock-cancelled-001",
        title="示例：压制《演唱会》.ts",
        status=TaskStatus.CANCELLED,
        encoder="x264",
        progress=18.0,
        message="用户停止任务",
        elapsed_sec=7.0,
    ),
]

# ----------------------------------------------------------------
# 错误 mock (ENCODER_UNAVAILABLE: 3 条原因 + 2 个操作)
# ----------------------------------------------------------------

MOCK_ERROR = ErrorInfo(
    title="硬件编码器不可用",
    causes=[
        "当前显卡驱动版本过低，与 NVENC 要求的编码 API 版本不匹配",
        "显卡不支持所选 NVENC 编码器，或硬件编码器被其他程序占用",
        "FFmpeg 构建未包含 NVENC 支持（缺少对应动态库）",
    ],
    actions=["改用 CPU 编码 (H.264 / H.265)", "更新显卡驱动后重试"],
    log_tail=(
        "[h264_nvenc @ 000001f4] Cannot load nvcuda.dll\n"
        "[h264_nvenc @ 000001f4] No NVENC capable devices found\n"
        "Conversion failed!"
    ),
    category=ErrorCategory.ENCODER_UNAVAILABLE,
)

# ----------------------------------------------------------------
# 媒体信息 mock (不跑 ffprobe)
# ----------------------------------------------------------------

MOCK_MEDIA = DetailedMediaInfo(
    path=r"D:\视频\示例影片.mkv",
    file_size_bytes=2_684_354_560,  # 2.5 GB
    format_name="matroska,webm",
    format_long_name="Matroska / WebM",
    duration_sec=7540.0,
    total_bitrate_kbps=2848,
    video_streams=[
        StreamInfo(
            index=0,
            stream_index=0,
            codec_type="video",
            codec_name="hevc",
            codec_long_name="H.265 / HEVC (High Efficiency Video Coding)",
            profile="Main 10",
            level="51",
            width=1920,
            height=1080,
            fps=23.976,
            pix_fmt="yuv420p10le",
            bitrate_kbps=2500,
        ),
    ],
    audio_streams=[
        StreamInfo(
            index=0,
            stream_index=1,
            codec_type="audio",
            codec_name="aac",
            codec_long_name="AAC (Advanced Audio Coding)",
            profile="LC",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
            bitrate_kbps=192,
            language="jpn",
            title="日语原声",
        ),
        StreamInfo(
            index=1,
            stream_index=2,
            codec_type="audio",
            codec_name="flac",
            codec_long_name="FLAC (Free Lossless Audio Codec)",
            sample_rate=48000,
            channels=2,
            channel_layout="stereo",
            bitrate_kbps=850,
            language="chi",
            title="国语",
        ),
    ],
    subtitle_streams=[
        StreamInfo(
            index=0,
            stream_index=3,
            codec_type="subtitle",
            codec_name="ass",
            codec_long_name="ASS (Advanced SubStation Alpha)",
            language="chi",
            title="简体中文",
        ),
    ],
    chapters=[{"id": 0, "start": 0.0, "end": 7540.0, "title": "正片"}],
)


# ----------------------------------------------------------------
# 演示播放器
# ----------------------------------------------------------------

class DemoTaskPlayer(QObject):
    """QTimer 驱动的演示任务播放器：running → SUCCESS，可手动 step() 确定性推进。

    不 import executors / task_runner / ffmpeg，只操作 TaskViewState。
    """

    #: 状态每次推进后发出 (参数: TaskViewState)
    state_changed = pyqtSignal(object)
    #: 到达终态时发出一次 (参数: task_id)
    finished = pyqtSignal(str)

    def __init__(self, state: TaskViewState = None, steps: int = 8,
                 interval_ms: int = 500, parent=None):
        super().__init__(parent)
        if state is None:
            state = replace(
                MOCK_TASKS[0],
                progress=0.0,
                speed=0.0,
                eta_sec=None,
                elapsed_sec=0.0,
            )
        self._state = state
        self._steps = max(1, int(steps))
        self._interval_ms = max(1, int(interval_ms))
        self._step_index = 0

        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.step)

    # ----------------------------------------------------------------
    # 状态
    # ----------------------------------------------------------------

    @property
    def state(self) -> TaskViewState:
        """当前视图状态。"""
        return self._state

    @property
    def steps(self) -> int:
        """推进到终态所需的 step 总数。"""
        return self._steps

    @property
    def is_running(self) -> bool:
        """QTimer 是否在运行。"""
        return self._timer.isActive()

    # ----------------------------------------------------------------
    # 控制
    # ----------------------------------------------------------------

    def start(self):
        """启动 QTimer (终态任务不启动)，返回自身便于链式调用。"""
        if not self._state.status.is_terminal:
            self._timer.start()
        return self

    def stop(self):
        """停止 QTimer (不改变当前任务状态)。"""
        self._timer.stop()

    def step(self) -> TaskViewState:
        """确定性推进一步；到达终态后返回当前状态且不再发信号。"""
        if self._state.status.is_terminal:
            self._timer.stop()
            return self._state

        self._step_index += 1
        elapsed = round(self._step_index * self._interval_ms / 1000.0, 1)
        progress = round(min(100.0, self._step_index * 100.0 / self._steps), 1)
        speed = round(1.0 + self._step_index * 0.25, 2)

        if self._step_index >= self._steps:
            new_state = replace(
                self._state,
                status=TaskStatus.SUCCESS,
                progress=100.0,
                speed=speed,
                eta_sec=0.0,
                elapsed_sec=elapsed,
                message="演示任务已完成",
            )
            self._timer.stop()
            self._state = new_state
            self.state_changed.emit(new_state)
            self.finished.emit(new_state.task_id)
            return new_state

        remaining = self._steps - self._step_index
        new_state = replace(
            self._state,
            status=TaskStatus.RUNNING,
            progress=progress,
            speed=speed,
            eta_sec=round(remaining * self._interval_ms / 1000.0, 1),
            elapsed_sec=elapsed,
        )
        self._state = new_state
        self.state_changed.emit(new_state)
        return new_state
