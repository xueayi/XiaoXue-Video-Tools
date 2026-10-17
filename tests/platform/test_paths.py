# -*- coding: utf-8 -*-
"""src/platform/paths.py 单元测试 (M4.1)。

覆盖: dev/frozen 资源目录、Windows portable 默认布局、只读安装目录回退
用户目录、mkdri 失败链式回退临时目录、用户目录 Qt/环境变量回退矩阵、
config.ini copy-not-move 迁移、单例与 reset、ensure_dir 写探测。
"""

import sys
import tempfile
from pathlib import Path

import pytest

from src.platform import paths


@pytest.fixture(autouse=True)
def _reset_paths_singleton():
    paths.reset_platform_paths()
    yield
    paths.reset_platform_paths()


def _isolate(monkeypatch, tmp_path):
    """把全部目录解析替换到 tmp_path 下, 返回各路径。"""
    dirs = {
        "install": tmp_path / "app",
        "resource": tmp_path / "app" / "_internal",
        "temp": tmp_path / "temp",
        "user_config": tmp_path / "user" / "config",
        "user_data": tmp_path / "user" / "data",
        "user_cache": tmp_path / "user" / "cache",
        "user_log": tmp_path / "user" / "logs",
    }
    dirs["install"].mkdir(parents=True, exist_ok=True)
    dirs["resource"].mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(paths, "resolve_install_dir", lambda: dirs["install"])
    monkeypatch.setattr(paths, "resolve_resource_dir", lambda: dirs["resource"])
    monkeypatch.setattr(paths, "resolve_temp_dir", lambda: dirs["temp"])
    monkeypatch.setattr(paths, "resolve_user_config_dir",
                        lambda: dirs["user_config"])
    monkeypatch.setattr(paths, "resolve_user_data_dir",
                        lambda: dirs["user_data"])
    monkeypatch.setattr(paths, "resolve_user_cache_dir",
                        lambda: dirs["user_cache"])
    monkeypatch.setattr(paths, "resolve_user_log_dir",
                        lambda: dirs["user_log"])
    return dirs


# ----------------------------------------------------------------
# 基础目录解析 (dev / frozen)
# ----------------------------------------------------------------

def test_dev_dirs_are_repo_root():
    assert not getattr(sys, "frozen", False)
    repo_root = Path(__file__).resolve().parents[2]
    assert paths.resolve_install_dir() == repo_root
    assert paths.resolve_resource_dir() == repo_root


def test_frozen_onedir_resource_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "x.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert paths.resolve_install_dir() == tmp_path / "app"
    assert paths.resolve_resource_dir() == tmp_path / "app" / "_internal"


def test_frozen_onefile_resource_dir_uses_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "x.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "m"), raising=False)
    assert paths.resolve_resource_dir() == tmp_path / "m"


# ----------------------------------------------------------------
# Windows portable / 回退链
# ----------------------------------------------------------------

def test_windows_portable_layout(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)

    result = paths.detect()

    assert result.resource_dir == dirs["resource"]
    assert result.install_dir == dirs["install"]
    assert result.config_dir == dirs["install"]
    assert result.data_dir == dirs["install"]
    assert result.cache_dir == dirs["install"] / "_cache"
    assert result.log_dir == dirs["install"]
    assert result.temp_dir == dirs["temp"]
    assert result.portable is True
    # 目录已实际创建 (便携布局 + temp)
    assert (dirs["install"] / "_cache").is_dir()
    assert dirs["temp"].is_dir()


def test_readonly_install_falls_back_to_user_dirs(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    real_ensure = paths.ensure_dir

    def fake_ensure(path):
        if str(path).startswith(str(dirs["install"])):
            return False  # 模拟安装目录只读
        return real_ensure(path)

    monkeypatch.setattr(paths, "ensure_dir", fake_ensure)

    result = paths.detect()

    assert result.config_dir == dirs["user_config"]
    assert result.data_dir == dirs["user_data"]
    assert result.cache_dir == dirs["user_cache"]
    assert result.log_dir == dirs["user_log"]
    assert result.portable is False
    assert dirs["user_config"].is_dir()


def test_mkdir_failure_chain_falls_back_to_temp(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setattr(paths, "ensure_dir", lambda path: False)
    monkeypatch.setattr(
        paths.tempfile, "gettempdir", lambda: str(tmp_path / "systmp"))

    result = paths.detect()

    # 全部候选不可写: 每一类目录都落到临时目录布局
    assert result.temp_dir == tmp_path / "systmp" / paths.APP_DIR_NAME
    assert result.config_dir == result.temp_dir / "config"
    assert result.data_dir == result.temp_dir / "data"
    assert result.cache_dir == result.temp_dir / "cache"
    assert result.log_dir == result.temp_dir / "logs"


def test_non_windows_never_uses_portable(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: False)

    result = paths.detect()

    assert result.config_dir == dirs["user_config"]
    assert result.data_dir == dirs["user_data"]
    assert result.cache_dir == dirs["user_cache"]
    assert result.log_dir == dirs["user_log"]
    assert result.portable is False
    assert not (dirs["install"] / "_cache").exists()


def test_user_dir_resolver_error_does_not_break_detect(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)

    def boom():
        raise RuntimeError("用户目录解析失败")

    monkeypatch.setattr(paths, "resolve_user_config_dir", boom)

    result = paths.detect()  # 不应抛出

    # 该级候选被跳过, 继续用 portable 目录
    assert result.config_dir == dirs["install"]


def test_detect_outer_failure_returns_temp_fallback(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def boom():
        raise RuntimeError("整体解析失败")

    monkeypatch.setattr(paths, "_detect_impl", boom)
    result = paths.detect()  # 不应抛出

    assert result.temp_dir.is_dir()
    assert result.config_dir.parent == result.temp_dir
    assert result.log_dir.parent == result.temp_dir


# ----------------------------------------------------------------
# 用户目录: Qt 优先 / 环境变量回退
# ----------------------------------------------------------------

def test_qt_writable_location_normalizes_app_dir():
    location = paths._qt_writable_location("AppConfigLocation")
    if location is None:
        pytest.skip("当前环境 Qt 不可用")
    assert location.name == paths.APP_DIR_NAME


def test_windows_env_fallback_for_user_dirs(monkeypatch, tmp_path):
    appdata = tmp_path / "roaming"
    localappdata = tmp_path / "local"
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setattr(paths, "_qt_writable_location", lambda name: None)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    assert paths.resolve_user_config_dir() == appdata / paths.APP_DIR_NAME
    assert paths.resolve_user_data_dir() == appdata / paths.APP_DIR_NAME
    assert paths.resolve_user_cache_dir() == (
        localappdata / paths.APP_DIR_NAME / "Cache")
    assert paths.resolve_user_log_dir() == (
        localappdata / paths.APP_DIR_NAME / "Logs")


def test_macos_env_fallback_for_user_dirs(monkeypatch):
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.setattr(paths, "_is_macos", lambda: True)
    monkeypatch.setattr(paths, "_qt_writable_location", lambda name: None)
    home = Path.home()

    assert paths.resolve_user_config_dir() == (
        home / "Library" / "Preferences" / paths.APP_DIR_NAME)
    assert paths.resolve_user_data_dir() == (
        home / "Library" / "Application Support" / paths.APP_DIR_NAME)
    assert paths.resolve_user_cache_dir() == (
        home / "Library" / "Caches" / paths.APP_DIR_NAME)
    assert paths.resolve_user_log_dir() == (
        home / "Library" / "Logs" / paths.APP_DIR_NAME)


def test_xdg_env_fallback_for_user_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.setattr(paths, "_is_macos", lambda: False)
    monkeypatch.setattr(paths, "_qt_writable_location", lambda name: None)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    assert paths.resolve_user_config_dir() == (
        tmp_path / "cfg" / paths.APP_DIR_NAME)
    assert paths.resolve_user_data_dir() == (
        tmp_path / "data" / paths.APP_DIR_NAME)
    assert paths.resolve_user_cache_dir() == (
        tmp_path / "cache" / paths.APP_DIR_NAME)


# ----------------------------------------------------------------
# config.ini 迁移 (copy-not-move)
# ----------------------------------------------------------------

def _force_user_config(monkeypatch, dirs):
    """让 config 回退到用户目录 (只读安装目录), 其它目录保持 portable。"""
    real_ensure = paths.ensure_dir
    readonly = (dirs["install"], dirs["install"] / "_cache")

    def fake_ensure(path):
        if Path(path) in readonly:
            return False
        return real_ensure(path)

    monkeypatch.setattr(paths, "ensure_dir", fake_ensure)


def test_config_migration_copies_and_keeps_source(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    _force_user_config(monkeypatch, dirs)
    legacy = dirs["install"] / "config.ini"
    legacy.write_text("[ui]\ntheme=dark\n", encoding="utf-8")

    result = paths.detect()

    target = dirs["user_config"] / "config.ini"
    assert result.config_dir == dirs["user_config"]
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")
    assert legacy.is_file()  # copy-not-move: 源文件保留


def test_config_migration_does_not_overwrite_existing(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    _force_user_config(monkeypatch, dirs)
    (dirs["install"] / "config.ini").write_text("old", encoding="utf-8")
    target = dirs["user_config"] / "config.ini"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("new", encoding="utf-8")

    paths.detect()

    assert target.read_text(encoding="utf-8") == "new"


def test_portable_mode_does_not_migrate(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    legacy = dirs["install"] / "config.ini"
    legacy.write_text("x", encoding="utf-8")

    result = paths.detect()

    assert result.config_dir == dirs["install"]  # portable
    assert not any(dirs["user_config"].glob("config.ini"))


# ----------------------------------------------------------------
# 单例 / reset / ensure_dir / resolve_log_dir
# ----------------------------------------------------------------

def test_platform_paths_singleton_and_reset(monkeypatch, tmp_path):
    calls = []

    def fake_detect():
        calls.append(1)
        return paths.PlatformPaths(
            resource_dir=tmp_path, install_dir=tmp_path,
            config_dir=tmp_path, data_dir=tmp_path, cache_dir=tmp_path,
            log_dir=tmp_path, temp_dir=tmp_path)

    monkeypatch.setattr(paths, "detect", fake_detect)

    first = paths.platform_paths()
    second = paths.platform_paths()
    assert first is second
    assert calls == [1]

    paths.reset_platform_paths()
    third = paths.platform_paths()
    assert third is not first
    assert calls == [1, 1]


def test_ensure_dir_ok_and_failure(tmp_path):
    target = tmp_path / "a" / "b"
    assert paths.ensure_dir(target) is True
    assert target.is_dir()

    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    assert paths.ensure_dir(blocker / "sub") is False


def test_resolve_log_dir_windows_portable(monkeypatch, tmp_path):
    install = tmp_path / "app"
    install.mkdir()
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setattr(paths, "resolve_install_dir", lambda: install)
    monkeypatch.setattr(paths, "_dir_writable", lambda path: True)
    assert paths.resolve_log_dir() == install

    monkeypatch.setattr(paths, "_dir_writable", lambda path: False)
    user_log = tmp_path / "userlogs"
    monkeypatch.setattr(paths, "resolve_user_log_dir", lambda: user_log)
    assert paths.resolve_log_dir() == user_log


def test_platform_paths_as_dict_and_portable(monkeypatch, tmp_path):
    dirs = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    result = paths.detect()

    data = result.as_dict()
    assert data["portable"] is True
    assert data["config_dir"] == str(dirs["install"])
    assert data["cache_dir"] == str(dirs["install"] / "_cache")
