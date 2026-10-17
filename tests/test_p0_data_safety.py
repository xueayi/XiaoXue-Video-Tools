# -*- coding: utf-8 -*-
"""
P0 数据安全回归测试（PR-01）。

覆盖范围：
- src/image_converter.py: FileConvertResult/can_delete_source、batch 逐文件结果、
  输出路径占位（不覆盖输入/既有文件/同批输出）、save 后输出复核；
- src/executors/file_executor.py: execute_image_convert 删除门控（仅 success +
  输出存在 + 非同一文件）、删除失败告警继续；execute_remux 删除门槛
  （rc==0 + 输出存在 + 非同一文件）与批内输出冲突加后缀。

约定：图片用 PIL 真实生成到 tmp_path（不依赖真实 ffmpeg）；remux 的
run_ffmpeg_command 用 monkeypatch 模拟，成功时真实写出输出文件，从而验证
“输出存在才删源”的门槛。全部为纯模块测试，不启动 GUI。
"""
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

import src.executors.file_executor as file_ex
import src.image_converter as ic
from src.image_converter import FileConvertResult
from src.task.result import TaskResult
from src.task.status import TaskStatus


# ----------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------

def make_image(path, color=(255, 0, 0), mode="RGB"):
    """在指定路径生成一张 4x4 小图片（按扩展名推断保存格式）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, (4, 4), color).save(path)
    return path


def make_broken(path):
    """写入一个不是合法图片的文件，用于模拟转换失败。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real image")
    return path


def image_args(inputs, target_ext="jpg", output_dir="", overwrite=True,
               skip_same=True, quality=95):
    """构造 execute_image_convert 的参数对象。"""
    return NS(
        img_input=list(inputs),
        img_output_dir=str(output_dir) if output_dir else "",
        img_format="自定义",
        img_format_custom=target_ext,
        img_quality=quality,
        img_overwrite=overwrite,
        img_skip_same_format=skip_same,
    )


def remux_args(inputs, custom_ext="mkv", output_dir="", overwrite=False):
    """构造 execute_remux 的参数对象。"""
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


def fake_ffmpeg_ok(outputs):
    """模拟 ffmpeg 成功：真实写出输出文件并记录 (输入, 输出)。"""
    def runner(cmd, **kwargs):
        src = cmd[cmd.index("-i") + 1]
        out = cmd[-1]
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"remuxed")
        outputs.append((src, out))
        return 0
    return runner


def fake_ffmpeg_no_output(cmd, **kwargs):
    """模拟 ffmpeg 返回成功但没有任何输出文件（异常场景）。"""
    return 0


def fake_ffmpeg_partial_fail(fail_names):
    """模拟 ffmpeg 部分失败：fail_names 中的源失败且不产出文件。"""
    def runner(cmd, **kwargs):
        src = cmd[cmd.index("-i") + 1]
        out = cmd[-1]
        if Path(src).name in fail_names:
            return 1
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"remuxed")
        return 0
    return runner


# ----------------------------------------------------------------
# FileConvertResult: 删除门控三条件
# ----------------------------------------------------------------

def test_can_delete_source_true_for_success_with_output(tmp_path):
    src = make_image(tmp_path / "a.png")
    out = make_image(tmp_path / "a.jpg")
    result = FileConvertResult(source=src, output=out, status="success")
    assert result.can_delete_source() is True


def test_can_delete_source_false_when_skipped(tmp_path):
    src = make_image(tmp_path / "a.jpg")
    out = make_image(tmp_path / "a.png")
    result = FileConvertResult(source=src, output=out, status="skipped")
    assert result.can_delete_source() is False


def test_can_delete_source_false_when_failed(tmp_path):
    src = make_image(tmp_path / "a.png")
    out = make_image(tmp_path / "a.jpg")
    result = FileConvertResult(source=src, output=out, status="failed",
                               error="boom")
    assert result.can_delete_source() is False


def test_can_delete_source_false_when_output_none(tmp_path):
    src = make_image(tmp_path / "a.png")
    result = FileConvertResult(source=src, output=None, status="success")
    assert result.can_delete_source() is False


def test_can_delete_source_false_when_output_missing(tmp_path):
    src = make_image(tmp_path / "a.png")
    result = FileConvertResult(source=src, output=tmp_path / "missing.jpg",
                               status="success")
    assert result.can_delete_source() is False


def test_can_delete_source_false_when_same_file(tmp_path):
    src = make_image(tmp_path / "a.png")
    result = FileConvertResult(source=src, output=src, status="success")
    assert result.can_delete_source() is False


def test_file_convert_result_is_frozen_and_coerces_paths(tmp_path):
    result = FileConvertResult(
        source=str(tmp_path / "a.png"),
        output=str(tmp_path / "a.jpg"),
        status="success",
    )
    assert isinstance(result.source, Path)
    assert isinstance(result.output, Path)
    with pytest.raises(Exception):
        result.status = "failed"


# ----------------------------------------------------------------
# batch_convert_images: 逐文件结果与输出冲突保护
# ----------------------------------------------------------------

def test_batch_convert_all_success(tmp_path):
    srcs = [make_image(tmp_path / f"{n}.png") for n in ("a", "b", "c")]
    out_dir = tmp_path / "out"
    results = ic.batch_convert_images([str(p) for p in srcs], str(out_dir), ".jpg")
    assert [r.status for r in results] == ["success"] * 3
    assert all(r.output is not None and r.output.is_file() for r in results)
    assert all(r.error is None for r in results)


def test_batch_convert_partial_failure_returns_per_file_results(tmp_path):
    good = make_image(tmp_path / "good.png")
    bad = make_broken(tmp_path / "bad.png")
    results = ic.batch_convert_images(
        [str(good), str(bad)], str(tmp_path / "out"), ".jpg",
        skip_same_format=False)
    assert results[0].status == "success"
    assert results[1].status == "failed"
    assert results[1].output is None
    assert results[1].error and "失败" in results[1].error
    assert bad.exists()  # 转换失败不删源
    assert (tmp_path / "out" / "good.jpg").exists()


def test_batch_convert_all_failed(tmp_path):
    ghosts = [str(tmp_path / "ghost1.png"), str(tmp_path / "ghost2.png")]
    results = ic.batch_convert_images(ghosts, None, ".jpg",
                                      skip_same_format=False)
    assert [r.status for r in results] == ["failed", "failed"]
    assert all(r.output is None and r.error for r in results)


def test_batch_convert_pillow_unavailable_returns_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "Image", None)
    results = ic.batch_convert_images(
        [str(tmp_path / "a.png"), str(tmp_path / "b.png")], None, ".jpg")
    assert [r.status for r in results] == ["failed", "failed"]
    assert all("Pillow" in r.error for r in results)


def test_batch_convert_unsupported_target_returns_failed(tmp_path):
    src = make_image(tmp_path / "a.png")
    results = ic.batch_convert_images([str(src)], None, ".xyz")
    assert results[0].status == "failed"
    assert "不支持的目标格式" in results[0].error
    assert src.exists()


def test_batch_convert_skip_same_format(tmp_path):
    src = make_image(tmp_path / "a.png")
    results = ic.batch_convert_images([str(src)], None, ".png")
    assert results[0].status == "skipped"
    assert results[0].output is None and results[0].error is None


def test_batch_convert_skip_alias_jpeg_to_jpg(tmp_path):
    src = make_image(tmp_path / "a.jpeg")
    results = ic.batch_convert_images([str(src)], None, ".jpg")
    assert results[0].status == "skipped"
    assert src.exists()
    assert not (tmp_path / "a.jpg").exists()


def test_batch_convert_skip_alias_tif_to_tiff(tmp_path):
    src = make_image(tmp_path / "a.tif")
    results = ic.batch_convert_images([str(src)], None, ".tiff")
    assert results[0].status == "skipped"
    assert src.exists()
    assert not (tmp_path / "a.tiff").exists()


def test_batch_convert_duplicate_basename_distinct_outputs(tmp_path):
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    a1 = make_image(d1 / "a.png", color=(255, 0, 0))
    a2 = make_image(d2 / "a.png", color=(0, 255, 0))
    out_dir = tmp_path / "out"
    results = ic.batch_convert_images([str(a1), str(a2)], str(out_dir), ".jpg")
    assert [r.status for r in results] == ["success", "success"]
    outputs = [r.output for r in results]
    assert outputs[0] != outputs[1]
    assert all(p.is_file() for p in outputs)
    assert {p.name for p in outputs} == {"a.jpg", "a_1.jpg"}


def test_batch_convert_existing_output_not_overwritten(tmp_path):
    src = make_image(tmp_path / "a.png")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    existing = out_dir / "a.jpg"
    existing.write_bytes(b"sentinel")  # 已存在的输出文件
    results = ic.batch_convert_images([str(src)], str(out_dir), ".jpg")
    assert results[0].status == "success"
    assert results[0].output != existing
    assert existing.read_bytes() == b"sentinel"  # 既有文件未被覆盖
    assert results[0].output.is_file()


def test_batch_convert_output_conflict_does_not_overwrite_other_input(tmp_path):
    red_png = make_image(tmp_path / "a.png", color=(255, 0, 0))
    green_jpg = make_image(tmp_path / "a.jpg", color=(0, 255, 0))
    original_jpg = green_jpg.read_bytes()
    results = ic.batch_convert_images(
        [str(red_png), str(green_jpg)], None, ".jpg", skip_same_format=False)
    assert [r.status for r in results] == ["success", "success"]
    outputs = [r.output for r in results]
    assert outputs[0] != outputs[1]
    assert green_jpg.read_bytes() == original_jpg  # 另一输入未被覆盖
    assert red_png.exists() and green_jpg.exists()  # 两源都保留
    assert outputs[0].is_file() and outputs[1].is_file()


def test_convert_image_fails_when_output_not_written(monkeypatch, tmp_path):
    class _FakeImage:
        mode = "RGB"
        size = (1, 1)

        def save(self, path, format=None, **kwargs):
            pass  # 故意不写文件

        def close(self):
            pass

    class _FakePIL:
        @staticmethod
        def open(path):
            return _FakeImage()

        @staticmethod
        def new(*args, **kwargs):
            return _FakeImage()

    monkeypatch.setattr(ic, "Image", _FakePIL)
    ok, msg = ic.convert_image(str(tmp_path / "a.png"),
                               str(tmp_path / "a.jpg"),
                               target_format="JPEG")
    assert ok is False
    assert "输出文件未生成" in msg


# ----------------------------------------------------------------
# execute_image_convert: 覆盖模式删除门控
# ----------------------------------------------------------------

def test_execute_image_convert_all_success_deletes_sources(capsys, tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png")
    out_dir = tmp_path / "out"
    result = file_ex.execute_image_convert(
        image_args([a, b], output_dir=out_dir, overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    per_file = result.details["results"]
    assert [r.status for r in per_file] == ["success", "success"]
    assert {Path(p).name for p in result.outputs} == {"a.jpg", "b.jpg"}
    assert not a.exists() and not b.exists()
    assert (out_dir / "a.jpg").exists() and (out_dir / "b.jpg").exists()
    assert "已删除 2 个原文件" in capsys.readouterr().out


def test_execute_image_convert_partial_failure_keeps_failed_source(capsys, tmp_path):
    good = make_image(tmp_path / "good.png")
    bad = make_broken(tmp_path / "bad.png")
    out_dir = tmp_path / "out"
    result = file_ex.execute_image_convert(
        image_args([good, bad], output_dir=out_dir, overwrite=True,
                   skip_same=False))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert [r.status for r in result.details["results"]] == ["success", "failed"]
    assert not good.exists()  # A 成功 -> 删除
    assert bad.exists()  # B 失败 -> 源保留
    assert not (out_dir / "bad.jpg").exists()
    out = capsys.readouterr().out
    assert "已删除 1 个原文件" in out
    assert "部分转换失败" in out


def test_execute_image_convert_all_failed_zero_delete(capsys, tmp_path):
    b1 = make_broken(tmp_path / "b1.png")
    b2 = make_broken(tmp_path / "b2.png")
    result = file_ex.execute_image_convert(
        image_args([b1, b2], output_dir=tmp_path / "out", overwrite=True,
                   skip_same=False))
    assert result.status is TaskStatus.FAILED
    assert result.details["failure_count"] == 2
    assert [r.status for r in result.details["results"]] == ["failed", "failed"]
    assert b1.exists() and b2.exists()  # 零删除
    out = capsys.readouterr().out
    assert "已删除 0 个原文件" in out
    assert "没有可安全删除的原文件" in out


def test_execute_image_convert_skip_same_format_keeps_source(capsys, tmp_path):
    src = make_image(tmp_path / "a.png")
    result = file_ex.execute_image_convert(
        image_args([src], target_ext="png", overwrite=True, skip_same=True))
    # 全部跳过不是失败: SUCCESS + 跳过 warning, 源文件保留
    assert result.status is TaskStatus.SUCCESS
    assert "跳过" in result.message
    assert result.details["results"][0].status == "skipped"
    assert any("跳过" in warning for warning in result.warnings)
    assert src.exists()  # 跳过不删
    assert "没有可安全删除的原文件" in capsys.readouterr().out


def test_execute_image_convert_alias_jpeg_skip_keeps_source(capsys, tmp_path):
    src = make_image(tmp_path / "a.jpeg")
    result = file_ex.execute_image_convert(
        image_args([src], target_ext="jpg", overwrite=True, skip_same=True))
    assert result.status is TaskStatus.SUCCESS
    assert result.details["results"][0].status == "skipped"
    assert src.exists()  # .jpeg 被 skip 后绝不删除


def test_execute_image_convert_alias_tif_skip_keeps_source(capsys, tmp_path):
    src = make_image(tmp_path / "a.tif")
    result = file_ex.execute_image_convert(
        image_args([src], target_ext="tiff", overwrite=True, skip_same=True))
    assert result.status is TaskStatus.SUCCESS
    assert result.details["results"][0].status == "skipped"
    assert src.exists()  # .tif 被 skip 后绝不删除


def test_execute_image_convert_no_overwrite_keeps_all_sources(capsys, tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png")
    out_dir = tmp_path / "out"
    result = file_ex.execute_image_convert(
        image_args([a, b], output_dir=out_dir, overwrite=False))
    assert result.status is TaskStatus.SUCCESS
    assert [r.status for r in result.details["results"]] == ["success", "success"]
    assert a.exists() and b.exists()
    assert "已删除" not in capsys.readouterr().out


def test_execute_image_convert_output_missing_keeps_source(monkeypatch, capsys, tmp_path):
    src = make_image(tmp_path / "a.png")
    monkeypatch.setattr(
        file_ex, "batch_convert_images",
        lambda **kw: [FileConvertResult(
            source=src, output=tmp_path / "gone.jpg", status="success")])
    result = file_ex.execute_image_convert(image_args([src], overwrite=True))
    assert src.exists()  # 输出不存在 -> 不删源
    assert any("未删除源文件" in warning for warning in result.warnings)
    assert "没有可安全删除的原文件" in capsys.readouterr().out


def test_execute_image_convert_delete_failure_warns_and_continues(
        monkeypatch, capsys, tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png")
    out_dir = tmp_path / "out"
    real_remove = file_ex.os.remove

    def failing_remove(path):
        if os.path.basename(str(path)) == "a.png":
            raise OSError("locked")
        return real_remove(path)

    monkeypatch.setattr(file_ex.os, "remove", failing_remove)
    result = file_ex.execute_image_convert(
        image_args([a, b], output_dir=out_dir, overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.details["results"]) == 2
    assert a.exists()  # 删除失败 -> 源保留
    assert not b.exists()  # 其余继续删除
    assert any("删除失败" in warning for warning in result.warnings)
    out = capsys.readouterr().out
    assert "删除失败" in out
    assert "已删除 1 个原文件" in out
    assert "删除失败 1 个" in out


def test_execute_image_convert_output_conflict_keeps_both_sources(capsys, tmp_path):
    red_png = make_image(tmp_path / "a.png", color=(255, 0, 0))
    green_jpg = make_image(tmp_path / "a.jpg", color=(0, 255, 0))
    original_jpg = green_jpg.read_bytes()
    result = file_ex.execute_image_convert(
        image_args([red_png, green_jpg], overwrite=False, skip_same=False))
    assert result.status is TaskStatus.SUCCESS
    per_file = result.details["results"]
    assert [r.status for r in per_file] == ["success", "success"]
    assert red_png.exists() and green_jpg.exists()  # 两源都保留
    assert green_jpg.read_bytes() == original_jpg  # 另一输入未被覆盖
    assert len(result.outputs) == 2
    assert per_file[0].output != per_file[1].output
    assert all(Path(p).is_file() for p in result.outputs)


def test_execute_image_convert_returns_task_result(capsys, tmp_path):
    src = make_image(tmp_path / "a.png")
    result = file_ex.execute_image_convert(
        image_args([src], output_dir=tmp_path / "out", overwrite=False))
    assert isinstance(result, TaskResult)
    assert result.status is TaskStatus.SUCCESS

    # 自定义格式为空时提前返回 FAILED（仍打印错误提示）
    empty = file_ex.execute_image_convert(image_args([src], target_ext=""))
    assert isinstance(empty, TaskResult)
    assert empty.status is TaskStatus.FAILED
    assert "必须输入扩展名" in empty.message
    assert "必须输入扩展名" in capsys.readouterr().out


# ----------------------------------------------------------------
# execute_remux: 删除门槛与批内输出冲突
# ----------------------------------------------------------------

def test_execute_remux_success_overwrite_deletes_source(monkeypatch, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    outputs = []
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", fake_ffmpeg_ok(outputs))
    result = file_ex.execute_remux(
        remux_args([src], custom_ext="mp4", overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    assert result.outputs == (str(tmp_path / "a_remux.mp4"),)
    assert not src.exists()  # rc==0 且输出存在 -> 删除
    assert (tmp_path / "a_remux.mp4").exists()


def test_execute_remux_partial_failure_keeps_failed_source(monkeypatch, capsys, tmp_path):
    good = tmp_path / "good.mkv"
    bad = tmp_path / "bad.mkv"
    good.write_bytes(b"x")
    bad.write_bytes(b"y")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command",
                        fake_ffmpeg_partial_fail({"bad.mkv"}))
    result = file_ex.execute_remux(
        remux_args([good, bad], custom_ext="mp4", overwrite=True))
    assert result.status is TaskStatus.PARTIAL
    assert result.message == "成功 1 个, 失败 1 个"
    assert len(result.outputs) == 1
    assert not good.exists()  # 成功的源删除
    assert bad.exists()  # 失败的源 100% 保留
    assert not (tmp_path / "bad_remux.mp4").exists()
    out = capsys.readouterr().out
    assert "成功 1 个, 失败 1 个" in out


def test_execute_remux_output_missing_keeps_source(monkeypatch, capsys, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", fake_ffmpeg_no_output)
    result = file_ex.execute_remux(
        remux_args([src], custom_ext="mp4", overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    assert any("输出文件不存在" in w for w in result.warnings)
    assert src.exists()  # rc==0 但输出不存在 -> 保留源
    out = capsys.readouterr().out
    assert "输出文件不存在" in out
    assert "已删除 0 个原文件" in out


def test_execute_remux_nonzero_rc_keeps_source_even_with_output(
        monkeypatch, capsys, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")

    def failing_with_output(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"partial")  # 残留半成品输出
        return 1

    monkeypatch.setattr(file_ex, "run_ffmpeg_command", failing_with_output)
    result = file_ex.execute_remux(
        remux_args([src], custom_ext="mp4", overwrite=True))
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 1
    assert src.exists()  # rc!=0 -> 绝不删源
    out = capsys.readouterr().out
    assert "成功 0 个, 失败 1 个" in out


def test_execute_remux_output_conflict_gets_suffix(monkeypatch, tmp_path):
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    s1 = d1 / "a.mkv"
    s2 = d2 / "a.mkv"
    s1.write_bytes(b"x")
    s2.write_bytes(b"y")
    out_dir = tmp_path / "out"
    outputs = []
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", fake_ffmpeg_ok(outputs))
    result = file_ex.execute_remux(
        remux_args([s1, s2], custom_ext="mp4", output_dir=out_dir,
                   overwrite=False))
    assert result.status is TaskStatus.SUCCESS
    assert len(result.outputs) == 2
    names = sorted(Path(out).name for _, out in outputs)
    assert names == ["a_remux.mp4", "a_remux_1.mp4"]  # 批内冲突加 _1
    assert all(Path(out).is_file() for _, out in outputs)
    assert s1.exists() and s2.exists()  # 未开覆盖 -> 源保留


def test_execute_remux_samefile_guard_keeps_source(monkeypatch, capsys, tmp_path):
    src = tmp_path / "a.mkv"
    src.write_bytes(b"x")
    # 极端场景：输出被解析为源文件自身
    monkeypatch.setattr(file_ex, "auto_generate_output_path",
                        lambda input_path, suffix, extension=None: input_path)
    monkeypatch.setattr(file_ex, "run_ffmpeg_command", fake_ffmpeg_no_output)
    result = file_ex.execute_remux(
        remux_args([src], custom_ext="mkv", overwrite=True))
    assert result.status is TaskStatus.SUCCESS
    assert any("同一文件" in w for w in result.warnings)
    assert src.exists()
    out = capsys.readouterr().out
    assert "同一文件" in out
    assert "已删除 0 个原文件" in out
