# -*- coding: utf-8 -*-
"""
日志工具模块
负责初始化日志系统、修复 Windows/PyInstaller 环境下的 IO 问题。

M4.1 起日志目录由 :mod:`src.platform.paths` 统一解析: Windows 便携布局
沿用安装目录 (与旧版本一致), 安装目录不可写时回退用户日志目录; 若日志
文件仍无法创建, 则逐级回退到临时目录/仅控制台, 绝不让启动因日志失败而
崩溃。
"""
import sys
import os
import logging
import tempfile
from logging.handlers import RotatingFileHandler

from .platform.paths import resolve_log_dir

# 日志文件名称
LOG_FILENAME = "xiaoxue_toolbox.log"


def get_log_dir() -> str:
    """获取日志存储目录 (PlatformPaths 规则的单目录便捷版)。"""
    try:
        return str(resolve_log_dir())
    except Exception:  # 最终兜底: 保持旧语义, 绝不让日志初始化崩溃
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build_file_handler(formatter):
    """创建滚动文件 handler; 目录不可写时逐级回退。

    Returns:
        (handler 或 None, 实际使用的目录或 None, 首选目录或 None)
    """
    candidates = [get_log_dir(), tempfile.gettempdir()]
    seen = set()
    first = candidates[0]
    for directory in candidates:
        if not directory or directory in seen:
            continue
        seen.add(directory)
        try:
            os.makedirs(directory, exist_ok=True)
            handler = RotatingFileHandler(
                os.path.join(directory, LOG_FILENAME),
                mode='a', maxBytes=2 * 1024 * 1024, backupCount=1,
                encoding='utf-8',
            )
        except (OSError, ValueError):
            continue
        handler.setFormatter(formatter)
        return handler, directory, first
    return None, None, first


def fix_sys_io(logger: logging.Logger):
    """
    修复 PyInstaller 无窗口模式下的 stdout/stderr。
    如果不修复，Gooey 无法捕获输出，且打印特殊字符时可能崩溃。
    """
    # 1. 尝试恢复 stdout (FD 1)
    if sys.stdout is None:
        try:
            # 即使 PyInstaller 置空了 sys.stdout，底层 FD 1 通常还连接着父进程
            # 强制 utf-8 编码以支持中文
            sys.stdout = os.fdopen(1, 'w', encoding='utf-8', buffering=1)
            logger.info("Successfully checked/attached sys.stdout to FD 1 (utf-8)")
        except Exception as e:
            # 确实无法连接，回退到 devnull
            logger.warning(f"Failed to attach FD 1: {e}")
            sys.stdout = open(os.devnull, 'w', encoding='utf-8')

    # 2. 尝试恢复 stderr (FD 2)
    if sys.stderr is None:
        try:
            sys.stderr = os.fdopen(2, 'w', encoding='utf-8', buffering=1)
            logger.info("Successfully checked/attached sys.stderr to FD 2 (utf-8)")
        except Exception as e:
            logger.warning(f"Failed to attach FD 2: {e}")
            sys.stderr = open(os.devnull, 'w', encoding='utf-8')

    # 3. 即使对象存在，也尝试强制重配置编码为 UTF-8
    # 解决 Windows 默认 GBK 导致 "\u2713" 等符号 崩溃的问题
    for stream_name, stream in [('stdout', sys.stdout), ('stderr', sys.stderr)]:
        try:
            if stream and hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
                logger.info(f"Reconfigured sys.{stream_name} to utf-8")
        except Exception as e:
            logger.debug(f"Could not reconfigure sys.{stream_name}: {e}")


def setup_logging():
    """初始化日志系统 (日志文件失败时降级为仅控制台, 绝不抛异常)。"""
    # 创建 logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 清除旧的 handlers (避免重复添加)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 格式化
    # 区分 Main 还是 Child 进程 (通过 sys.argv判断)
    is_child = '--ignore-gooey-kwarg-ref' in sys.argv or 'gooey-seed-config' in str(sys.argv)
    proc_mark = "[CHILD]" if is_child else "[MAIN]"
    
    formatter = logging.Formatter(
        fmt=f'%(asctime)s %(levelname)s {proc_mark} %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. 文件输出 (Rolling, Max 2MB, Backup 1); 不可写时回退临时目录
    file_handler, used_dir, wanted_dir = _build_file_handler(formatter)
    if file_handler is not None:
        logger.addHandler(file_handler)
        if used_dir != wanted_dir:
            _warn_once(
                f"[日志] 日志目录不可写, 已回退到临时目录: {used_dir}")
    else:
        _warn_once("[日志] 无法创建日志文件, 本次仅输出到控制台")

    # 2. 控制台输出 (如果是开发环境或有控制台)
    # 注意：Gooey 会捕获 stdout，所以只要 print/logging 写入 stdout 即可
    # 但我们不通过 Logger 写入 stdout，因为业务逻辑主要靠 print 传递给 Gooey
    # Logger 主要用于记录"后台"发生的事件到文件。
    # 
    # 如果希望 logger.info 也显示在 GUI 面板，则添加 StreamHandler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 执行 IO 修复
    # 先把基础日志系统搭好，再修复 IO，这样修复过程中的 info 能记下来
    fix_sys_io(logger)

    logger.info("=" * 30)
    logger.info(f"XiaoXue Toolbox Started. Ver: {sys.version}")
    logger.info(f"Executable: {sys.executable}")
    
    return logger


_warned_once = False


def _warn_once(message: str):
    """日志降级警告只打印一次 (避免多 handler/重复初始化刷屏)。"""
    global _warned_once
    if _warned_once:
        return
    _warned_once = True
    try:
        print(message, file=sys.stderr or sys.stdout)
    except Exception:
        pass
