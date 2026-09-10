# -*- coding: utf-8 -*-
"""qc.py 覆盖测试。"""

import pytest

import src.qc as qc
from src.qc import (
    MediaInfo, check_compatibility, detect_image_format_by_header,
    generate_report, get_expected_extension, probe_media, scan_directory,
)


def write_magic(tmp_path, name, magic):
    p = tmp_path / name
    p.write_bytes(magic + b"\x00" * 8)
    return p


# ----------------------------------------------------------------
# 文件头检测
# ----------------------------------------------------------------

@pytest.mark.parametrize("name, magic, expect", [
    ("a.jpg", b"\xff\xd8\xff\xe0", "jpeg"),
    ("a.png", b"\x89PNG\r\n\x1a\n", "png"),
    ("a.gif", b"GIF89a", "gif"),
    ("a.bmp", b"BM", "bmp"),
    ("a.tif", b"II*\x00", "tiff"),
    ("b.tif", b"MM\x00*", "tiff"),
    ("a.webp", b"RIFF\x00\x00\x00\x00WEBP", "webp"),
    ("a.heic", b"\x00\x00\x00\x18ftypheic", "heic"),
    ("a.avif", b"\x00\x00\x00\x18ftypavif", "avif"),
    ("a.txt", b"just text here!!", None),
])
def test_detect_image_format(tmp_path, name, magic, expect):
    p = write_magic(tmp_path, name, magic)
    assert detect_image_format_by_header(str(p)) == expect


def test_detect_image_format_edge_cases(tmp_path):
    short = tmp_path / "short.bin"
    short.write_bytes(b"\x01\x02")
    assert detect_image_format_by_header(str(short)) is None
    assert detect_image_format_by_header(str(tmp_path / "none")) is None


def test_get_expected_extension():
    assert get_expected_extension("jpeg") == ".jpg"
    assert get_expected_extension("unknown") == ""


# ----------------------------------------------------------------
# probe_media
# ----------------------------------------------------------------

GOOD_JSON = {
    "format": {"duration": "10.0", "bit_rate": "5000000"},
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920,
         "height": 1080, "r_frame_rate": "30000/1001"},
        {"codec_type": "audio", "codec_name": "aac", "bit_rate": "192000"},
    ],
}


def test_probe_media_success(monkeypatch, tmp_path):
    class R:
        returncode = 0
        stdout = json.dumps(GOOD_JSON)
        stderr = ""
    import src.qc as m
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: R())
    import json as _json
    info = probe_media("x.mp4")
    assert info.video_codec == "h264"
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.audio_codec == "aac"


import json  # noqa: E402


def test_probe_media_nonzero(monkeypatch, tmp_path):
    class R:
        returncode = 1
        stdout = ""
        stderr = "bad file"
    import src.qc as m
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: R())
    info = probe_media("x.mp4")
    assert info.is_valid is False
    assert "无法读取文件" in info.errors[0]


def test_probe_media_exception(monkeypatch, tmp_path):
    import src.qc as m
    monkeypatch.setattr(m.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    info = probe_media("x.mp4")
    assert info.is_valid is False
    assert "探测失败" in info.errors[0]


def test_parse_bad_fps(monkeypatch, tmp_path):
    data = {"format": {}, "streams": [
        {"codec_type": "video", "codec_name": "h264",
         "r_frame_rate": "a/b"}]}
    info = qc._parse_ffprobe_output("x.mp4", data)
    assert info.fps == 0


# ----------------------------------------------------------------
# check_compatibility
# ----------------------------------------------------------------

def base_info(**kw):
    defaults = dict(path="C:/v.mp4")
    defaults.update(kw)
    return MediaInfo(**defaults)


def test_compat_bitrate_thresholds():
    info = check_compatibility(base_info(bitrate_kbps=9000),
                               max_bitrate_kbps=8000)
    assert any("超过最大阈值" in w for w in info.warnings)
    info2 = check_compatibility(base_info(bitrate_kbps=100),
                                min_bitrate_kbps=500)
    assert any("低于最小阈值" in w for w in info2.warnings)


def test_compat_resolution_thresholds():
    info = check_compatibility(base_info(width=3840, height=2160),
                               max_resolution="1920x1080")
    assert any("超过最大阈值" in w for w in info.warnings)
    info2 = check_compatibility(base_info(width=640, height=480),
                                min_resolution="1920x1080")
    assert any("低于最小阈值" in w for w in info2.warnings)
    info3 = check_compatibility(base_info(width=100, height=100),
                                max_resolution="bad")
    assert info3.warnings == []
    info4 = check_compatibility(base_info(width=100, height=100),
                                min_resolution="bad")
    assert info4.warnings == []


def test_compat_container_and_codec():
    info = check_compatibility(base_info(path="C:/v.mkv",
                                         video_codec="vp9"))
    assert any("容器" in w for w in info.warnings)
    assert any("编码" in w for w in info.warnings)


def test_compat_mkv_hint():
    info = check_compatibility(base_info(path="C:/v.mkv"))
    assert any("MKV" in w for w in info.warnings)


def test_compat_custom_rules():
    info = check_compatibility(base_info(),
                               incompatible_containers={".xyz"},
                               incompatible_codecs={"weird"},
                               check_pr_image=False)
    assert not any("MKV" in w for w in info.warnings)


def test_compat_image_format_error_and_mismatch(tmp_path):
    # webp 后缀 + webp 内容 -> 错误
    img = tmp_path / "pic.webp"
    img.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8)
    info = MediaInfo(path=str(img))
    checked = check_compatibility(info, check_pr_image=True,
                                  check_pr_video=False)
    assert any("不被支持" in e for e in checked.errors)

    # jpg 后缀 + png 内容 -> 格式不匹配警告
    mismatch = tmp_path / "fake.jpg"
    mismatch.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    info2 = MediaInfo(path=str(mismatch))
    checked2 = check_compatibility(info2, check_pr_image=True,
                                   check_pr_video=False)
    assert any("格式不匹配" in w for w in checked2.warnings)


# ----------------------------------------------------------------
# scan_directory / generate_report
# ----------------------------------------------------------------

def test_scan_directory_with_mock(monkeypatch, tmp_path):
    make = tmp_path / "a.mp4"
    make.write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")

    def fake_probe(path):
        info = MediaInfo(path=path, video_codec="h264", width=1920,
                         height=1080)
        return info
    monkeypatch.setattr(qc, "probe_media", fake_probe)
    results = scan_directory(str(tmp_path), check_pr_video=True)
    assert len(results) == 2


def test_generate_report_mixed(tmp_path):
    ok = MediaInfo(path="C:/ok.mp4", video_codec="h264", width=1920,
                   height=1080)
    warn = MediaInfo(path="C:/w.mkv")
    warn.warnings.append("MKV 提示")
    err = MediaInfo(path="C:/e.mp4")
    err.is_valid = False
    err.errors.append("无法读取")
    out = tmp_path / "qc.txt"
    content = generate_report([ok, warn, err], str(out))
    assert out.exists()
    assert "✗" in content and "⚠" in content and "✓" in content
