# -*- coding: utf-8 -*-
"""
GUI 配置模块：包含 Gooey GUI 的配置常量和图标获取函数。
"""
import os

from .utils import get_base_dir, get_internal_dir


def get_icon_path():
    """
    获取图标路径 (可选)。
    
    Returns:
        图标文件的绝对路径，如果未找到则返回 None
    """
    base = get_base_dir()
    internal = get_internal_dir()
    
    # 优先检查 _internal 目录 (PyInstaller 打包环境)
    icon_internal = os.path.join(internal, "icon.ico")
    if os.path.exists(icon_internal):
        print(f"[图标] 图标路径: {icon_internal}")
        return icon_internal
    
    # 回退到 exe 同目录 (开发环境)
    icon_base = os.path.join(base, "icon.ico")
    if os.path.exists(icon_base):
        print(f"[图标] 图标路径: {icon_base}")
        return icon_base
    
    print(f"[图标] 未找到图标文件")
    return None


def get_gooey_config() -> dict:
    """
    获取 Gooey GUI 配置字典。
    
    Returns:
        Gooey 配置字典
    """
    return {
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
        "menu": _get_menu_config(),
        "image_dir": get_base_dir(),
        "program_icon": get_icon_path(),
    }


def _get_menu_config() -> list:
    """
    获取菜单配置。
    
    Returns:
        菜单配置列表
    """
    return [
        {
            "name": "关于",
            "items": [
                {
                    "type": "AboutDialog",
                    "menuTitle": "关于小雪工具箱",
                    "name": "小雪工具箱",
                    "description": "一个简单的视频压制与检测工具",
                    "version": "1.5.0",
                    "developer": "雪阿宜",
                    "website": "https://github.com/xueayi/XiaoXue-Video-Tools",
                },
            ],
        },
        {
            "name": "帮助文档",
            "items": [
                {
                    "type": "Link",
                    "menuTitle": "使用手册首页 (Home)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Home",
                },
                {
                    "type": "Link",
                    "menuTitle": "安装与环境 (Installation)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Installation",
                },
                {
                    "type": "Link",
                    "menuTitle": "视频压制 (Video Encode)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Video-Encode",
                },
                {
                    "type": "Link",
                    "menuTitle": "音频工具 (Audio Tools)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Audio-Tools",
                },
                {
                    "type": "Link",
                    "menuTitle": "封装与图片 (Remux & Image)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Remux-Image",
                },
                {
                    "type": "Link",
                    "menuTitle": "素材质量检测 (QC)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Quality-Control",
                },
                {
                    "type": "Link",
                    "menuTitle": "批量与效率工具 (Batch Tools)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Batch-Tools",
                },
                {
                    "type": "Link",
                    "menuTitle": "通知设置 (Notification)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/Features-Notification",
                },
                {
                    "type": "Link",
                    "menuTitle": "常见问题 (FAQ)",
                    "url": "https://github.com/xueayi/XiaoXue-Video-Tools/wiki/FAQ",
                },
            ],
        },
        {
            "name": "主页链接",
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
    ]
