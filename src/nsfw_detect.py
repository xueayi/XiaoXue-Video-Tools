# -*- coding: utf-8 -*-
"""
露骨图片识别 (Shield) 模块：检测有 B 站投稿过审风险的图片，支持自动打码。
基于 dghs-imgutils 库实现。
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image

from colorama import Fore, Style

# 延迟导入 imgutils（仅在实际调用时导入，方便条件检测）
_imgutils_available = None


def _check_imgutils() -> bool:
    """检查 imgutils 是否可用。"""
    global _imgutils_available
    if _imgutils_available is None:
        try:
            from imgutils.validate import anime_rating
            _imgutils_available = True
        except ImportError:
            _imgutils_available = False
    return _imgutils_available


# 常见图片扩展名
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

# 风险等级映射（B 站过审参考）
RATING_RISK_MAP = {
    "safe": "safe",           # 安全
    "general": "safe",        # 安全（部分模型使用 general）
    "sensitive": "low",       # 低风险（轻度擦边）
    "questionable": "medium", # 中风险（R-15）
    "r15": "medium",          # 中风险（部分模型使用 r15）
    "explicit": "high",       # 高风险（R-18）
    "r18": "high",            # 高风险（部分模型使用 r18）
}

# 风险阈值顺序（用于比较）
RATING_ORDER = ["safe", "general", "sensitive", "questionable", "r15", "explicit", "r18"]


@dataclass
class NSFWResult:
    """单张图片的检测结果。"""
    path: str
    filename: str = ""
    rating: str = "unknown"
    scores: Dict[str, float] = field(default_factory=dict)
    sensitive_areas: List[Tuple] = field(default_factory=list)
    risk_level: str = "unknown"  # safe, low, medium, high
    warnings: List[str] = field(default_factory=list)
    censored_path: str = ""  # 打码后的图片路径（如有）
    
    def __post_init__(self):
        self.filename = os.path.basename(self.path)
        if self.rating in RATING_RISK_MAP:
            self.risk_level = RATING_RISK_MAP[self.rating]


def classify_image(image_path: str) -> Tuple[str, Dict[str, float]]:
    """
    对图片进行 NSFW 分类。
    
    Args:
        image_path: 图片路径。
    
    Returns:
        (rating, scores): 评级和分数（当前仅包含最高分）。
    """
    if not _check_imgutils():
        raise ImportError("imgutils 未安装，请使用 Shield 增强版")
    
    from imgutils.validate import anime_rating
    
    # imgutils 仅返回 (rating, score)
    try:
        rating, score = anime_rating(image_path)
        # 构造成字典格式，以便兼容原有逻辑
        scores = {rating: score}
        return rating, scores
    except Exception as e:
        print(f"{Fore.RED}[错误] 分类失败: {e}{Style.RESET_ALL}")
        return "unknown", {}



def detect_sensitive_areas(image_path: str) -> List[Tuple]:
    """
    检测图片中的敏感区域。
    
    Args:
        image_path: 图片路径。
    
    Returns:
        检测结果列表: [((x1, y1, x2, y2), label, confidence), ...]
    """
    if not _check_imgutils():
        raise ImportError("imgutils 未安装，请使用 Shield 增强版")
    
    from imgutils.detect.censor import detect_censors
    
    return detect_censors(image_path)


class ImageOverlayCensor:
    """自定义图片覆盖打码器。"""
    def __init__(self, overlay_path: str):
        if not os.path.exists(overlay_path):
            raise FileNotFoundError(f"覆盖图片不存在: {overlay_path}")
        self.overlay = Image.open(overlay_path).convert("RGBA")

    def censor(self, image: Image.Image, area: Tuple[int, int, int, int]) -> Image.Image:
        x1, y1, x2, y2 = area
        width, height = x2 - x1, y2 - y1
        if width <= 0 or height <= 0:
            return image
        
        # 调整覆盖图大小
        resized_overlay = self.overlay.resize((width, height))
        # 粘贴 (使用 alpha 通道作为 mask)
        image.paste(resized_overlay, (x1, y1), resized_overlay)
        return image


def apply_censor(
    image: Image.Image,
    areas: List[Tuple],
    censor_type: str = "pixelate",
    block_size: int = 16,
    overlay_path: str = "",
    expand_pixels: int = 0
) -> Image.Image:
    """
    手动应用打码逻辑。
    
    Args:
        image: PIL Image 对象 (将被修改)。
        areas: 敏感区域列表 [((x1, y1, x2, y2), label, confidence), ...]
        censor_type: 打码类型 (pixelate/blur/black/emoji/custom).
        block_size: 马赛克大小 或 模糊半径。
        overlay_path: 自定义覆盖图片路径 (censor_type='custom' 时需要)。
        expand_pixels: 扩展打码范围 (像素)，向外扩展检测到的敏感区域。
    
    Returns:
        处理后的 Image 对象。
    """
    from PIL import ImageFilter, ImageDraw
    
    img = image.copy()
    draw = ImageDraw.Draw(img)
    
    # 准备自定义打码器
    overlay_censor = None
    if censor_type == "custom" and overlay_path:
        try:
            overlay_censor = ImageOverlayCensor(overlay_path)
        except Exception as e:
            print(f"{Fore.YELLOW}[警告] 加载覆盖图片失败: {e}，将回退到马赛克模式{Style.RESET_ALL}")
            censor_type = "pixelate"

    for area_info in areas:
        # 提取坐标 (格式: (box, label, score))
        box = area_info[0]
        x1, y1, x2, y2 = map(int, box)
        
        # 应用区域扩展
        if expand_pixels > 0:
            img_width, img_height = img.size
            x1 = max(0, x1 - expand_pixels)
            y1 = max(0, y1 - expand_pixels)
            x2 = min(img_width, x2 + expand_pixels)
            y2 = min(img_height, y2 + expand_pixels)
        
        width = x2 - x1
        height = y2 - y1
        
        if width <= 0 or height <= 0:
            continue
            
        region = (x1, y1, x2, y2)
        
        if censor_type == "pixelate":
            # 马赛克
            # 1. 缩小
            small_w = max(1, width // block_size)
            small_h = max(1, height // block_size)
            small_img = img.crop(region).resize((small_w, small_h), resample=Image.NEAREST)
            # 2. 放大回原尺寸
            pixelated_area = small_img.resize((width, height), resample=Image.NEAREST)
            img.paste(pixelated_area, region)
            
        elif censor_type == "blur":
            # 高斯模糊
            cropped = img.crop(region)
            blurred = cropped.filter(ImageFilter.GaussianBlur(radius=block_size))
            img.paste(blurred, region)
            
        elif censor_type == "black":
            # 黑色遮盖 (block_size 控制圆角大小，0=无圆角)
            corner_radius = block_size
            if corner_radius > 0 and corner_radius < min(width, height) // 2:
                # 绘制圆角矩形
                draw.rounded_rectangle(region, radius=corner_radius, fill="black")
            else:
                draw.rectangle(region, fill="black")
            
        elif censor_type == "custom" and overlay_censor:
            # 自定义图片覆盖
            img = overlay_censor.censor(img, region)
            # 重新获取 draw 对象因为 img 可能被修改（虽然这里我们是原地修改，但保险起见）
            draw = ImageDraw.Draw(img)
            
        elif censor_type == "emoji":
            # 表情覆盖 (block_size 控制内部元素大小比例)
            # 用黄色圆圈代替，因为绘制真实 emoji 需要字体支持
            draw.ellipse(region, fill="yellow")
            # 绘制简单的笑脸
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            r = min(width, height) // 2
            # 眼睛 (block_size 控制眼睛大小比例，越大眼睛越大)
            eye_scale = max(3, min(10, block_size // 2))  # 限制 3-10 范围
            eye_r = r // eye_scale
            draw.ellipse((cx - r//3, cy - r//3, cx - r//3 + eye_r, cy - r//3 + eye_r), fill="black")
            draw.ellipse((cx + r//3 - eye_r, cy - r//3, cx + r//3, cy - r//3 + eye_r), fill="black")
            # 嘴巴 (简单的弧线 tricky, 用直线代替)
            draw.line((cx - r//3, cy + r//3, cx + r//3, cy + r//3), fill="black", width=max(1, r//10))

    return img


def apply_mosaic(
    image_path: str, 
    output_path: str, 
    block_size: int = 16,
    censor_type: str = "pixelate",
    overlay_path: str = "",
    expand_pixels: int = 0
) -> bool:
    """
    对图片的敏感区域应用打码 (入口函数)。
    """
    if not _check_imgutils():
        raise ImportError("imgutils 未安装，请使用 Shield 增强版")
        
    try:
        # 1. 检测敏感区域
        areas = detect_sensitive_areas(image_path)
        if not areas:
            return False
            
        # 2. 加载图片
        image = Image.open(image_path)
        
        # 3. 应用打码
        censored_img = apply_censor(
            image, 
            areas, 
            censor_type=censor_type, 
            block_size=block_size,
            overlay_path=overlay_path,
            expand_pixels=expand_pixels
        )
        
        # 4. 保存
        input_ext = os.path.splitext(image_path)[1].lower()
        if input_ext in (".jpg", ".jpeg"):
            # JPEG 不支持 RGBA，需转为 RGB
            if censored_img.mode == "RGBA":
                censored_img = censored_img.convert("RGB")
                
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        censored_img.save(output_path)
        return True
        
    except Exception as e:
        print(f"{Fore.RED}[错误] 打码失败: {image_path} - {e}{Style.RESET_ALL}")
        return False


def should_flag(rating: str, threshold: str) -> bool:
    """
    判断是否应该标记为风险图片。
    
    Args:
        rating: 图片评级。
        threshold: 阈值（达到此级别及以上标记）。
    
    Returns:
        是否标记。
    """
    if threshold == "all":
        return True
    
    try:
        rating_idx = RATING_ORDER.index(rating)
        threshold_idx = RATING_ORDER.index(threshold)
        return rating_idx >= threshold_idx
    except ValueError:
        return False


def scan_image(
    image_path: str,
    threshold: str = "questionable",
    enable_censor: bool = False,
    output_dir: str = "",
    censor_type: str = "pixelate",
    mosaic_size: int = 16,
    overlay_path: str = "",
    expand_pixels: int = 0
) -> NSFWResult:
    """
    扫描单张图片。
    
    Args:
        image_path: 图片路径。
        threshold: 风险阈值。
        enable_censor: 是否打码。
        output_dir: 打码图片输出目录。
        censor_type: 打码类型。
        mosaic_size: 马赛克大小。
        overlay_path: 覆盖图片路径。
    
    Returns:
        NSFWResult 对象。
    """
    result = NSFWResult(path=image_path)
    
    try:
        # 1. 分类检测
        rating, scores = classify_image(image_path)
        result.rating = rating
        result.scores = scores
        result.risk_level = RATING_RISK_MAP.get(rating, "unknown")
        
        # 2. 判断是否需要标记
        if should_flag(rating, threshold):
            result.warnings.append(f"[风险] 评级 {rating} 达到阈值 {threshold}")
            
            # 3. 检测敏感区域（如果需要打码）
            if enable_censor:
                areas = detect_sensitive_areas(image_path)
                result.sensitive_areas = areas
                
                if areas:
                    # 生成打码图片
                    if not output_dir:
                        output_dir = os.path.join(os.path.dirname(image_path), "shield_output")
                    
                    censored_filename = f"censored_{result.filename}"
                    censored_path = os.path.join(output_dir, censored_filename)
                    
                    if apply_mosaic(image_path, censored_path, mosaic_size, censor_type, overlay_path, expand_pixels):
                        result.censored_path = censored_path
                        result.warnings.append(f"[已打码] 检测到 {len(areas)} 个敏感区域")
                else:
                    result.warnings.append("[提示] 未检测到需要打码的区域")
                    
    except Exception as e:
        result.warnings.append(f"[错误] 检测失败: {str(e)}")
        result.risk_level = "error"
    
    return result


def scan_directory(
    directory: str,
    threshold: str = "questionable",
    recursive: bool = True,
    enable_censor: bool = False,
    output_dir: str = "",
    censor_type: str = "pixelate",
    mosaic_size: int = 16,
    overlay_path: str = "",
    expand_pixels: int = 0
) -> List[NSFWResult]:
    """
    递归扫描目录下的图片。
    
    Args:
        directory: 目标目录。
        threshold: 风险阈值。
        recursive: 是否递归扫描。
        enable_censor: 是否打码。
        output_dir: 输出目录。
        censor_type: 打码类型。
        mosaic_size: 马赛克大小。
        overlay_path: 覆盖图片路径。
    
    Returns:
        NSFWResult 列表。
    """
    if not _check_imgutils():
        print(f"{Fore.RED}[错误] imgutils 未安装，请使用 Shield 增强版{Style.RESET_ALL}")
        return []
    
    results = []
    
    print(f"{Fore.CYAN}[小雪工具箱] 开始扫描目录: {directory}{Style.RESET_ALL}")
    print(f"  风险阈值: {threshold}")
    print(f"  自动打码: {'是' if enable_censor else '否'}")
    
    # 遍历文件
    if recursive:
        walker = os.walk(directory)
    else:
        walker = [(directory, [], os.listdir(directory))]
    
    for root, dirs, files in walker:
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                file_path = os.path.join(root, filename)
                print(f"  扫描: {file_path}")
                
                result = scan_image(
                    file_path,
                    threshold=threshold,
                    enable_censor=enable_censor,
                    output_dir=output_dir,
                    censor_type=censor_type,
                    mosaic_size=mosaic_size,
                    overlay_path=overlay_path,
                    expand_pixels=expand_pixels,
                )
                results.append(result)
                
                # 实时显示风险图片
                if result.risk_level in ("medium", "high"):
                    print(f"    {Fore.YELLOW}⚠ {result.rating} ({result.risk_level}){Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}[完成] 共扫描 {len(results)} 张图片{Style.RESET_ALL}")
    return results


def scan_files(
    file_paths: List[str],
    threshold: str = "questionable",
    enable_censor: bool = False,
    output_dir: str = "",
    censor_type: str = "pixelate",
    mosaic_size: int = 16,
    overlay_path: str = "",
    expand_pixels: int = 0
) -> List[NSFWResult]:
    """
    扫描指定的图片文件列表。
    
    Args:
        file_paths: 图片文件路径列表。
        其他参数同 scan_directory。
    
    Returns:
        NSFWResult 列表。
    """
    if not _check_imgutils():
        print(f"{Fore.RED}[错误] imgutils 未安装，请使用 Shield 增强版{Style.RESET_ALL}")
        return []
    
    results = []
    
    print(f"{Fore.CYAN}[小雪工具箱] 开始扫描 {len(file_paths)} 个文件{Style.RESET_ALL}")
    
    for file_path in file_paths:
        if not os.path.isfile(file_path):
            continue
            
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
            
        print(f"  扫描: {file_path}")
        
        result = scan_image(
            file_path,
            threshold=threshold,
            enable_censor=enable_censor,
            output_dir=output_dir,
            censor_type=censor_type,
            mosaic_size=mosaic_size,
            overlay_path=overlay_path,
            expand_pixels=expand_pixels,
        )
        results.append(result)
        
        if result.risk_level in ("medium", "high"):
            print(f"    {Fore.YELLOW}⚠ {result.rating} ({result.risk_level}){Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}[完成] 共扫描 {len(results)} 张图片{Style.RESET_ALL}")
    return results


def generate_report(results: List[NSFWResult], output_path: str) -> str:
    """
    生成检测报告 (TXT 格式)。
    
    Args:
        results: NSFWResult 列表。
        output_path: 报告输出路径。
    
    Returns:
        报告内容字符串。
    """
    lines = []
    lines.append("=" * 60)
    lines.append("小雪工具箱 - 露骨图片识别报告 (Shield Report)")
    lines.append("=" * 60)
    lines.append("")
    
    # 统计
    total = len(results)
    high_risk = sum(1 for r in results if r.risk_level == "high")
    medium_risk = sum(1 for r in results if r.risk_level == "medium")
    low_risk = sum(1 for r in results if r.risk_level == "low")
    safe_count = sum(1 for r in results if r.risk_level == "safe")
    # 统计其他状态
    error_count = sum(1 for r in results if r.risk_level == "error")
    unknown_count = sum(1 for r in results if r.risk_level == "unknown")
    
    censored_count = sum(1 for r in results if r.censored_path)
    
    # 1. 打印统计结果
    lines.append(f"总计扫描: {total} 张图片")
    lines.append(f"  ✓ 安全: {safe_count}")
    lines.append(f"  △ 低风险 (sensitive): {low_risk}")
    lines.append(f"  ⚠ 中风险 (questionable): {medium_risk}")
    lines.append(f"  ✗ 高风险 (explicit): {high_risk}")
    
    if error_count > 0:
        lines.append(f"  ! 错误: {error_count}")
    
    if censored_count:
        lines.append(f"  🔲 已处理 (打码): {censored_count}")
    lines.append("")
    lines.append("-" * 60)
    
    # 2. 打印所有图片的扫描情况
    lines.append("\n【所有图片检测详情】\n")
    for r in results:
        # 图标
        if r.risk_level == "high":
            icon = "✗"
        elif r.risk_level == "medium":
            icon = "⚠"
        elif r.risk_level == "low":
            icon = "△"
        elif r.risk_level == "safe":
            icon = "✓"
        elif r.risk_level == "error":
            icon = "!"
        else:
            icon = "?"
            
        lines.append(f"[{icon}] {r.filename}")
        lines.append(f"     评级: {r.rating} ({r.risk_level})")
        # 分数
        if r.scores:
            scores_str = ", ".join([f"{k}: {v:.2%}" for k, v in r.scores.items()])
            lines.append(f"     分数: {scores_str}")
        
        # 错误信息
        for warn in r.warnings:
            # 过滤掉非错误的提示，避免混淆
            if "[错误]" in warn:
                 lines.append(f"     错误: {warn}")
        lines.append("")

    lines.append("-" * 60)

    # 3. 打印处理情况 (已处理列表)
    censored_list = [r for r in results if r.censored_path]
    uncensored_risk_list = [r for r in results if not r.censored_path and r.risk_level in ("low", "medium", "high")]
    
    if censored_list:
        lines.append("\n【已打码处理】\n")
        for r in censored_list:
            # 风险图标
            if r.risk_level == "high":
                risk_icon = "✗"
            elif r.risk_level == "medium":
                risk_icon = "⚠"
            elif r.risk_level == "low":
                risk_icon = "△"
            else:
                risk_icon = "-"
            
            area_count = len(r.sensitive_areas) if r.sensitive_areas else 0
            
            lines.append(f"[✓] {r.filename}")
            lines.append(f"     风险状态: [{risk_icon}] {r.rating} ({r.risk_level})")
            lines.append(f"     敏感区域: 检测到 {area_count} 个")
            lines.append(f"     打码状态: ✓ 已处理")
            lines.append(f"     输出文件: {r.censored_path}")
            lines.append("")
    
    if uncensored_risk_list:
        lines.append("\n【风险图片 (未处理)】\n")
        for r in uncensored_risk_list:
            lines.append(f"[!] {r.filename}")
            if any("未检测到" in w for w in r.warnings):
                lines.append(f"     原因: 未检测到敏感区域 (虽然评级为风险)")
            elif any("打码失败" in w for w in r.warnings):
                lines.append(f"     原因: 打码失败 (请查看详细日志)")
            else:
                lines.append(f"     原因: 未启用自动打码")
            lines.append("")
    
    lines.append("=" * 60)
    lines.append("报告生成完毕")
    lines.append("=" * 60)
    
    report_content = "\n".join(lines)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print(f"{Fore.GREEN}[成功] 报告已保存到: {output_path}{Style.RESET_ALL}")
    return report_content
