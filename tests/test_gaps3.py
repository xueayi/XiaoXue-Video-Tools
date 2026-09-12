# -*- coding: utf-8 -*-
"""覆盖率收尾补充 (第三轮): 剩余打印/异常/图标分支。"""

import sys
from types import SimpleNamespace as NS

import pytest
from PIL import Image

import src.batch_renamer as br
import src.executors.batch_executor as batch_ex
import src.executors.file_executor as file_ex
import src.nsfw_detect as nsfw
from src.nsfw_detect import NSFWResult


# ----------------------------------------------------------------
# batch_executor 错误打印
# ----------------------------------------------------------------

def test_folder_creator_error_print(capsys, monkeypatch, tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "1_动漫").write_text("占位", encoding="utf-8")

    real_makedirs = fc_makedirs = None
    import src.folder_creator as fc
    real = fc.os.makedirs

    def fake_makedirs(path, exist_ok=False):
        if "动漫" in str(path):
            raise FileExistsError(path)
        return real(path, exist_ok=exist_ok)
    monkeypatch.setattr(fc.os, "makedirs", fake_makedirs)
    args = NS(folder_txt=str(txt), folder_output_dir=str(out),
              folder_auto_number=True)
    batch_ex.execute_folder_creator(args)
    assert "部分创建失败" in capsys.readouterr().out


def test_batch_rename_error_print(capsys, monkeypatch, tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")

    def failing_rename(src, dst):
        raise OSError("blocked")
    monkeypatch.setattr(br.os, "rename", failing_rename)
    args = NS(rename_input_dir=str(d), rename_mode="原地重命名",
              rename_target="图片和视频",
              rename_recursive="递归模式（保持目录结构）",
              rename_image_exts="png", rename_video_exts="mp4",
              rename_output_dir="", rename_exclude_underscore=True,
              rename_sort_method="按文件名排序",
              rename_sort_order="升序（从小到大）",
              rename_priority_keyword="")
    batch_ex.execute_batch_rename(args)
    assert "部分重命名失败" in capsys.readouterr().out


# ----------------------------------------------------------------
# file_executor 字幕自定义打印与删除失败
# ----------------------------------------------------------------

def test_remux_subtitle_custom_print(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = NS(remux_input=[str(src)], remux_preset="自定义",
              remux_format_custom=".mkv", remux_output="",
              remux_overwrite=False, remux_audio_tracks="全部保留",
              remux_audio_tracks_custom="",
              remux_subtitle_tracks="自定义选择 (填写编号)",
              remux_subtitle_tracks_custom="2")
    file_ex.execute_remux(args)
    assert "自定义选择: #2" in capsys.readouterr().out


def test_image_convert_overwrite_delete_failure(capsys, monkeypatch, tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(src)
    monkeypatch.setattr(file_ex, "batch_convert_images",
                        lambda **kw: (1, 0, 0, []))

    real_remove = file_ex.os.remove

    def failing_remove(path):
        if path == str(src):
            raise OSError("locked")
        return real_remove(path)
    monkeypatch.setattr(file_ex.os, "remove", failing_remove)
    args = NS(img_input=[str(src)], img_format="JPG/JPEG (有损压缩)",
              img_format_custom="", img_output_dir="", img_quality=95,
              img_overwrite=True, img_skip_same_format=False)
    file_ex.execute_image_convert(args)
    assert "删除失败" in capsys.readouterr().out


# ----------------------------------------------------------------
# nsfw_detect: RGBA jpg 打码 + 未处理风险图标
# ----------------------------------------------------------------

def test_apply_mosaic_rgba_jpg(fake_imgutils, tmp_path):
    # PNG 字节 + .jpg 扩展名: Image.open 后为 RGBA, 走 RGB 转换分支
    raw = tmp_path / "rgba.jpg"
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
    import io as _io
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    raw.write_bytes(buf.getvalue())
    fake_imgutils["censors"] = [((2, 2, 12, 12), "censor", 0.9)]
    out = tmp_path / "out" / "censored_rgba.jpg"
    assert nsfw.apply_mosaic(str(raw), str(out)) is True
    assert out.exists()


def test_report_uncensored_risk_icons(tmp_path):
    r_medium = NSFWResult(path="C:/m.png", rating="questionable")
    r_medium.warnings.append("[风险] 评级 questionable 达到阈值 safe")
    r_low = NSFWResult(path="C:/l.png", rating="sensitive")
    r_low.warnings.append("[风险] 评级 sensitive 达到阈值 safe")
    r_odd = NSFWResult(path="C:/o.png", rating="unknown")
    r_odd.warnings.append("[风险] 评级 unknown 达到阈值 safe")
    r_high = NSFWResult(path="C:/h.png", rating="explicit")
    r_high.warnings.append("[风险] 评级 explicit 达到阈值 safe")

    # 已打码列表的各风险等级图标 (medium/low/unknown)
    c_medium = NSFWResult(path="C:/cm.png", rating="questionable",
                          censored_path="C:/cm_c.png")
    c_low = NSFWResult(path="C:/cl.png", rating="sensitive",
                       censored_path="C:/cl_c.png")
    c_unknown = NSFWResult(path="C:/cu.png", rating="weird",
                           censored_path="C:/cu_c.png")

    content = nsfw.generate_report(
        [r_medium, r_low, r_odd, r_high, c_medium, c_low, c_unknown],
        str(tmp_path / "r.txt"))
    assert "【风险图片 (未处理)】" in content
