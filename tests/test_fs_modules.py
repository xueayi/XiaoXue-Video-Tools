# -*- coding: utf-8 -*-
"""批 2: folder_creator / batch_renamer / image_converter (真实文件系统)。"""

from dataclasses import dataclass, field

import pytest
from PIL import Image

import src.folder_creator as fc
import src.image_converter as ic
import src.batch_renamer as br


# ----------------------------------------------------------------
# folder_creator
# ----------------------------------------------------------------

def test_detect_encoding_utf8(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("动漫\n音乐\n", encoding="utf-8")
    enc = fc.detect_encoding(str(f))
    assert isinstance(enc, str)


def test_detect_encoding_fallback_no_chardet(monkeypatch, tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(fc, "chardet", None)
    assert fc.detect_encoding(str(f)) == "utf-8"


def test_sanitize_folder_name():
    assert fc.sanitize_folder_name("  a<b>c  ") == "a_b_c"
    assert fc.sanitize_folder_name("___") == "untitled"
    assert fc.sanitize_folder_name("正常名称") == "正常名称"
    assert fc.sanitize_folder_name("a//b") == "a_b"


def test_read_folder_names_dedup_and_clean(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("动漫\n\n动漫\n  音乐  \n", encoding="utf-8")
    names = fc.read_folder_names_from_txt(str(f))
    assert names == ["动漫", "untitled", "音乐"]


def test_batch_create_folders(tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n音乐\n", encoding="utf-8")
    out = tmp_path / "out"
    ok, fail, errors = fc.batch_create_folders(str(txt), str(out), True)
    assert ok == 2 and fail == 0 and errors == []
    assert (out / "1_动漫").is_dir()
    assert (out / "2_音乐").is_dir()


def test_batch_create_folders_no_number(tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n", encoding="utf-8")
    out = tmp_path / "out"
    ok, fail, errors = fc.batch_create_folders(str(txt), str(out), False)
    assert ok == 1
    assert (out / "动漫").is_dir()


def test_batch_create_folders_empty_txt(tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("", encoding="utf-8")
    ok, fail, errors = fc.batch_create_folders(str(txt), str(tmp_path / "o"))
    assert ok == 0 and fail == 0


def test_batch_create_folders_read_failure(tmp_path):
    ok, fail, errors = fc.batch_create_folders(
        str(tmp_path / "missing.txt"), str(tmp_path / "o"))
    assert ok == 0 and fail == 1 and errors


# ----------------------------------------------------------------
# batch_renamer
# ----------------------------------------------------------------

def make_tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "img_01.png").write_bytes(b"1")
    (tmp_path / "sub" / "img_02.png").write_bytes(b"22")
    (tmp_path / "vid.mp4").write_bytes(b"v" * 10)
    (tmp_path / "note.txt").write_text("x")


def test_normalize_extensions():
    assert br.normalize_extensions([".PNG", " Jpg ", "", "."]) == ["png", "jpg"]


def test_get_file_size_missing(tmp_path):
    assert br.get_file_size(str(tmp_path / "nope")) == 0


def test_collect_files_recursive_and_not(tmp_path):
    make_tree(tmp_path)
    files = br._collect_files(str(tmp_path), ["png", "mp4"], True)
    assert len(files) == 3
    files = br._collect_files(str(tmp_path), ["png", "mp4"], False)
    assert len(files) == 1  # 只有 vid.mp4 在根目录


def test_get_sorted_files_size_and_priority(tmp_path):
    make_tree(tmp_path)
    files = br.get_sorted_files(str(tmp_path), ["png", "mp4"], True,
                                sort_method="size", sort_order="desc",
                                priority_keyword="vid")
    assert files[0].endswith("vid.mp4")
    files = br.get_sorted_files(str(tmp_path), ["png", "mp4"], True,
                                sort_method="size", sort_order="asc")
    assert files[0].endswith("img_01.png")


def test_process_parent_folder_name(tmp_path):
    sub = tmp_path / "Series_01"
    sub.mkdir()
    f = sub / "img.png"
    f.write_bytes(b"x")
    assert br.process_parent_folder_name(str(f), str(tmp_path), True) == "Series_"
    assert br.process_parent_folder_name(str(f), str(tmp_path), False) == "Series_01_"
    assert br.process_parent_folder_name(str(tmp_path / "top.png"),
                                         str(tmp_path)) == ""


def test_determine_media_type(tmp_path):
    cfg = br.RenameConfig()
    assert br.determine_media_type("a.png", cfg) == "图片"
    assert br.determine_media_type("a.mp4", cfg) == "视频"
    assert br.determine_media_type("a.gif", cfg) is None
    images_only = br.RenameConfig(target_type="images")
    assert br.determine_media_type("a.mp4", images_only) is None


def test_batch_rename_in_place(tmp_path):
    make_tree(tmp_path)
    cfg = br.RenameConfig()
    ok, fail, errors = br.batch_rename(str(tmp_path), cfg)
    assert ok == 3 and fail == 0 and errors == []
    names = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert any(n.startswith("视频_") for n in names)
    assert any("图片_1" in n for n in names)


def test_batch_rename_copy_and_move(tmp_path):
    make_tree(tmp_path)
    out = tmp_path / "out"
    cfg = br.RenameConfig(mode="copy_rename", output_dir=str(out))
    ok, fail, errors = br.batch_rename(str(tmp_path), cfg)
    assert ok == 3 and fail == 0
    assert list(out.rglob("视频_*.mp4"))  # 根目录视频已复制重命名
    src_still = list(tmp_path.glob("*.mp4"))
    assert src_still  # 复制模式源文件保留

    src2 = tmp_path / "src2"
    (src2 / "sub").mkdir(parents=True)
    (src2 / "sub" / "img_01.png").write_bytes(b"1")
    (src2 / "vid.mp4").write_bytes(b"v" * 10)
    cfg2 = br.RenameConfig(mode="move_rename")
    ok2, fail2, _ = br.batch_rename(str(src2), cfg2)
    assert ok2 == 2
    assert not list(src2.rglob("img_01.png"))  # 移动模式源文件消失


def test_batch_rename_invalid_dir(tmp_path):
    cfg = br.RenameConfig()
    ok, fail, errors = br.batch_rename(str(tmp_path / "nope"), cfg)
    assert ok == 0 and fail == 1


def test_batch_rename_no_files(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    cfg = br.RenameConfig()
    ok, fail, errors = br.batch_rename(str(d), cfg)
    assert ok == 0 and fail == 0


# ----------------------------------------------------------------
# image_converter
# ----------------------------------------------------------------

def make_png(tmp_path, name="a.png", mode="RGB"):
    p = tmp_path / name
    if mode == "RGBA":
        Image.new("RGBA", (4, 4), (255, 0, 0, 128)).save(p)
    else:
        Image.new("RGB", (4, 4), (255, 0, 0)).save(p)
    return p


def test_check_pillow_available():
    assert ic.check_pillow_available() is True


def test_convert_image_png_to_jpeg(tmp_path):
    src = make_png(tmp_path)
    ok, msg = ic.convert_image(str(src), str(tmp_path / "a.jpg"))
    assert ok and (tmp_path / "a.jpg").exists()


def test_convert_image_rgba_to_jpeg_flatten(tmp_path):
    src = make_png(tmp_path, "t.png", mode="RGBA")
    ok, msg = ic.convert_image(str(src), str(tmp_path / "t.jpg"))
    assert ok and (tmp_path / "t.jpg").exists()


def test_convert_image_failure(tmp_path):
    ok, msg = ic.convert_image(str(tmp_path / "nope.png"),
                               str(tmp_path / "x.jpg"))
    assert ok is False and "失败" in msg


def test_normalize_extension():
    assert ic._normalize_extension(".JPEG") == ".jpg"
    assert ic._normalize_extension(".tif") == ".tiff"
    assert ic._normalize_extension(".png") == ".png"


def test_batch_convert_basic(tmp_path):
    a = make_png(tmp_path, "a.png")
    b = make_png(tmp_path, "b.png")
    out = tmp_path / "out"
    ok, fail, skip, errors = ic.batch_convert_images(
        [str(a), str(b)], str(out), ".jpg")
    assert ok == 2 and fail == 0 and skip == 0 and errors == []
    assert (out / "a.jpg").exists()


def test_batch_convert_skip_same_format(tmp_path):
    a = make_png(tmp_path, "a.png")
    ok, fail, skip, _ = ic.batch_convert_images([str(a)], None, ".png")
    assert ok == 0 and skip == 1


def test_batch_convert_unsupported_format(tmp_path):
    a = make_png(tmp_path, "a.png")
    ok, fail, skip, errors = ic.batch_convert_images([str(a)], None, ".xyz")
    assert ok == 0 and fail == 1 and errors


def test_batch_convert_same_path_gets_suffix(tmp_path):
    # 目标输出与源文件同名同目录 -> 自动加 _converted 后缀
    a = make_png(tmp_path, "a.jpg")  # jpeg 源
    target = str(tmp_path / "a.png")
    ok, fail, skip, _ = ic.batch_convert_images([str(a)], str(tmp_path), ".png",
                                                skip_same_format=False)
    assert ok == 1 and (tmp_path / "a.png").exists()
