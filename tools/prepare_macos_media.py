# -*- coding: utf-8 -*-
"""下载固定版本媒体依赖，先校验 SHA256，再验证 arm64/系统库与功能。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def download_verified_archive(url, expected_sha256, archive):
    request = Request(url, headers={'User-Agent': 'XiaoXueToolbox-media-builder/1.0'})
    with urlopen(request, timeout=180) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError(f'{Path(archive).name} SHA256 校验失败')
    Path(archive).write_bytes(content)


def extract_verified_archive(archive, expected_sha256, name, destination):
    archive, destination = Path(archive), Path(destination)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError(f"{name} SHA256 校验失败")
    with zipfile.ZipFile(archive) as bundle:
        entries = [entry for entry in bundle.infolist() if entry.filename == name]
        if len(entries) != 1:
            raise ValueError(f"归档中缺少唯一的 {name}")
        content = bundle.read(entries[0])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(0o755)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def validate_binary(path):
    arch = subprocess.check_output(['lipo', '-archs', str(path)], text=True).split()
    if arch != ['arm64']:
        raise ValueError(f"{path}: 需要原生 arm64，实际 {arch}")
    libraries = subprocess.check_output(['otool', '-L', str(path)], text=True)
    for line in libraries.splitlines()[1:]:
        library = line.strip().split(' (', 1)[0]
        if library and not library.startswith(('/usr/lib/', '/System/Library/')):
            raise ValueError(f"{path}: 非系统动态库依赖 {library}")
    version = subprocess.check_output([str(path), '-version'], text=True)
    if '--enable-nonfree' in version:
        raise ValueError(f"{path}: 不接受 nonfree 构建")
    return version.splitlines()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/macos-media')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'build-resources/macos-media.json').read_text())
    cache = args.output / 'cache'
    cache.mkdir(parents=True, exist_ok=True)
    for name, artifact in manifest['artifacts'].items():
        archive = cache / f'{name}.zip'
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != artifact['sha256']:
            download_verified_archive(artifact['url'], artifact['sha256'], archive)
        binary = args.output / 'bin' / name
        extract_verified_archive(archive, artifact['sha256'], name, binary)
        print(validate_binary(binary))
    ffmpeg = str(args.output / 'bin/ffmpeg')
    encoders = subprocess.check_output([ffmpeg, '-hide_banner', '-encoders'], text=True)
    filters = subprocess.check_output([ffmpeg, '-hide_banner', '-filters'], text=True)
    for required in ('libx264', 'libx265', 'h264_videotoolbox', 'hevc_videotoolbox', 'aac'):
        if required not in encoders.split():
            raise ValueError(f'缺少编码器: {required}')
    if 'subtitles' not in filters.split():
        raise ValueError('缺少 libass subtitles 滤镜')
    notice_dir = args.output / 'licenses'
    notice_dir.mkdir(exist_ok=True)
    (notice_dir / 'media-build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    license_text = subprocess.check_output([ffmpeg, '-hide_banner', '-L'], text=True)
    (notice_dir / 'FFmpeg-license.txt').write_text(license_text)
    print('媒体依赖已校验: arm64 / 系统库 / 编码器 / 字幕滤镜')


if __name__ == '__main__':
    main()
