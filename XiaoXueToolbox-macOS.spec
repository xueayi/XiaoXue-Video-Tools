# -*- mode: python ; coding: utf-8 -*-
"""Apple Silicon 原生应用包，媒体依赖由 prepare_macos_media.py 准备。"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
from PIL import Image

root = Path(SPECPATH)
version = os.environ.get('XIAOXUE_BUILD_VERSION', '2.3.0-alpha.4')
hook = root / 'build/macos-version.py'
hook.parent.mkdir(parents=True, exist_ok=True)
hook.write_text(f'import src._version; src._version.__version__ = {version!r}\n')
media = root / 'build/macos-media'
icon = root / 'build/macos-icon.icns'
Image.open(root / 'image/小雪工具箱亮色.png').save(icon, format='ICNS')

a = Analysis(
    [str(root / 'main.py')], pathex=[str(root)],
    binaries=[(str(media / 'bin' / name), 'bin') for name in ('ffmpeg', 'ffprobe')],
    datas=[(str(root / 'image'), 'image'), (str(root / 'icon.ico'), '.'),
           (str(root / 'LICENSE'), 'licenses'), (str(root / 'build-resources/THIRD_PARTY.md'), 'licenses'),
           (str(media / 'licenses'), 'licenses')] + collect_data_files('qtawesome'),
    hiddenimports=['PyQt6.QtWidgets', 'PyQt6.QtCore', 'PyQt6.QtGui',
                   'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'qtawesome'],
    excludes=['pytest'], runtime_hooks=[str(hook)], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='XiaoXueToolbox',
    debug=False, strip=False, upx=False, console=False, argv_emulation=False,
    target_arch='arm64', codesign_identity=os.environ.get('XIAOXUE_CODESIGN_IDENTITY'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='XiaoXueToolbox')
app = BUNDLE(
    coll, name='小雪工具箱.app', icon=str(icon), bundle_identifier='site.xueayi.xiaoxuetoolbox',
    version=version.split('-')[0],
    info_plist={'CFBundleDisplayName': '小雪工具箱', 'NSHighResolutionCapable': True,
                'LSMinimumSystemVersion': '13.0', 'NSPrincipalClass': 'NSApplication'},
)
