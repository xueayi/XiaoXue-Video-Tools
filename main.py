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
    from src.ui.theme import get_stylesheet
    from src.ui.main_window import MainWindow

    load_notify_config()

    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())

    notify_config = get_notify_config()
    window = MainWindow(
        shield_available=SHIELD_AVAILABLE,
        notify_config=notify_config,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
