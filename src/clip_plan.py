"""当前视频的不可变片段计划和 FFmpeg 时间线滤镜。"""
from dataclasses import dataclass
import shlex


@dataclass(frozen=True)
class ClipSpec:
    in_us: int
    out_us: int


@dataclass(frozen=True)
class ClipPlan:
    input_path: str
    clips: tuple[ClipSpec, ...]

    def __post_init__(self):
        object.__setattr__(self, "clips", tuple(self.clips))

    @property
    def total_duration_us(self) -> int:
        return sum(c.out_us - c.in_us for c in self.clips)

    def validate(self, duration_us: int | None = None) -> None:
        if not self.clips:
            raise ValueError("片段模式已启用，请至少添加一个片段")
        for i, clip in enumerate(self.clips, 1):
            if (type(clip.in_us) is not int or type(clip.out_us) is not int
                    or not 0 <= clip.in_us < clip.out_us):
                raise ValueError(f"片段 {i}：入点必须非负且早于出点")
            if duration_us is not None and clip.out_us > duration_us:
                raise ValueError(f"片段 {i}：出点超出当前视频时长")


def clip_extra_args(text: str | None) -> list[str]:
    """片段模式只接受不改变输入、映射和时间线的编码选项。"""
    tokens = shlex.split(text or "")
    allowed = {"-tune", "-profile:v", "-level:v", "-pix_fmt", "-movflags",
               "-maxrate", "-bufsize", "-tag:v", "-rc", "-b:v", "-cq",
               "-qp", "-global_quality", "-q:v", "-preset", "-quality", "-prio_speed"}
    for index in range(0, len(tokens), 2):
        if tokens[index] not in allowed or index + 1 >= len(tokens):
            raise ValueError(f"片段模式不支持额外参数 {tokens[index]}；时间、滤镜和流映射由片段计划管理")
    return tokens


def select_audio_indices(option: str, custom: str, count: int) -> tuple[int, ...]:
    if option == "none" or count == 0:
        return ()
    if option == "all":
        return tuple(range(count))
    raw = custom.split(",") if option == "custom" else [option]
    if not raw or any(not value.strip().isdigit() for value in raw):
        raise ValueError("片段模式的音轨编号无效")
    indices = tuple(dict.fromkeys(int(value.strip()) for value in raw))
    if any(value >= count for value in indices):
        raise ValueError("片段模式选择的音轨不存在")
    return indices


def _seconds(us: int) -> str:
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


def build_clip_filters(plan: ClipPlan, video_filters: list[str],
                       audio_indices: tuple[int, ...]) -> tuple[str, list[str]]:
    plan.validate()
    count = len(plan.clips)
    nodes = []
    # 字幕在源时间轴上渲染，再裁切；缩放同样复用既有滤镜。
    prefix = ",".join(video_filters)
    if prefix:
        prefix += ","
    nodes.append(f"[0:v:0]{prefix}split={count}" + "".join(f"[cv{i}]" for i in range(count)))
    for i, clip in enumerate(plan.clips):
        nodes.append(f"[cv{i}]trim=start={_seconds(clip.in_us)}:end={_seconds(clip.out_us)},"
                     f"setpts=PTS-STARTPTS[sv{i}]")
    nodes.append("".join(f"[sv{i}]" for i in range(count)) + f"concat=n={count}:v=1:a=0[clip_v]")
    maps = ["-map", "[clip_v]"]
    for track, source in enumerate(audio_indices):
        # 补齐源音轨开头和末尾的静音，避免短音轨导致下一段声音提前。
        nodes.append(f"[0:a:{source}]aresample=async=1:first_pts=0,apad,asplit={count}"
                     + "".join(f"[ca{track}_{i}]" for i in range(count)))
        for i, clip in enumerate(plan.clips):
            nodes.append(f"[ca{track}_{i}]atrim=start={_seconds(clip.in_us)}:end={_seconds(clip.out_us)},"
                         f"asetpts=PTS-STARTPTS[sa{track}_{i}]")
        nodes.append("".join(f"[sa{track}_{i}]" for i in range(count))
                     + f"concat=n={count}:v=0:a=1[clip_a{track}]")
        maps.extend(["-map", f"[clip_a{track}]"])
        maps.extend([f"-map_metadata:s:a:{track}", f"0:s:a:{source}"])
    if not audio_indices:
        maps.append("-an")
    maps.append("-sn")
    return ";".join(nodes), maps
