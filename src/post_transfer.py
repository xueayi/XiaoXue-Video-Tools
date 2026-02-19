# -*- coding: utf-8 -*-
"""
压制后文件分发模块：将成品文件复制或移动到指定目录。

配合 WebDAV、SMB 等网络位置挂载方式，可变相实现自动上传成品。
"""
import os
import shutil

from colorama import Fore, Style


def transfer_file(
    source: str,
    target_dir: str,
    mode: str = "copy",
) -> str:
    """
    将文件复制或移动到目标目录。

    Args:
        source: 源文件路径
        target_dir: 目标目录路径
        mode: 分发模式 ("copy" 或 "move")

    Returns:
        目标文件路径

    Raises:
        FileNotFoundError: 源文件不存在
        ValueError: 无效的分发模式
    """
    if not os.path.isfile(source):
        raise FileNotFoundError(f"源文件不存在: {source}")

    if mode not in ("copy", "move"):
        raise ValueError(f"无效的分发模式: {mode}")

    # 自动创建目标目录
    os.makedirs(target_dir, exist_ok=True)

    filename = os.path.basename(source)
    target_path = os.path.join(target_dir, filename)

    # 避免覆盖已有文件
    if os.path.exists(target_path):
        base, ext = os.path.splitext(target_path)
        counter = 1
        while os.path.exists(target_path):
            target_path = f"{base}_{counter}{ext}"
            counter += 1

    if mode == "copy":
        shutil.copy2(source, target_path)
        op = "复制"
    else:
        shutil.move(source, target_path)
        op = "移动"

    print(f"{Fore.GREEN}[分发]{Style.RESET_ALL} 已{op}成品到: {target_path}")
    return target_path
