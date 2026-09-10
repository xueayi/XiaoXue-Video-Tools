# -*- coding: utf-8 -*-
"""覆盖率收尾: 执行器打印分支、批量重命名边界、通知头解析、nsfw 报告图标。"""

import io
import json
import sys
from types import SimpleNamespace as NS

import pytest
from PIL import Image

import src.batch_renamer as br
import src.executors.file_executor as file_ex
import src.executors.misc_executor as misc_ex
import src.executors.probe_executor as probe_ex
import src.executors.qc_executor as qc_ex
import src.executors.shield_executor as shield_ex
import src.folder_creator as fc
import src.log_utils as log_utils
import src.notify as notify
import src.nsfw_detect as nsfw
from src.nsfw_detect import NSFWResult


# ----------------------------------------------------------------
# probe_executor
# ----------------------------------------------------------------

def _probe_info(path):
    from src.media_probe import DetailedMediaInfo, StreamInfo
    info = DetailedMediaInfo(path=path)
    info.video_streams.append(StreamInfo(index=0, stream_index=0,
                                         codec_type="video",
                                         codec_name="h264"))
    return info


def test_probe_single_string_input(capsys, monkeypatch, tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(probe_ex, "probe_detailed",
                        lambda p: _probe_info(p))
    args = NS(probe_input_files=str(f), probe_input_dir="",
              probe_recursive=True, probe_report_output="")
    probe_ex.execute_media_probe(args)
    assert "共分析 1 个文件" in capsys.readouterr().out


def test_probe_recursive_dir(capsys, monkeypatch, tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.mkv").write_bytes(b"x")
    monkeypatch.setattr(probe_ex, "probe_detailed",
                        lambda p: _probe_info(p))
    args = NS(probe_input_files=None, probe_input_dir=str(tmp_path),
              probe_recursive=True, probe_report_output="")
    probe_ex.execute_media_probe(args)
    assert "共分析 2 个文件" in capsys.readouterr().out


# ----------------------------------------------------------------
# qc_executor / shield_executor / misc
# ----------------------------------------------------------------

def test_qc_custom_resolution_scan_dir_not_dir(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(qc_ex, "scan_directory", lambda **kw: [])
    args = NS(scan_dir=str(tmp_path / "no"), report_output="",
              max_res_preset="自定义", max_res_custom="1920x1080",
              min_res_preset="自定义", min_res_custom="480x360",
              max_bitrate=0, min_bitrate=0, check_pr_video=False,
              check_pr_image=False, custom_containers="",
              custom_codecs="", custom_images="")
    qc_ex.execute_qc(args)
    assert "自动生成报告路径" in capsys.readouterr().out


def test_shield_censor_custom_print(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(shield_ex, "SHIELD_AVAILABLE", True)
    shield_mod = NS(scan_directory=lambda **kw: [],
                    scan_files=lambda **kw: [],
                    generate_report=lambda res, path: "")
    monkeypatch.setitem(sys.modules, "src.nsfw_detect", shield_mod)
    args = NS(shield_input_dir=str(tmp_path), shield_input_files=None,
              shield_output_dir="", shield_report="",
              shield_threshold="Questionable 及以上 (推荐)",
              shield_recursive=True, shield_enable_censor=True,
              shield_censor_type="自定义图片 (Custom)", shield_mosaic_size="16",
              shield_overlay_image="cover.png", shield_expand_pixels="5")
    shield_ex.execute_shield(args)
    assert "覆盖图片" in capsys.readouterr().out


def test_notification_no_channels(capsys):
    args = NS(enabled=False, save_notify_config=False,
              delete_notify_config=False, feishu_webhook="",
              feishu_title="", feishu_content="", feishu_color="blue",
              webhook_url="", webhook_headers="", webhook_body="")
    misc_ex.execute_notification(args)
    assert "未配置任何通知渠道" in capsys.readouterr().out


# ----------------------------------------------------------------
# file_executor 打印与删除分支
# ----------------------------------------------------------------

def _remux_args(tmp_path, src, **kw):
    defaults = dict(remux_input=[str(src)], remux_preset="自定义",
                    remux_format_custom=".mkv", remux_output="",
                    remux_overwrite=False, remux_audio_tracks="全部保留",
                    remux_audio_tracks_custom="",
                    remux_subtitle_tracks="全部保留",
                    remux_subtitle_tracks_custom="")
    defaults.update(kw)
    return NS(**defaults)


def test_remux_track_print_branches(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = _remux_args(tmp_path, src,
                       remux_audio_tracks="自定义选择 (填写编号)",
                       remux_audio_tracks_custom="0",
                       remux_subtitle_tracks="仅保留第 1 条 (#0)",
                       remux_subtitle_tracks_custom="")
    file_ex.execute_remux(args)
    out = capsys.readouterr().out
    assert "自定义选择: #0" in out
    assert "仅保留 #0" in out


def test_remux_digit_only_tracks(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = _remux_args(tmp_path, src,
                       remux_audio_tracks="仅保留第 1 条 (#0)",
                       remux_subtitle_tracks="不保留字幕")
    file_ex.execute_remux(args)
    out = capsys.readouterr().out
    assert "仅保留 #0" in out
    assert "不保留" in out


def test_remux_overwrite_delete_failure(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 0)

    real_remove = file_ex.os.remove

    def failing_remove(path):
        if path == str(src):
            raise OSError("locked")
        return real_remove(path)
    monkeypatch.setattr(file_ex.os, "remove", failing_remove)
    args = _remux_args(tmp_path, src, remux_format_custom="mp4",
                       remux_overwrite=True)
    file_ex.execute_remux(args)
    assert "删除失败" in capsys.readouterr().out


def test_image_convert_str_input(capsys, monkeypatch, tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(src)
    monkeypatch.setattr(file_ex, "batch_convert_images",
                        lambda **kw: (1, 0, 0, []))
    args = NS(img_input=str(src), img_format="PNG (无损)",
              img_format_custom="", img_output_dir="", img_quality=95,
              img_overwrite=False, img_skip_same_format=True)
    file_ex.execute_image_convert(args)
    assert "文件数量] 1" in capsys.readouterr().out


def test_image_convert_overwrite_delete_runs(capsys, monkeypatch, tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(src)
    monkeypatch.setattr(file_ex, "batch_convert_images",
                        lambda **kw: (1, 0, 0, []))
    args = NS(img_input=[str(src)], img_format="JPG/JPEG (有损压缩)",
              img_format_custom="", img_output_dir="", img_quality=95,
              img_overwrite=True, img_skip_same_format=False)
    file_ex.execute_image_convert(args)
    out = capsys.readouterr().out
    assert "已删除 1 个原文件" in out


# ----------------------------------------------------------------
# batch_renamer 边界
# ----------------------------------------------------------------

def test_parent_folder_name_all_cleaned(tmp_path):
    sub = tmp_path / "___"
    sub.mkdir()
    f = sub / "img.png"
    f.write_bytes(b"x")
    assert br.process_parent_folder_name(str(f), str(tmp_path), True) == ""


def test_batch_rename_skip_non_media(tmp_path, monkeypatch):
    d = tmp_path / "media"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    monkeypatch.setattr(br, "determine_media_type", lambda f, c: None)
    cfg = br.RenameConfig()
    ok, fail, errors = br.batch_rename(str(d), cfg)
    assert ok == 0 and fail == 0


def test_batch_rename_copy_twice_counter(tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    cfg = br.RenameConfig(mode="copy_rename",
                          output_dir=str(tmp_path / "out"))
    ok1, _, _ = br.batch_rename(str(d), cfg)
    ok2, _, _ = br.batch_rename(str(d), cfg)
    assert ok1 == 1 and ok2 == 1
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert len(names) == 2  # 第二次生成 _1 后缀


def test_batch_rename_failure_branch(tmp_path, monkeypatch):
    d = tmp_path / "media"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")

    def failing_rename(src, dst):
        raise OSError("rename blocked")
    monkeypatch.setattr(br.os, "rename", failing_rename)
    cfg = br.RenameConfig()
    ok, fail, errors = br.batch_rename(str(d), cfg)
    assert ok == 0 and fail == 1 and errors


# ----------------------------------------------------------------
# folder_creator / log_utils / notify
# ----------------------------------------------------------------

def test_detect_encoding_final_fallback(monkeypatch, tmp_path):
    f = tmp_path / "bin.bin"
    f.write_bytes(b"\xff\xff\x00")  # 所有编码尝试都失败
    monkeypatch.setattr(fc, "chardet", None)
    assert fc.detect_encoding(str(f)) == "utf-8"


def test_fix_sys_io_fdopen_success(monkeypatch):
    logger = logging.getLogger("fdopen-ok")
    logger.addHandler(logging.NullHandler())
    fake_out = io.StringIO()
    fake_err = io.StringIO()

    def fake_fdopen(fd, *a, **k):
        return fake_out if fd == 1 else fake_err
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(log_utils.os, "fdopen", fake_fdopen)
    log_utils.fix_sys_io(logger)
    monkeypatch.undo()
    assert sys.stdout is not None
    assert sys.stderr is not None


import logging  # noqa: E402


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = "raw"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_webhook_headers_dict_and_json(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(kw)
        return _Resp(200, {"ok": 1})
    monkeypatch.setattr(notify.requests, "post", fake_post)
    assert send_webhook_with_headers_dict(monkeypatch) is True
    assert send_webhook_with_headers_json(monkeypatch) is True
    assert calls[0]["headers"]["X-A"] == "1"
    assert calls[1]["headers"]["X-B"] == "2"
    assert calls[1]["json"] == {"b": 2}


def send_webhook_with_headers_dict(monkeypatch):
    from src.notify import send_webhook_notification
    return send_webhook_notification("https://hook", headers={"X-A": "1"},
                                     body={"a": 1})


def send_webhook_with_headers_json(monkeypatch):
    from src.notify import send_webhook_notification
    return send_webhook_notification("https://hook",
                                     headers_json='{"X-B": "2"}',
                                     body_json='{"b": 2}')


# ----------------------------------------------------------------
# nsfw_detect 报告图标与扫描打印
# ----------------------------------------------------------------

def test_scan_files_medium_rating_print(capsys, fake_imgutils, tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (16, 16), (1, 2, 3)).save(src)
    fake_imgutils["rating"] = ("questionable", 0.8)
    results = nsfw.scan_files([str(src)], threshold="questionable")
    assert results[0].risk_level == "medium"
    out = capsys.readouterr().out
    assert "⚠" in out


def test_nsfw_report_safe_and_unknown_icons(tmp_path):
    safe = NSFWResult(path="C:/s.png", rating="general")
    unknown = NSFWResult(path="C:/u.png", rating="weird-rating")
    content = nsfw.generate_report([safe, unknown], str(tmp_path / "r.txt"))
    assert "[✓]" in content
    assert "[?]" in content
