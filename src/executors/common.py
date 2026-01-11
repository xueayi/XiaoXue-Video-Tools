# -*- coding: utf-8 -*-
"""
执行器共用模块：包含各执行器共享的辅助函数。
"""

from colorama import Fore, Style


def print_task_header(task_name: str):
    """
    打印任务开始的标题栏。
    
    Args:
        task_name: 任务名称
    """
    print(f"\n{'='*50}")
    print(f"{Fore.CYAN}【{task_name}】{Style.RESET_ALL}")
    print(f"{'='*50}\n")


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
