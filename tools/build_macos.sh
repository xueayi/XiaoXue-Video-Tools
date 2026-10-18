#!/bin/bash
# 从仓库根目录构建；解释器可通过 XIAOXUE_BUILD_PYTHON 指定。
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo "需要 Apple Silicon macOS 构建环境" >&2
    exit 1
fi
build_python="${XIAOXUE_BUILD_PYTHON:-python3}"
"$build_python" - <<'PY'
import pathlib, re, subprocess, sys, sysconfig
if sys.version_info[:2] != (3, 12):
    raise SystemExit('需要 Python 3.12')
library = pathlib.Path(sys.base_prefix) / 'lib' / sysconfig.get_config_var('LDLIBRARY')
if not library.exists():
    library = pathlib.Path(sys.base_prefix) / 'Python'
output = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(library)], text=True)
minimums = re.findall(r'minos\s+(\d+)\.(\d+)', output)
if not minimums or any(tuple(map(int, v)) > (13, 0) for v in minimums):
    raise SystemExit('Python 构建最低系统版本高于 macOS 13，请改用可兼容的 Python 3.12')
PY
"$build_python" tools/prepare_macos_media.py
"$build_python" -m PyInstaller XiaoXueToolbox-macOS.spec --noconfirm
codesign --verify --deep --strict 'dist/小雪工具箱.app'
mkdir -p dist/packages
version="${XIAOXUE_BUILD_VERSION:-2.3.0-alpha.2}"
ditto -c -k --keepParent 'dist/小雪工具箱.app' "dist/packages/XiaoXueToolbox_v${version}_macOS_arm64.zip"
shasum -a 256 "dist/packages/XiaoXueToolbox_v${version}_macOS_arm64.zip"
