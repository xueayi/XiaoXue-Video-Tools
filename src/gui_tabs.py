# -*- coding: utf-8 -*-
"""
GUI 标签页定义模块：将各功能标签页的参数定义抽象为独立函数。
使得 main.py 更加简洁，功能逻辑与界面定义解耦。
"""
from gooey import GooeyParser

from .presets import (
    ENCODERS,
    QUALITY_PRESETS,
    AUDIO_ENCODERS,
    AUDIO_BITRATES,
    CPU_PRESETS,
    NVENC_PRESETS,
    RATE_CONTROL_MODES,
    VIDEO_BITRATES,
    RESOLUTION_PRESETS,
    REMUX_PRESETS,
    IMAGE_FORMATS,
    RENAME_MODES,
    RENAME_TARGETS,
    RENAME_BEHAVIORS,
    SHIELD_THRESHOLDS,
    SHIELD_CENSOR_TYPES,
    SHIELD_MOSAIC_SIZES,
    SHIELD_EXPAND_OPTIONS,
)
from .notify import FEISHU_COLORS


def register_encode_tab(subs) -> None:
    """注册视频压制标签页。"""
    encode_parser = subs.add_parser(
        "视频压制",
        help="视频转码、压缩、字幕烧录"
    )

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
    io_group.add_argument(
        "--compat-mode",
        metavar="兼容模式 (字幕)",
        action="store_true",
        default=False,
        help="开启：使用 AviSynth+VSFilter 渲染。\n当发现 ASS 字幕特效异常，或无法调用 TTC/OTF 字体的内置字重时请勾选。\n关闭 (默认)：使用 FFmpeg 内置 libass 渲染。速度更快，适合 SRT 及大多数 ASS 字幕。",
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
        default="【均衡画质】x264常用导出(CRF18)",
        help="选择预设配置，或选择 '自定义' 手动配置参数",
    )

    # ========== 编码器设置 ==========
    # 注意：已移除"复制 (不重新编码)"选项，该功能由封装转换模块提供
    encode_only_encoders = {k: v for k, v in ENCODERS.items() if v != "copy"}
    
    encoder_group = encode_parser.add_argument_group(
        "编码器设置",
        description="选择自定义模式时生效",
        gooey_options={"columns": 2}
    )
    encoder_group.add_argument(
        "--encoder",
        metavar="视频编码器",
        choices=list(encode_only_encoders.keys()),
        default="H.264 (CPU - libx264)",
        help="选择视频编码器 (CPU/NVIDIA/Intel/AMD)",
    )
    encoder_group.add_argument(
        "--speed-preset",
        metavar="编码速度",
        choices=CPU_PRESETS,
        default="medium",
        help="编码速度预设 (越慢画质越好)",
    )
    encoder_group.add_argument(
        "--nvenc-preset",
        metavar="N卡速度档位",
        choices=["使用预设默认"] + NVENC_PRESETS,
        default="使用预设默认",
        help="NVENC 速度档位 (p1最快/p7最慢)，选择 NVENC 编码器时生效",
    )

    # ========== 质量与码率 ==========
    quality_group = encode_parser.add_argument_group(
        "质量与码率",
        description="CRF/CQ 模式由质量值控制；VBR/CBR 模式需设置目标码率",
        gooey_options={"columns": 2}
    )
    quality_group.add_argument(
        "--rate-control",
        metavar="码率控制模式",
        choices=list(RATE_CONTROL_MODES.keys()),
        default="CRF/CQ (恒定质量)",
        help="恒定质量(推荐) / 可变码率 / 恒定码率 / 两遍编码",
    )
    quality_group.add_argument(
        "--crf",
        metavar="质量值 (CRF/CQ)",
        type=int,
        default=18,
        gooey_options={"min": 0, "max": 51},
        help="0-51，越低画质越好，推荐 18-23",
    )
    quality_group.add_argument(
        "--video-bitrate",
        metavar="目标码率",
        choices=VIDEO_BITRATES,
        default="",
        help=(
            "不同模式下的作用：\n"
            "• CRF/CQ 模式：留空，由上方质量值控制\n"
            "• VBR 模式：设置平均码率，允许波动\n"
            "• CBR 模式：设置恒定码率，适合直播\n"
            "• 2-Pass 模式：设置目标码率，更精确"
        ),
    )

    # ========== 视频输出 ==========
    output_group = encode_parser.add_argument_group(
        "视频输出",
        gooey_options={"columns": 2}
    )
    output_group.add_argument(
        "--resolution",
        metavar="分辨率",
        default="",
        help="如 1920x1080，留空保持原分辨率",
    )
    output_group.add_argument(
        "--fps",
        metavar="帧率",
        type=int,
        default=0,
        help="如 30、60，填 0 保持原帧率",
    )

    # ========== 音频设置 ==========
    audio_group = encode_parser.add_argument_group(
        "音频设置",
        gooey_options={"columns": 2}
    )
    audio_group.add_argument(
        "--audio-encoder",
        metavar="音频编码器",
        choices=list(AUDIO_ENCODERS.keys()),
        default="复制 (不重新编码)",
        help="选择音频编码器",
    )
    audio_group.add_argument(
        "--audio-bitrate",
        metavar="音频码率",
        choices=AUDIO_BITRATES,
        default="192k",
        help="音频码率",
    )

    # ========== 高级选项 ==========
    extra_group = encode_parser.add_argument_group(
        "高级选项",
        description=(
            "额外参数会追加到 FFmpeg 命令末尾，直接填写参数即可。\n"
            "【填写示例】-ss 00:01:00 -t 30 -tune animation"
        ),
        gooey_options={"columns": 1}
    )
    extra_group.add_argument(
        "--extra-args",
        metavar="额外 FFmpeg 参数",
        default="",
        help="多个参数用空格分隔，会追加到命令末尾",
    )
    extra_group.add_argument(
        "--debug_mode",
        metavar="Debug 模式",
        help="勾选后仅打印 FFmpeg 命令，不执行实际编码。",
        action="store_true",
        default=False
    )

    # 在线文档
    docs_group = encode_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-encode",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Video-Encode",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_replace_audio_tab(subs) -> None:
    """注册音频替换标签页。"""
    audio_parser = subs.add_parser(
        "音频替换",
        help="替换视频中的音轨"
    )

    audio_io = audio_parser.add_argument_group(
        "输入/输出设置",
    )

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
        metavar="输出路径 (可选)",
        required=False,
        default="",
        widget="FileSaver",
        gooey_options={"wildcard": "MP4 文件 (*.mp4)|*.mp4|所有文件 (*.*)|*.*"},
        help="留空则自动生成: [原视频名]_replaced.mp4",
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

    # 在线文档
    docs_group = audio_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-audio",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Audio-Tools",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_remux_tab(subs) -> None:
    """注册封装转换标签页（支持批量）。"""
    remux_parser = subs.add_parser(
        "封装转换",
        help="更换容器格式 (不重新编码，支持批量)"
    )

    remux_io = remux_parser.add_argument_group(
        "输入/输出设置",
    )

    remux_io.add_argument(
        "--remux-input",
        metavar="输入文件 (可多选)",
        required=True,
        nargs="+",
        widget="MultiFileChooser",
        gooey_options={"wildcard": "视频文件 (*.mp4;*.mov;*.avi;*.mkv;*.webm;*.ts;*.mxf)|*.mp4;*.mov;*.avi;*.mkv;*.webm;*.ts;*.mxf|所有文件 (*.*)|*.*"},
        help="选择要转换的文件 (可批量选择多个)",
    )
    
    remux_preset = remux_parser.add_argument_group("输出格式")
    remux_preset.add_argument(
        "--remux-preset",
        metavar="封装预设",
        choices=list(REMUX_PRESETS.keys()),
        default="MP4 (H.264 兼容)",
        help="选择目标封装格式预设",
    )
    remux_preset.add_argument(
        "--remux-output",
        metavar="输出目录 (可选)",
        required=False,
        default="",
        widget="DirChooser",
        help="批量模式: 选择输出目录。单文件留空则在原位置生成",
    )
    remux_preset.add_argument(
        "--remux-overwrite",
        metavar="覆盖原文件",
        action="store_true",
        default=False,
        help="⚠️ 危险: 转换后删除原文件，仅保留新文件",
    )

    # 在线文档
    docs_group = remux_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-remux",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Remux-Image",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_qc_tab(subs) -> None:
    """注册素材质量检测标签页。"""
    qc_parser = subs.add_parser(
        "素材质量检测",
        help="批量检测素材兼容性"
    )

    qc_io = qc_parser.add_argument_group(
        "扫描设置",
    )

    qc_io.add_argument(
        "--scan-dir",
        metavar="扫描目录",
        required=True,
        widget="DirChooser",
        help="选择要扫描的文件夹 (将递归扫描)",
    )
    qc_io.add_argument(
        "--report-output",
        metavar="报告输出路径 (可选)",
        required=False,
        default="",
        widget="FileSaver",
        gooey_options={"wildcard": "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*"},
        help="留空则自动生成: [扫描目录内]/QC_报告.txt",
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
        "--min-bitrate",
        metavar="最小码率 (kbps)",
        type=int,
        default=0,
        help="低于此码率将警告 (0 表示不检查)",
    )
    qc_thresholds.add_argument(
        "--max-res-preset",
        metavar="最大分辨率 (预设)",
        choices=list(RESOLUTION_PRESETS.keys()),
        default="不限制",
        help="选择最大分辨率预设，或选择 '自定义'",
    )
    qc_thresholds.add_argument(
        "--max-res-custom",
        metavar="最大分辨率 (自定义)",
        default="",
        help="如果上方选择 '自定义'，请在此输入 (如 1920x1080), 留空不检查",
    )
    qc_thresholds.add_argument(
        "--min-res-preset",
        metavar="最小分辨率 (预设)",
        choices=list(RESOLUTION_PRESETS.keys()),
        default="不限制",
        help="选择最小分辨率预设，或选择 '自定义'",
    )
    qc_thresholds.add_argument(
        "--min-res-custom",
        metavar="最小分辨率 (自定义)",
        default="",
        help="如果上方选择 '自定义'，请在此输入 (如 1280x720), 留空不检查",
    )
    
    qc_pr = qc_parser.add_argument_group("Premiere Pro 兼容性检测")
    qc_pr.add_argument(
        "--check-pr-video",
        metavar="PR 视频兼容性",
        action="store_true",
        default=True,
        help="检测可能会导致 PR 导入问题的视频格式 (如 MKV, VFR)",
    )
    qc_pr.add_argument(
        "--check-pr-image",
        metavar="PR 图片兼容性",
        action="store_true",
        default=True,
        help="检测可能会导致 PR 导入问题的图片格式",
    )
    
    # 自定义兼容性规则
    qc_custom = qc_parser.add_argument_group("自定义兼容性规则 (高级)")
    qc_custom.add_argument(
        "--custom-containers",
        metavar="不兼容容器",
        default="mkv,webm,ogv,ogg,flv",
        help="逗号分隔的不兼容容器扩展名 (不含点号)",
    )
    qc_custom.add_argument(
        "--custom-codecs",
        metavar="不兼容编码",
        default="vp8,vp9,av1,theora",
        help="逗号分隔的不兼容视频编码名称",
    )
    qc_custom.add_argument(
        "--custom-images",
        metavar="不兼容图片",
        default="webp,heic,avif",
        help="逗号分隔的不兼容图片扩展名 (不含点号)",
    )

    # 在线文档
    docs_group = qc_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-qc",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Quality-Control",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_extract_audio_tab(subs) -> None:
    """注册音频抽取标签页。"""
    extract_parser = subs.add_parser(
        "音频抽取",
        help="从视频中提取音频轨道"
    )

    extract_io = extract_parser.add_argument_group(
        "输入/输出设置",
    )

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
        metavar="输出音频 (可选)",
        required=False,
        default="",
        widget="FileSaver",
        gooey_options={"wildcard": "MP3 文件 (*.mp3)|*.mp3|AAC 文件 (*.aac)|*.aac|WAV 文件 (*.wav)|*.wav|FLAC 文件 (*.flac)|*.flac|所有文件 (*.*)|*.*"},
        help="留空则自动生成: [原视频名]_extract.[ext]",
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

    # 在线文档
    docs_group = extract_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-extract",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Audio-Tools",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_notification_tab(subs, config: dict = None) -> None:
    """
    注册通知设置标签页。
    
    Args:
        subs: 子解析器
        config: 已加载的通知配置字典 (用于设置默认值)
    """
    if config is None:
        config = {}
    
    notify_parser = subs.add_parser(
        "通知设置",
        help="配置飞书/Webhook 通知"
    )

    # 自动通知设置
    auto_group = notify_parser.add_argument_group(
        "自动通知设置",
        description="配置文件保存在程序目录下的 notify_config.json",
    )

    auto_group.add_argument(
        "--enable-auto-notify",
        metavar="启用自动通知",
        action="store_true",
        default=config.get("enabled", False),
        help="勾选后，其他任务完成时会自动发送通知",
    )
    auto_group.add_argument(
        "--save-notify-config",
        metavar="保存配置(运行后生效)",
        action="store_true",
        default=False,
        help="保存当前通知配置，下次启动时自动加载",
    )
    auto_group.add_argument(
        "--delete-notify-config",
        metavar="删除已保存配置",
        action="store_true",
        default=False,
        help="勾选后运行将删除已保存的配置文件",
    )

    # 飞书通知
    feishu_group = notify_parser.add_argument_group("飞书通知")
    feishu_group.add_argument(
        "--feishu-webhook",
        metavar="飞书 Webhook URL",
        default=config.get("feishu_webhook", ""),
        help="飞书机器人 Webhook 地址 (留空则跳过飞书通知)",
    )
    feishu_group.add_argument(
        "--feishu-title",
        metavar="卡片标题",
        default=config.get("feishu_title", "任务完成通知"),
        help="飞书消息卡片的标题",
    )
    feishu_group.add_argument(
        "--feishu-content",
        metavar="消息内容",
        default=config.get("feishu_content", "您的视频处理任务已完成！"),
        widget="Textarea",
        gooey_options={"height": 80},
        help="飞书消息内容 (支持 lark_md 格式)",
    )
    
    # 颜色需要反向查找显示名
    saved_color = config.get("feishu_color", "blue")
    color_display = "蓝色 (Blue)"
    for name, code in FEISHU_COLORS.items():
        if code == saved_color:
            color_display = name
            break
    
    feishu_group.add_argument(
        "--feishu-color",
        metavar="卡片颜色",
        choices=list(FEISHU_COLORS.keys()),
        default=color_display,
        help="消息卡片头部颜色",
    )

    # 自定义 Webhook
    webhook_group = notify_parser.add_argument_group("自定义 Webhook")
    webhook_group.add_argument(
        "--webhook-url",
        metavar="Webhook URL",
        default=config.get("webhook_url", ""),
        help="自定义 POST 请求 URL (留空则跳过)",
    )
    webhook_group.add_argument(
        "--webhook-headers",
        metavar="请求头 (JSON)",
        default=config.get("webhook_headers", '{"Content-Type": "application/json"}'),
        help='JSON 格式的请求头, 如: {"Authorization": "Bearer xxx"}',
    )
    webhook_group.add_argument(
        "--webhook-body",
        metavar="请求体 (JSON)",
        default=config.get("webhook_body", '{"message": "任务完成"}'),
        widget="Textarea",
        gooey_options={"height": 80},
        help='JSON 格式的请求体',
    )

    # 在线文档
    docs_group = notify_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-notify",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Notification",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_help_tab(subs) -> None:
    """注册使用说明标签页。"""
    help_parser = subs.add_parser(
        "使用说明",
        help="各功能使用指南"
    )

    help_group = help_parser.add_argument_group(
        "功能说明",
    )

    help_group.add_argument(
        "--help-topic",
        metavar="选择功能",
        choices=[
            "视频压制",
            "音频替换",
            "封装转换",
            "素材质量检测",
            "音频抽取",
            "图片转换",
            "文件夹创建",
            "批量重命名",
            "通知设置",
            "常见问题",
        ],
        default="视频压制",
        help="选择要查看说明的功能模块",
    )

    # 在线文档
    docs_group = help_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-home",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Home",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_image_convert_tab(subs) -> None:
    """注册图片格式转换标签页。"""
    img_parser = subs.add_parser(
        "图片转换",
        help="批量图片格式转换"
    )

    img_io = img_parser.add_argument_group(
        "输入/输出设置",
    )

    img_io.add_argument(
        "--img-input",
        metavar="输入图片 (可多选)",
        required=True,
        nargs="+",
        widget="MultiFileChooser",
        gooey_options={"wildcard": "图片文件 (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tiff)|*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tiff|所有文件 (*.*)|*.*"},
        help="选择要转换的图片文件 (可批量选择多个)",
    )
    img_io.add_argument(
        "--img-output-dir",
        metavar="输出目录 (可选)",
        required=False,
        default="",
        widget="DirChooser",
        help="留空则在原文件位置生成转换后的图片",
    )
    img_io.add_argument(
        "--img-overwrite",
        metavar="覆盖原文件",
        action="store_true",
        default=False,
        help="⚠️ 危险: 转换后删除原文件，仅保留新文件",
    )

    img_format = img_parser.add_argument_group("输出格式")
    img_format.add_argument(
        "--img-format",
        metavar="目标格式",
        choices=list(IMAGE_FORMATS.keys()),
        default="PNG (无损)",
        help="选择目标图片格式，或选择 '自定义' 手动输入",
    )
    img_format.add_argument(
        "--img-format-custom",
        metavar="自定义格式",
        default="",
        help="当上方选择 '自定义' 时，在此输入扩展名 (如 ico, tga)",
    )
    img_format.add_argument(
        "--img-quality",
        metavar="质量 (JPG/WEBP)",
        type=int,
        default=95,
        gooey_options={"min": 1, "max": 100},
        help="JPEG/WEBP 格式的压缩质量 (1-100)，其他格式忽略",
    )

    # 在线文档
    docs_group = img_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-img",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Remux-Image",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_folder_creator_tab(subs) -> None:
    """注册批量创建文件夹标签页。"""
    folder_parser = subs.add_parser(
        "文件夹创建",
        help="从 TXT 批量创建文件夹"
    )

    folder_io = folder_parser.add_argument_group(
        "输入/输出设置",
    )

    folder_io.add_argument(
        "--folder-txt",
        metavar="TXT 文件",
        required=True,
        widget="FileChooser",
        gooey_options={"wildcard": "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*"},
        help="选择包含文件夹名称的 TXT 文件，每行一个名称",
    )
    folder_io.add_argument(
        "--folder-output-dir",
        metavar="输出目录 (可选)",
        required=False,
        default="",
        widget="DirChooser",
        help="留空则在 TXT 文件所在目录创建。注意：路径不能以 / 或 \\ 结尾",
    )

    folder_options = folder_parser.add_argument_group("选项设置")
    folder_options.add_argument(
        "--folder-auto-number",
        metavar="自动排序",
        action="store_true",
        default=True,
        help="开启后自动在文件夹名前添加序号 (如 1_文件夹名)",
    )

    # 在线文档
    docs_group = folder_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-folder",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )


def register_batch_rename_tab(subs) -> None:
    """注册批量序列重命名标签页。"""
    rename_parser = subs.add_parser(
        "批量重命名",
        help="批量序列重命名图片/视频"
    )

    # 输入配置
    rename_io = rename_parser.add_argument_group(
        "输入设置",
    )

    rename_io.add_argument(
        "--rename-input-dir",
        metavar="输入目录",
        required=True,
        widget="DirChooser",
        help="选择要重命名的文件所在目录",
    )

    # 重命名模式
    rename_mode = rename_parser.add_argument_group("重命名模式")
    rename_mode.add_argument(
        "--rename-mode",
        metavar="模式",
        choices=list(RENAME_MODES.keys()),
        default="原地重命名",
        help="原地: 直接重命名; 复制: 保留原文件; 移动: 移动到新位置",
    )
    rename_mode.add_argument(
        "--rename-output-dir",
        metavar="安全输出路径 (可选)",
        required=False,
        default="",
        widget="DirChooser",
        help="复制/移动模式: 留空则在输入目录创建 'rename_output' 文件夹",
    )

    # 对象设置
    rename_target = rename_parser.add_argument_group("重命名对象")
    rename_target.add_argument(
        "--rename-target",
        metavar="目标类型",
        choices=list(RENAME_TARGETS.keys()),
        default="图片和视频",
        help="选择要重命名的文件类型",
    )
    rename_target.add_argument(
        "--rename-image-exts",
        metavar="图片格式",
        default="png,jpg",
        help="逗号分隔的图片扩展名 (不含点号)",
    )
    rename_target.add_argument(
        "--rename-video-exts",
        metavar="视频格式",
        default="mp4,mov",
        help="逗号分隔的视频扩展名 (不含点号)",
    )

    # 行为设置
    rename_behavior = rename_parser.add_argument_group(
        "重命名行为",
        description=(
            "【递归模式示例】\n"
            "输入目录: 图包\n"
            "  图包/新作/1_新闻/001.png → 新作_1_图片_1.png\n"
            "  图包/周边/2_采访/clip.mp4 → 周边_2_视频_1.mp4\n"
            "  图包/001.png → 图片_1.png\n"
            "【非递归模式示例】\n"
            "输入目录: 图包\n"
            "  图包/001.png → 图片_1.png\n"
            "  图包/clip.mp4 → 视频_1.mp4\n"
            "  图包/新作/1_新闻/001.png → 无重命名行为"
        ),
    )
    rename_behavior.add_argument(
        "--rename-recursive",
        metavar="行为模式",
        choices=list(RENAME_BEHAVIORS.keys()),
        default="递归模式（保持目录结构）",
        help="递归: 包含子目录; 非递归: 仅当前目录",
    )

    # 高级选项
    rename_advanced = rename_parser.add_argument_group("高级选项")
    rename_advanced.add_argument(
        "--rename-exclude-underscore",
        metavar="排除下划线后文字",
        action="store_true",
        default=True,
        help="递归模式下，忽略文件夹名中第一个下划线后的内容",
    )

    # 在线文档
    docs_group = rename_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-rename",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )

def register_shield_tab(subs) -> None:
    """注册露骨图片识别标签页 (Shield)。"""
    shield_parser = subs.add_parser(
        "露骨图片识别",
        help="识别 B 站过审风险图片，可选打码"
    )

    # 输入设置
    io_group = shield_parser.add_argument_group(
        "输入设置",
        description="选择要扫描的文件夹或图片文件",
    )
    io_group.add_argument(
        "--shield-input-dir",
        metavar="扫描目录",
        widget="DirChooser",
        default="",
        help="选择要扫描的文件夹 (递归扫描所有图片)",
    )
    io_group.add_argument(
        "--shield-input-files",
        metavar="或选择图片 (可多选)",
        nargs="*",
        widget="MultiFileChooser",
        gooey_options={"wildcard": "图片文件 (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif)|*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif|所有文件 (*.*)|*.*"},
        help="直接选择多个图片文件，与上方二选一",
    )

    # 输出设置
    output_group = shield_parser.add_argument_group("输出设置")
    output_group.add_argument(
        "--shield-output-dir",
        metavar="输出目录 (可选)",
        widget="DirChooser",
        default="",
        help="打码图片和报告的输出目录。留空则在输入目录下创建 shield_output 子目录",
    )
    output_group.add_argument(
        "--shield-report",
        metavar="报告路径 (可选)",
        widget="FileSaver",
        gooey_options={"wildcard": "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*"},
        default="",
        help="留空则自动生成: [输出目录]/shield_report.txt",
    )

    # 检测设置
    detect_group = shield_parser.add_argument_group("检测设置")
    detect_group.add_argument(
        "--shield-threshold",
        metavar="风险阈值",
        choices=list(SHIELD_THRESHOLDS.keys()),
        default="Questionable 及以上 (推荐)",
        help="达到此级别及以上将被标记为风险图片",
    )
    detect_group.add_argument(
        "--shield-recursive",
        metavar="递归扫描子目录",
        action="store_true",
        default=True,
        help="勾选后将扫描所有子目录中的图片",
    )

    # 打码设置
    censor_group = shield_parser.add_argument_group("打码设置 (可选)")
    censor_group.add_argument(
        "--shield-enable-censor",
        metavar="启用自动打码",
        action="store_true",
        default=False,
        help="对风险图片的敏感区域自动打码",
    )
    censor_group.add_argument(
        "--shield-censor-type",
        metavar="打码类型",
        choices=list(SHIELD_CENSOR_TYPES.keys()),
        default="马赛克 (Pixelate)",
        help="选择打码效果",
    )
    censor_group.add_argument(
        "--shield-mosaic-size",
        metavar="处理强度/大小",
        widget="Dropdown",
        choices=SHIELD_MOSAIC_SIZES,
        default="16",
        help="马赛克模式=方块大小，模糊模式=半径，黑色遮盖=圆角大小，表情=元素比例",
    )

    censor_group.add_argument(
        "--shield-overlay-image",
        metavar="覆盖图片 (自定义模式)",
        widget="FileChooser",
        gooey_options={"wildcard": "图片文件 (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg|所有文件 (*.*)|*.*"},
        default="",
        help="当打码类型选择“自定义图片”时，使用此图片覆盖敏感区域",
    )

    censor_group.add_argument(
        "--shield-expand-pixels",
        metavar="打码范围扩展 (像素)",
        widget="Dropdown",
        choices=SHIELD_EXPAND_OPTIONS,
        default="0",
        help="向外扩展打码区域的像素数，值越大覆盖范围越广 (所有模式生效)",
    )

    # 在线文档
    docs_group = shield_parser.add_argument_group("在线文档")
    docs_group.add_argument(
        "--wiki-shield",
        metavar="文档链接",
        default="https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Shield",
        help="复制此链接到浏览器访问",
        gooey_options={"visible": True, "full_width": True}
    )
