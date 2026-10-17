# -*- coding: utf-8 -*-
"""
杂项执行器模块：包含使用说明相关执行函数。
"""
from ..help_texts import get_help_text
from .common import print_task_header


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
