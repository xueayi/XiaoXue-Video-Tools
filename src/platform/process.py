# -*- coding: utf-8 -*-
"""子进程平台参数 (M4.1)。

统一 ``subprocess`` 的平台差异, 避免各处散落
``subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0``:

* Windows: 无控制台窗口启动子进程, 防止打包后 (console=False) 调 ffmpeg
  时弹出黑窗口; 非 Windows 该常量为 0 / 不存在。
"""

import os
import subprocess

#: Windows 隐藏控制台窗口标志; 非 Windows 平台为 0
CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
)


def no_window_kwargs() -> dict:
    """返回 ``subprocess.Popen/run`` 的平台参数。

    Windows 下返回 ``{"creationflags": CREATE_NO_WINDOW}``,
    其它平台返回空 dict (可直接 ``**no_window_kwargs()`` 展开)。
    """
    if os.name == "nt" and CREATE_NO_WINDOW:
        return {"creationflags": CREATE_NO_WINDOW}
    return {}
