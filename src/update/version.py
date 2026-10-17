# -*- coding: utf-8 -*-
"""版本号解析与比较 (跨平台纯函数, M4.2)。

从旧 ``src/updater.py`` 原样迁出, 行为与测试保持不变:
正式版 > rc > beta > alpha; 无法解析的版本不参与升级判断。
"""

import re
from typing import Optional, Tuple

_VERSION_RE = re.compile(
    r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:-?(alpha|beta|rc)[.\-]?(\d+)?)?\s*$", re.I)
_PRE_RANK = {"": 3, "rc": 2, "beta": 1, "alpha": 0}


def parse_version(version: str) -> Optional[Tuple[int, int, int, int, int]]:
    """解析版本号为可比较元组; 无法解析返回 None。

    2.1.0 -> (2, 1, 0, 3, 0)   正式版 > rc > beta > alpha
    """
    m = _VERSION_RE.match(str(version))
    if not m:
        return None
    rank = _PRE_RANK[(m.group(4) or "").lower()]
    num = int(m.group(5)) if m.group(5) else 0
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), rank, num)


def is_newer(remote: str, local: str) -> bool:
    """远端版本是否严格更新于本地; 任一版本无法解析时返回 False。"""
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    return r > l


def is_dev_version(version: str) -> bool:
    """开发版本 (git 描述失败回退的 *-dev) 不参与静默提示。"""
    return "dev" in str(version).lower()
