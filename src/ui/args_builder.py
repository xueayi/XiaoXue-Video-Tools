# -*- coding: utf-8 -*-
"""参数构建模块：从 GUI 表单构建 argparse.Namespace 兼容对象。"""


class ArgsNamespace:
    """兼容 argparse.Namespace 的参数容器，供 executor 函数使用。"""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        items = vars(self)
        return f"ArgsNamespace({', '.join(f'{k}={v!r}' for k, v in items.items())})"

    def __contains__(self, key):
        return hasattr(self, key)
