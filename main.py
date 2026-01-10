# -*- coding: utf-8 -*-
"""
小雪工具箱 (XiaoXue Video Toolbox) - 一个简单的视频压制与检测工具
使用 Gooey 构建图形界面，调用 FFmpeg 进行视频处理。
"""
import os
import sys
import json

# 初始化日志系统 (包含 IO 修复)
from src.log_utils import setup_logging
logger = setup_logging()

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
    QUALITY_PRESETS,
    AUDIO_ENCODERS,
    RESOLUTION_PRESETS,
    REMUX_PRESETS,
    ENCODERS,
)
from src.notify import send_feishu_notification, send_webhook_notification, FEISHU_COLORS
from src.utils import get_base_dir, generate_output_path, auto_generate_output_path
from src.help_texts import get_help_text

# 导入 GUI 标签页定义
from src.gui_tabs import (
    register_encode_tab,
    register_replace_audio_tab,
    register_remux_tab,
    register_qc_tab,
    register_extract_audio_tab,
    register_notification_tab,
    register_help_tab,
)


# ============================================================
# 通知配置管理
# ============================================================
NOTIFY_CONFIG_FILE = os.path.join(get_base_dir(), "notify_config.json")

# 全局通知配置 (运行时缓存)
_notify_config = {
    "enabled": False,
    "feishu_webhook": "",
    "feishu_title": "任务完成通知",
    "feishu_content": "您的视频处理任务已完成！",
    "feishu_color": "blue",
    "webhook_url": "",
    "webhook_headers": '{"Content-Type": "application/json"}',
    "webhook_body": '{"message": "任务完成"}',
}


def load_notify_config():
    """加载通知配置文件。"""
    global _notify_config
    if os.path.exists(NOTIFY_CONFIG_FILE):
        try:
            with open(NOTIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                _notify_config.update(saved)
                print(f"{Fore.GREEN}[配置] 已加载通知配置{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[警告] 加载通知配置失败: {e}{Style.RESET_ALL}")


def save_notify_config(config: dict):
    """保存通知配置到文件。"""
    try:
        with open(NOTIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"{Fore.GREEN}[配置] 通知配置已保存到 {NOTIFY_CONFIG_FILE}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[错误] 保存通知配置失败: {e}{Style.RESET_ALL}")


def send_auto_notification(task_name: str):
    """
    根据全局配置自动发送通知。
    
    Args:
        task_name: 完成的任务名称
    """
    if not _notify_config.get("enabled", False):
        return
    
    print(f"\n{Fore.CYAN}[自动通知] 正在发送任务完成通知...{Style.RESET_ALL}")
    
    # 动态替换内容中的任务名称
    content = _notify_config.get("feishu_content", "").replace("{task}", task_name)
    body = _notify_config.get("webhook_body", "").replace("{task}", task_name)
    
    # 发送飞书通知
    if _notify_config.get("feishu_webhook"):
        send_feishu_notification(
            webhook_url=_notify_config["feishu_webhook"],
            title=_notify_config.get("feishu_title", "任务完成通知"),
            content=content,
            color=_notify_config.get("feishu_color", "blue"),
        )
    
    # 发送自定义 Webhook
    if _notify_config.get("webhook_url"):
        send_webhook_notification(
            url=_notify_config["webhook_url"],
            headers_json=_notify_config.get("webhook_headers"),
            body_json=body,
        )


# ============================================================
# Gooey 配置常量
# ============================================================
GOOEY_CONFIG = {
    "program_name": "小雪工具箱",
    "program_description": "一个简单的视频压制与检测工具",
    "language": "chinese",
    "navigation": "SIDEBAR",
    "sidebar_title": "功能导航",
    "show_sidebar": True,
    "default_size": (900, 700),
    "richtext_controls": True,
    "show_success_modal": False,
    "show_failure_modal": False,
    "show_stop_warning": True,
    # Light Mode 配置 - 浅色主题，清晰易读
    "body_bg_color": "#f5f5f5",
    "header_bg_color": "#00AEEC",
    "footer_bg_color": "#e0e0e0",
    "sidebar_bg_color": "#ffffff",
    "terminal_panel_color": "#ffffff",
    "terminal_font_color": "#333333",
    "show_restart_button": True,
    "menu": [
        {
            "name": "帮助",
            "items": [
                {
                    "type": "AboutDialog",
                    "menuTitle": "关于",
                    "name": "小雪工具箱",
                    "description": "一个简单的视频压制与检测工具",
                    "version": "1.2.0",
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
    "image_dir": get_base_dir(),
}


def get_icon_path():
    """获取图标路径 (可选)。"""
    base = get_base_dir()
    icon = os.path.join(base, "icon.ico")
    return icon if os.path.exists(icon) else None


@Gooey(**GOOEY_CONFIG)
def main():
    """主入口函数，定义 Gooey 界面。"""
    # 启动时加载通知配置
    load_notify_config()
    
    parser = GooeyParser(description="选择左侧功能进行操作")
    subs = parser.add_subparsers(dest="command", help="功能选择")

    # 注册所有标签页
    register_encode_tab(subs)
    register_replace_audio_tab(subs)
    register_remux_tab(subs)
    register_qc_tab(subs)
    register_extract_audio_tab(subs)
    register_notification_tab(subs)
    register_help_tab(subs)

    args = parser.parse_args()

    # 命令分发
    dispatch_command(args)


def dispatch_command(args):
    """根据子命令分发到对应的执行函数。"""
    # 需要自动通知的任务
    auto_notify_tasks = {
        "视频压制": execute_encode,
        "音频替换": execute_replace_audio,
        "封装转换": execute_remux,
        "质量检测": execute_qc,
        "音频抽取": execute_extract_audio,
    }
    
    # 不需要自动通知的任务
    other_tasks = {
        "通知设置": execute_notification,
        "使用说明": execute_help,
    }

    if args.command in auto_notify_tasks:
        handler = auto_notify_tasks[args.command]
        handler(args)
        # 任务完成后发送自动通知
        send_auto_notification(args.command)
    elif args.command in other_tasks:
        handler = other_tasks[args.command]
        handler(args)
    else:
        print(f"{Fore.YELLOW}请从左侧选择一个功能{Style.RESET_ALL}")


# ============================================================
# 执行函数
# ============================================================

def execute_encode(args):
    """执行视频压制任务。"""
    print_task_header("视频压制")

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
    print_task_header("音频替换")

    output_path = args.audio_output
    if not output_path:
        output_path = auto_generate_output_path(args.video_input, "_replaced")
        print(f"[自动生成输出路径] {output_path}", flush=True)

    cmd = build_replace_audio_command(
        video_path=args.video_input,
        audio_path=args.audio_input,
        output_path=output_path,
        audio_encoder=AUDIO_ENCODERS.get(args.audio_enc, "aac"),
        audio_bitrate=args.audio_br,
    )

    run_ffmpeg_command(cmd)


def execute_remux(args):
    """执行封装转换任务。"""
    print_task_header("封装转换")

    output_path = args.remux_output
    preset_name = getattr(args, 'remux_preset', 'MP4 (H.264 兼容)')
    preset = REMUX_PRESETS.get(preset_name, {})
    
    if not output_path:
        # 根据预设自动生成输出路径
        extension = preset.get("extension", ".mp4")
        if extension:
            output_path = auto_generate_output_path(args.remux_input, "_remux", extension)
        else:
            output_path = auto_generate_output_path(args.remux_input, "_remux")
        print(f"[预设] {preset_name}", flush=True)
        print(f"[自动生成输出路径] {output_path}", flush=True)

    cmd = build_remux_command(
        input_path=args.remux_input,
        output_path=output_path,
    )

    run_ffmpeg_command(cmd)


def execute_qc(args):
    """执行质量检测任务。"""
    print_task_header("质量检测")

    report_path = args.report_output
    if not report_path:
        if os.path.isdir(args.scan_dir):
            report_path = os.path.join(args.scan_dir, "QC_报告.txt")
        else:
            report_path = auto_generate_output_path(args.scan_dir, "_QC_报告", ".txt")
        print(f"[自动生成报告路径] {report_path}", flush=True)

    # 处理分辨率预设
    max_res = RESOLUTION_PRESETS.get(args.max_res_preset, "")
    if max_res == "custom":
        max_res = args.max_res_custom
        
    min_res = RESOLUTION_PRESETS.get(args.min_res_preset, "")
    if min_res == "custom":
        min_res = args.min_res_custom

    # 解析自定义兼容性规则
    custom_containers = parse_comma_list(getattr(args, 'custom_containers', ''), prefix='.')
    custom_codecs = parse_comma_list(getattr(args, 'custom_codecs', ''))
    custom_images = parse_comma_list(getattr(args, 'custom_images', ''), prefix='.')

    results = scan_directory(
        directory=args.scan_dir,
        max_bitrate_kbps=args.max_bitrate,
        max_resolution=max_res,
        min_bitrate_kbps=args.min_bitrate,
        min_resolution=min_res,
        check_pr_video=args.check_pr_video,
        check_pr_image=args.check_pr_image,
        incompatible_containers=custom_containers if custom_containers else None,
        incompatible_codecs=custom_codecs if custom_codecs else None,
        incompatible_images=custom_images if custom_images else None,
    )

    report = generate_report(results, report_path)

    # 在终端显示报告预览
    print("\n" + "=" * 50)
    print("报告预览:")
    print("=" * 50)
    print(report)


def execute_extract_audio(args):
    """执行音频抽取任务。"""
    print_task_header("音频抽取")

    output_path = args.extract_output
    if not output_path:
        # 简单推断扩展名
        encoder_key = args.extract_encoder
        ext = ".m4a"
        if "MP3" in encoder_key:
            ext = ".mp3"
        elif "WAV" in encoder_key:
            ext = ".wav"
        elif "FLAC" in encoder_key:
            ext = ".flac"
        
        output_path = auto_generate_output_path(args.extract_input, "_extract", ext)
        print(f"[自动生成输出路径] {output_path}", flush=True)

    cmd = build_extract_audio_command(
        input_path=args.extract_input,
        output_path=output_path,
        audio_encoder=AUDIO_ENCODERS.get(args.extract_encoder, "aac"),
        audio_bitrate=args.extract_bitrate,
    )

    run_ffmpeg_command(cmd)


def execute_notification(args):
    """执行通知设置/测试任务。"""
    global _notify_config
    
    print_task_header("通知设置")

    # 更新全局配置
    _notify_config["enabled"] = getattr(args, 'enable_auto_notify', False)
    _notify_config["feishu_webhook"] = args.feishu_webhook
    _notify_config["feishu_title"] = args.feishu_title
    _notify_config["feishu_content"] = args.feishu_content
    _notify_config["feishu_color"] = FEISHU_COLORS.get(args.feishu_color, "blue")
    _notify_config["webhook_url"] = args.webhook_url
    _notify_config["webhook_headers"] = args.webhook_headers
    _notify_config["webhook_body"] = args.webhook_body
    
    # 显示配置状态
    print(f"\n[配置状态]")
    print(f"  自动通知: {'✓ 已启用' if _notify_config['enabled'] else '✗ 未启用'}")
    if _notify_config["feishu_webhook"]:
        print(f"  飞书 Webhook: 已配置")
    if _notify_config["webhook_url"]:
        print(f"  自定义 Webhook: 已配置")
    
    # 保存配置
    if getattr(args, 'save_notify_config', False):
        save_notify_config(_notify_config)
    
    # 测试发送
    success_count = 0
    fail_count = 0

    if args.feishu_webhook:
        print(f"\n{Fore.CYAN}[测试飞书通知]{Style.RESET_ALL}")
        result = send_feishu_notification(
            webhook_url=args.feishu_webhook,
            title=args.feishu_title,
            content=args.feishu_content,
            color=FEISHU_COLORS.get(args.feishu_color, "blue"),
        )
        if result:
            success_count += 1
        else:
            fail_count += 1

    if args.webhook_url:
        print(f"\n{Fore.CYAN}[测试自定义 Webhook]{Style.RESET_ALL}")
        result = send_webhook_notification(
            url=args.webhook_url,
            headers_json=args.webhook_headers,
            body_json=args.webhook_body,
        )
        if result:
            success_count += 1
        else:
            fail_count += 1

    # 汇总
    print(f"\n{'='*50}")
    if success_count > 0 or fail_count > 0:
        print(f"测试通知发送完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    else:
        print("未配置任何通知渠道，请填写 Webhook URL")
    
    if _notify_config["enabled"]:
        print(f"\n{Fore.GREEN}✓ 自动通知已启用，其他任务完成后将自动发送通知{Style.RESET_ALL}")


def execute_help(args):
    """执行使用说明显示。"""
    print_task_header("使用说明")

    topic = getattr(args, 'help_topic', '视频压制')
    
    help_content = get_help_text(topic)
    
    print(f"\n{'='*50}")
    print(f"📖 {topic} 使用说明")
    print(f"{'='*50}\n")
    print(help_content)


# ============================================================
# 辅助函数
# ============================================================

def print_task_header(task_name: str):
    """打印任务开始的标题栏。"""
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}", flush=True)
    print(f"{Fore.CYAN}[小雪工具箱] {task_name}任务开始{Style.RESET_ALL}", flush=True)
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}", flush=True)


def parse_comma_list(value: str, prefix: str = '') -> set:
    """
    解析逗号分隔的字符串为集合。
    
    Args:
        value: 逗号分隔的字符串 (如 "mkv,webm,flv")
        prefix: 可选前缀 (如 "." 用于扩展名)
    
    Returns:
        处理后的集合
    """
    if not value or not value.strip():
        return set()
    
    items = [item.strip().lower() for item in value.split(',') if item.strip()]
    if prefix:
        items = [f"{prefix}{item}" if not item.startswith(prefix) else item for item in items]
    
    return set(items)


if __name__ == "__main__":
    main()
