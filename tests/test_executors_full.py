# -*- coding: utf-8 -*-
"""executors 覆盖测试 (mock 底层服务函数)。"""

import sys
from types import SimpleNamespace as NS

import pytest

import src.executors.batch_executor as batch_ex
import src.executors.common as common
import src.executors.file_executor as file_ex
import src.executors.misc_executor as misc_ex
import src.executors.probe_executor as probe_ex
import src.executors.qc_executor as qc_ex
import src.executors.shield_executor as shield_ex
import src.executors.video_executor as ve


def test_common_helpers():
    common.print_task_header("任务")
    assert common.parse_comma_list("") == set()
    assert common.parse_comma_list("mkv, webm") == {"mkv", "webm"}
    assert common.parse_comma_list("mkv,webm", prefix=".") == {".mkv", ".webm"}
    assert common.parse_comma_list(".flv", prefix=".") == {".flv"}
    assert common.parse_comma_list("  ") == set()


def encode_args(**kw):
    defaults = dict(
        input="in.mp4", output="", preset="自定义 (Custom)",
        encoder="H.264 (CPU - libx264)", speed_preset="medium",
        nvenc_preset="使用预设默认", rate_control="CRF/CQ (恒定质量)",
        crf=18, video_bitrate="", resolution="", fps=0,
        audio_encoder="复制 (不重新编码)", audio_bitrate="192k",
        subtitle="", compat_mode=False, extra_args="", debug_mode=True,
        post_transfer_mode="不分发", post_transfer_dir="")
    defaults.update(kw)
    return NS(**defaults)


# ----------------------------------------------------------------
# video_executor
# ----------------------------------------------------------------

def test_execute_encode_invalid_input(capsys, tmp_path):
    args = encode_args(input=str(tmp_path / "no.mp4"))
    assert ve.execute_encode(args) == 1
    assert "错误" in capsys.readouterr().out


def test_execute_encode_dry_run_normal(capsys, tmp_path):
    real = tmp_path / "in.mp4"
    real.write_bytes(b"x")
    args = encode_args(input=str(real))
    rc = ve.execute_encode(args)
    assert rc == 0
    assert "Debug 模式" in capsys.readouterr().out


def test_execute_encode_compat_dry_run(capsys, monkeypatch, tmp_path):
    import src.compat_encoder as ce
    real = tmp_path / "in.mp4"
    real.write_bytes(b"x")
    sub = tmp_path / "s.ass"
    sub.write_text("[Script Info]", encoding="utf-8")
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))
    args = encode_args(input=str(real), output=str(tmp_path / "o.mp4"),
                       compat_mode=True, subtitle=str(sub))
    rc = ve.execute_encode(args)
    assert rc == 0


def test_execute_encode_2pass_dry_run(capsys, tmp_path):
    real = tmp_path / "in.mp4"
    real.write_bytes(b"x")
    args = encode_args(input=str(real), rate_control="2-Pass VBR (两遍编码)",
                       crf=None, video_bitrate="8M")
    rc = ve.execute_encode(args)
    assert rc == 0
    assert "2-Pass" in capsys.readouterr().out


def test_execute_encode_post_transfer(capsys, monkeypatch, tmp_path):
    real = tmp_path / "in.mp4"
    real.write_bytes(b"x")
    out = tmp_path / "o.mp4"
    out.write_bytes(b"x")
    dest = tmp_path / "dest"
    dest.mkdir()
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = encode_args(input=str(real), output=str(out), debug_mode=False,
                       post_transfer_mode="复制到指定目录",
                       post_transfer_dir=str(dest))
    ve.execute_encode(args)
    assert (dest / "o.mp4").exists()


def test_post_transfer_skips(capsys, tmp_path):
    ve._post_transfer(NS(post_transfer_mode="不分发",
                         post_transfer_dir=""), "x.mp4", 0)
    ve._post_transfer(NS(post_transfer_mode="复制到指定目录",
                         post_transfer_dir=""), "x.mp4", 0)
    ve._post_transfer(NS(post_transfer_mode="复制到指定目录",
                         post_transfer_dir=str(tmp_path)), "x.mp4", 1)
    ve._post_transfer(NS(post_transfer_mode="复制到指定目录",
                         post_transfer_dir=str(tmp_path)), "Z:/no.mp4", 0)
    out = capsys.readouterr().out
    assert "跳过分发" in out


def test_post_transfer_failure_logged(capsys, monkeypatch, tmp_path):
    def boom(src, dst, mode="copy"):
        raise OSError("no space")
    monkeypatch.setattr(ve, "transfer_file", boom)
    out_file = tmp_path / "o.mp4"
    out_file.write_bytes(b"x")
    ve._post_transfer(NS(post_transfer_mode="复制到指定目录",
                         post_transfer_dir=str(tmp_path)),
                      str(out_file), 0)
    assert "分发失败" in capsys.readouterr().out


def test_execute_replace_audio_dry_run(capsys, monkeypatch, tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    a = tmp_path / "a.m4a"
    a.write_bytes(b"x")
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = NS(video_input=str(v), audio_input=str(a), audio_output="",
              audio_enc="AAC (推荐)", audio_br="192k", dry_run=True)
    ve.execute_replace_audio(args)  # dry_run 未被该实现使用, mock 掉真实执行
    assert "音频替换" in capsys.readouterr().out


def test_execute_extract_av_dry_run(capsys, monkeypatch, tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = NS(av_input=str(v), extract_mode="both",
              extract_input=str(v), extract_output="",
              extract_video_output="", extract_encoder="AAC (推荐)",
              extract_bitrate="192k", extract_audio=True,
              extract_video=True, dry_run=True)
    ve.execute_extract_av(args)  # dry_run 未被该实现使用, mock 掉真实执行
    out = capsys.readouterr().out
    assert "音频抽取" in out and "视频抽取" in out


# ----------------------------------------------------------------
# file_executor
# ----------------------------------------------------------------

def test_execute_remux_missing_custom_ext(capsys):
    args = NS(remux_input=["a.mp4"], remux_preset="自定义",
              remux_format_custom="", remux_output="",
              remux_overwrite=False)
    file_ex.execute_remux(args)
    assert "必须输入自定义后缀名" in capsys.readouterr().out


def test_execute_remux_run(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    cmds = []
    monkeypatch.setattr(file_ex, "run_ffmpeg_command",
                        lambda cmd, **k: cmds.append(cmd) or 0)
    args = NS(remux_input=[str(src)], remux_preset="自定义",
              remux_format_custom="mkv", remux_output=str(tmp_path / "out"),
              remux_overwrite=False, remux_audio_tracks="全部保留",
              remux_audio_tracks_custom="", remux_subtitle_tracks="全部保留",
              remux_subtitle_tracks_custom="")
    file_ex.execute_remux(args)
    assert len(cmds) == 1
    assert "批量转换完成: 成功 1 个" in capsys.readouterr().out


def test_execute_remux_overwrite_deletes_original(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 0)
    args = NS(remux_input=[str(src)], remux_preset="自定义",
              remux_format_custom="mkv", remux_output="",
              remux_overwrite=True, remux_audio_tracks="全部保留",
              remux_audio_tracks_custom="", remux_subtitle_tracks="全部保留",
              remux_subtitle_tracks_custom="")
    file_ex.execute_remux(args)
    # mkv -> mkv 同名不同后缀 (a.mkv -> a_remux.mkv), 覆盖模式删除原文件
    assert not src.exists()
    assert "覆盖模式" in capsys.readouterr().out


def test_execute_remux_failure_counts(capsys, monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", lambda cmd, **k: 1)
    args = NS(remux_input=[str(src)], remux_preset="自定义",
              remux_format_custom=".mkv", remux_output="",
              remux_overwrite=False, remux_audio_tracks="不保留音轨",
              remux_audio_tracks_custom="", remux_subtitle_tracks="不保留字幕",
              remux_subtitle_tracks_custom="")
    file_ex.execute_remux(args)
    assert "成功 0 个, 失败 1 个" in capsys.readouterr().out


def test_execute_image_convert_custom_empty(capsys):
    args = NS(img_input=["a.png"], img_format="自定义",
              img_format_custom="", img_output_dir="", img_quality=95,
              img_overwrite=False, img_skip_same_format=True)
    file_ex.execute_image_convert(args)
    assert "必须输入扩展名" in capsys.readouterr().out


def test_execute_image_convert_run(capsys, monkeypatch, tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(src)
    monkeypatch.setattr(file_ex, "batch_convert_images",
                        lambda **kw: (1, 0, 0, ["e1"]))
    args = NS(img_input=[str(src)], img_format="自定义",
              img_format_custom="webp", img_output_dir=str(tmp_path / "o"),
              img_quality=90, img_overwrite=False, img_skip_same_format=True)
    file_ex.execute_image_convert(args)
    assert "部分转换失败" in capsys.readouterr().out


def test_execute_image_convert_overwrite_deletes(capsys, monkeypatch, tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (255, 0, 0)).save(src)
    monkeypatch.setattr(file_ex, "batch_convert_images",
                        lambda **kw: (1, 0, 0, []))
    args = NS(img_input=[str(src)], img_format="PNG (无损)",
              img_format_custom="", img_output_dir="", img_quality=95,
              img_overwrite=True, img_skip_same_format=False)
    file_ex.execute_image_convert(args)
    assert "覆盖模式" in capsys.readouterr().out


# ----------------------------------------------------------------
# batch_executor
# ----------------------------------------------------------------

def test_execute_folder_creator(capsys, tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n", encoding="utf-8")
    args = NS(folder_txt=str(txt), folder_output_dir=str(tmp_path / "o"),
              folder_auto_number=True)
    batch_ex.execute_folder_creator(args)
    assert "批量创建文件夹" in capsys.readouterr().out


def test_execute_folder_creator_auto_output_dir(capsys, tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n", encoding="utf-8")
    args = NS(folder_txt=str(txt), folder_output_dir="", folder_auto_number=True)
    batch_ex.execute_folder_creator(args)
    assert (tmp_path / "1_动漫").is_dir()


def test_execute_batch_rename(capsys, tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    (d / "a.png").write_bytes(b"x")
    args = NS(rename_input_dir=str(d), rename_mode="原地重命名",
              rename_target="图片和视频",
              rename_recursive="递归模式（保持目录结构）",
              rename_image_exts="png", rename_video_exts="mp4",
              rename_output_dir="", rename_exclude_underscore=True,
              rename_sort_method="按文件名排序",
              rename_sort_order="升序（从小到大）",
              rename_priority_keyword="")
    batch_ex.execute_batch_rename(args)
    assert "批量序列重命名" in capsys.readouterr().out


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


def test_execute_media_probe_no_files(capsys):
    args = NS(probe_input_files=None, probe_input_dir="",
              probe_recursive=True, probe_report_output="")
    probe_ex.execute_media_probe(args)
    assert "未找到可分析的媒体文件" in capsys.readouterr().out


def test_execute_media_probe_with_files(capsys, monkeypatch, tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(probe_ex, "probe_detailed",
                        lambda p: _probe_info(p))
    args = NS(probe_input_files=[str(f)], probe_input_dir="",
              probe_recursive=True,
              probe_report_output=str(tmp_path / "report.txt"))
    probe_ex.execute_media_probe(args)
    out = capsys.readouterr().out
    assert "共分析 1 个文件" in out
    assert (tmp_path / "report.txt").exists()


def test_execute_media_probe_dir_scan(capsys, monkeypatch, tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.mkv").write_bytes(b"x")
    monkeypatch.setattr(probe_ex, "probe_detailed",
                        lambda p: _probe_info(p))
    args = NS(probe_input_files=None, probe_input_dir=str(tmp_path),
              probe_recursive=False, probe_report_output="")
    probe_ex.execute_media_probe(args)
    assert "共分析 1 个文件" in capsys.readouterr().out


def test_execute_media_probe_errors_counted(capsys, monkeypatch, tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")

    def bad_probe(p):
        info = _probe_info(p)
        info.errors.append("坏")
        return info
    monkeypatch.setattr(probe_ex, "probe_detailed", bad_probe)
    args = NS(probe_input_files=[str(f)], probe_input_dir="",
              probe_recursive=True, probe_report_output="")
    probe_ex.execute_media_probe(args)
    assert "探测出错" in capsys.readouterr().out


# ----------------------------------------------------------------
# qc_executor
# ----------------------------------------------------------------

def test_execute_qc_full(capsys, monkeypatch, tmp_path):
    scan_dir = tmp_path / "media"
    scan_dir.mkdir()
    (scan_dir / "a.mp4").write_bytes(b"x")
    report = tmp_path / "qc.txt"

    from src.qc import MediaInfo

    def fake_scan(**kw):
        return [MediaInfo(path=str(scan_dir / "a.mp4"), video_codec="h264",
                          width=1920, height=1080)]
    monkeypatch.setattr(qc_ex, "scan_directory", fake_scan)
    args = NS(scan_dir=str(scan_dir), report_output=str(report),
              max_res_preset="1080P (1920x1080)", max_res_custom="",
              min_res_preset="自定义", min_res_custom="480x360",
              max_bitrate=5000, min_bitrate=0, check_pr_video=True,
              check_pr_image=False, custom_containers="mkv",
              custom_codecs="", custom_images="")
    qc_ex.execute_qc(args)
    assert report.exists()
    assert "报告预览" in capsys.readouterr().out


def test_execute_qc_auto_report_path(capsys, monkeypatch, tmp_path):
    scan_dir = tmp_path / "media"
    scan_dir.mkdir()
    monkeypatch.setattr(qc_ex, "scan_directory", lambda **kw: [])
    args = NS(scan_dir=str(scan_dir), report_output="",
              max_res_preset="不限制", max_res_custom="",
              min_res_preset="不限制", min_res_custom="",
              max_bitrate=0, min_bitrate=0, check_pr_video=False,
              check_pr_image=False, custom_containers="",
              custom_codecs="", custom_images="")
    qc_ex.execute_qc(args)
    assert "自动生成报告路径" in capsys.readouterr().out


# ----------------------------------------------------------------
# misc_executor
# ----------------------------------------------------------------

def test_execute_notification_full(capsys, monkeypatch):
    import src.notify_config as nc
    sent = []
    monkeypatch.setattr(misc_ex, "send_feishu_notification",
                        lambda **kw: sent.append("feishu") or True)
    monkeypatch.setattr(misc_ex, "send_webhook_notification",
                        lambda **kw: sent.append("webhook") or True)
    monkeypatch.setattr(misc_ex, "save_notify_config", lambda cfg: None)
    nc._notify_config.clear()
    nc._notify_config.update({"enabled": True})
    args = NS(enable_auto_notify=True, save_notify_config=True,
              delete_notify_config=False,
              feishu_webhook="https://f", feishu_title="t",
              feishu_content="c", feishu_color="blue",
              webhook_url="https://h", webhook_headers="{}",
              webhook_body="{}")
    misc_ex.execute_notification(args)
    assert sent == ["feishu", "webhook"]
    assert "自动通知已启用" in capsys.readouterr().out


def test_execute_notification_delete_config(capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(misc_ex, "delete_notify_config",
                        lambda: calls.append("del"))
    args = NS(enabled=False, save_notify_config=False,
              delete_notify_config=True, feishu_webhook="",
              feishu_title="", feishu_content="", feishu_color="blue",
              webhook_url="", webhook_headers="", webhook_body="")
    misc_ex.execute_notification(args)
    assert calls == ["del"]
    assert "配置文件已删除" in capsys.readouterr().out


def test_execute_notification_test_failure(capsys, monkeypatch):
    monkeypatch.setattr(misc_ex, "send_feishu_notification",
                        lambda **kw: False)
    monkeypatch.setattr(misc_ex, "send_webhook_notification",
                        lambda **kw: False)
    args = NS(enabled=False, save_notify_config=False,
              delete_notify_config=False, feishu_webhook="https://f",
              feishu_title="t", feishu_content="c", feishu_color="blue",
              webhook_url="https://h", webhook_headers="{}",
              webhook_body="{}")
    misc_ex.execute_notification(args)
    assert "失败 2 个" in capsys.readouterr().out


def test_execute_help(capsys):
    args = NS(help_topic="视频压制")
    misc_ex.execute_help(args)
    assert "使用说明" in capsys.readouterr().out


# ----------------------------------------------------------------
# shield_executor
# ----------------------------------------------------------------

def test_execute_shield_unavailable(capsys, monkeypatch):
    monkeypatch.setattr(shield_ex, "SHIELD_AVAILABLE", False)
    args = NS(shield_input_dir="", shield_input_files=None)
    shield_ex.execute_shield(args)
    assert "Shield 功能不可用" in capsys.readouterr().out


def test_execute_shield_no_input(capsys, monkeypatch):
    monkeypatch.setattr(shield_ex, "SHIELD_AVAILABLE", True)
    args = NS(shield_input_dir="", shield_input_files=None)
    shield_ex.execute_shield(args)
    assert "请选择扫描目录或图片文件" in capsys.readouterr().out


def test_execute_shield_directory_flow(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(shield_ex, "SHIELD_AVAILABLE", True)
    results = [NS(path=str(tmp_path / "a.png"), filename="a.png",
                  rating="general", scores={}, sensitive_areas=[],
                  risk_level="safe", warnings=[], censored_path="")]

    captured = {}

    def fake_scan(directory, **kw):
        captured.update(kw)
        return results

    shield_mod = NS(scan_directory=fake_scan,
                    scan_files=lambda **kw: [],
                    generate_report=lambda res, path: "报告内容")
    monkeypatch.setitem(sys.modules, "src.nsfw_detect", shield_mod)
    args = NS(shield_input_dir=str(tmp_path), shield_input_files=None,
              shield_output_dir="", shield_report="",
              shield_threshold="Questionable 及以上 (推荐)",
              shield_recursive=True, shield_enable_censor=False,
              shield_censor_type="马赛克 (Pixelate)", shield_mosaic_size="16",
              shield_overlay_image="", shield_expand_pixels="0")
    shield_ex.execute_shield(args)
    assert "报告预览" in capsys.readouterr().out


def test_execute_shield_files_flow_no_results(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(shield_ex, "SHIELD_AVAILABLE", True)
    shield_mod = NS(scan_directory=lambda **kw: [],
                    scan_files=lambda **kw: [],
                    generate_report=lambda res, path: "")
    monkeypatch.setitem(sys.modules, "src.nsfw_detect", shield_mod)
    args = NS(shield_input_dir="", shield_input_files=[str(tmp_path / "x.png")],
              shield_output_dir="", shield_report="",
              shield_threshold="Questionable 及以上 (推荐)",
              shield_recursive=True, shield_enable_censor=True,
              shield_censor_type="马赛克 (Pixelate)", shield_mosaic_size="16",
              shield_overlay_image="", shield_expand_pixels="5")
    shield_ex.execute_shield(args)
    assert "未找到可扫描的图片" in capsys.readouterr().out
