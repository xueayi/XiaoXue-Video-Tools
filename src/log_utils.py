# -*- coding: utf-8 -*-
"""
日志工具模块
负责初始化日志系统、修复 Windows/PyInstaller 环境下的 IO 问题。
"""
import sys
import os
import logging
import datetime
from logging.handlers import RotatingFileHandler

# 日志文件名称
LOG_FILENAME = "xiaoxue_toolbox.log"


def get_log_dir() -> str:
    """获取日志存储目录"""
    if getattr(sys, 'frozen', False):
        # EXE 模式：存在 exe 同级目录
        return os.path.dirname(sys.executable)
    else:
        # 开发模式：存在项目根目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    """初始化日志系统"""
    log_dir = get_log_dir()
    log_path = os.path.join(log_dir, LOG_FILENAME)

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

    # 1. 文件输出 (Rolling, Max 2MB, Backup 1)
    file_handler = RotatingFileHandler(
        log_path, mode='a', maxBytes=2*1024*1024, backupCount=1, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

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
