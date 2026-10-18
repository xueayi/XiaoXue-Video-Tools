"""精确解码每个区间的首帧；防止空片段被concat静默忽略。"""
import os
from .clip_plan import ClipPlan, _seconds
from .utils import get_ffmpeg_path
from .task.context import TaskCancelled


def validate_clip_frames(plan: ClipPlan) -> None:
    from .core import run_ffmpeg_streaming
    checked = set()
    for index, clip in enumerate(plan.clips, 1):
        if clip in checked:
            continue
        frame_count = 0

        def progress(line):
            nonlocal frame_count
            key, _, value = line.strip().partition("=")
            if key == "frame" and value.strip().isdigit():
                frame_count = int(value)

        print(f"[片段检查] {index}/{len(plan.clips)}", flush=True)
        command = [get_ffmpeg_path(), "-v", "error", "-ss", _seconds(clip.in_us),
                   "-i", plan.input_path, "-t", _seconds(clip.out_us - clip.in_us),
                   "-map", "0:v:0", "-an", "-sn", "-frames:v", "1",
                   "-progress", "pipe:1", "-nostats", "-f", "null", os.devnull]
        try:
            result = run_ffmpeg_streaming(command, on_progress=progress, on_log=lambda _: None, timeout=30)
        except TaskCancelled:
            raise
        except Exception as exc:
            raise ValueError(f"片段 {index}：无法完成视频帧检查：{exc}") from exc
        if result.exit_code != 0 or frame_count < 1:
            raise ValueError(f"片段 {index}：所选区间内没有可输出的视频帧，请调整入点/出点")
        checked.add(clip)
