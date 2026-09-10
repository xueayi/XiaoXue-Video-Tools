# -*- coding: utf-8 -*-
"""qtawesome 图标统一入口 —— 颜色随主题令牌联动。

主题切换后需重新调用各图标设置函数 (颜色令牌已变化)。
"""

import qtawesome as qta

from . import theme


def icon(name: str, token: str = "icon_color"):
    """按主题令牌生成图标; token 也可以是原始色值 (如 "#ffffff")。"""
    color = token if token.startswith("#") else theme.color(token)
    return qta.icon(name, color=color)


def accent(name: str):
    """强调色图标 (选中态)。"""
    return icon(name, "icon_color_accent")


def secondary(name: str):
    """次要色图标。"""
    return icon(name, "icon_color_secondary")
