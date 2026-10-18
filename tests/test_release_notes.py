"""发布说明必须对应准确版本，且包含双平台资产及可解析校验和。"""
import hashlib
import pytest


def test_notes_use_exact_prerelease_and_both_checksums(tmp_path):
    from tools.release_notes import build_notes
    from src.update.checker import parse_checksums_from_body
    changelog = "# 更新日志\n\n## [2.3.0-alpha.2] - 2026-10-18\n\n- 片段截取与原片预览\n\n## [2.3.0]\n旧版本正文\n"
    names = ["XiaoXueToolbox_v2.3.0-alpha.2_Windows_x64.zip", "XiaoXueToolbox_v2.3.0-alpha.2_macOS_arm64.zip"]
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    body = build_notes("v2.3.0-alpha.2", changelog, tmp_path, "xueayi/XiaoXue-Video-Tools")
    assert "片段截取与原片预览" in body and "旧版本正文" not in body
    checksums = parse_checksums_from_body(body)
    assert set(checksums) == set(names)
    assert checksums[names[0]] == hashlib.sha256(names[0].encode()).hexdigest()
    assert "/blob/v2.3.0-alpha.2/CLIP_EDITING.md" in body


@pytest.mark.parametrize("tag,changelog", [
    ("v2.3.0-alpha.2", "## [2.3.0]\n不应回退此正文"),
    ("v2.3.0", "## [2.3.0]\n正式版"),
    ("v2.3.0-alpha.2; echo bad", ""),
])
def test_missing_entry_or_non_prerelease_is_rejected(tmp_path, tag, changelog):
    from tools.release_notes import build_notes
    with pytest.raises(ValueError):
        build_notes(tag, changelog, tmp_path, "owner/repo")


def test_missing_platform_package_prevents_release_notes(tmp_path):
    from tools.release_notes import build_notes
    (tmp_path / "XiaoXueToolbox_v2.3.0-alpha.2_Windows_x64.zip").write_bytes(b"zip")
    with pytest.raises(ValueError, match="macOS"):
        build_notes("v2.3.0-alpha.2", "## [2.3.0-alpha.2]\n- 更新", tmp_path, "owner/repo")
