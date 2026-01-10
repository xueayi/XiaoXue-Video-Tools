# -*- coding: utf-8 -*-
"""
批量创建文件夹模块：从 TXT 文件读取文件夹名并批量创建。
"""
import os
import re
from typing import List, Tuple

from colorama import Fore, Style

try:
    import chardet
except ImportError:
    chardet = None


# Windows 文件名非法字符
ILLEGAL_CHARS = r'[\\/:*?"<>|]'


def detect_encoding(file_path: str) -> str:
    """
    检测文本文件编码。

    Args:
        file_path: 文件路径

    Returns:
        检测到的编码名称
    """
    # 如果有 chardet 库，使用它检测
    if chardet:
        with open(file_path, "rb") as f:
            raw_data = f.read()
        result = chardet.detect(raw_data)
        encoding = result.get("encoding", "utf-8")
        confidence = result.get("confidence", 0)
        print(f"[编码检测] {encoding} (置信度: {confidence:.1%})")
        return encoding

    # 回退方案：尝试常见编码
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "utf-16"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                f.read()
            print(f"[编码检测] 使用 {enc}")
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # 最后回退到 utf-8
    return "utf-8"


def sanitize_folder_name(name: str) -> str:
    """
    清理文件夹名称，将非法字符替换为下划线。

    Args:
        name: 原始名称

    Returns:
        清理后的名称
    """
    # 移除首尾空白
    name = name.strip()
    
    # 替换非法字符为下划线
    name = re.sub(ILLEGAL_CHARS, "_", name)
    
    # 替换连续的下划线为单个
    name = re.sub(r"_+", "_", name)
    
    # 移除首尾下划线
    name = name.strip("_")
    
    # 如果名称为空，返回默认值
    if not name:
        return "untitled"
    
    return name


def read_folder_names_from_txt(txt_path: str) -> List[str]:
    """
    从 TXT 文件读取文件夹名称列表。

    Args:
        txt_path: TXT 文件路径

    Returns:
        文件夹名称列表
    """
    encoding = detect_encoding(txt_path)
    
    with open(txt_path, "r", encoding=encoding) as f:
        lines = f.readlines()
    
    # 过滤空行，清理并去重
    names = []
    seen = set()
    for line in lines:
        name = sanitize_folder_name(line)
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    
    return names


def batch_create_folders(
    txt_path: str,
    output_dir: str,
    auto_number: bool = True,
) -> Tuple[int, int, List[str]]:
    """
    批量创建文件夹。

    Args:
        txt_path: TXT 文件路径
        output_dir: 输出目录
        auto_number: 是否自动添加序号前缀

    Returns:
        (成功数, 失败数, 错误消息列表)
    """
    print(f"\n{Fore.CYAN}[批量创建文件夹]{Style.RESET_ALL}")
    print(f"TXT 文件: {txt_path}")
    print(f"输出目录: {output_dir}")
    print(f"自动排序: {'是' if auto_number else '否'}")
    print("-" * 50)

    # 读取文件夹名称
    try:
        names = read_folder_names_from_txt(txt_path)
    except Exception as e:
        return 0, 1, [f"读取 TXT 文件失败: {str(e)}"]

    if not names:
        print(f"{Fore.YELLOW}[警告] TXT 文件为空或无有效内容{Style.RESET_ALL}")
        return 0, 0, []

    print(f"读取到 {len(names)} 个有效文件夹名")
    print("-" * 50)

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    success_count = 0
    fail_count = 0
    errors = []

    for i, name in enumerate(names, 1):
        # 添加序号前缀
        if auto_number:
            folder_name = f"{i}_{name}"
        else:
            folder_name = name

        folder_path = os.path.join(output_dir, folder_name)

        try:
            os.makedirs(folder_path, exist_ok=True)
            print(f"{Fore.GREEN}[创建成功]{Style.RESET_ALL} {folder_name}")
            success_count += 1
        except Exception as e:
            print(f"{Fore.RED}[创建失败]{Style.RESET_ALL} {folder_name}: {e}")
            fail_count += 1
            errors.append(f"{folder_name}: {str(e)}")

    print("-" * 50)
    print(f"完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    return success_count, fail_count, errors
