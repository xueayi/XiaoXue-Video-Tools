"""媒体归档完整性校验失败时不得覆盖现有依赖。"""
import hashlib
import os
import zipfile
from pathlib import Path
import pytest
from tools.prepare_macos_media import extract_verified_archive


@pytest.mark.parametrize('bad_hash', [False, True])
def test_extract_checks_integrity_before_replacing(tmp_path, bad_hash):
    archive = tmp_path / 'ffmpeg.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('ffmpeg', b'validated binary')
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    dest = tmp_path / 'bin' / 'ffmpeg'
    dest.parent.mkdir()
    dest.write_bytes(b'existing')
    if bad_hash:
        with pytest.raises(ValueError, match='SHA256'):
            extract_verified_archive(archive, '0' * 64, 'ffmpeg', dest)
        assert dest.read_bytes() == b'existing'
    else:
        extract_verified_archive(archive, sha, 'ffmpeg', dest)
        assert dest.read_bytes() == b'validated binary'
        if os.name != "nt":
            assert dest.stat().st_mode & 0o111


def test_extract_refuses_paths_outside_archive_root(tmp_path):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('../ffmpeg', b'bad')
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='ffmpeg'):
        extract_verified_archive(archive, sha, 'ffmpeg', tmp_path / 'bin' / 'ffmpeg')
    assert not (tmp_path / 'ffmpeg').exists()
