# -*- coding: utf-8 -*-
"""
通知配置管理模块：负责通知配置的加载、保存和自动发送。
"""
import os
import json

from colorama import Fore, Style

from .utils import get_base_dir
from .notify import send_feishu_notification, send_webhook_notification


# 通知配置文件路径
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


def get_notify_config() -> dict:
    """
    获取当前通知配置。
    
    Returns:
        通知配置字典的副本
    """
    return _notify_config.copy()


def update_notify_config(updates: dict):
    """
    更新通知配置。
    
    Args:
        updates: 要更新的配置项
    """
    global _notify_config
    _notify_config.update(updates)


def is_config_loaded() -> bool:
    """
    检查配置是否已从文件加载。
    
    Returns:
        True 如果已加载配置文件
    """
    return _notify_config_loaded


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


def delete_notify_config() -> bool:
    """
    删除通知配置文件。
    
    Returns:
        True 删除成功或文件不存在
    """
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
