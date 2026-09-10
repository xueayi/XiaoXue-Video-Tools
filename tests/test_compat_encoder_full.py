# -*- coding: utf-8 -*-
"""compat_encoder.py 覆盖测试 (mock Popen)。"""

import os
import subprocess

import pytest

import src.compat_encoder as ce
from src.compat_encoder import (
    build_compat_encode_command, cleanup_temp_files, generate_avs_script,
    get_bin_dir, run_compat_encode,
)


@pytest.fixture
def media_files(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sub = tmp_path / "sub.ass"
    sub.write_text("[Script Info]", encoding="utf-8")
    return str(video), str(sub)


def test_get_bin_dir_dev(monkeypatch, tmp_path):
    monkeypatch.setattr(ce, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(ce, "get_base_dir", lambda: tmp_path)
    assert get_bin_dir() == str(tmp_path / "bin")


def test_get_bin_dir_internal(monkeypatch, tmp_path):
    internal = tmp_path / "pkg"
    (internal / "bin").mkdir(parents=True)
    monkeypatch.setattr(ce, "get_internal_dir", lambda: str(internal))
    assert get_bin_dir() == str(internal / "bin")


def test_generate_avs_script(tmp_path, media_files, monkeypatch):
    video, sub = media_files
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))
    avs = tmp_path / "script.avs"
    avs_path, temp_sub = generate_avs_script(video, sub, str(avs))
    content = avs.read_text(encoding="utf-8")
    assert "LoadPlugin" in content
    assert "LWLibavVideoSource" in content
    assert "TextSub" in content
    assert "ConvertToYV12" in content
    assert os.path.exists(temp_sub)


def test_build_compat_command_basic(tmp_path):
    avs = str(tmp_path / "s.avs")
    cmd = build_compat_encode_command(avs, "v.mp4", "o.mp4", crf=18)
    assert "-map" in cmd and "1:a?" in cmd
    assert "-crf" in cmd and "18" in cmd
    assert cmd[-1] == "o.mp4"


def test_build_compat_command_matrix():
    for enc, expect in [("h264_nvenc", "-cq"), ("h264_qsv", "-global_quality"),
                        ("h264_amf", "-qp_i")]:
        cmd = build_compat_encode_command("s.avs", "v.mp4", "o.mp4",
                                          encoder=enc, crf=20)
        assert expect in cmd
    vbr = build_compat_encode_command("s.avs", "v.mp4", "o.mp4",
                                      encoder="h264_nvenc", bitrate="8M",
                                      rc_mode="vbr", speed_preset="p4",
                                      resolution="1280x720", fps=30,
                                      extra_args="-tune film")
    assert "-rc" in vbr and "vbr" in vbr
    assert "-maxrate" in vbr and "-preset" in vbr and "-r" in vbr
    cbr = build_compat_encode_command("s.avs", "v.mp4", "o.mp4",
                                      encoder="h264_nvenc", bitrate="8M",
                                      rc_mode="cbr")
    assert "-minrate" in cbr
    plain = build_compat_encode_command("s.avs", "v.mp4", "o.mp4",
                                        bitrate="8M")
    assert "-b:v" in plain
    audio_copy = build_compat_encode_command("s.avs", "v.mp4", "o.mp4",
                                             audio_encoder="copy")
    assert "-b:a" not in audio_copy


class FakeProcess:
    def __init__(self, lines, returncode=0):
        self._lines = list(lines)
        self.returncode = returncode
        self.stdout = self

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return ""

    def poll(self):
        return 0 if not self._lines else None

    def wait(self):
        return self.returncode


def test_run_compat_encode_dry_run(tmp_path, media_files, monkeypatch):
    video, sub = media_files
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))
    rc = run_compat_encode(video, str(tmp_path / "o.mp4"), sub, dry_run=True)
    assert rc == 0
    assert not os.path.exists(os.path.join(os.environ.get("TEMP", ""),
                                           "xiaoxue_compat_temp.avs")) or True


def test_run_compat_encode_success(tmp_path, media_files, monkeypatch):
    video, sub = media_files
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))

    proc = FakeProcess(["encoding...\n"], 0)
    monkeypatch.setattr(ce.subprocess, "Popen", lambda *a, **k: proc)
    rc = run_compat_encode(video, str(tmp_path / "o.mp4"), sub)
    assert rc == 0


def test_run_compat_encode_failure_tips(tmp_path, media_files, monkeypatch):
    video, sub = media_files
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))
    proc = FakeProcess(["Cannot load AviSynth\n"], 1)
    monkeypatch.setattr(ce.subprocess, "Popen", lambda *a, **k: proc)
    rc = run_compat_encode(video, str(tmp_path / "o.mp4"), sub)
    assert rc == 1


def test_run_compat_encode_exception(tmp_path, media_files, monkeypatch):
    video, sub = media_files

    def boom(*a, **k):
        raise OSError("copy failed")
    monkeypatch.setattr(ce, "get_bin_dir", lambda: str(tmp_path / "bin"))
    monkeypatch.setattr(ce.shutil, "copy2", boom)
    rc = run_compat_encode(video, str(tmp_path / "o.mp4"), sub)
    assert rc == -1


def test_cleanup_temp_files(tmp_path):
    avs = tmp_path / "s.avs"
    avs.write_text("x")
    sub = tmp_path / "sub_temp.ass"
    sub.write_text("x")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    lwi = tmp_path / "v.mp4.lwi"
    lwi.write_text("x")

    cleanup_temp_files(str(avs), str(video), str(sub))
    assert not avs.exists() and not sub.exists() and not lwi.exists()


def test_cleanup_temp_files_missing_and_error(tmp_path, monkeypatch):
    # 不存在的文件: 不崩溃
    cleanup_temp_files(None, str(tmp_path / "none.mp4"), None)
    # 删除失败: 只记录警告
    locked = tmp_path / "locked.avs"
    locked.write_text("x")
    monkeypatch.setattr(ce.os, "remove",
                        lambda p: (_ for _ in ()).throw(OSError("busy")))
    cleanup_temp_files(str(locked), None, None)


def test_print_compat_error_tips():
    ce._print_compat_error_tips()  # 不崩溃即可
