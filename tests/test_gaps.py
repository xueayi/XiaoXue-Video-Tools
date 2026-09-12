# -*- coding: utf-8 -*-
"""覆盖率最终补缺: import 守卫、编码回退、报告分支、扫描边界。"""

import builtins
import importlib

import pytest
from PIL import Image

import src.folder_creator as fc
import src.image_converter as ic
import src.nsfw_detect as nsfw
from src.nsfw_detect import NSFWResult


# ----------------------------------------------------------------
# image_converter: Pillow 缺失守卫与分支
# ----------------------------------------------------------------

def test_pillow_unavailable_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "Image", None)
    assert ic.check_pillow_available() is False
    ok, msg = ic.convert_image(str(tmp_path / "a.png"), str(tmp_path / "b.png"))
    assert ok is False and "Pillow" in msg
    ok2, fail2, skip2, errors = ic.batch_convert_images(
        [str(tmp_path / "a.png")], None, ".jpg")
    assert ok2 == 0 and fail2 == 1 and "Pillow" in errors[0]


def make_png(tmp_path, name):
    p = tmp_path / name
    Image.new("RGB", (4, 4), (1, 2, 3)).save(p)
    return p


def test_convert_palette_mode(tmp_path):
    src = tmp_path / "p.gif"
    Image.new("P", (8, 8)).save(src)
    ok, _ = ic.convert_image(str(src), str(tmp_path / "p.png"))
    assert ok


def test_convert_flatten_palette_to_jpg(tmp_path):
    src = tmp_path / "pal.gif"
    Image.new("P", (8, 8)).save(src)
    ok, _ = ic.convert_image(str(src), str(tmp_path / "pal.jpg"))
    assert ok


def test_batch_convert_no_dot_extension(tmp_path):
    src = make_png(tmp_path, "x.png")
    ok, fail, skip, _ = ic.batch_convert_images([str(src)], None, "jpg")
    assert ok == 1  # "jpg" 自动补点, .jpg 与 .jpeg 归一化


def test_batch_convert_output_dir_none(tmp_path):
    src = make_png(tmp_path, "y.png")
    ok, fail, skip, _ = ic.batch_convert_images([str(src)], None, ".bmp")
    assert ok == 1 and (tmp_path / "y.bmp").exists()


def test_batch_convert_same_path_gets_suffix(tmp_path):
    src = make_png(tmp_path, "same.png")
    ok, fail, skip, _ = ic.batch_convert_images(
        [str(src)], None, ".png", skip_same_format=False)
    assert ok == 1
    assert (tmp_path / "same_converted.png").exists()


def test_batch_convert_fail_branch(tmp_path):
    missing = str(tmp_path / "ghost.png")
    ok, fail, skip, errors = ic.batch_convert_images(
        [missing], None, ".jpg", skip_same_format=False)
    assert ok == 0 and fail == 1 and errors


def test_image_converter_pillow_import_guard(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    importlib.reload(ic)
    assert ic.Image is None
    monkeypatch.undo()
    importlib.reload(ic)
    assert ic.Image is not None


# ----------------------------------------------------------------
# folder_creator: 编码回退、导入守卫、创建失败
# ----------------------------------------------------------------

def test_detect_encoding_fallback_gbk(monkeypatch, tmp_path):
    f = tmp_path / "gbk.txt"
    f.write_bytes("动漫音乐".encode("gbk"))
    monkeypatch.setattr(fc, "chardet", None)
    assert fc.detect_encoding(str(f)) == "gbk"


def test_batch_create_folder_failure_branch(monkeypatch, tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "1_动漫").write_text("同名文件占位", encoding="utf-8")

    real_makedirs = fc.os.makedirs

    def fake_makedirs(path, exist_ok=False):
        if "动漫" in str(path):
            raise FileExistsError(path)
        return real_makedirs(path, exist_ok=exist_ok)
    monkeypatch.setattr(fc.os, "makedirs", fake_makedirs)
    ok, fail, errors = fc.batch_create_folders(str(txt), str(out), True)
    assert ok == 0 and fail == 1 and errors


def test_folder_creator_chardet_import_guard(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "chardet":
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    importlib.reload(fc)
    assert fc.chardet is None
    monkeypatch.undo()
    importlib.reload(fc)
    assert fc.chardet is not None


# ----------------------------------------------------------------
# shield_executor: imgutils 导入守卫
# ----------------------------------------------------------------

def test_shield_import_guard(monkeypatch):
    import src.executors.shield_executor as shield_ex
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("imgutils"):
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    importlib.reload(shield_ex)
    assert shield_ex.SHIELD_AVAILABLE is False
    monkeypatch.undo()
    importlib.reload(shield_ex)
    assert shield_ex.SHIELD_AVAILABLE is True


# ----------------------------------------------------------------
# nsfw_detect 剩余分支
# ----------------------------------------------------------------

def make_image(tmp_path, name="img.png"):
    p = tmp_path / name
    Image.new("RGB", (32, 32), (10, 20, 30)).save(p)
    return str(p)


def test_nsfw_result_risk_level_mapping():
    r = NSFWResult(path="C:/x.png", rating="explicit")
    assert r.risk_level == "high"


def test_apply_censor_black_rectangle(tmp_path):
    p = tmp_path / "b.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(p)
    img = Image.open(str(p))
    out = nsfw.apply_censor(img, [((2, 2, 30, 30), "x", 0.9)],
                            censor_type="black", block_size=0)
    assert out.size == img.size


def test_apply_mosaic_detect_raises(fake_imgutils, tmp_path):
    src = make_image(tmp_path)

    def boom(p):
        raise RuntimeError("detect boom")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(nsfw, "detect_sensitive_areas", boom)
    try:
        assert nsfw.apply_mosaic(src, str(tmp_path / "o.png")) is False
    finally:
        monkey.undo()


def test_scan_image_censor_default_output_dir(fake_imgutils, tmp_path):
    src = make_image(tmp_path)
    fake_imgutils["rating"] = ("explicit", 0.98)
    fake_imgutils["censors"] = [((5, 5, 20, 20), "censor", 0.9)]
    result = nsfw.scan_image(src, threshold="safe", enable_censor=True,
                             output_dir="")
    assert result.censored_path


def test_scan_image_detect_areas_raises(fake_imgutils, tmp_path):
    src = make_image(tmp_path)
    fake_imgutils["rating"] = ("explicit", 0.98)

    def boom(p):
        raise RuntimeError("boom")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(nsfw, "detect_sensitive_areas", boom)
    try:
        result = nsfw.scan_image(src, threshold="safe", enable_censor=True)
        assert result.risk_level == "error"
    finally:
        monkey.undo()


def test_scan_directory_non_recursive_high(fake_imgutils, tmp_path):
    make_image(tmp_path, "a.png")
    fake_imgutils["rating"] = ("explicit", 0.98)
    results = nsfw.scan_directory(str(tmp_path), recursive=False,
                                  threshold="questionable")
    assert results and results[0].risk_level == "high"


def test_scan_files_skip_wrong_ext(fake_imgutils, tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    results = nsfw.scan_files([str(tmp_path / "a.png"),
                               str(tmp_path / "b.txt")])
    assert len(results) == 1


def test_generate_report_all_sections(tmp_path):
    r_medium = NSFWResult(path="C:/m.png", rating="sensitive")
    r_high_censored = NSFWResult(path="C:/c.png", rating="explicit",
                                 censored_path="C:/censored_c.png",
                                 sensitive_areas=[((0, 0, 1, 1), "x", 0.9)])
    r_flagged_no_area = NSFWResult(path="C:/n.png", rating="questionable")
    r_flagged_no_area.warnings.append("[风险] 评级 questionable 达到阈值 safe")
    r_flagged_no_area.warnings.append("[提示] 未检测到需要打码的区域")
    r_flagged_fail = NSFWResult(path="C:/f.png", rating="explicit")
    r_flagged_fail.warnings.append("[风险] 评级 explicit 达到阈值 safe")
    r_flagged_fail.warnings.append("[打码失败] 输出目录不可写")
    r_error = NSFWResult(path="C:/e.png")
    r_error.warnings.append("[错误] 检测失败: xxx")
    r_error.risk_level = "error"

    out = tmp_path / "shield.txt"
    content = nsfw.generate_report(
        [r_medium, r_high_censored, r_flagged_no_area, r_flagged_fail,
         r_error], str(out))
    assert out.exists()
    assert "已打码处理" in content
    assert "未检测到敏感区域" in content
    assert "打码失败" in content
