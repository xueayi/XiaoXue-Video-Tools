# -*- coding: utf-8 -*-
"""UI 覆盖率最后一轮补缺。"""

import pytest
from PyQt6.QtCore import QPointF, QMimeData, QUrl, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QFileDialog, QLabel

from src.media_probe import DetailedMediaInfo, StreamInfo
from src.ui.base_tab import BaseTab, FileDropLineEdit
from src.ui.log_panel import _ansi_to_html
from src.ui.main_window import MainWindow
from src.ui.tabs import EncodeTab, RemuxTab
from src.ui.task_runner import _StreamRedirect


def _info(**kw):
    with_subs = kw.pop("with_subs", True)
    video_codec = kw.pop("video_codec", "h264")
    audio_codec = kw.pop("audio_codec", "aac")
    defaults = dict(
        path="C:/a.mp4",
        video_streams=[StreamInfo(index=0, stream_index=0, codec_type="video",
                                  codec_name=video_codec, width=640, height=480)],
        audio_streams=[StreamInfo(index=0, stream_index=1, codec_type="audio",
                                  codec_name=audio_codec)],
        subtitle_streams=[StreamInfo(index=0, stream_index=2,
                                     codec_type="subtitle", codec_name="srt")],
        duration_sec=61.5,
    )
    if not with_subs:
        defaults["subtitle_streams"] = []
    defaults.update(kw)
    return DetailedMediaInfo(**defaults)


@pytest.fixture
def win(qapp):
    w = MainWindow(shield_available=True, notify_config=None)
    yield w
    w.close()


@pytest.fixture
def encode_tab(qapp):
    return EncodeTab()


@pytest.fixture
def remux_tab(qapp):
    return RemuxTab()


# ----------------------------------------------------------------
# base_tab
# ----------------------------------------------------------------

def test_drop_multi_few_files_uses_joined_text(qapp):
    edit = FileDropLineEdit(multi=True)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(f"C:/x/{i}.mp4") for i in range(2)])
    ev = QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, mime,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    ev._mime = mime
    edit.dropEvent(ev)
    assert "; " in edit.text()
    assert "已选择" not in edit.text()


def test_multi_browse_many_files_uses_summary(qapp, monkeypatch, tmp_path):
    class MultiTab(BaseTab):
        def build_args(self):
            return None

    tab = MultiTab("x")
    io = tab.add_group("g")
    edit = tab.add_multi_file_chooser(io, "多选")
    many = [str(tmp_path / f"{i}.mp4") for i in range(5)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (many, "")))
    from PyQt6.QtWidgets import QPushButton
    for b in io.parentWidget().findChildren(QPushButton):
        if b.text() == "浏览":
            b.click()
    assert edit.text() == f"已选择 {len(many)} 个文件"


# ----------------------------------------------------------------
# sidebar / log_panel / ffmpeg_progress / task_runner
# ----------------------------------------------------------------

def test_pill_slide_restarts_when_running(qapp):
    from src.ui.sidebar import Sidebar
    s = Sidebar()
    for n in ("a", "b", "c"):
        s.add_item(n, "ri.film-line")
    s.show()
    qapp.processEvents()
    s.setCurrentRow(0)
    s.setCurrentRow(1)
    s.setCurrentRow(2)  # 动画运行中再次触发 -> stop 分支
    assert s.currentRow() == 2


def test_ansi_bold_after_color_closes_span():
    out = _ansi_to_html("\033[32mgreen\033[1mbold")
    assert "green" in out and "bold" in out
    assert out.count("<span") == out.count("</span>")


def test_stream_redirect_write_and_flush(qapp):
    from src.ui.task_runner import TaskRunner
    got = []
    runner = TaskRunner(lambda a: None, None, "c")
    runner.log_signal.connect(got.append)
    r = _StreamRedirect(runner.log_signal)
    r.write("x")
    r.flush()
    assert got == ["x"]


def test_parser_fps_bad_value_swallowed(qapp):
    from src.ui.ffmpeg_progress import FFmpegProgressParser
    parser = FFmpegProgressParser()
    parser.feed_line("frame=7 fps=1.2.3 time=00:00:01.00\n")
    assert parser._info.frame == 7
    assert parser._info.fps == 0.0


# ----------------------------------------------------------------
# encode_tab
# ----------------------------------------------------------------

def test_encode_clear_layout_with_widget(encode_tab):
    encode_tab._track_audio_layout.addWidget(QLabel("x"))
    encode_tab._clear_layout(encode_tab._track_audio_layout)
    assert encode_tab._track_audio_layout.count() == 0


def test_encode_resolve_selection_empty(encode_tab):
    assert EncodeTab._resolve_track_selection([], "全部保留", "不保留") == (
        "全部保留", "")


def test_encode_build_args_uses_detected_tracks(encode_tab, monkeypatch, tmp_path):
    real = tmp_path / "v.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr("src.ui.tabs.encode_tab.probe_detailed",
                        lambda p: _info())
    encode_tab.input_edit.setText(str(real))
    encode_tab._audio_checks[0][0].setChecked(False)
    args = encode_tab.build_args()
    assert args.audio_tracks == "不保留音轨"
    assert args.subtitle_tracks == "不保留字幕"


def test_encode_empty_input_resets(encode_tab, tmp_path):
    real = tmp_path / "v.mp4"
    real.write_bytes(b"x")
    encode_tab.input_edit.setText(str(real))
    encode_tab.input_edit.setText("")  # 清空 -> 空路径重置分支
    assert "自动检测" in encode_tab._track_status.text()


def test_encode_preset_nvenc_cq_and_speed(encode_tab):
    # N 卡预设使用 cq + NVENC 档位, 命中 crf/cq 二选一与 p 档位分支
    encode_tab.preset_combo.setCurrentText("【速度优先】NVIDIA 显卡加速")
    assert encode_tab.crf_spin.value() == 23
    assert encode_tab.nvenc_preset_combo.currentText() == "p4"
    encode_tab.preset_combo.setCurrentText("【画质优先】NVIDIA 显卡加速 (HQ)")
    assert encode_tab.crf_spin.value() == 19
    assert encode_tab.nvenc_preset_combo.currentText() == "p7"
    encode_tab.preset_combo.setCurrentText("【均衡画质】x264 常用导出 (CRF18)")
    assert encode_tab.crf_spin.value() == 18


# ----------------------------------------------------------------
# remux_tab
# ----------------------------------------------------------------

def test_remux_populate_twice_clears_container(remux_tab, monkeypatch, tmp_path):
    real = tmp_path / "v.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr("src.ui.tabs.remux_tab.probe_detailed",
                        lambda p: _info())
    remux_tab.remux_input_edit.setText(str(real))
    remux_tab._do_probe()
    remux_tab._do_probe()  # 二次探测 -> _clear_container 带 widget 的分支
    assert len(remux_tab._audio_checks) == 1


def test_remux_mp4_opus_audio_unsupported(remux_tab, monkeypatch, tmp_path):
    real = tmp_path / "opus.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr("src.ui.tabs.remux_tab.probe_detailed",
                        lambda p: _info(audio_codec="opus", with_subs=False))
    remux_tab.remux_input_edit.setText(str(real))
    assert "兼容性警告" in remux_tab._compat_warn_label.text()


def test_remux_resolve_selection_mixed(remux_tab):
    on = type("CB", (), {"isChecked": lambda self: True})()
    off = type("CB", (), {"isChecked": lambda self: False})()
    assert RemuxTab._resolve_track_selection(
        [(on, 0), (off, 1)], "全部保留", "不保留字幕") == (
        "自定义选择 (填写编号)", "0")


# ----------------------------------------------------------------
# main_window 防御分支
# ----------------------------------------------------------------

def test_try_set_duration_probe_raises(qapp, monkeypatch, tmp_path):
    import src.media_probe as mp
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")

    def boom(p):
        raise RuntimeError("probe 挂了")
    monkeypatch.setattr(mp, "probe_detailed", boom)
    win = MainWindow(shield_available=True, notify_config=None)

    class A:
        input = str(video)
    win._try_set_duration(A())  # 异常被 except 吞掉
    win.close()


def test_auto_notification_failure_swallowed(win, qapp, monkeypatch):
    def broken(name):
        raise RuntimeError("通知挂了")
    monkeypatch.setattr(mw_module(), "send_auto_notification", broken)
    win._handlers["视频压制"] = lambda args: None
    win._sidebar.setCurrentRow(0)
    win._on_execute()
    import time
    deadline = time.time() + 5
    while "完成" not in win.statusBar().currentMessage() and time.time() < deadline:
        qapp.processEvents()
    assert "完成" in win.statusBar().currentMessage()


def test_first_run_centers_when_no_saved_geometry(qapp, monkeypatch):
    from PyQt6.QtCore import QSettings
    monkeypatch.setattr(QSettings, "value",
                        lambda self, key, default=None: default)
    win = MainWindow(shield_available=True, notify_config=None)
    center = win.screen().availableGeometry().center()
    assert win.frameGeometry().center().x() == pytest.approx(center.x(), abs=2)
    win.close()


def mw_module():
    import src.ui.main_window as m
    return m
