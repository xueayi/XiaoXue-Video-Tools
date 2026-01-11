# -*- coding: utf-8 -*-
"""
小雪工具箱 (XiaoXue Video Toolbox) - 一个简单的视频压制与检测工具

使用 Gooey 构建图形界面，调用 FFmpeg 进行视频处理。

项目结构:
- main.py: 程序入口和命令分发
- src/gui_config.py: GUI 配置常量
- src/gui_tabs.py: GUI 标签页定义
- src/notify_config.py: 通知配置管理
- src/executors/: 各功能执行器模块
- src/core.py: FFmpeg 核心调用
- src/presets.py: 预设配置
"""

# ============================================================
# 初始化
# ============================================================

# 初始化日志系统 (包含 IO 修复)
from src.log_utils import setup_logging
logger = setup_logging()

from gooey import Gooey, GooeyParser
from colorama import init as colorama_init, Fore, Style

# 初始化 colorama
colorama_init()

# ============================================================
# 导入模块
# ============================================================

# GUI 配置
from src.gui_config import get_gooey_config

# 通知配置
from src.notify_config import load_notify_config, send_auto_notification, get_notify_config

# GUI 标签页定义
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
    register_shield_tab,
)

# 执行器模块
from src.executors import (
    execute_encode,
    execute_replace_audio,
    execute_extract_audio,
    execute_remux,
    execute_image_convert,
    execute_folder_creator,
    execute_batch_rename,
    execute_qc,
    execute_notification,
    execute_help,
    execute_shield,
    SHIELD_AVAILABLE,
)


# ============================================================
# 程序入口
# ============================================================

@Gooey(**get_gooey_config())
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
    
    # Shield 功能（仅在 imgutils 可用时注册）
    if SHIELD_AVAILABLE:
        register_shield_tab(subs)
    
    # 获取通知配置用于标签页默认值
    notify_config = get_notify_config()
    register_notification_tab(subs, notify_config)
    register_help_tab(subs)

    args = parser.parse_args()

    # 命令分发
    dispatch_command(args)


def dispatch_command(args):
    """
    根据子命令分发到对应的执行函数。
    
    Args:
        args: argparse 解析后的参数对象
    """
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
    
    # Shield 功能（仅在可用时添加）
    if SHIELD_AVAILABLE:
        auto_notify_tasks["露骨图片识别"] = execute_shield

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


if __name__ == "__main__":
    main()
