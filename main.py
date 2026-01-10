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
    build_2pass_commands,
    build_replace_audio_command,
    build_remux_command,
    build_extract_audio_command,
    run_ffmpeg_command,
    run_2pass_encode,
)
from src.qc import scan_directory, generate_report
from src.presets import (
    QUALITY_PRESETS,
    AUDIO_ENCODERS,
    RESOLUTION_PRESETS,
    REMUX_PRESETS,
    ENCODERS,
    RATE_CONTROL_MODES,
    IMAGE_FORMATS,
    RENAME_MODES,
    RENAME_TARGETS,
    RENAME_BEHAVIORS,
)
from src.image_converter import batch_convert_images
from src.folder_creator import batch_create_folders
from src.batch_renamer import batch_rename, RenameConfig
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
    register_image_convert_tab,
    register_folder_creator_tab,
    register_batch_rename_tab,
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

# 配置加载状态
_notify_config_loaded = False


def load_notify_config():
    """加载通知配置文件。"""
    global _notify_config, _notify_config_loaded
    
    print(f"[配置] 配置文件路径: {NOTIFY_CONFIG_FILE}")
    
    if os.path.exists(NOTIFY_CONFIG_FILE):
        try:
            with open(NOTIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                _notify_config.update(saved)
                _notify_config_loaded = True
                print(f"{Fore.GREEN}[配置] ✓ 已加载通知配置{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[警告] 加载通知配置失败: {e}{Style.RESET_ALL}")
    else:
        print(f"[配置] 未找到配置文件，使用默认设置")


def save_notify_config(config: dict):
    """保存通知配置到文件。"""
    try:
        with open(NOTIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"{Fore.GREEN}[配置] 通知配置已保存到 {NOTIFY_CONFIG_FILE}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[错误] 保存通知配置失败: {e}{Style.RESET_ALL}")


def delete_notify_config():
    """删除通知配置文件。"""
    global _notify_config_loaded
    if os.path.exists(NOTIFY_CONFIG_FILE):
        try:
            os.remove(NOTIFY_CONFIG_FILE)
            _notify_config_loaded = False
            print(f"{Fore.GREEN}[配置] ✓ 已删除通知配置文件{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}[错误] 删除配置文件失败: {e}{Style.RESET_ALL}")
            return False
    else:
        print(f"[配置] 配置文件不存在，无需删除")
        return True


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
            "name": "关于",
            "items": [
                {
                    "type": "AboutDialog",
                    "menuTitle": "关于小雪工具箱",
                    "name": "小雪工具箱",
                    "description": "一个简单的视频压制与检测工具",
                    "version": "1.2.0",
                    "developer": "雪阿宜",
                    "website": "https://github.com/xueayi/XiaoXue-Video-Tools",
                },
            ],
        },
        {
            "name": "链接",
            "items": [
                {
                    "type": "Link",
                    "menuTitle": "GitHub 仓库",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools",
                },
                {
                    "type": "Link",
                    "menuTitle": "B站主页",
                    "url": "https://space.bilibili.com/107936977",
                },
            ],
        },
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
    register_image_convert_tab(subs)
    register_folder_creator_tab(subs)
    register_batch_rename_tab(subs)
    register_notification_tab(subs, _notify_config)
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
        "素材质量检测": execute_qc,
        "音频抽取": execute_extract_audio,
        "图片转换": execute_image_convert,
        "文件夹创建": execute_folder_creator,
        "批量重命名": execute_batch_rename,
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

    # 判断是否使用预设模式
    preset_name = args.preset
    is_custom = preset_name == "自定义 (Custom)"
    
    # 获取实际使用的编码器
    if not is_custom and preset_name in QUALITY_PRESETS:
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

    # 获取码率控制参数
    rc_mode_name = getattr(args, 'rate_control', 'CRF/CQ (恒定质量)')
    rc_mode = RATE_CONTROL_MODES.get(rc_mode_name, "crf")
    video_bitrate = getattr(args, 'video_bitrate', '')
    
    # 打印码率控制参数信息 (自定义模式下)
    if is_custom:
        print(f"  码率控制: {rc_mode_name}", flush=True)
        if video_bitrate:
            print(f"  视频码率: {video_bitrate}", flush=True)

    # 2-Pass 编码模式 - 使用真正的两遍编码
    if rc_mode == "2pass" and video_bitrate:
        print(f"{Fore.CYAN}[2-Pass 模式] 将执行真正的两遍编码{Style.RESET_ALL}", flush=True)
        
        pass1_cmd, pass2_cmd = build_2pass_commands(
            input_path=args.input,
            output_path=output_path,
            preset_name=args.preset,
            encoder=args.encoder if is_custom else None,  # 非自定义模式不传入编码器
            bitrate=video_bitrate,
            speed_preset=getattr(args, 'speed_preset', None) if is_custom else None,
            resolution=args.resolution if args.resolution else None,
            fps=args.fps if args.fps > 0 else None,
            audio_encoder=AUDIO_ENCODERS.get(args.audio_encoder, "aac"),
            audio_bitrate=args.audio_bitrate,
            subtitle_path=args.subtitle if args.subtitle else None,
            extra_args=args.extra_args if args.extra_args else None,
        )
        
        run_2pass_encode(pass1_cmd, pass2_cmd)
    else:
        # 普通编码模式
        cmd = build_encode_command(
            input_path=args.input,
            output_path=output_path,
            preset_name=args.preset,
            encoder=args.encoder if is_custom else None,  # 非自定义模式不传入编码器，使用预设值
            crf=args.crf if is_custom else None,
            bitrate=video_bitrate if video_bitrate else None,
            speed_preset=getattr(args, 'speed_preset', None) if is_custom else None,
            resolution=args.resolution if args.resolution else None,
            fps=args.fps if args.fps > 0 else None,
            audio_encoder=AUDIO_ENCODERS.get(args.audio_encoder, "aac"),
            audio_bitrate=args.audio_bitrate,
            subtitle_path=args.subtitle if args.subtitle else None,
            extra_args=args.extra_args if args.extra_args else None,
            rc_mode=rc_mode if rc_mode != "crf" else None,
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
    """执行封装转换任务（支持批量）。"""
    print_task_header("封装转换")

    preset_name = getattr(args, 'remux_preset', 'MP4 (H.264 兼容)')
    preset = REMUX_PRESETS.get(preset_name, {})
    extension = preset.get("extension", ".mp4")
    overwrite = getattr(args, 'remux_overwrite', False)
    
    # 获取输入文件列表
    input_files = args.remux_input
    if isinstance(input_files, str):
        input_files = [input_files]
    
    output_dir = args.remux_output if args.remux_output else None
    
    print(f"[预设] {preset_name}")
    print(f"[输入文件数] {len(input_files)}")
    if output_dir:
        print(f"[输出目录] {output_dir}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")
    print("-" * 50)

    success_count = 0
    fail_count = 0
    files_to_delete = []  # 成功后需要删除的原文件

    for i, input_path in enumerate(input_files, 1):
        print(f"\n[{i}/{len(input_files)}] 处理: {os.path.basename(input_path)}")
        
        # 生成输出路径
        if output_dir:
            basename = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(output_dir, basename + "_remux" + extension)
        else:
            output_path = auto_generate_output_path(input_path, "_remux", extension)
        
        print(f"[输出] {output_path}")

        cmd = build_remux_command(
            input_path=input_path,
            output_path=output_path,
        )

        result = run_ffmpeg_command(cmd)
        if result == 0:
            success_count += 1
            if overwrite and os.path.normpath(input_path) != os.path.normpath(output_path):
                files_to_delete.append(input_path)
        else:
            fail_count += 1

    # 覆盖模式：删除原文件
    if overwrite and files_to_delete:
        print(f"\n{Fore.YELLOW}[覆盖模式] 删除 {len(files_to_delete)} 个原文件...{Style.RESET_ALL}")
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"  ✓ 已删除: {os.path.basename(f)}")
            except Exception as e:
                print(f"  ✗ 删除失败: {os.path.basename(f)} - {e}")

    print(f"\n{'='*50}")
    print(f"批量转换完成: 成功 {success_count} 个, 失败 {fail_count} 个")


def execute_qc(args):
    """执行素材质量检测任务。"""
    print_task_header("素材质量检测")

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

    # 显示配置加载状态
    print(f"\n[配置文件信息]")
    print(f"  路径: {NOTIFY_CONFIG_FILE}")
    print(f"  加载状态: {'✓ 已加载' if _notify_config_loaded else '✗ 未加载 (使用默认配置)'}")
    
    # 处理删除配置请求
    if getattr(args, 'delete_notify_config', False):
        print(f"\n{Fore.YELLOW}[操作] 删除配置文件...{Style.RESET_ALL}")
        delete_notify_config()
        print(f"\n{'='*50}")
        print("配置文件已删除，下次启动将使用默认设置")
        return

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
    print(f"\n[当前配置]")
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


def execute_image_convert(args):
    """执行图片格式转换任务。"""
    print_task_header("图片格式转换")

    # 获取输入文件列表
    input_files = args.img_input
    if isinstance(input_files, str):
        input_files = [input_files]

    # 确定目标格式
    format_preset = getattr(args, 'img_format', 'PNG (无损)')
    if format_preset == "自定义":
        target_ext = getattr(args, 'img_format_custom', 'png')
        if not target_ext:
            print(f"{Fore.RED}[错误] 选择自定义格式时必须输入扩展名{Style.RESET_ALL}")
            return
    else:
        target_ext = IMAGE_FORMATS.get(format_preset, ".png")

    # 确保扩展名格式正确
    if target_ext and not target_ext.startswith("."):
        target_ext = "." + target_ext

    output_dir = args.img_output_dir if args.img_output_dir else None
    quality = getattr(args, 'img_quality', 95)
    overwrite = getattr(args, 'img_overwrite', False)

    print(f"[目标格式] {target_ext}")
    print(f"[质量] {quality}")
    print(f"[文件数量] {len(input_files)}")
    if overwrite:
        print(f"{Fore.YELLOW}[警告] 覆盖模式已开启，原文件将被删除{Style.RESET_ALL}")

    success, fail, errors = batch_convert_images(
        input_paths=input_files,
        output_dir=output_dir,
        target_extension=target_ext,
        quality=quality,
    )

    # 覆盖模式：删除成功转换的原文件
    if overwrite and success > 0:
        print(f"\n{Fore.YELLOW}[覆盖模式] 删除原文件...{Style.RESET_ALL}")
        deleted_count = 0
        for input_path in input_files:
            # 只删除成功转换的，且新旧文件扩展名不同的
            input_ext = os.path.splitext(input_path)[1].lower()
            if input_ext != target_ext.lower():
                try:
                    os.remove(input_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"  ✗ 删除失败: {os.path.basename(input_path)} - {e}")
        if deleted_count > 0:
            print(f"  ✓ 已删除 {deleted_count} 个原文件")

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分转换失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")


def execute_folder_creator(args):
    """执行批量创建文件夹任务。"""
    print_task_header("批量创建文件夹")

    txt_path = args.folder_txt
    output_dir = args.folder_output_dir
    auto_number = getattr(args, 'folder_auto_number', True)

    # 如果未指定输出目录，使用 TXT 文件所在目录
    if not output_dir or not output_dir.strip():
        output_dir = os.path.dirname(txt_path)
        print(f"[自动设置] 输出目录: {output_dir}")
    else:
        # 清理尾部斜杠
        output_dir = output_dir.rstrip("/\\")

    success, fail, errors = batch_create_folders(
        txt_path=txt_path,
        output_dir=output_dir,
        auto_number=auto_number,
    )

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分创建失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")


def execute_batch_rename(args):
    """执行批量序列重命名任务。"""
    print_task_header("批量序列重命名")

    input_dir = args.rename_input_dir
    
    # 解析模式
    mode_name = getattr(args, 'rename_mode', '原地重命名')
    mode = RENAME_MODES.get(mode_name, 'rename_in_place')
    
    # 解析目标类型
    target_name = getattr(args, 'rename_target', '图片和视频')
    target_type = RENAME_TARGETS.get(target_name, 'both')
    
    # 解析递归行为
    behavior_name = getattr(args, 'rename_recursive', '递归模式（保持目录结构）')
    recursive = RENAME_BEHAVIORS.get(behavior_name, True)
    
    # 解析扩展名
    image_exts = [ext.strip() for ext in args.rename_image_exts.split(',') if ext.strip()]
    video_exts = [ext.strip() for ext in args.rename_video_exts.split(',') if ext.strip()]
    
    # 输出目录
    output_dir = args.rename_output_dir if args.rename_output_dir else None
    
    # 排除下划线
    exclude_underscore = getattr(args, 'rename_exclude_underscore', True)

    # 创建配置
    config = RenameConfig(
        mode=mode,
        output_dir=output_dir,
        target_type=target_type,
        image_extensions=image_exts,
        video_extensions=video_exts,
        recursive=recursive,
        exclude_underscore=exclude_underscore,
    )

    success, fail, errors = batch_rename(
        input_path=input_dir,
        config=config,
    )

    if errors:
        print(f"\n{Fore.YELLOW}[警告] 部分重命名失败:{Style.RESET_ALL}")
        for err in errors[:5]:
            print(f"  - {err}")


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
