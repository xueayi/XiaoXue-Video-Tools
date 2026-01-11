# -*- coding: utf-8 -*-
"""
杂项执行器模块：包含通知设置、使用说明相关执行函数。
"""
from colorama import Fore, Style

from ..notify import send_feishu_notification, send_webhook_notification, FEISHU_COLORS
from ..notify_config import (
    NOTIFY_CONFIG_FILE,
    get_notify_config,
    update_notify_config,
    is_config_loaded,
    save_notify_config,
    delete_notify_config,
)
from ..help_texts import get_help_text
from .common import print_task_header


def execute_notification(args):
    """
    执行通知设置/测试任务。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("通知设置")

    # 显示配置加载状态
    print(f"\n[配置文件信息]")
    print(f"  路径: {NOTIFY_CONFIG_FILE}")
    print(f"  加载状态: {'✓ 已加载' if is_config_loaded() else '✗ 未加载 (使用默认配置)'}")
    
    # 处理删除配置请求
    if getattr(args, 'delete_notify_config', False):
        print(f"\n{Fore.YELLOW}[操作] 删除配置文件...{Style.RESET_ALL}")
        delete_notify_config()
        print(f"\n{'='*50}")
        print("配置文件已删除，下次启动将使用默认设置")
        return

    # 更新配置
    new_config = {
        "enabled": getattr(args, 'enable_auto_notify', False),
        "feishu_webhook": args.feishu_webhook,
        "feishu_title": args.feishu_title,
        "feishu_content": args.feishu_content,
        "feishu_color": FEISHU_COLORS.get(args.feishu_color, "blue"),
        "webhook_url": args.webhook_url,
        "webhook_headers": args.webhook_headers,
        "webhook_body": args.webhook_body,
    }
    update_notify_config(new_config)
    
    # 获取当前配置用于显示和测试
    config = get_notify_config()
    
    # 显示配置状态
    print(f"\n[当前配置]")
    print(f"  自动通知: {'✓ 已启用' if config['enabled'] else '✗ 未启用'}")
    if config["feishu_webhook"]:
        print(f"  飞书 Webhook: 已配置")
    if config["webhook_url"]:
        print(f"  自定义 Webhook: 已配置")
    
    # 保存配置
    if getattr(args, 'save_notify_config', False):
        save_notify_config(config)
    
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
    
    if config["enabled"]:
        print(f"\n{Fore.GREEN}✓ 自动通知已启用，其他任务完成后将自动发送通知{Style.RESET_ALL}")


def execute_help(args):
    """
    执行使用说明显示。
    
    Args:
        args: argparse 解析后的参数对象
    """
    print_task_header("使用说明")

    topic = getattr(args, 'help_topic', '视频压制')
    
    help_content = get_help_text(topic)
    
    print(f"\n{'='*50}")
    print(f"📖 {topic} 使用说明")
    print(f"{'='*50}\n")
    print(help_content)
