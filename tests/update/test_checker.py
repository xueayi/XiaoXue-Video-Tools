# -*- coding: utf-8 -*-
"""GitHub Release 检查 / 下载 / SHA256 测试 (M4.2)。

迁移映射 (自 tests/test_updater.py, 断言强度不变):
    * test_pick_asset_standard / test_pick_asset_missing
    * test_fetch_latest_has_update / no_update / network_error / http_error /
      bad_json
    * test_download_full / resume / resume_unsupported_restarts / cancel /
      http_error / connection_error / interrupted_keeps_part
    * test_sha256_roundtrip
    * test_fetch_checksum_ok / 404_returns_none / empty / http_error /
      network_error
    * test_release_info_defaults
    * test_parse_checksums_from_body / no_section / stops_at_next_heading /
      skips_invalid_lines
    * test_resolve_checksum_prefers_body / falls_back_to_asset / all_missing
新增: find_asset、check-only 场景 allow_missing_asset (require_asset=False)。
"""

import os

import pytest

import src.update.checker as checker
from src.update.checker import (
    CHUNK_SIZE,
    ReleaseInfo,
    UpdateError,
    _pick_asset,
    download,
    fetch_checksum,
    fetch_latest,
    find_asset,
    parse_checksums_from_body,
    resolve_checksum,
    sha256_of,
    verify_sha256,
)


# ----------------------------------------------------------------
# 资产挑选
# ----------------------------------------------------------------

ASSETS = [
    {"name": "XiaoXueToolbox_v2.2.0_Windows_x64.zip",
     "browser_download_url": "https://dl/std.zip", "size": 10},
]


def test_pick_asset_standard():
    a = _pick_asset(ASSETS)
    assert a["browser_download_url"] == "https://dl/std.zip"


def test_pick_asset_missing():
    with pytest.raises(UpdateError):
        _pick_asset([])


def test_find_asset_returns_none_instead_of_raising():
    assert find_asset(ASSETS) is not None
    assert find_asset(ASSETS, "_macOS_arm64.zip") is None
    assert find_asset([], "_Windows_x64.zip") is None


def test_find_asset_respects_suffix():
    assets = [{"name": "x_macOS_arm64.zip", "browser_download_url": "u"}]
    assert find_asset(assets, "_macOS_arm64.zip")["browser_download_url"] == "u"
    assert find_asset(assets, "_Windows_x64.zip") is None


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
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(RELEASE_PAYLOAD))
    info = fetch_latest("2.1.0")
    assert info.version == "2.2.0"
    assert info.asset_url == "https://dl/std.zip"
    assert info.sha256_url == "https://dl/std.zip.sha256"
    assert info.asset_size == 10
    assert "更新说明" in info.notes


def test_fetch_latest_no_update(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(RELEASE_PAYLOAD))
    assert fetch_latest("2.2.0") is None
    assert fetch_latest("2.3.0") is None


def test_fetch_latest_network_error(monkeypatch):
    import requests as requests_mod

    def boom(*a, **k):
        raise requests_mod.exceptions.ConnectionError("断网")
    monkeypatch.setattr(checker.requests, "get", boom)
    with pytest.raises(UpdateError, match="无法连接"):
        fetch_latest("2.1.0")


def test_fetch_latest_http_error(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(None, 403))
    with pytest.raises(UpdateError, match="403"):
        fetch_latest("2.1.0")


def test_fetch_latest_bad_json(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(None))
    with pytest.raises(UpdateError, match="解析失败"):
        fetch_latest("2.1.0")


def test_fetch_latest_requires_asset_by_default(monkeypatch):
    payload = dict(RELEASE_PAYLOAD, assets=[])
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(payload))
    with pytest.raises(UpdateError, match="匹配的安装包"):
        fetch_latest("2.1.0")


def test_fetch_latest_check_only_allows_missing_asset(monkeypatch):
    """macOS check-only: 发行页没有当前平台资产也必须能拿到版本信息。"""
    payload = dict(RELEASE_PAYLOAD, assets=[])
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(payload))

    info = fetch_latest("2.1.0", require_asset=False)

    assert info is not None
    assert info.version == "2.2.0"
    assert info.asset_name == "" and info.asset_url == ""
    assert info.sha256_url == ""
    assert "更新说明" in info.notes
    assert info.html_url.endswith("/v2.2.0")


def test_fetch_latest_check_only_still_compares_versions(monkeypatch):
    payload = dict(RELEASE_PAYLOAD, assets=[])
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: api_response(payload))
    assert fetch_latest("2.2.0", require_asset=False) is None


def test_chunk_size_constant():
    assert CHUNK_SIZE == 256 * 1024


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
    seen = {}

    def fake_get(url, headers=None, stream=True, timeout=None):
        seen["headers"] = headers
        return FakeStreamResp(headers={"Content-Length": "11"})
    monkeypatch.setattr(checker.requests, "get", fake_get)

    dest = str(tmp_path / "update.zip")
    got = []
    download("https://dl/x.zip", dest,
             progress_cb=lambda d, t: got.append((d, t)))
    assert open(dest, "rb").read() == b"hello world"
    assert got[-1] == (11, 11)
    assert not os.path.exists(dest + ".part")


def test_download_resume(monkeypatch, tmp_path):
    dest = str(tmp_path / "update.zip")
    with open(dest + ".part", "wb") as f:
        f.write(b"hello ")

    def fake_get(url, headers=None, stream=True, timeout=None):
        assert headers["Range"] == "bytes=6-"
        return FakeStreamResp(status_code=206, chunks=(b"world",),
                              headers={"Content-Length": "5"})
    monkeypatch.setattr(checker.requests, "get", fake_get)
    download("https://dl/x.zip", dest)
    assert open(dest, "rb").read() == b"hello world"


def test_download_resume_unsupported_restarts(monkeypatch, tmp_path):
    dest = str(tmp_path / "update.zip")
    with open(dest + ".part", "wb") as f:
        f.write(b"OLD")

    def fake_get(url, headers=None, stream=True, timeout=None):
        assert "Range" in headers  # 仍携带 Range, 但服务器回 200
        return FakeStreamResp(status_code=200, chunks=(b"new",),
                              headers={"Content-Length": "3"})
    monkeypatch.setattr(checker.requests, "get", fake_get)
    download("https://dl/x.zip", dest)
    assert open(dest, "rb").read() == b"new"


def test_download_cancel(monkeypatch, tmp_path):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: FakeStreamResp())
    dest = str(tmp_path / "update.zip")
    with pytest.raises(UpdateError, match="已取消"):
        download("https://dl/x.zip", dest, check_cancel=lambda: True)
    assert os.path.exists(dest + ".part")  # 进度保留供续传
    assert not os.path.exists(dest)


def test_download_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: FakeStreamResp(status_code=404))
    with pytest.raises(UpdateError, match="404"):
        download("https://dl/x.zip", str(tmp_path / "u.zip"))


def test_download_connection_error(monkeypatch, tmp_path):
    import requests as requests_mod

    def fake_get(*a, **k):
        raise requests_mod.exceptions.ConnectionError("x")
    monkeypatch.setattr(checker.requests, "get", fake_get)
    with pytest.raises(UpdateError, match="下载请求失败"):
        download("https://dl/x.zip", str(tmp_path / "u.zip"))


def test_download_interrupted_keeps_part(monkeypatch, tmp_path):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: FakeStreamResp(fail_after=1))
    dest = str(tmp_path / "update.zip")
    with pytest.raises(UpdateError, match="下载中断"):
        download("https://dl/x.zip", dest)
    assert os.path.exists(dest + ".part")


# ----------------------------------------------------------------
# SHA256 / 校验和
# ----------------------------------------------------------------

def test_sha256_roundtrip(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"data")
    digest = sha256_of(str(f))
    assert verify_sha256(str(f), digest)
    assert not verify_sha256(str(f), "0" * 64)


def test_fetch_checksum_ok(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _text_resp("abc123\n"))
    assert fetch_checksum("https://dl/x.sha256") == "abc123"


def _text_resp(text, status_code=200):
    class R:
        def __init__(self):
            self.status_code = status_code
            self.text = text
    return R()


def test_fetch_checksum_404_returns_none(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _text_resp("", 404))
    assert fetch_checksum("https://dl/x.sha256") is None


def test_fetch_checksum_empty(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _text_resp("  \n"))
    assert fetch_checksum("https://dl/x.sha256") is None


def test_fetch_checksum_http_error(monkeypatch):
    monkeypatch.setattr(checker.requests, "get",
                        lambda *a, **k: _text_resp("", 500))
    with pytest.raises(UpdateError):
        fetch_checksum("https://dl/x.sha256")


def test_fetch_checksum_network_error(monkeypatch):
    import requests as requests_mod

    def boom(*a, **k):
        raise requests_mod.exceptions.Timeout()
    monkeypatch.setattr(checker.requests, "get", boom)
    with pytest.raises(UpdateError, match="校验和下载失败"):
        fetch_checksum("https://dl/x.sha256")


def test_fetch_checksum_empty_url_returns_none():
    assert fetch_checksum("") is None


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
    "```" + chr(10)
)


def test_parse_checksums_from_body():
    got = parse_checksums_from_body(BODY_WITH_SHA)
    assert got == {
        "XiaoXueToolbox_v2.2.1_Windows_x64.zip": "a" * 64,
    }


def test_parse_checksums_no_section():
    assert parse_checksums_from_body("普通说明, 无校验段") == {}
    assert parse_checksums_from_body("") == {}
    assert parse_checksums_from_body(None) == {}


def test_parse_checksums_stops_at_next_heading():
    body = ("### SHA256 校验和" + chr(10) +
            "c" * 64 + "  a.zip" + chr(10) +
            "### 下一段" + chr(10) +
            "d" * 64 + "  b.zip" + chr(10))
    got = parse_checksums_from_body(body)
    assert got == {"a.zip": "c" * 64}  # 段落到下一个标题为止


def test_parse_checksums_skips_invalid_lines():
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
    monkeypatch.setattr(checker, "fetch_checksum",
                        lambda url: called.append(url))
    got = resolve_checksum(_release(BODY_WITH_SHA))
    assert got == "a" * 64
    assert called == []  # 正文命中, 不再请求资产


def test_resolve_checksum_falls_back_to_asset(monkeypatch):
    monkeypatch.setattr(checker, "fetch_checksum",
                        lambda url: "f" * 64)
    got = resolve_checksum(_release("无校验段的正文"))
    assert got == "f" * 64


def test_resolve_checksum_all_missing(monkeypatch):
    monkeypatch.setattr(checker, "fetch_checksum",
                        lambda url: None)
    assert resolve_checksum(_release("", sha_url="")) is None
