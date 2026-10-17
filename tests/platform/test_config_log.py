# -*- coding: utf-8 -*-
"""gui_config / log_utils 落盘路径与只读兜底测试 (M4.1)。

覆盖: config.ini 走 PlatformPaths.config_dir、路径解析失败回退临时目录、
QSettings 文件读写、日志目录走 PlatformPaths、日志文件创建失败逐级回退
且绝不抛异常。
"""

import logging
import os
from pathlib import Path

import pytest

import src.gui_config as gc
import src.log_utils as lu
from src.platform.paths import APP_DIR_NAME


class _FakePaths:
    def __init__(self, config_dir):
        self.config_dir = Path(config_dir)


@pytest.fixture
def fake_platform_paths(monkeypatch, tmp_path):
    config_dir = tmp_path / "cfg" / APP_DIR_NAME
    monkeypatch.setattr(gc, "platform_paths",
                        lambda: _FakePaths(config_dir))
    return config_dir


@pytest.fixture
def clean_logger():
    """保存/恢复 root logger, 避免 setup_logging 影响其他用例。"""
    root = logging.getLogger()
    previous = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in previous:
            root.removeHandler(handler)
            handler.close()
    for handler in previous:
        if handler not in root.handlers:
            root.addHandler(handler)


# ----------------------------------------------------------------
# gui_config: config.ini 位置
# ----------------------------------------------------------------

def test_get_config_path_uses_platform_paths(fake_platform_paths):
    path = gc.get_config_path()
    assert Path(path) == fake_platform_paths / "config.ini"
    assert fake_platform_paths.is_dir()  # 目录被创建


def test_get_config_path_falls_back_to_temp(monkeypatch, tmp_path, capsys):
    def boom():
        raise RuntimeError("平台路径解析失败")

    monkeypatch.setattr(gc, "platform_paths", boom)
    monkeypatch.setattr(gc, "_warned_config_fallback", False)
    monkeypatch.setattr(gc.tempfile, "gettempdir", lambda: str(tmp_path))

    path = gc.get_config_path()

    assert Path(path) == tmp_path / APP_DIR_NAME / "config.ini"
    captured = capsys.readouterr()
    assert "回退临时目录" in captured.err + captured.out


def test_get_qsettings_roundtrip(fake_platform_paths):
    settings = gc.get_qsettings()
    settings.setValue("ui/theme", "dark")
    settings.sync()

    assert os.path.normcase(settings.fileName()) == os.path.normcase(
        str(fake_platform_paths / "config.ini"))
    reloaded = gc.get_qsettings()
    assert reloaded.value("ui/theme") == "dark"


def test_get_qsettings_falls_back_when_path_fails(
        monkeypatch, tmp_path, capsys):
    def boom():
        raise RuntimeError("config 路径不可用")

    monkeypatch.setattr(gc, "get_config_path", boom)
    monkeypatch.setattr(gc, "_warned_config_fallback", False)
    monkeypatch.setattr(gc.tempfile, "gettempdir", lambda: str(tmp_path))

    settings = gc.get_qsettings()  # 不应抛出

    assert os.path.normcase(settings.fileName()) == os.path.normcase(
        str(tmp_path / APP_DIR_NAME / "config.ini"))
    assert "回退临时目录" in capsys.readouterr().err


# ----------------------------------------------------------------
# log_utils: 日志目录与失败兜底
# ----------------------------------------------------------------

def test_get_log_dir_uses_platform_paths(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(lu, "resolve_log_dir", lambda: log_dir)
    assert lu.get_log_dir() == str(log_dir)


def test_get_log_dir_falls_back_to_repo_root_dev(monkeypatch):
    def boom():
        raise RuntimeError("日志目录解析失败")

    monkeypatch.setattr(lu, "resolve_log_dir", boom)
    monkeypatch.setattr(lu.sys, "frozen", False, raising=False)
    repo_root = Path(__file__).resolve().parents[2]
    assert lu.get_log_dir() == str(repo_root)


def test_get_log_dir_falls_back_to_exe_dir_frozen(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("日志目录解析失败")

    monkeypatch.setattr(lu, "resolve_log_dir", boom)
    monkeypatch.setattr(lu.sys, "frozen", True, raising=False)
    monkeypatch.setattr(lu.sys, "executable", str(tmp_path / "app.exe"))
    assert lu.get_log_dir() == str(tmp_path)


def test_setup_logging_writes_file(monkeypatch, tmp_path, clean_logger):
    monkeypatch.setattr(lu, "get_log_dir", lambda: str(tmp_path))
    logger = lu.setup_logging()
    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()
    assert (tmp_path / lu.LOG_FILENAME).is_file()


def test_setup_logging_falls_back_to_temp(
        monkeypatch, tmp_path, clean_logger, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(lu, "get_log_dir",
                        lambda: str(blocker / "logs"))
    monkeypatch.setattr(lu.tempfile, "gettempdir",
                        lambda: str(tmp_path / "tmpdir"))
    monkeypatch.setattr(lu, "_warned_once", False)

    logger = lu.setup_logging()  # 不应抛出

    assert (tmp_path / "tmpdir" / lu.LOG_FILENAME).is_file()
    assert "回退到临时目录" in capsys.readouterr().err
    assert logger.handlers


def test_setup_logging_no_file_handler_still_returns_logger(
        monkeypatch, tmp_path, clean_logger, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(lu, "get_log_dir",
                        lambda: str(blocker / "logs"))
    monkeypatch.setattr(lu.tempfile, "gettempdir",
                        lambda: str(blocker / "tmp"))
    monkeypatch.setattr(lu, "_warned_once", False)

    logger = lu.setup_logging()  # 全部目录失败也不抛出

    assert logger.handlers  # 至少有控制台 handler
    assert "仅输出到控制台" in capsys.readouterr().err


def test_warn_once_only_first_time(monkeypatch, capsys):
    monkeypatch.setattr(lu, "_warned_once", False)
    lu._warn_once("第一条")
    lu._warn_once("第二条")
    captured = capsys.readouterr()
    assert "第一条" in captured.err
    assert "第二条" not in captured.err
