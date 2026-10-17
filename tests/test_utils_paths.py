# -*- coding: utf-8 -*-
"""utils.py ffmpeg/ffprobe 解析器测试 (M4.1)。

查找顺序约定: 资源目录/安装目录 bin → 环境变量/配置 → 系统 PATH。
不假设可执行文件后缀 (Windows 带/不带 .exe 都尝试), 内置与配置路径做
isfile + X_OK 校验, PATH 结果交给 shutil.which。
"""

import os
from pathlib import Path

import pytest

import src.utils as utils

_ENV_VARS = ("XIAOXUE_FFMPEG", "FFMPEG", "XIAOXUE_FFPROBE", "FFPROBE")


def _mk_exe(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"exe")
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def dirs(monkeypatch, tmp_path):
    internal = tmp_path / "internal"
    base = tmp_path / "install"
    user_config = tmp_path / "userconf"
    for directory in (internal, base, user_config):
        directory.mkdir()
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(internal))
    monkeypatch.setattr(utils, "get_base_dir", lambda: str(base))
    monkeypatch.setattr(utils, "resolve_install_dir", lambda: base)
    monkeypatch.setattr(utils, "resolve_user_config_dir", lambda: user_config)
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(utils.shutil, "which", lambda name: None)
    return {
        "internal": internal,
        "base": base,
        "user_config": user_config,
        "tmp": tmp_path,
    }


def _name(stem: str) -> str:
    """当前平台下 make 时的真实文件名 (Windows 用 .exe)。"""
    return stem + ".exe" if os.name == "nt" else stem


# ----------------------------------------------------------------
# 资源目录优先级
# ----------------------------------------------------------------

def test_resource_bin_priority_over_env_and_path(dirs, monkeypatch):
    bundled = _mk_exe(dirs["internal"] / "bin" / _name("ffmpeg"))
    env_exe = _mk_exe(dirs["tmp"] / "env" / "ffmpeg.exe")
    monkeypatch.setenv("XIAOXUE_FFMPEG", env_exe)
    monkeypatch.setattr(utils.shutil, "which", lambda name: "C:/path/ffmpeg.exe")

    assert utils.get_ffmpeg_path() == bundled


def test_base_bin_used_as_portable_override(dirs):
    bundled = _mk_exe(dirs["base"] / "bin" / _name("ffmpeg"))
    assert utils.get_ffmpeg_path() == bundled


def test_no_extension_assumption(dirs):
    """资源目录里无后缀的 ffmpeg 也必须能找到 (macOS/Linux 布局)。"""
    bundled = _mk_exe(dirs["internal"] / "bin" / "ffmpeg")
    assert utils.get_ffmpeg_path() == bundled


def test_ffprobe_no_extension_assumption(dirs):
    bundled = _mk_exe(dirs["internal"] / "bin" / "ffprobe")
    assert utils.get_ffprobe_path() == bundled


def test_windows_prefers_exe_suffix(dirs):
    if os.name != "nt":
        pytest.skip("仅 Windows 同时存在两种后缀")
    both = _mk_exe(dirs["internal"] / "bin" / "ffmpeg")
    exe = _mk_exe(dirs["internal"] / "bin" / "ffmpeg.exe")
    assert utils.get_ffmpeg_path() == exe
    assert both  # 无后缀文件存在但不优先


def test_ffprobe_base_bin(dirs):
    bundled = _mk_exe(dirs["base"] / "bin" / _name("ffprobe"))
    assert utils.get_ffprobe_path() == bundled


# ----------------------------------------------------------------
# 环境变量 / 配置覆盖
# ----------------------------------------------------------------

def test_env_priority_over_config_and_path(dirs, monkeypatch):
    env_exe = _mk_exe(dirs["tmp"] / "env" / "ffmpeg.exe")
    cfg_exe = _mk_exe(dirs["tmp"] / "cfg" / "ffmpeg.exe")
    (dirs["base"] / "config.ini").write_text(
        f"[paths]\nffmpeg={cfg_exe}\n", encoding="utf-8")
    monkeypatch.setenv("XIAOXUE_FFMPEG", env_exe)
    monkeypatch.setattr(utils.shutil, "which", lambda name: "C:/path/ffmpeg.exe")

    assert utils.get_ffmpeg_path() == env_exe


def test_xiaoxue_env_beats_generic_env(dirs, monkeypatch):
    preferred = _mk_exe(dirs["tmp"] / "a" / "ffmpeg.exe")
    generic = _mk_exe(dirs["tmp"] / "b" / "ffmpeg.exe")
    monkeypatch.setenv("XIAOXUE_FFMPEG", preferred)
    monkeypatch.setenv("FFMPEG", generic)
    assert utils.get_ffmpeg_path() == preferred


def test_config_paths_section_override(dirs):
    cfg_exe = _mk_exe(dirs["tmp"] / "cfg" / "ffmpeg.exe")
    (dirs["base"] / "config.ini").write_text(
        f"[paths]\nffmpeg={cfg_exe}\n", encoding="utf-8")
    assert utils.get_ffmpeg_path() == cfg_exe


def test_config_ffmpeg_section_override(dirs):
    cfg_exe = _mk_exe(dirs["tmp"] / "cfg" / "ffmpeg.exe")
    (dirs["user_config"] / "config.ini").write_text(
        f"[ffmpeg]\npath={cfg_exe}\n", encoding="utf-8")
    assert utils.get_ffmpeg_path() == cfg_exe


def test_invalid_config_path_falls_through_to_path(dirs, monkeypatch):
    (dirs["base"] / "config.ini").write_text(
        "[paths]\nffmpeg=C:/missing/ffmpeg.exe\n", encoding="utf-8")
    monkeypatch.setattr(utils.shutil, "which",
                        lambda name: "C:/sys/ffmpeg.exe")
    assert utils.get_ffmpeg_path() == "C:/sys/ffmpeg.exe"


def test_ffprobe_env_override(dirs, monkeypatch):
    env_exe = _mk_exe(dirs["tmp"] / "env" / "ffprobe.exe")
    monkeypatch.setenv("XIAOXUE_FFPROBE", env_exe)
    assert utils.get_ffprobe_path() == env_exe


# ----------------------------------------------------------------
# 校验 / PATH / 最终回退
# ----------------------------------------------------------------

def test_invalid_env_ignored(dirs, monkeypatch):
    monkeypatch.setenv("XIAOXUE_FFMPEG", str(dirs["tmp"] / "nope.exe"))
    monkeypatch.setattr(utils.shutil, "which", lambda name: "C:/sys/ffmpeg.exe")
    assert utils.get_ffmpeg_path() == "C:/sys/ffmpeg.exe"


def test_bundled_directory_not_treated_as_executable(dirs):
    fake = dirs["internal"] / "bin" / _name("ffmpeg")
    fake.mkdir(parents=True)
    assert utils.get_ffmpeg_path() == "ffmpeg"


def test_xok_validation_skips_non_executable(dirs, monkeypatch):
    _mk_exe(dirs["internal"] / "bin" / _name("ffmpeg"))
    real_access = os.access

    def fake_access(path, mode):
        if mode == os.X_OK:
            return False  # 模拟不可执行
        return real_access(path, mode)

    monkeypatch.setattr(utils.os, "access", fake_access)
    assert utils.get_ffmpeg_path() == "ffmpeg"


def test_path_fallback_trusts_shutil_which(dirs, monkeypatch):
    monkeypatch.setattr(utils.shutil, "which",
                        lambda name: "C:/sys/ffmpeg.exe")
    assert utils.get_ffmpeg_path() == "C:/sys/ffmpeg.exe"


def test_which_tries_expected_suffixes(dirs, monkeypatch):
    seen = []

    def fake_which(name):
        seen.append(name)
        return None

    monkeypatch.setattr(utils.shutil, "which", fake_which)
    utils.get_ffmpeg_path()
    if os.name == "nt":
        assert seen == ["ffmpeg.exe", "ffmpeg"]
    else:
        assert seen == ["ffmpeg"]


def test_final_fallback_bare_names(dirs):
    assert utils.get_ffmpeg_path() == "ffmpeg"
    assert utils.get_ffprobe_path() == "ffprobe"


def test_is_executable_file_helper(tmp_path):
    assert utils._is_executable_file(str(tmp_path / "missing")) is False
    existing = tmp_path / "tool"
    existing.write_bytes(b"x")
    existing.chmod(0o755)
    assert utils._is_executable_file(str(existing)) is True
    assert utils._is_executable_file(str(tmp_path)) is False  # 目录不算
