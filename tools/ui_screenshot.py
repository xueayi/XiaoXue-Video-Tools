# -*- coding: utf-8 -*-
"""UI 截图开发工具 —— 离屏渲染主窗口各页面为 PNG。

不弹出真实窗口 (offscreen 平台)，用于界面改造前后的视觉对比。

用法:
    python tools/ui_screenshot.py           # 输出到 .ui_screens/
    python tools/ui_screenshot.py --theme dark
    python tools/ui_screenshot.py --page 0  # 只截某个页面索引
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402


def _settle(app, ms=350):
    """跑一圈事件循环，让切换动画播完再截图。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="light", choices=["light", "dark"])
    parser.add_argument("--page", type=int, default=-1, help="-1 表示全部页面")
    parser.add_argument("--out", default=".ui_screens")
    args = parser.parse_args()

    from src.ui.theme import apply_theme, set_theme
    from src.ui.main_window import MainWindow
    from src._version import __version__

    app = QApplication(sys.argv)
    set_theme(args.theme)  # 让代码侧取色 (图标/Logo) 与目标主题一致
    apply_theme(app, args.theme)

    window = MainWindow(shield_available=True, notify_config=None)
    window.resize(1180, 800)
    # 不调用 show()：窗口保持隐藏，grab() 仍可离屏渲染，不干扰桌面
    app.processEvents()

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           args.out, args.theme)
    os.makedirs(out_dir, exist_ok=True)

    count = window._stack.count()
    pages = [args.page] if args.page >= 0 else range(count)

    for i in pages:
        window._sidebar.setCurrentRow(i)
        _settle(app)  # 等页面切换动画 (200ms) 和药丸动画 (250ms) 播完
        name = window._sidebar.item_text(i).replace("/", "_") or f"page{i}"
        pix = window.grab()
        path = os.path.join(out_dir, f"{i:02d}_{name}_v{__version__}.png")
        pix.save(path)
        print("saved:", path)

    window.close()
    print("done.")


if __name__ == "__main__":
    main()
