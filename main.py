# -*- coding: utf-8 -*-
"""
小雪工具箱 (XiaoXue Video Toolbox) - 一个简单的视频压制与检测工具
使用 Gooey 构建图形界面，调用 FFmpeg 进行视频处理。
"""
import os
import sys

# PyInstaller 无窗口模式 (--windowed) 下 stdout/stderr 为 None
# 需要重定向以避免 colored 库报错
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

from gooey import Gooey, GooeyParser
from colorama import init as colorama_init, Fore, Style

# 初始化 colorama
colorama_init()

# 导入后端模块
from src.core import (
    build_encode_command,
    build_replace_audio_command,
    build_remux_command,
    build_extract_audio_command,
    run_ffmpeg_command,
)
from src.qc import scan_directory, generate_report
from src.presets import (
    ENCODERS,
    QUALITY_PRESETS,
    AUDIO_ENCODERS,
    AUDIO_BITRATES,
    CPU_PRESETS,
    NVENC_PRESETS,
)
from src.utils import get_base_dir, generate_output_path


# 获取图标路径 (可选)
def get_icon_path():
    base = get_base_dir()
    icon = os.path.join(base, "icon.ico")
    return icon if os.path.exists(icon) else None


@Gooey(
    program_name="小雪工具箱",
    program_description="一个简单的视频压制与检测工具",
    language="chinese",
    navigation="SIDEBAR",
    sidebar_title="功能导航",
    show_sidebar=True,
    default_size=(900, 700),
    richtext_controls=True,
    show_success_modal=False,
    show_failure_modal=False,
    show_stop_warning=True,
    # Light Mode 配置 - 浅色主题，清晰易读
    body_bg_color="#f5f5f5",
    header_bg_color="#00AEEC",
    footer_bg_color="#e0e0e0",
    sidebar_bg_color="#ffffff",
    terminal_panel_color="#ffffff",
    terminal_font_color="#333333",
    # 隐藏不需要的元素
    show_restart_button=True,
    # 菜单栏控制
    menu=[
        {
            "name": "帮助",
            "items": [
                {
                    "type": "AboutDialog",
                    "menuTitle": "关于",
                    "name": "小雪工具箱",
                    "description": "一个简单的视频压制与检测工具",
                    "version": "1.0.0",
                    "developer": "雪阿宜",
                },
                {
                    "type": "Link",
                    "menuTitle": "B站主页",
                    "url": "https://space.bilibili.com/107936977",
                },
            ],
        }
    ],
    image_dir=get_base_dir(),
)
def main():
    """主入口函数，定义 Gooey 界面。"""
    parser = GooeyParser(description="选择左侧功能进行操作")

    # 创建子命令 (对应 Sidebar 各项)
    subs = parser.add_subparsers(dest="command", help="功能选择")

    # ========================
    # 1. 视频压制 (Video Encoding)
    # ========================
    encode_parser = subs.add_parser("视频压制", help="视频转码、压缩、字幕烧录")

    # 输入输出分组
    io_group = encode_parser.add_argument_group(
        "输入/输出设置",
        gooey_options={"columns": 1}
    )
    io_group.add_argument(
        "--input",
        metavar="输入视频",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "视频文件 (*.mp4;*.mov;*.avi;*.mkv)|*.mp4;*.mov;*.avi;*.mkv|所有文件 (*.*)|*.*"},
        help="选择要处理的视频文件",
    )
    io_group.add_argument(
        "--output",
        metavar="输出路径 (可选)",
        required=False,
        default="",
        widget="FileSaver",
        gooey_options={"wildcard": "MP4 文件 (*.mp4)|*.mp4|MKV 文件 (*.mkv)|*.mkv|所有文件 (*.*)|*.*"},
        help="留空则自动生成: 输入文件名_编码器.mp4",
    )
    io_group.add_argument(
        "--subtitle",
        metavar="字幕文件 (可选)",
        widget="FileChooser",
        gooey_options={"wildcard": "字幕文件 (*.srt;*.ass;*.ssa)|*.srt;*.ass;*.ssa|所有文件 (*.*)|*.*"},
        help="选择要烧录的字幕文件 (留空则不烧录)",
    )

    # 预设分组
    preset_group = encode_parser.add_argument_group(
        "预设选择",
        gooey_options={"columns": 1}
    )
    preset_group.add_argument(
        "--preset",
        metavar="质量预设",
        choices=list(QUALITY_PRESETS.keys()),
        default="【标准推荐】1080P/60FPS 均衡",
        help="选择预设配置，或选择 '自定义' 手动配置参数",
    )

    # 高级参数分组 (当选择自定义时使用)
    advanced_group = encode_parser.add_argument_group(
        "高级参数 (自定义模式)",
        gooey_options={"columns": 2}
    )
    advanced_group.add_argument(
        "--encoder",
        metavar="视频编码器",
        choices=list(ENCODERS.keys()),
        default="H.264 (CPU - libx264)",
        help="选择视频编码器",
    )
    advanced_group.add_argument(
        "--crf",
        metavar="CRF 值",
        type=int,
        default=20,
        gooey_options={"min": 0, "max": 51},
        help="质量控制 (0-51, 越低画质越好, 推荐 18-23)",
    )
    advanced_group.add_argument(
        "--speed-preset",
        metavar="编码速度",
        choices=CPU_PRESETS,
        default="medium",
        help="编码速度预设 (越慢画质越好)",
    )
    advanced_group.add_argument(
        "--resolution",
        metavar="分辨率",
        default="",
        help="输出分辨率 (如 1920x1080), 留空保持原分辨率",
    )
    advanced_group.add_argument(
        "--fps",
        metavar="帧率",
        type=int,
        default=0,
        help="输出帧率 (如 30, 60), 填 0 保持原帧率",
    )
    advanced_group.add_argument(
        "--audio-encoder",
        metavar="音频编码器",
        choices=list(AUDIO_ENCODERS.keys()),
        default="AAC (推荐)",
        help="选择音频编码器",
    )
    advanced_group.add_argument(
        "--audio-bitrate",
        metavar="音频码率",
        choices=AUDIO_BITRATES,
        default="192k",
        help="音频码率",
    )
    advanced_group.add_argument(
        "--extra-args",
        metavar="额外参数",
        default="",
        help="额外的 FFmpeg 参数 (高级用户)",
    )

    # ========================
    # 2. 音频替换 (Replace Audio)
    # ========================
    audio_parser = subs.add_parser("音频替换", help="替换视频中的音轨")

    audio_io = audio_parser.add_argument_group("输入/输出设置")
    audio_io.add_argument(
        "--video-input",
        metavar="原始视频",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "视频文件 (*.mp4;*.mov;*.avi;*.mkv)|*.mp4;*.mov;*.avi;*.mkv|所有文件 (*.*)|*.*"},
        help="选择原始视频文件",
    )
    audio_io.add_argument(
        "--audio-input",
        metavar="新音频文件",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "音频文件 (*.mp3;*.aac;*.wav;*.flac;*.m4a)|*.mp3;*.aac;*.wav;*.flac;*.m4a|所有文件 (*.*)|*.*"},
        help="选择要替换的新音频文件",
    )
    audio_io.add_argument(
        "--audio-output",
        metavar="输出路径",
        required=True,
        widget="FileSaver",
        gooey_options={"wildcard": "MP4 文件 (*.mp4)|*.mp4|所有文件 (*.*)|*.*"},
        help="选择输出文件的保存位置",
    )

    audio_settings = audio_parser.add_argument_group("音频设置")
    audio_settings.add_argument(
        "--audio-enc",
        metavar="音频编码器",
        choices=list(AUDIO_ENCODERS.keys()),
        default="AAC (推荐)",
        help="选择音频编码器",
    )
    audio_settings.add_argument(
        "--audio-br",
        metavar="音频码率",
        choices=AUDIO_BITRATES,
        default="192k",
        help="音频码率",
    )

    # ========================
    # 3. 转封装 (Remux)
    # ========================
    remux_parser = subs.add_parser("转封装", help="更换容器格式 (不重新编码)")

    remux_io = remux_parser.add_argument_group("输入/输出设置")
    remux_io.add_argument(
        "--remux-input",
        metavar="输入文件",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "视频文件 (*.mp4;*.mov;*.avi;*.mkv;*.webm)|*.mp4;*.mov;*.avi;*.mkv;*.webm|所有文件 (*.*)|*.*"},
        help="选择要转换的文件",
    )
    remux_io.add_argument(
        "--remux-output",
        metavar="输出路径",
        required=True,
        widget="FileSaver",
        gooey_options={"wildcard": "MP4 文件 (*.mp4)|*.mp4|MKV 文件 (*.mkv)|*.mkv|MOV 文件 (*.mov)|*.mov|所有文件 (*.*)|*.*"},
        help="选择输出文件 (通过扩展名决定容器格式)",
    )

    # ========================
    # 4. 质量检测 (QC Report)
    # ========================
    qc_parser = subs.add_parser("质量检测", help="批量检测素材兼容性")

    qc_io = qc_parser.add_argument_group("扫描设置")
    qc_io.add_argument(
        "--scan-dir",
        metavar="扫描目录",
        required=True,
        widget="DirChooser",
        help="选择要扫描的文件夹 (将递归扫描)",
    )
    qc_io.add_argument(
        "--report-output",
        metavar="报告输出路径",
        required=True,
        widget="FileSaver",
        gooey_options={"wildcard": "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*"},
        help="选择报告保存位置",
    )

    qc_thresholds = qc_parser.add_argument_group("阈值设置 (可选)")
    qc_thresholds.add_argument(
        "--max-bitrate",
        metavar="最大码率 (kbps)",
        type=int,
        default=0,
        help="超过此码率将警告 (0 表示不检查)",
    )
    qc_thresholds.add_argument(
        "--max-resolution",
        metavar="最大分辨率",
        default="",
        help="超过此分辨率将警告 (如 1920x1080, 留空不检查)",
    )

    # ========================
    # 5. 音频抽取 (Extract Audio)
    # ========================
    extract_parser = subs.add_parser("音频抽取", help="从视频中提取音频轨道")

    extract_io = extract_parser.add_argument_group("输入/输出设置")
    extract_io.add_argument(
        "--extract-input",
        metavar="输入视频",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "视频文件 (*.mp4;*.mov;*.avi;*.mkv;*.webm)|*.mp4;*.mov;*.avi;*.mkv;*.webm|所有文件 (*.*)|*.*"},
        help="选择要提取音频的视频文件",
    )
    extract_io.add_argument(
        "--extract-output",
        metavar="输出音频",
        required=True,
        widget="FileSaver",
        gooey_options={"wildcard": "MP3 文件 (*.mp3)|*.mp3|AAC 文件 (*.aac)|*.aac|WAV 文件 (*.wav)|*.wav|FLAC 文件 (*.flac)|*.flac|所有文件 (*.*)|*.*"},
        help="选择音频输出路径 (通过扩展名决定格式)",
    )

    extract_settings = extract_parser.add_argument_group("音频设置")
    extract_settings.add_argument(
        "--extract-encoder",
        metavar="音频编码器",
        choices=list(AUDIO_ENCODERS.keys()),
        default="AAC (推荐)",
        help="选择音频编码器 (选 '复制' 可直接提取原始音频)",
    )
    extract_settings.add_argument(
        "--extract-bitrate",
        metavar="音频码率",
        choices=AUDIO_BITRATES,
        default="192k",
        help="音频码率 (仅转码时生效)",
    )

    args = parser.parse_args()

    # 根据子命令执行对应逻辑
    if args.command == "视频压制":
        execute_encode(args)
    elif args.command == "音频替换":
        execute_replace_audio(args)
    elif args.command == "转封装":
        execute_remux(args)
    elif args.command == "质量检测":
        execute_qc(args)
    elif args.command == "音频抽取":
        execute_extract_audio(args)
    else:
        print(f"{Fore.YELLOW}请从左侧选择一个功能{Style.RESET_ALL}")


def execute_encode(args):
    """执行视频压制任务。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}", flush=True)
    print(f"{Fore.CYAN}[小雪工具箱] 视频压制任务开始{Style.RESET_ALL}", flush=True)
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}", flush=True)

    # 获取实际使用的编码器
    preset_name = args.preset
    if preset_name and preset_name in QUALITY_PRESETS and preset_name != "自定义 (Custom)":
        preset = QUALITY_PRESETS[preset_name]
        actual_encoder = preset.get("encoder", "libx264")
        print(f"[预设] {preset_name}", flush=True)
        print(f"  编码器: {actual_encoder}", flush=True)
        print(f"  CRF: {preset.get('crf', 'N/A')}", flush=True)
        print(f"  速度: {preset.get('preset', 'N/A')}", flush=True)
    else:
        actual_encoder = ENCODERS.get(args.encoder, "libx264")
        print(f"[自定义模式]", flush=True)
        print(f"  编码器: {actual_encoder}", flush=True)
        print(f"  CRF: {args.crf}", flush=True)

    # 自动生成输出路径 (如果未指定或为空)
    output_path = args.output
    if not output_path or output_path.strip() == "":
        output_path = generate_output_path(args.input, actual_encoder)
        print(f"[自动生成输出路径] {output_path}", flush=True)

    # 构建命令
    cmd = build_encode_command(
        input_path=args.input,
        output_path=output_path,
        preset_name=args.preset,
        encoder=args.encoder,
        crf=args.crf if args.preset == "自定义 (Custom)" else None,
        speed_preset=getattr(args, 'speed_preset', None),
        resolution=args.resolution if args.resolution else None,
        fps=args.fps if args.fps > 0 else None,
        audio_encoder=AUDIO_ENCODERS.get(args.audio_encoder, "aac"),
        audio_bitrate=args.audio_bitrate,
        subtitle_path=args.subtitle if args.subtitle else None,
        extra_args=args.extra_args if args.extra_args else None,
    )

    run_ffmpeg_command(cmd)


def execute_replace_audio(args):
    """执行音频替换任务。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[小雪工具箱] 音频替换任务开始{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    cmd = build_replace_audio_command(
        video_path=args.video_input,
        audio_path=args.audio_input,
        output_path=args.audio_output,
        audio_encoder=AUDIO_ENCODERS.get(args.audio_enc, "aac"),
        audio_bitrate=args.audio_br,
    )

    run_ffmpeg_command(cmd)


def execute_remux(args):
    """执行转封装任务。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[小雪工具箱] 转封装任务开始{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    cmd = build_remux_command(
        input_path=args.remux_input,
        output_path=args.remux_output,
    )

    run_ffmpeg_command(cmd)


def execute_qc(args):
    """执行质量检测任务。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[小雪工具箱] 质量检测任务开始{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    results = scan_directory(
        directory=args.scan_dir,
        max_bitrate_kbps=args.max_bitrate,
        max_resolution=args.max_resolution,
    )

    report = generate_report(results, args.report_output)

    # 在终端显示报告预览
    print("\n" + "=" * 50)
    print("报告预览:")
    print("=" * 50)
    print(report)


def execute_extract_audio(args):
    """执行音频抽取任务。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[小雪工具箱] 音频抽取任务开始{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    cmd = build_extract_audio_command(
        input_path=args.extract_input,
        output_path=args.extract_output,
        audio_encoder=AUDIO_ENCODERS.get(args.extract_encoder, "aac"),
        audio_bitrate=args.extract_bitrate,
    )

    run_ffmpeg_command(cmd)


if __name__ == "__main__":
    main()
