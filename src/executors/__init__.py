# -*- coding: utf-8 -*-
"""
执行器模块包：包含所有功能执行函数。

每个执行器按功能域分组，便于独立测试和维护。
"""

from .common import print_task_header

from .video_executor import (
    execute_encode,
    execute_replace_audio,
    execute_extract_audio,
)

from .file_executor import (
    execute_remux,
    execute_image_convert,
)

from .batch_executor import (
    execute_folder_creator,
    execute_batch_rename,
)

from .qc_executor import (
    execute_qc,
)

from .misc_executor import (
    execute_notification,
    execute_help,
)

# Shield 执行器需要条件导入（依赖 imgutils）
try:
    from .shield_executor import execute_shield
    SHIELD_AVAILABLE = True
except ImportError:
    SHIELD_AVAILABLE = False
    execute_shield = None


__all__ = [
    # 共用
    "print_task_header",
    # 视频
    "execute_encode",
    "execute_replace_audio",
    "execute_extract_audio",
    # 文件
    "execute_remux",
    "execute_image_convert",
    # 批量
    "execute_folder_creator",
    "execute_batch_rename",
    # 质量检测
    "execute_qc",
    # 杂项
    "execute_notification",
    "execute_help",
    # Shield
    "execute_shield",
    "SHIELD_AVAILABLE",
]
