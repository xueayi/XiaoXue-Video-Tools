"""发布说明必须对应准确版本，且包含双平台资产及可解析校验和。"""
import hashlib
import pytest


def _assets(tmp_path, tag):
    names = [f"XiaoXueToolbox_{tag}_Windows_x64.zip", f"XiaoXueToolbox_{tag}_macOS_arm64.zip"]
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    return names


def test_notes_use_exact_prerelease_and_both_checksums(tmp_path):
    from tools.release_notes import build_notes
    from src.update.checker import parse_checksums_from_body
    changelog = "# 更新日志\n\n## [2.3.0-alpha.2] - 2026-10-18\n\n- 片段截取与原片预览\n\n## [2.3.0]\n旧版本正文\n"
    names = _assets(tmp_path, "v2.3.0-alpha.2")
    body = build_notes("v2.3.0-alpha.2", changelog, tmp_path, "xueayi/XiaoXue-Video-Tools")
    assert "片段截取与原片预览" in body and "旧版本正文" not in body
    checksums = parse_checksums_from_body(body)
    assert set(checksums) == set(names)
    assert checksums[names[0]] == hashlib.sha256(names[0].encode()).hexdigest()
    assert "/wiki/Features-Clip-Editing" in body


def test_stable_tag_uses_same_body_without_prerelease_suffix(tmp_path):
    """正式版与预发布共用正文结构, 只去掉标题的「（预发布）」后缀。"""
    from tools.release_notes import build_notes
    from src.update.checker import parse_checksums_from_body
    changelog = "# 更新日志\n\n## [2.3.0] - 2026-10-18\n\n- 双平台正式版\n\n## [2.2.2]\n旧版本正文\n"
    names = _assets(tmp_path, "v2.3.0")
    body = build_notes("v2.3.0", changelog, tmp_path, "xueayi/XiaoXue-Video-Tools")
    assert body.startswith("## 小雪工具箱 v2.3.0\n")
    assert "（预发布）" not in body
    assert "双平台正式版" in body and "旧版本正文" not in body
    assert set(parse_checksums_from_body(body)) == set(names)
    assert "/blob/v2.3.0/CHANGELOG.md" in body


@pytest.mark.parametrize("tag,changelog", [
    ("v2.3.0-alpha.2", "## [2.3.0]\n不应回退此正文"),      # 缺准确条目, 不得回退
    ("v2.3.0", "## [2.3.0-alpha.2]\n不应回退此正文"),
    ("v2.3.0-alpha.2; echo bad", ""),                      # 非法字符
    ("v2.3", ""),                                          # 缺 patch 号
    ("v2.3.0.1", ""),                                      # 四段版本号
])
def test_missing_entry_or_invalid_tag_is_rejected(tmp_path, tag, changelog):
    from tools.release_notes import build_notes
    with pytest.raises(ValueError):
        build_notes(tag, changelog, tmp_path, "owner/repo")


def test_missing_platform_package_prevents_release_notes(tmp_path):
    from tools.release_notes import build_notes
    (tmp_path / "XiaoXueToolbox_v2.3.0-alpha.2_Windows_x64.zip").write_bytes(b"zip")
    with pytest.raises(ValueError, match="macOS"):
        build_notes("v2.3.0-alpha.2", "## [2.3.0-alpha.2]\n- 更新", tmp_path, "owner/repo")


def test_is_stable_classification():
    from tools.release_notes import is_stable
    assert is_stable("v2.3.0") is True
    assert is_stable("v2.3.0-alpha.5") is False
    assert is_stable("v2.3.0-beta.1") is False
    assert is_stable("v2.3.0-rc.1") is False
