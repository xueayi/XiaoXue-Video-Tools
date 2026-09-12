# -*- coding: utf-8 -*-
"""
小雪工具箱 (XiaoXue Video Toolbox) - 一个简单的视频压制与检测工具

使用 PyQt6 构建图形界面，调用 FFmpeg 进行视频处理。

项目结构:
- main.py: 程序入口
- src/ui/: PyQt6 图形界面模块
- src/executors/: 各功能执行器模块
- src/core.py: FFmpeg 核心调用
- src/presets.py: 预设配置
"""

import os
import sys

from src.log_utils import setup_logging

logger = setup_logging()

from colorama import init as colorama_init

colorama_init()

from src.notify_config import load_notify_config, get_notify_config
from src.executors import SHIELD_AVAILABLE


def main():
    """主入口函数，启动 PyQt6 图形界面。"""
    from PyQt6.QtWidgets import QApplication
    from src import updater
    from src.ui.theme import apply_theme, get_theme
    from src.ui.main_window import MainWindow

    # 有下载就绪但尚未应用的更新 (上次重启安装未完成) 时,
    # 优先拉起更新器完成替换并重启, 而不是进入主界面
    if updater.has_pending_update(updater_install_dir()):
        logger.info("检测到待应用更新, 拉起更新器继续完成安装")
        updater.launch_updater(updater_install_dir(), os.getpid())
        sys.exit(0)

    load_notify_config()

    app = QApplication(sys.argv)
    apply_theme(app, get_theme())

    notify_config = get_notify_config()
    window = MainWindow(
        shield_available=SHIELD_AVAILABLE,
        notify_config=notify_config,
    )
    window.show()
    sys.exit(app.exec())


def updater_install_dir():
    from src.utils import get_base_dir
    return get_base_dir()


if __name__ == "__main__":
    main()
