# -*- coding: utf-8 -*-
"""
版本号模块。

构建时由 CI 注入实际版本号 (替换 _FALLBACK)。
开发时自动从 git tag 读取；两者都没有时使用 _FALLBACK。
"""
import subprocess

_FALLBACK = "2.0.0-dev"


def _git_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out.lstrip("v") if out else ""
    except Exception:
        return ""


# CI 构建时，此行会被替换为:  __version__ = "2.0.0"
__version__: str = _git_version() or _FALLBACK
