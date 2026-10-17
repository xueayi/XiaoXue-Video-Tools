# -*- coding: utf-8 -*-
"""覆盖率最终补缺: import 守卫、编码回退、创建失败分支。"""

import builtins
import importlib

import pytest
from PIL import Image

import src.folder_creator as fc
import src.image_converter as ic


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
