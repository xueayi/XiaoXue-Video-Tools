# -*- coding: utf-8 -*-
"""M2.2 executor TaskResult 语义回归测试。

覆盖除 execute_encode（已有 test_encode_task_result.py）外全部 executor 的
成功 / 失败 / 部分失败三类结果映射，以及 TaskRunner 的归一化收紧：

    * 全部成功 -> SUCCESS
    * 全部失败 -> FAILED（FFmpeg 非零退出保留 exit_code）
    * 有成功有失败 -> PARTIAL（message 汇总成功/失败数）
    * 批量任务输出路径进 outputs，删除失败/删除跳过等进 warnings

约定：图片用 PIL 真实生成；ffmpeg 用 monkeypatch 模拟（成功时真实写出输出
文件，便于验证“输出存在才删源”的删除门槛）；不启动 GUI。
"""
from pathlib import Path
from types import SimpleNamespace as NS

import os
import pytest
from PIL import Image

import src.executors.batch_executor as batch_ex
import src.executors.file_executor as file_ex
import src.executors.misc_executor as misc_ex
import src.executors.probe_executor as probe_ex
import src.executors.qc_executor as qc_ex
import src.executors.video_executor as ve
from src.task.result import TaskResult
from src.task.status import TaskStatus


# ----------------------------------------------------------------
# 工具
# ----------------------------------------------------------------

def make_image(path, color=(255, 0, 0)):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color).save(path)
    return path


def image_args(inputs, target_ext="jpg", output_dir="", overwrite=False,
               skip_same=True):
    return NS(
        img_input=list(inputs),
        img_output_dir=str(output_dir) if output_dir else "",
        img_format="自定义",
        img_format_custom=target_ext,
        img_quality=95,
        img_overwrite=overwrite,
        img_skip_same_format=skip_same,
    )


def remux_args(inputs, custom_ext="mp4", output_dir="", overwrite=False):
    return NS(
        remux_input=list(inputs),
        remux_output=str(output_dir) if output_dir else "",
        remux_preset="自定义",
        remux_format_custom=custom_ext,
        remux_overwrite=overwrite,
        remux_audio_tracks="全部保留",
        remux_audio_tracks_custom="",
        remux_subtitle_tracks="全部保留",
        remux_subtitle_tracks_custom="",
    )


def audio_args(video, audio, output=""):
    return NS(video_input=str(video), audio_input=str(audio),
              audio_output=output, audio_enc="AAC (推荐)",
              audio_br="192k")


def extract_args(video, mode, audio_output="", video_output=""):
    return NS(extract_input=str(video), extract_mode=mode,
              extract_output=audio_output,
              extract_video_output=video_output,
              extract_encoder="AAC (推荐)", extract_bitrate="192k")


def probe_info(path):
    from src.media_probe import DetailedMediaInfo, StreamInfo
    info = DetailedMediaInfo(path=path)
    info.video_streams.append(StreamInfo(
        index=0, stream_index=0, codec_type="video", codec_name="h264"))
    return info


def field_args(**kwargs):
    """构造 qc/probe 等 args 的默认集合。"""
    defaults = dict(
        scan_dir="", report_output="",
        max_res_preset="不限制", max_res_custom="",
        min_res_preset="不限制", min_res_custom="",
        max_bitrate=0, min_bitrate=0, check_pr_video=False,
        check_pr_image=False, custom_containers="", custom_codecs="",
        custom_images="",
        probe_input_files=None, probe_input_dir="", probe_recursive=True,
        probe_report_output="",
        help_topic="视频压制",
    )
    defaults.update(kwargs)
    return NS(**defaults)


# ----------------------------------------------------------------
# video_executor: execute_replace_audio
# ----------------------------------------------------------------

def test_replace_audio_success(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.m4a"
    video.write_bytes(b"x")
    audio.write_bytes(b"x")
    output = tmp_path / "out.mp4"
    monkeypatch.setattr(ve, "build_replace_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 0)
    result = ve.execute_replace_audio(audio_args(video, audio, str(output)))
    assert result.status is TaskStatus.SUCCESS
    assert result.exit_code == 0
    assert result.outputs == (str(output),)


def test_replace_audio_auto_output_path(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.m4a"
    video.write_bytes(b"x")
    audio.write_bytes(b"x")
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return ["ffmpeg", "x"]

    monkeypatch.setattr(ve, "build_replace_audio_command", fake_build)
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 0)
    result = ve.execute_replace_audio(audio_args(video, audio))
    assert result.status is TaskStatus.SUCCESS
    assert "_replaced" in captured["output_path"]
    assert result.outputs == (captured["output_path"],)


def test_replace_audio_failure_keeps_exit_code(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.m4a"
    video.write_bytes(b"x")
    audio.write_bytes(b"x")
    monkeypatch.setattr(ve, "build_replace_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 2)
    result = ve.execute_replace_audio(
        audio_args(video, audio, str(tmp_path / "out.mp4")))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 2
    assert result.outputs == ()


# ----------------------------------------------------------------
# video_executor: execute_extract_av
# ----------------------------------------------------------------

def test_extract_av_audio_only_success(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(ve, "build_extract_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 0)
    result = ve.execute_extract_av(extract_args(video, "仅音频"))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.outputs) == 1
    assert result.outputs[0].endswith(".m4a")


def test_extract_av_audio_only_failure(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(ve, "build_extract_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 4)
    result = ve.execute_extract_av(extract_args(video, "仅音频"))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 4


def test_extract_av_both_success_outputs_two(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(ve, "build_extract_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "build_extract_video_command",
                        lambda **kw: ["ffmpeg", "y"])
    monkeypatch.setattr(ve, "run_ffmpeg_command", lambda cmd, **kw: 0)
    result = ve.execute_extract_av(extract_args(video, "音频+视频"))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.outputs) == 2


def test_extract_av_both_partial_keeps_successful_output(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    audio_out = str(tmp_path / "a.m4a")
    video_out = str(tmp_path / "v_noaudio.mp4")
    monkeypatch.setattr(ve, "build_extract_audio_command",
                        lambda **kw: ["ffmpeg", "x"])
    monkeypatch.setattr(ve, "build_extract_video_command",
                        lambda **kw: ["ffmpeg", "y"])
    # 音频成功, 视频失败
    monkeypatch.setattr(ve, "run_ffmpeg_command",
                        lambda cmd, **kw: 0 if cmd == ["ffmpeg", "x"] else 1)
    result = ve.execute_extract_av(
        extract_args(video, "音频+视频", audio_out, video_out))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert result.outputs == (audio_out,)


# ----------------------------------------------------------------
# file_executor: execute_remux
# ----------------------------------------------------------------

def _write_remux_ok(outputs):
    def runner(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"remuxed")
        outputs.append(cmd[-1])
        return 0
    return runner


def test_remux_all_success(monkeypatch, tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for src in srcs:
        src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command",
                        _write_remux_ok([]))
    result = file_ex.execute_remux(remux_args(srcs))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.outputs) == 2
    assert all(Path(path).is_file() for path in result.outputs)


def test_remux_all_failed(monkeypatch, tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for src in srcs:
        src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command",
                        lambda cmd, **kw: 1)
    result = file_ex.execute_remux(remux_args(srcs))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 1
    assert result.outputs == ()
    assert result.details["failure_count"] == 2


def test_remux_partial(monkeypatch, tmp_path):
    good = tmp_path / "good.mkv"
    bad = tmp_path / "bad.mkv"
    good.write_bytes(b"x")
    bad.write_bytes(b"y")

    def runner(cmd, **kwargs):
        if Path(cmd[cmd.index("-i") + 1]).name == "bad.mkv":
            return 1
        Path(cmd[-1]).write_bytes(b"remuxed")
        return 0

    monkeypatch.setattr(file_ex, "run_ffmpeg_command", runner)
    result = file_ex.execute_remux(remux_args([good, bad]))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert len(result.outputs) == 1


def test_remux_missing_custom_extension_failed():
    args = remux_args(["a.mp4"], custom_ext="")
    result = file_ex.execute_remux(args)
    assert result.status is TaskStatus.FAILED
    assert "必须输入自定义后缀名" in result.message


def test_remux_empty_inputs_failed():
    result = file_ex.execute_remux(remux_args([]))
    assert result.status is TaskStatus.FAILED
    assert "没有可处理的任务输入" in result.message


# ----------------------------------------------------------------
# file_executor: execute_image_convert
# ----------------------------------------------------------------

def test_image_convert_all_success(tmp_path):
    srcs = [make_image(tmp_path / "a.png"), make_image(tmp_path / "b.png")]
    out_dir = tmp_path / "out"
    result = file_ex.execute_image_convert(
        image_args(srcs, output_dir=out_dir))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.outputs) == 2
    assert [r.status for r in result.details["results"]] == [
        "success", "success"]


def test_image_convert_partial(tmp_path):
    good = make_image(tmp_path / "good.png")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    result = file_ex.execute_image_convert(
        image_args([good, bad], output_dir=tmp_path / "out", skip_same=False))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert result.details["success_count"] == 1
    assert result.details["failure_count"] == 1


def test_image_convert_all_failed(tmp_path):
    bads = []
    for name in ("b1.png", "b2.png"):
        path = tmp_path / name
        path.write_bytes(b"broken")
        bads.append(path)
    result = file_ex.execute_image_convert(
        image_args(bads, output_dir=tmp_path / "out", skip_same=False))
    assert result.status is TaskStatus.FAILED
    assert result.details["failure_count"] == 2
    assert result.outputs == ()


def test_image_convert_all_skipped_is_success(tmp_path):
    src = make_image(tmp_path / "a.png")
    result = file_ex.execute_image_convert(
        image_args([src], target_ext="png", skip_same=True))
    assert result.status is TaskStatus.SUCCESS
    assert "跳过 1 个" in result.message
    assert any("跳过" in warning for warning in result.warnings)


def test_image_convert_delete_failure_goes_to_warnings(monkeypatch, tmp_path):
    src = make_image(tmp_path / "a.png")
    out_dir = tmp_path / "out"
    real_remove = file_ex.os.remove

    def failing_remove(path):
        if os.path.basename(str(path)) == "a.png":
            raise OSError("locked")
        return real_remove(path)

    monkeypatch.setattr(file_ex.os, "remove", failing_remove)
    result = file_ex.execute_image_convert(
        image_args([src], output_dir=out_dir, overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    assert any("删除失败" in warning for warning in result.warnings)


# ----------------------------------------------------------------
# batch_executor
# ----------------------------------------------------------------

def test_folder_creator_success(tmp_path):
    txt = tmp_path / "names.txt"
    txt.write_text("动漫\n音乐\n", encoding="utf-8")
    args = NS(folder_txt=str(txt), folder_output_dir=str(tmp_path / "o"),
              folder_auto_number=True)
    result = batch_ex.execute_folder_creator(args)
    assert result.status is TaskStatus.SUCCESS
    assert result.details["success_count"] == 2


def test_folder_creator_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_ex, "batch_create_folders",
                        lambda **kw: (1, 1, ["b: 创建失败"]))
    args = NS(folder_txt="names.txt", folder_output_dir=str(tmp_path),
              folder_auto_number=True)
    result = batch_ex.execute_folder_creator(args)
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"


def test_folder_creator_all_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_ex, "batch_create_folders",
                        lambda **kw: (0, 2, ["a: x", "b: y"]))
    args = NS(folder_txt="names.txt", folder_output_dir=str(tmp_path),
              folder_auto_number=True)
    result = batch_ex.execute_folder_creator(args)
    assert result.status is TaskStatus.FAILED
    assert "全部失败（2 个）" in result.message


def _rename_args(tmp_path):
    return NS(rename_input_dir=str(tmp_path), rename_mode="原地重命名",
              rename_target="图片和视频",
              rename_recursive="递归模式（保持目录结构）",
              rename_image_exts="png", rename_video_exts="mp4",
              rename_output_dir="", rename_exclude_underscore=True,
              rename_sort_method="按文件名排序",
              rename_sort_order="升序（从小到大）",
              rename_priority_keyword="")


def test_batch_rename_success(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "a.png").write_bytes(b"x")
    result = batch_ex.execute_batch_rename(_rename_args(media))
    assert result.status is TaskStatus.SUCCESS
    assert result.details["success_count"] == 1


def test_batch_rename_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_ex, "batch_rename",
                        lambda **kw: (2, 1, ["c.png: err"]))
    result = batch_ex.execute_batch_rename(_rename_args(tmp_path))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 2 个, 失败 1 个"


def test_batch_rename_all_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_ex, "batch_rename",
                        lambda **kw: (0, 2, ["a.png: x", "b.png: y"]))
    result = batch_ex.execute_batch_rename(_rename_args(tmp_path))
    assert result.status is TaskStatus.FAILED
    assert result.details["failure_count"] == 2


# ----------------------------------------------------------------
# qc_executor
# ----------------------------------------------------------------

def _media_info(path, valid=True):
    from src.qc import MediaInfo
    info = MediaInfo(path=str(path), video_codec="h264",
                     width=1920, height=1080)
    if not valid:
        info.is_valid = False
        info.errors.append("无法读取文件: bad")
    return info


def test_qc_success_outputs_report(monkeypatch, tmp_path):
    scan_dir = tmp_path / "media"
    scan_dir.mkdir()
    report = tmp_path / "qc.txt"
    monkeypatch.setattr(qc_ex, "scan_directory",
                        lambda **kw: [_media_info(scan_dir / "a.mp4")])
    args = field_args(scan_dir=str(scan_dir), report_output=str(report))
    result = qc_ex.execute_qc(args)
    assert result.status is TaskStatus.SUCCESS
    assert result.outputs == (str(report),)
    assert report.exists()


def test_qc_partial_probe_failures(monkeypatch, tmp_path):
    scan_dir = tmp_path / "media"
    scan_dir.mkdir()
    report = tmp_path / "qc.txt"
    infos = [_media_info(scan_dir / "ok.mp4"),
             _media_info(scan_dir / "bad.mp4", valid=False)]
    monkeypatch.setattr(qc_ex, "scan_directory", lambda **kw: infos)
    args = field_args(scan_dir=str(scan_dir), report_output=str(report))
    result = qc_ex.execute_qc(args)
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert any("无法读取文件" in warning for warning in result.warnings)


def test_qc_all_probe_failures(monkeypatch, tmp_path):
    scan_dir = tmp_path / "media"
    scan_dir.mkdir()
    report = tmp_path / "qc.txt"
    infos = [_media_info(scan_dir / "a.mp4", valid=False),
             _media_info(scan_dir / "b.mp4", valid=False)]
    monkeypatch.setattr(qc_ex, "scan_directory", lambda **kw: infos)
    args = field_args(scan_dir=str(scan_dir), report_output=str(report))
    result = qc_ex.execute_qc(args)
    assert result.status is TaskStatus.FAILED
    assert result.details["failure_count"] == 2


def test_qc_scan_failure(monkeypatch, tmp_path):
    def boom(**kw):
        raise RuntimeError("目录不可读")

    monkeypatch.setattr(qc_ex, "scan_directory", boom)
    args = field_args(scan_dir=str(tmp_path), report_output="")
    result = qc_ex.execute_qc(args)
    assert result.status is TaskStatus.FAILED
    assert "扫描失败" in result.message


# ----------------------------------------------------------------
# probe_executor
# ----------------------------------------------------------------

def test_probe_success_with_report(monkeypatch, tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    report = tmp_path / "probe.txt"
    monkeypatch.setattr(probe_ex, "probe_detailed",
                        lambda path: probe_info(path))
    args = field_args(probe_input_files=[str(media)],
                      probe_report_output=str(report))
    result = probe_ex.execute_media_probe(args)
    assert result.status is TaskStatus.SUCCESS
    assert result.outputs == (str(report),)
    assert report.exists()


def test_probe_all_failed(monkeypatch, tmp_path):
    media = tmp_path / "a.mp4"
    media.write_bytes(b"x")
    monkeypatch.setattr(probe_ex, "probe_detailed", lambda path: None)
    args = field_args(probe_input_files=[str(media)])
    result = probe_ex.execute_media_probe(args)
    assert result.status is TaskStatus.FAILED
    assert "探测失败" in result.message
    assert result.details["failed_count"] == 1


def test_probe_no_input_files_failed():
    result = probe_ex.execute_media_probe(field_args())
    assert result.status is TaskStatus.FAILED
    assert "未找到可分析的媒体文件" in result.message


def test_probe_partial_files_success_with_warnings(monkeypatch, tmp_path):
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good.write_bytes(b"x")
    bad.write_bytes(b"y")

    def fake_probe(path):
        return probe_info(path) if Path(path).name == "good.mp4" else None

    monkeypatch.setattr(probe_ex, "probe_detailed", fake_probe)
    args = field_args(probe_input_files=[str(good), str(bad)])
    result = probe_ex.execute_media_probe(args)
    assert result.status is TaskStatus.SUCCESS
    assert any("探测失败" in warning for warning in result.warnings)


# ----------------------------------------------------------------
# misc_executor
# ----------------------------------------------------------------

def test_help_returns_success(capsys):
    result = misc_ex.execute_help(NS(help_topic="视频压制"))
    assert result.status is TaskStatus.SUCCESS
    assert "视频压制" in result.message
    assert "使用说明" in capsys.readouterr().out
