# -*- coding: utf-8 -*-
"""nsfw_detect.py 覆盖测试 (注入假 imgutils 模块)。"""

import sys
import types

import pytest
from PIL import Image

import src.nsfw_detect as nsfw


# ----------------------------------------------------------------
# 假 imgutils 模块
# ----------------------------------------------------------------

def png_file(tmp_path):
    p = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), (200, 100, 100)).save(p)
    return str(p)


# ----------------------------------------------------------------
# 基础函数
# ----------------------------------------------------------------

def test_check_imgutils_with_fake(fake_imgutils):
    assert nsfw._check_imgutils() is True


def test_check_imgutils_missing(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    nsfw._imgutils_available = None
    assert nsfw._check_imgutils() is False


def test_classify_image(fake_imgutils, png_file):
    fake_imgutils["rating"] = ("explicit", 0.97)
    rating, scores = nsfw.classify_image(png_file)
    assert rating == "explicit"
    assert scores == {"explicit": 0.97}


def test_classify_image_error(fake_imgutils, png_file, monkeypatch):
    import imgutils.validate as iv

    def boom(p):
        raise RuntimeError("model error")
    monkeypatch.setattr(iv, "anime_rating", boom)
    rating, scores = nsfw.classify_image(png_file)
    assert rating == "unknown" and scores == {}


def test_classify_image_no_imgutils(png_file, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    nsfw._imgutils_available = None
    with pytest.raises(ImportError):
        nsfw.classify_image(png_file)


def test_detect_sensitive_areas(fake_imgutils, png_file):
    fake_imgutils["censors"] = [((1, 2, 30, 30), "censor", 0.8)]
    areas = nsfw.detect_sensitive_areas(png_file)
    assert areas == [((1, 2, 30, 30), "censor", 0.8)]


def test_detect_sensitive_areas_no_imgutils(png_file, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    nsfw._imgutils_available = None
    with pytest.raises(ImportError):
        nsfw.detect_sensitive_areas(png_file)


def test_should_flag():
    assert nsfw.should_flag("explicit", "questionable") is True
    assert nsfw.should_flag("general", "questionable") is False
    assert nsfw.should_flag("anything", "all") is True
    assert nsfw.should_flag("unknown-rating", "safe") is False


# ----------------------------------------------------------------
# 打码
# ----------------------------------------------------------------

def test_apply_censor_pixelate(png_file):
    img = Image.open(png_file)
    out = nsfw.apply_censor(img, [((5, 5, 25, 25), "censor", 0.9)],
                            censor_type="pixelate", block_size=4)
    assert out.size == img.size


def test_apply_censor_blur_black_emoji(png_file):
    img = Image.open(png_file)
    for ctype, bs in [("blur", 5), ("black", 3), ("emoji", 8)]:
        out = nsfw.apply_censor(img, [((2, 2, 20, 20), "x", 0.9)],
                                censor_type=ctype, block_size=bs)
        assert out.size == img.size


def test_apply_censor_expand_and_invalid_area(png_file):
    img = Image.open(png_file)
    out = nsfw.apply_censor(img, [((0, 0, 10, 10), "x", 0.9)],
                            censor_type="pixelate", expand_pixels=5)
    out2 = nsfw.apply_censor(img, [((0, 0, 0, 0), "x", 0.9)])
    assert out2.size == img.size


def test_apply_censor_custom_overlay(png_file, tmp_path):
    overlay = tmp_path / "cover.png"
    Image.new("RGBA", (10, 10), (0, 255, 0, 255)).save(overlay)
    img = Image.open(png_file)
    out = nsfw.apply_censor(img, [((2, 2, 18, 18), "x", 0.9)],
                            censor_type="custom",
                            overlay_path=str(overlay))
    assert out.size == img.size


def test_apply_censor_custom_overlay_fallback(png_file, tmp_path):
    img = Image.open(png_file)
    out = nsfw.apply_censor(img, [((2, 2, 18, 18), "x", 0.9)],
                            censor_type="custom",
                            overlay_path=str(tmp_path / "missing.png"))
    assert out.size == img.size  # 回退到马赛克


def test_image_overlay_censor_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        nsfw.ImageOverlayCensor(str(tmp_path / "no.png"))


def test_image_overlay_censor_invalid_area(png_file, tmp_path):
    overlay = tmp_path / "cover.png"
    Image.new("RGBA", (5, 5), (0, 255, 0, 255)).save(overlay)
    censor = nsfw.ImageOverlayCensor(str(overlay))
    img = Image.open(png_file)
    out = censor.censor(img, (0, 0, 0, 0))  # 无效区域 -> 原图返回
    assert out.size == img.size


def test_apply_mosaic_success(fake_imgutils, png_file, tmp_path):
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    out_path = tmp_path / "out" / "censored.png"
    assert nsfw.apply_mosaic(png_file, str(out_path)) is True
    assert out_path.exists()


def test_apply_mosaic_no_areas(fake_imgutils, png_file, tmp_path):
    fake_imgutils["censors"] = []
    assert nsfw.apply_mosaic(png_file, str(tmp_path / "o.png")) is False


def test_apply_mosaic_jpg_rgb(fake_imgutils, tmp_path):
    src = tmp_path / "p.jpg"
    Image.new("RGBA", (16, 16), (0, 0, 255, 200)).convert("RGB").save(src)
    fake_imgutils["censors"] = [((1, 1, 10, 10), "censor", 0.9)]
    out = tmp_path / "out" / "c.jpg"
    assert nsfw.apply_mosaic(str(src), str(out)) is True


def test_apply_mosaic_no_imgutils(png_file, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    nsfw._imgutils_available = None
    with pytest.raises(ImportError):
        nsfw.apply_mosaic(png_file, str(png_file) + ".out")


# ----------------------------------------------------------------
# 扫描与报告
# ----------------------------------------------------------------

def test_scan_image_safe(fake_imgutils, png_file):
    result = nsfw.scan_image(png_file, threshold="questionable")
    assert result.rating == "general"
    assert result.risk_level == "safe"
    assert result.warnings == []


def test_scan_image_flagged_no_censor(fake_imgutils, png_file):
    fake_imgutils["rating"] = ("explicit", 0.98)
    result = nsfw.scan_image(png_file, threshold="questionable")
    assert any("[风险]" in w for w in result.warnings)


def test_scan_image_flagged_with_censor(fake_imgutils, png_file, tmp_path):
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    out = tmp_path / "shield_out"
    result = nsfw.scan_image(png_file, threshold="questionable",
                             enable_censor=True, output_dir=str(out))
    assert result.censored_path
    assert any("[已打码]" in w for w in result.warnings)


def test_scan_image_flagged_no_areas(fake_imgutils, png_file):
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = []
    result = nsfw.scan_image(png_file, threshold="questionable",
                             enable_censor=True)
    assert any("未检测到" in w for w in result.warnings)


def test_scan_image_classify_error(fake_imgutils, png_file, monkeypatch):
    import imgutils.validate as iv

    def boom(p):
        raise RuntimeError("model crash")
    monkeypatch.setattr(iv, "anime_rating", boom)
    result = nsfw.scan_image(png_file)
    # classify_image 内部吞掉异常返回 unknown, 结果标记为 safe/unknown 而非 error
    assert result.rating in ("unknown", "general")


def test_scan_directory_and_files(fake_imgutils, tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    results = nsfw.scan_directory(str(tmp_path))
    assert len(results) == 1

    results2 = nsfw.scan_files([str(tmp_path / "a.png"),
                                str(tmp_path / "missing.png")])
    assert len(results2) == 1


def test_scan_directory_no_imgutils(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    nsfw._imgutils_available = None
    assert nsfw.scan_directory(str(tmp_path)) == []
    assert nsfw.scan_files([]) == []


def test_generate_report(fake_imgutils, png_file, tmp_path):
    fake_imgutils["rating"] = ("explicit", 0.98)
    result = nsfw.scan_image(png_file, threshold="safe")
    out = tmp_path / "shield.txt"
    content = nsfw.generate_report([result], str(out))
    assert out.exists()
    assert "pic.png" in content


# ----------------------------------------------------------------
# 逻辑修复回归: 规范化阈值比较 / 复用检测结果 / 防覆盖 / 失败告警
# ----------------------------------------------------------------

@pytest.mark.parametrize("rating, threshold, expect", [
    ("explicit", "questionable", True),
    ("questionable", "questionable", True),
    ("sensitive", "questionable", False),
    ("general", "sensitive", False),
    ("r15", "questionable", True),      # 同义级别: 与 questionable 同档
    ("questionable", "r15", True),      # 修复前此处误判 False (别名排序)
    ("weird-rating", "questionable", False),
    ("anything", "all", True),
])
def test_should_flag_canonical_aliases(rating, threshold, expect):
    assert nsfw.should_flag(rating, threshold) is expect


def test_apply_mosaic_reuses_detected_areas(fake_imgutils, tmp_path,
                                            monkeypatch):
    """传入 areas 时不得再次运行 censor 检测 (省一半推理)。"""
    src = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    calls = []

    def counting_detect(p):
        calls.append(p)
        return [((5, 5, 20, 20), "censor", 0.9)]
    monkeypatch.setattr(nsfw, "detect_sensitive_areas", counting_detect)

    known = [((5, 5, 20, 20), "censor", 0.9)]
    out = tmp_path / "out" / "censored.png"
    assert nsfw.apply_mosaic(str(src), str(out), areas=known) is True
    assert calls == []  # 未重复检测
    assert out.exists()


def test_scan_image_passes_areas_to_mosaic(fake_imgutils, tmp_path,
                                           monkeypatch):
    """scan_image 把已检测区域传给打码, 不触发第二次检测。"""
    src = tmp_path / "p.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    calls = []

    def counting_detect(p):
        calls.append(p)
        return [((5, 5, 20, 20), "censor", 0.9)]
    monkeypatch.setattr(nsfw, "detect_sensitive_areas", counting_detect)
    monkeypatch.setattr(nsfw, "apply_mosaic",
                        lambda *a, **k: True)  # 拦截真实打码

    result = nsfw.scan_image(str(src), threshold="questionable",
                             enable_censor=True,
                             output_dir=str(tmp_path / "out"))
    assert len(calls) == 1  # 仅 scan_image 检测一次
    assert result.warnings and "[已打码]" in result.warnings[-1]


def test_censored_filename_collision_gets_suffix(fake_imgutils, tmp_path):
    """不同来源同名文件打码后不互相覆盖。"""
    out = tmp_path / "out"
    out.mkdir()
    (out / "censored_pic.png").write_bytes(b"previous result")

    src = tmp_path / "pic.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]

    result = nsfw.scan_image(str(src), threshold="questionable",
                             enable_censor=True, output_dir=str(out))
    import os
    assert os.path.basename(result.censored_path) == "censored_pic_1.png"
    # 旧文件未被覆盖
    assert (out / "censored_pic.png").read_bytes() == b"previous result"


def test_scan_image_censor_failure_warns(fake_imgutils, tmp_path,
                                         monkeypatch):
    """打码输出失败时必须有明确告警, 报告原因才不会误标为未启用打码。"""
    src = tmp_path / "p.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    monkeypatch.setattr(nsfw, "apply_mosaic", lambda *a, **k: False)

    result = nsfw.scan_image(str(src), threshold="questionable",
                             enable_censor=True,
                             output_dir=str(tmp_path / "out"))
    assert any("[打码失败]" in w for w in result.warnings)
    assert result.censored_path == ""


def test_apply_mosaic_bare_filename_output(fake_imgutils, tmp_path,
                                           monkeypatch):
    """输出为纯文件名 (无目录成分) 时不因 makedirs("") 崩溃。"""
    src = tmp_path / "p.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(src)
    fake_imgutils["censors"] = [((2, 2, 12, 12), "censor", 0.9)]
    monkeypatch.chdir(tmp_path)
    assert nsfw.apply_mosaic(str(src), "censored_bare.png") is True
    assert (tmp_path / "censored_bare.png").exists()


def test_media_report_creates_missing_dir(tmp_path):
    from src.media_probe import DetailedMediaInfo, generate_media_report
    out = tmp_path / "deep" / "dir" / "report.txt"
    content = generate_media_report([DetailedMediaInfo(path="C:/a.mp4")],
                                    str(out))
    assert out.exists()
    assert "媒体元数据检测报告" in content
