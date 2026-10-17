# -*- coding: utf-8 -*-
"""FFmpeg 领域模型 (M2.5)。

导出错误分类能力：

    * :class:`ErrorCategory` —— 8 类用户可感知错误；
    * :class:`UserFacingError` —— 可直接展示的错误信息；
    * :func:`classify` —— 从 stderr 尾部 / 退出码 / 取消标志归类。

本包纯 Python，不依赖 Qt；UI 层 (``src.ui.error_card``) 只做展示模型转换。
"""

from .errors import ErrorCategory, UserFacingError, classify

__all__ = [
    "ErrorCategory",
    "UserFacingError",
    "classify",
]
