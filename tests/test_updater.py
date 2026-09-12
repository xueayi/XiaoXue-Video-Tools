# -*- coding: utf-8 -*-
"""updater.py 覆盖测试 (全部 mock 网络)。"""

import io
import os
import zipfile

import pytest

import src.updater as updater
from src.updater import (
    ReleaseInfo, UpdateError, cleanup_staging, download, ensure_disk_space,
    fetch_checksum, fetch_latest, get_skip_version, is_dev_version,
    is_newer, launch_updater, parse_checksums_from_body, parse_version,
    prepare, resolve_checksum, set_skip_version, sha256_of,
    verify_sha256, _pick_asset,
)


# ----------------------------------------------------------------
# 版本比较
# ----------------------------------------------------------------

@pytest.mark.parametrize("v, expect", [
    ("2.1.0", (2, 1, 0, 3, 0)),
    ("v2.1.0", (2, 1, 0, 3, 0)),
    ("2.1.0-beta", (2, 1, 0, 1, 0)),
    ("2.1.0-beta.2", (2, 1, 0, 1, 2)),
    ("2.1.0-rc.1", (2, 1, 0, 2, 1)),
    ("2.1.0-alpha.3", (2, 1, 0, 0, 3)),
    (" 垃圾输入 ", None),
    ("", None),
])
def test_parse_version(v, expect):
    assert parse_version(v) == expect


@pytest.mark.parametrize("remote, local, expect", [
    ("2.2.0", "2.1.0", True),
    ("2.1.0", "2.1.0", False),
    ("2.1.0", "2.2.0", False),
    ("2.1.0", "2.1.0-beta", True),
    ("2.1.0-rc.1", "2.1.0-beta.9", True),
    ("10.0.0", "2.9.9", True),
])
def test_is_newer(remote, local, expect):
    assert is_newer(remote, local) is expect


def test_is_newer_unparseable():
    assert is_newer("garbage", "2.1.0") is False
    assert is_newer("2.1.0", "garbage") is False


def test_is_dev_version():
    assert is_dev_version("2.0.0-dev") is True
    assert is_dev_version("2.1.0") is False


# ----------------------------------------------------------------
# 资产挑选
# ----------------------------------------------------------------

ASSETS = [
    {"name": "XiaoXueToolbox_v2.2.0_Windows_x64.zip",
     "browser_download_url": "https://dl/std.zip", "size": 10},
    {"name": "XiaoXueToolbox_v2.2.0_Shield_Windows_x64.zip",
     "browser_download_url": "https://dl/shield.zip", "size": 20},
]


def test_pick_asset_standard_excludes_shield():
    a = _pick_asset(ASSETS, shield=False)
    assert a["browser_download_url"] == "https://dl/std.zip"


def test_pick_asset_shield():
    a = _pick_asset(ASSETS, shield=True)
    assert a["browser_download_url"] == "https://dl/shield.zip"


def test_pick_asset_missing():
    with pytest.raises(UpdateError):
        _pick_asset([], shield=False)


# ----------------------------------------------------------------
# fetch_latest
# ----------------------------------------------------------------

def api_response(payload, status_code=200):
    class R:
        def __init__(self):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError("bad json")
            return self._payload
    return R()


RELEASE_PAYLOAD = {
    "tag_name": "v2.2.0",
    "body": "更新说明",
    "published_at": "2026-09-12T00:00:00Z",
    "html_url": "https://github.com/xueayi/XiaoXue-Video-Tools/releases/tag/v2.2.0",
    "assets": ASSETS,
}


def test_fetch_latest_has_update(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: api_response(RELEASE_PAYLOAD))
    info = fetch_latest("2.1.0", shield=False)
    assert info.version == "2.2.0"
    assert info.asset_url == "https://dl/std.zip"
    assert info.sha256_url == "https://dl/std.zip.sha256"
    assert info.asset_size == 10
    assert "更新说明" in info.notes


def test_fetch_latest_shield_variant(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: api_response(RELEASE_PAYLOAD))
    info = fetch_latest("2.1.0", shield=True)
    assert info.asset_url == "https://dl/shield.zip"


def test_fetch_latest_no_update(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: api_response(RELEASE_PAYLOAD))
    assert fetch_latest("2.2.0") is None
    assert fetch_latest("2.3.0") is None


def test_fetch_latest_network_error(monkeypatch):
    import requests as requests_mod
    import src.updater as m

    def boom(*a, **k):
        raise requests_mod.exceptions.ConnectionError("断网")
    monkeypatch.setattr(m.requests, "get", boom)
    with pytest.raises(UpdateError, match="无法连接"):
        fetch_latest("2.1.0")


def test_fetch_latest_http_error(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: api_response(None, 403))
    with pytest.raises(UpdateError, match="403"):
        fetch_latest("2.1.0")


def test_fetch_latest_bad_json(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: api_response(None))
    with pytest.raises(UpdateError, match="解析失败"):
        fetch_latest("2.1.0")


# ----------------------------------------------------------------
# 磁盘空间
# ----------------------------------------------------------------

def test_ensure_disk_space_zero_size_skips(tmp_path):
    ensure_disk_space(str(tmp_path), 0)  # 不检查, 不抛


def test_ensure_disk_space_insufficient(tmp_path):
    with pytest.raises(UpdateError, match="磁盘空间不足"):
        ensure_disk_space(str(tmp_path), 1 << 60)


def test_ensure_disk_space_ok(tmp_path):
    ensure_disk_space(str(tmp_path), 1024)


# ----------------------------------------------------------------
# 下载
# ----------------------------------------------------------------

class FakeStreamResp:
    def __init__(self, status_code=200, chunks=(b"hello ", b"world"),
                 headers=None, fail_after=None):
        self.status_code = status_code
        self._chunks = list(chunks)
        self._fail_after = fail_after
        self.headers = headers or {}
        self.request_headers = None

    def iter_content(self, chunk_size):
        sent = 0
        for c in self._chunks:
            if self._fail_after is not None and sent >= self._fail_after:
                import requests as r
                raise r.exceptions.ChunkedEncodingError("connection reset")
            sent += 1
            yield c


def test_download_full(monkeypatch, tmp_path):
    import src.updater as m
    seen = {}

    def fake_get(url, headers=None, stream=True, timeout=None):
        seen["headers"] = headers
        return FakeStreamResp(headers={"Content-Length": "11"})
    monkeypatch.setattr(m.requests, "get", fake_get)

    dest = str(tmp_path / "update.zip")
    got = []
    download("https://dl/x.zip", dest,
             progress_cb=lambda d, t: got.append((d, t)))
    assert open(dest, "rb").read() == b"hello world"
    assert got[-1] == (11, 11)
    assert not os.path.exists(dest + ".part")


def test_download_resume(monkeypatch, tmp_path):
    import src.updater as m
    dest = str(tmp_path / "update.zip")
    with open(dest + ".part", "wb") as f:
        f.write(b"hello ")

    def fake_get(url, headers=None, stream=True, timeout=None):
        assert headers["Range"] == "bytes=6-"
        return FakeStreamResp(status_code=206, chunks=(b"world",),
                              headers={"Content-Length": "5"})
    monkeypatch.setattr(m.requests, "get", fake_get)
    download("https://dl/x.zip", dest)
    assert open(dest, "rb").read() == b"hello world"


def test_download_resume_unsupported_restarts(monkeypatch, tmp_path):
    import src.updater as m
    dest = str(tmp_path / "update.zip")
    with open(dest + ".part", "wb") as f:
        f.write(b"OLD")

    def fake_get(url, headers=None, stream=True, timeout=None):
        assert "Range" in headers  # 仍携带 Range, 但服务器回 200
        return FakeStreamResp(status_code=200, chunks=(b"new",),
                              headers={"Content-Length": "3"})
    monkeypatch.setattr(m.requests, "get", fake_get)
    download("https://dl/x.zip", dest)
    assert open(dest, "rb").read() == b"new"


def test_download_cancel(monkeypatch, tmp_path):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: FakeStreamResp())
    dest = str(tmp_path / "update.zip")
    with pytest.raises(UpdateError, match="已取消"):
        download("https://dl/x.zip", dest, check_cancel=lambda: True)
    assert os.path.exists(dest + ".part")  # 进度保留供续传
    assert not os.path.exists(dest)


def test_download_http_error(monkeypatch, tmp_path):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: FakeStreamResp(status_code=404))
    with pytest.raises(UpdateError, match="404"):
        download("https://dl/x.zip", str(tmp_path / "u.zip"))


def test_download_connection_error(monkeypatch, tmp_path):
    import requests as requests_mod
    import src.updater as m

    def fake_get(*a, **k):
        raise requests_mod.exceptions.ConnectionError("x")
    monkeypatch.setattr(m.requests, "get", fake_get)
    with pytest.raises(UpdateError, match="下载请求失败"):
        download("https://dl/x.zip", str(tmp_path / "u.zip"))


def test_download_interrupted_keeps_part(monkeypatch, tmp_path):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: FakeStreamResp(fail_after=1))
    dest = str(tmp_path / "update.zip")
    with pytest.raises(UpdateError, match="下载中断"):
        download("https://dl/x.zip", dest)
    assert os.path.exists(dest + ".part")


# ----------------------------------------------------------------
# 校验和
# ----------------------------------------------------------------

def test_sha256_roundtrip(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"data")
    digest = sha256_of(str(f))
    assert verify_sha256(str(f), digest)
    assert not verify_sha256(str(f), "0" * 64)


def test_fetch_checksum_ok(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: _text_resp("abc123\n"))
    assert fetch_checksum("https://dl/x.sha256") == "abc123"


def _text_resp(text, status_code=200):
    class R:
        def __init__(self):
            self.status_code = status_code
            self.text = text
    return R()


def test_fetch_checksum_404_returns_none(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: _text_resp("", 404))
    assert fetch_checksum("https://dl/x.sha256") is None


def test_fetch_checksum_empty(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: _text_resp("  \n"))
    assert fetch_checksum("https://dl/x.sha256") is None


def test_fetch_checksum_http_error(monkeypatch):
    import src.updater as m
    monkeypatch.setattr(m.requests, "get",
                        lambda *a, **k: _text_resp("", 500))
    with pytest.raises(UpdateError):
        fetch_checksum("https://dl/x.sha256")


def test_fetch_checksum_network_error(monkeypatch):
    import requests as requests_mod
    import src.updater as m

    def boom(*a, **k):
        raise requests_mod.exceptions.Timeout()
    monkeypatch.setattr(m.requests, "get", boom)
    with pytest.raises(UpdateError, match="校验和下载失败"):
        fetch_checksum("https://dl/x.sha256")


# ----------------------------------------------------------------
# 跳过版本 (QSettings)
# ----------------------------------------------------------------

@pytest.fixture
def isolated_qsettings(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings

    ini = tmp_path / "config.ini"

    def fake_qsettings():
        return QSettings(str(ini), QSettings.Format.IniFormat)

    import src.gui_config as gc
    monkeypatch.setattr(gc, "get_qsettings", fake_qsettings)


def test_skip_version_roundtrip(isolated_qsettings):
    assert get_skip_version() == ""
    set_skip_version("2.2.0")
    assert get_skip_version() == "2.2.0"


# ----------------------------------------------------------------
# prepare / launch / cleanup
# ----------------------------------------------------------------

def make_update_zip(tmp_path, name="update.zip", with_exe=True,
                    with_internal=True):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        if with_exe:
            zf.writestr("小雪工具箱.exe", "MZWLOADER")
        if with_internal:
            zf.writestr("_internal/run.py", "print('hi')")
    return str(path)


def test_prepare_ok(tmp_path):
    zip_path = make_update_zip(tmp_path)
    ps1 = prepare(zip_path, str(tmp_path), "2.2.0")
    assert os.path.exists(ps1)
    assert ps1.endswith(os.path.join("_update", "updater.ps1"))
    raw = open(ps1, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM, PowerShell 5.1 兼容
    assert b"param(" in raw
    new_dir = tmp_path / "_update" / "new"
    assert (new_dir / "version.txt").read_text(encoding="utf-8") == "2.2.0"
    assert (new_dir / "_internal" / "run.py").exists()


def test_prepare_removes_stale_new_dir(tmp_path):
    stale = tmp_path / "_update" / "new"
    stale.mkdir(parents=True)
    (stale / "junk.txt").write_text("x")
    zip_path = make_update_zip(tmp_path)
    prepare(zip_path, str(tmp_path), "2.2.0")
    assert not (stale / "junk.txt").exists()


def test_prepare_bad_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(UpdateError, match="解压失败"):
        prepare(str(bad), str(tmp_path), "2.2.0")


def test_prepare_missing_exe(tmp_path):
    zip_path = make_update_zip(tmp_path, with_exe=False)
    with pytest.raises(UpdateError, match="未找到主程序"):
        prepare(zip_path, str(tmp_path), "2.2.0")


def test_prepare_missing_internal(tmp_path):
    zip_path = make_update_zip(tmp_path, with_internal=False)
    with pytest.raises(UpdateError, match="运行时目录"):
        prepare(zip_path, str(tmp_path), "2.2.0")


def test_launch_updater(monkeypatch, tmp_path):
    import src.updater as m
    captured = {}

    def fake_popen(args, creationflags=0, close_fds=False):
        captured["args"] = args
        captured["flags"] = creationflags
        return object()
    monkeypatch.setattr(m.subprocess, "Popen", fake_popen)
    launch_updater(str(tmp_path), 12345)
    args = captured["args"]
    assert args[0] == "powershell"
    assert "-File" in args
    assert str(tmp_path / "_update" / "updater.ps1") in args
    assert "12345" in args
    assert captured["flags"] != 0  # Windows 下带 NO_WINDOW | DETACHED


def test_cleanup_staging(tmp_path):
    (tmp_path / "_backup").mkdir()
    (tmp_path / "_backup" / "x").write_text("x")
    (tmp_path / "_update").mkdir()
    cleanup_staging(str(tmp_path))
    assert not (tmp_path / "_backup").exists()
    assert not (tmp_path / "_update").exists()
    cleanup_staging(str(tmp_path))  # 不存在时也安全


def test_release_info_defaults():
    info = ReleaseInfo(version="2.2.0", asset_name="a.zip",
                       asset_url="u", asset_size=1, sha256_url="s")
    assert info.notes == "" and info.html_url == ""


# ----------------------------------------------------------------
# Release 正文校验和
# ----------------------------------------------------------------

BODY_WITH_SHA = (
    "## 小雪工具箱 v2.2.1" + chr(10) + chr(10) +
    "### 下载说明" + chr(10) + chr(10) +
    "- 解压后运行 小雪工具箱.exe" + chr(10) + chr(10) +
    "### SHA256 校验和" + chr(10) + chr(10) +
    "```" + chr(10) +
    "a" * 64 + "  XiaoXueToolbox_v2.2.1_Windows_x64.zip" + chr(10) +
    "b" * 64 + "  XiaoXueToolbox_v2.2.1_Shield_Windows_x64.zip" + chr(10) +
    "```" + chr(10)
)


def test_parse_checksums_from_body():
    from src.updater import parse_checksums_from_body
    got = parse_checksums_from_body(BODY_WITH_SHA)
    assert got == {
        "XiaoXueToolbox_v2.2.1_Windows_x64.zip": "a" * 64,
        "XiaoXueToolbox_v2.2.1_Shield_Windows_x64.zip": "b" * 64,
    }


def test_parse_checksums_no_section():
    from src.updater import parse_checksums_from_body
    assert parse_checksums_from_body("普通说明, 无校验段") == {}
    assert parse_checksums_from_body("") == {}
    assert parse_checksums_from_body(None) == {}


def test_parse_checksums_stops_at_next_heading():
    from src.updater import parse_checksums_from_body
    body = ("### SHA256 校验和" + chr(10) +
            "c" * 64 + "  a.zip" + chr(10) +
            "### 下一段" + chr(10) +
            "d" * 64 + "  b.zip" + chr(10))
    got = parse_checksums_from_body(body)
    assert got == {"a.zip": "c" * 64}  # 段落到下一个标题为止


def test_parse_checksums_skips_invalid_lines():
    from src.updater import parse_checksums_from_body
    body = ("### SHA256 校验和" + chr(10) +
            "not-a-hash  bad.zip" + chr(10) +
            "e" * 64 + "  good.zip" + chr(10))
    got = parse_checksums_from_body(body)
    assert got == {"good.zip": "e" * 64}


def _release(notes, sha_url="https://dl/x.zip.sha256"):
    return ReleaseInfo(
        version="2.2.1",
        asset_name="XiaoXueToolbox_v2.2.1_Windows_x64.zip",
        asset_url="https://dl/x.zip", asset_size=10,
        sha256_url=sha_url, notes=notes)


def test_resolve_checksum_prefers_body(monkeypatch):
    called = []
    monkeypatch.setattr(updater, "fetch_checksum",
                        lambda url: called.append(url))
    got = resolve_checksum(_release(BODY_WITH_SHA))
    assert got == "a" * 64
    assert called == []  # 正文命中, 不再请求资产


def test_resolve_checksum_falls_back_to_asset(monkeypatch):
    monkeypatch.setattr(updater, "fetch_checksum",
                        lambda url: "f" * 64)
    got = resolve_checksum(_release("无校验段的正文"))
    assert got == "f" * 64


def test_resolve_checksum_all_missing(monkeypatch):
    monkeypatch.setattr(updater, "fetch_checksum",
                        lambda url: None)
    assert resolve_checksum(_release("", sha_url="")) is None
