# -*- coding: utf-8 -*-
"""业务模块批 1: _version / help_texts / log_utils / utils / gui_config /
post_transfer / notify_config / encode_params 边界。"""

import json
import logging
import sys

import pytest

import src._version as version_mod
import src.help_texts as help_mod
import src.log_utils as log_utils
import src.utils as utils


# ----------------------------------------------------------------
# _version
# ----------------------------------------------------------------

def test_git_version_success(monkeypatch):
    monkeypatch.setattr(version_mod.subprocess, "check_output",
                        lambda *a, **k: "v3.1.4\n")
    assert version_mod._git_version() == "3.1.4"


def test_git_version_empty_output(monkeypatch):
    monkeypatch.setattr(version_mod.subprocess, "check_output",
                        lambda *a, **k: "  \n")
    assert version_mod._git_version() == ""


def test_git_version_exception(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(version_mod.subprocess, "check_output", boom)
    assert version_mod._git_version() == ""


# ----------------------------------------------------------------
# help_texts
# ----------------------------------------------------------------

def test_get_help_text_known_and_unknown():
    topic = next(iter(help_mod.HELP_TEXTS))
    assert help_mod.get_help_text(topic)
    assert help_mod.get_help_text("不存在的功能") == "暂无此功能的说明。"


# ----------------------------------------------------------------
# log_utils
# ----------------------------------------------------------------

def test_get_log_dir_dev_mode():
    assert "XiaoXue" in log_utils.get_log_dir() or log_utils.get_log_dir()


def test_get_log_dir_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "app.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert log_utils.get_log_dir() == str(tmp_path)


def test_setup_logging_writes_file(monkeypatch, tmp_path):
    monkeypatch.setattr(log_utils, "get_log_dir", lambda: str(tmp_path))
    logger = log_utils.setup_logging()
    logger.info("hello log")
    for h in logger.handlers:
        h.flush()
    assert (tmp_path / log_utils.LOG_FILENAME).exists()


def test_setup_logging_child_process_mark(monkeypatch, tmp_path):
    monkeypatch.setattr(log_utils, "get_log_dir", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["main.py", "--ignore-gooey-kwarg-ref"])
    logger = log_utils.setup_logging()
    logger.info("child")
    assert logger.level == logging.INFO


def test_fix_sys_io_with_none_stdout(monkeypatch, tmp_path):
    logger = logging.getLogger("fixio-test")
    logger.addHandler(logging.NullHandler())
    # stdout 为 None 且 fdopen 失败 -> 回退 devnull
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(log_utils.os, "fdopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("bad fd")))
    log_utils.fix_sys_io(logger)
    sys.stdout.close()
    sys.stderr.close()
    monkeypatch.undo()
    assert sys.stdout is not None
    assert sys.stderr is not None


def test_fix_sys_io_reconfigure_error(monkeypatch):
    class FakeStream:
        def reconfigure(self, **kw):
            raise ValueError("nope")
    fake = FakeStream()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys, "stderr", fake)
    logger = logging.getLogger("fixio-test2")
    logger.addHandler(logging.NullHandler())
    log_utils.fix_sys_io(logger)
    monkeypatch.undo()


# ----------------------------------------------------------------
# utils
# ----------------------------------------------------------------

def test_get_base_dir_and_internal_dir_dev():
    assert utils.get_base_dir() == utils.get_internal_dir()


def test_get_base_dir_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "x.exe"))
    assert utils.get_base_dir() == str(tmp_path)


def test_get_internal_dir_frozen_onedir(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "x.exe"))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert utils.get_internal_dir() == str(tmp_path / "_internal")


def test_get_internal_dir_frozen_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "m"), raising=False)
    assert utils.get_internal_dir() == str(tmp_path / "m")


def test_get_ffmpeg_path_internal(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffmpeg.exe").write_bytes(b"x")
    assert utils.get_ffmpeg_path() == str(tmp_path / "bin" / "ffmpeg.exe")


def test_get_ffmpeg_path_base_bin(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffmpeg.exe").write_bytes(b"x")
    assert utils.get_ffmpeg_path() == str(tmp_path / "bin" / "ffmpeg.exe")


def test_get_ffmpeg_path_system_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path / "no2")
    monkeypatch.setattr(utils.shutil, "which", lambda n: "C:/sys/ffmpeg.exe")
    assert utils.get_ffmpeg_path() == "C:/sys/ffmpeg.exe"


def test_get_ffmpeg_path_final_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path / "no2")
    monkeypatch.setattr(utils.shutil, "which", lambda n: None)
    assert utils.get_ffmpeg_path() == "ffmpeg"


def test_get_ffprobe_path_final_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path / "no2")
    monkeypatch.setattr(utils.shutil, "which", lambda n: None)
    assert utils.get_ffprobe_path() == "ffprobe"


def test_get_ffprobe_path_internal(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path))
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffprobe.exe").write_bytes(b"x")
    assert utils.get_ffprobe_path() == str(tmp_path / "bin" / "ffprobe.exe")


def test_get_ffprobe_path_base_bin(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffprobe.exe").write_bytes(b"x")
    assert utils.get_ffprobe_path() == str(tmp_path / "bin" / "ffprobe.exe")


def test_get_ffprobe_path_system(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(utils, "get_base_dir", lambda: tmp_path / "no2")
    monkeypatch.setattr(utils.shutil, "which", lambda n: "C:/sys/ffprobe.exe")
    assert utils.get_ffprobe_path() == "C:/sys/ffprobe.exe"


def test_escape_path_for_ffmpeg():
    assert utils.escape_path_for_ffmpeg("C:\\my subs\\a's.ass") == \
        "C\\:/my subs/a'\\''s.ass"


def test_generate_output_path():
    assert utils.generate_output_path("a.mp4", "libx264") == "a_x264.mp4"
    assert utils.generate_output_path("a.mp4", "libx264", ".mkv") == "a_x264.mkv"
    assert utils.generate_output_path("a.mp4", "h264_nvenc", "mkv") == \
        "a_h264nvenc.mkv"


def test_auto_generate_output_path():
    assert utils.auto_generate_output_path("a.mp4", "_remux") == "a_remux.mp4"
    assert utils.auto_generate_output_path("a.mp4", "_x", ".mkv") == "a_x.mkv"


# ----------------------------------------------------------------
# gui_config
# ----------------------------------------------------------------

def test_get_icon_path_frozen_internal(monkeypatch, tmp_path):
    import src.gui_config as gc
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"))
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "icon.ico").write_bytes(b"x")
    monkeypatch.setattr(gc, "get_internal_dir", lambda: str(internal))
    monkeypatch.setattr(gc, "get_base_dir", lambda: str(tmp_path))
    assert gc.get_icon_path() == str(internal / "icon.ico")


def test_get_icon_path_base_fallback(monkeypatch, tmp_path):
    import src.gui_config as gc
    monkeypatch.setattr(gc, "get_internal_dir", lambda: str(tmp_path / "no"))
    monkeypatch.setattr(gc, "get_base_dir", lambda: str(tmp_path))
    (tmp_path / "icon.ico").write_bytes(b"x")
    assert gc.get_icon_path() == str(tmp_path / "icon.ico")


# ----------------------------------------------------------------
# post_transfer
# ----------------------------------------------------------------

def test_transfer_file_copy_and_move(tmp_path):
    from src.post_transfer import transfer_file
    src = tmp_path / "done.mp4"
    src.write_bytes(b"video")
    dst = tmp_path / "out"
    out = transfer_file(str(src), str(dst), "copy")
    assert out == str(dst / "done.mp4")
    assert (dst / "done.mp4").exists() and src.exists()
    out2 = transfer_file(str(src), str(dst), "move")
    assert out2 == str(dst / "done_1.mp4")
    assert not src.exists()


def test_transfer_file_errors(tmp_path):
    from src.post_transfer import transfer_file
    with pytest.raises(FileNotFoundError):
        transfer_file(str(tmp_path / "nope.mp4"), str(tmp_path))
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    with pytest.raises(ValueError):
        transfer_file(str(src), str(tmp_path), "delete")


# ----------------------------------------------------------------
# notify_config
# ----------------------------------------------------------------

@pytest.fixture
def restore_notify_state():
    import src.notify_config as nc
    saved = dict(nc._notify_config)
    saved_loaded = nc._notify_config_loaded
    yield
    nc._notify_config.clear()
    nc._notify_config.update(saved)
    nc._notify_config_loaded = saved_loaded


def test_notify_config_roundtrip(monkeypatch, tmp_path, restore_notify_state):
    import src.notify_config as nc
    cfg_file = tmp_path / "notify_config.json"
    monkeypatch.setattr(nc, "NOTIFY_CONFIG_FILE", str(cfg_file))
    nc._notify_config.clear()
    nc._notify_config.update({"enabled": False})
    nc._notify_config_loaded = False

    nc.load_notify_config()  # 文件不存在 -> 默认
    assert nc.is_config_loaded() is False

    nc.update_notify_config({"enabled": True, "feishu_webhook": "https://x"})
    assert nc.get_notify_config()["enabled"] is True

    nc.save_notify_config(dict(nc._notify_config))
    assert cfg_file.exists()

    nc.load_notify_config()
    assert nc.is_config_loaded() is True
    assert nc.get_notify_config()["feishu_webhook"] == "https://x"

    assert nc.delete_notify_config() is True
    assert nc.is_config_loaded() is False
    assert nc.delete_notify_config() is True  # 不存在也返回 True


def test_notify_config_load_broken_file(monkeypatch, tmp_path, restore_notify_state):
    import src.notify_config as nc
    cfg_file = tmp_path / "broken.json"
    cfg_file.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(nc, "NOTIFY_CONFIG_FILE", str(cfg_file))
    nc._notify_config.clear()
    nc._notify_config.update({"enabled": False})
    nc.load_notify_config()  # 损坏文件 -> 警告并保持默认
    assert nc.get_notify_config()["enabled"] is False


def test_notify_config_save_failure(monkeypatch, tmp_path):
    import src.notify_config as nc
    bad = tmp_path / "no_dir" / "cfg.json"
    monkeypatch.setattr(nc, "NOTIFY_CONFIG_FILE", str(bad))
    nc.save_notify_config({"enabled": True})  # 目录不存在 -> 仅打印错误


def test_notify_config_delete_failure(monkeypatch, tmp_path):
    import src.notify_config as nc
    cfg_file = tmp_path / "locked.json"
    cfg_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(nc, "NOTIFY_CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(nc.os, "remove",
                        lambda p: (_ for _ in ()).throw(OSError("locked")))
    assert nc.delete_notify_config() is False


def test_send_auto_notification_disabled(monkeypatch, restore_notify_state):
    import src.notify_config as nc
    nc._notify_config.clear()
    nc._notify_config.update({"enabled": False})
    nc.send_auto_notification("视频压制")  # 未启用 -> 直接返回


def test_send_auto_notification_enabled(monkeypatch, restore_notify_state):
    import src.notify_config as nc
    calls = []
    monkeypatch.setattr(nc, "send_feishu_notification",
                        lambda **kw: calls.append(("feishu", kw)))
    monkeypatch.setattr(nc, "send_webhook_notification",
                        lambda **kw: calls.append(("webhook", kw)))
    nc._notify_config.clear()
    nc._notify_config.update({
        "enabled": True,
        "feishu_webhook": "https://feishu",
        "feishu_title": "完成",
        "feishu_content": "任务 {task} 完成",
        "feishu_color": "blue",
        "webhook_url": "https://hook",
        "webhook_headers": "{}",
        "webhook_body": "{task}",
    })
    nc.send_auto_notification("视频压制")
    kinds = [k for k, _ in calls]
    assert kinds == ["feishu", "webhook"]
    assert calls[0][1]["content"] == "任务 视频压制 完成"
    assert calls[1][1]["body_json"] == "视频压制"
