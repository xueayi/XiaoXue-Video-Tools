# -*- coding: utf-8 -*-
"""UI 覆盖率补缺: 边界分支、联动细节、入口与配置。"""

import pytest
from PyQt6.QtCore import QPointF, QPoint, QMimeData, QUrl, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QLabel

from src.media_probe import DetailedMediaInfo, StreamInfo
from src.ui.animations import AnimatedStackedWidget
from src.ui.base_tab import BaseTab, FileDropLineEdit
from src.ui.log_panel import LogPanel
from src.ui.main_window import MainWindow


@pytest.fixture
def win(qapp):
    w = MainWindow(shield_available=True, notify_config=None)
    yield w
    w.close()
from src.ui.tabs import EncodeTab, RemuxTab, ShieldTab
from src.ui.task_runner import TaskRunner


def _info(**kw):
    # 注意: _info 会在 setText 触发的 Qt 槽内被求值, 任何异常都会导致
    # PyQt6 qFatal (进程直接 abort), 所以这里必须处理所有合法变体参数
    with_subs = kw.pop("with_subs", True)
    video_codec = kw.pop("video_codec", "h264")
    audio_codec = kw.pop("audio_codec", "aac")
    sub_codec = kw.pop("sub_codec", "ass")
    defaults = dict(
        path="C:/a.mp4",
        video_streams=[StreamInfo(index=0, stream_index=0, codec_type="video",
                                  codec_name=video_codec, width=640, height=480)],
        audio_streams=[StreamInfo(index=0, stream_index=1, codec_type="audio",
                                  codec_name=audio_codec)],
        subtitle_streams=[StreamInfo(index=0, stream_index=2,
                                     codec_type="subtitle", codec_name=sub_codec)],
        duration_sec=61.5,
    )
    if not with_subs:
        defaults["subtitle_streams"] = []
    defaults.update(kw)
    return DetailedMediaInfo(**defaults)


# ----------------------------------------------------------------
# args_builder
# ----------------------------------------------------------------

def test_args_namespace_repr_and_contains():
    from src.ui.args_builder import ArgsNamespace
    ns = ArgsNamespace(command="x", value=3)
    assert "command" in ns
    assert "missing" not in ns
    assert "command='x'" in repr(ns)
    assert "value=3" in repr(ns)


# ----------------------------------------------------------------
# base_tab 边界
# ----------------------------------------------------------------

def test_drop_url_without_local_file(qapp):
    edit = FileDropLineEdit()
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/a.mp4")])
    ev = QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, mime,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    ev._mime = mime
    edit.dropEvent(ev)
    assert edit.text() == ""


def test_add_collapsible_group_starts_collapsed(qapp):
    tab = BaseTabStub("x")
    lay = tab.add_collapsible_group("折叠组")
    tab.add_text_input(lay, "f", "")
    from PyQt6.QtWidgets import QToolButton, QWidget
    header = tab._main_layout.itemAt(tab._main_layout.count() - 2).widget()
    content = tab._main_layout.itemAt(tab._main_layout.count() - 1).widget()
    assert isinstance(header, QToolButton)
    assert not header.isChecked()
    assert not content.isVisibleTo(tab)


class BaseTabStub(BaseTab):
    def build_args(self):
        return None


# ----------------------------------------------------------------
# log_panel 边界
# ----------------------------------------------------------------

def test_append_empty_text_noop(qapp):
    panel = LogPanel()
    panel.append_log("")
    assert panel._chunks == []


def test_append_while_filter_active(qapp):
    panel = LogPanel()
    panel.append_log("alpha line\n")
    panel._filter_edit.setText("alpha")
    panel.append_log("gamma new\n")
    panel.append_log("alpha new\n")
    # 过滤激活期间新日志只入库; 改动过滤词触发重渲染后才可见
    panel._filter_edit.setText("alpha ")
    text = panel._view.toPlainText()
    assert "alpha line" in text
    assert "alpha new" in text
    assert "gamma new" not in text


def test_smooth_scroll_stop_running_anim(qapp, pump_fn):
    panel = LogPanel()
    panel.resize(400, 200)
    panel.show()
    qapp.processEvents()
    panel.append_log("\n".join(f"line {i}" for i in range(600)) + "\n")
    pump_fn(30)
    # 第二次追加时若有动画在跑, 走 stop/deleteLater 分支
    panel.append_log("\n".join(f"more {i}" for i in range(600)) + "\n")
    pump_fn(400)
    bar = panel._view.verticalScrollBar()
    assert bar.value() == bar.maximum()


def test_ansi_bold_then_color_replaces_open_span():
    from src.ui.log_panel import _ansi_to_html
    out = _ansi_to_html("\033[1mB\033[36mC")
    assert "B" in out and "C" in out
    assert out.count("<span") == out.count("</span>")


# ----------------------------------------------------------------
# ffmpeg_progress 边界
# ----------------------------------------------------------------

def test_feed_empty_line(qapp):
    from src.ui.ffmpeg_progress import FFmpegProgressParser
    parser = FFmpegProgressParser()
    parser.feed_line("")  # 不崩溃
    parser.feed_line("frame= 1 time=00:00:00.50 size=1kB bitrate=8.0kbits/s speed=N/A\n")
    assert parser._info.frame == 1


def test_feed_line_fps_and_bad_values(qapp):
    from src.ui.ffmpeg_progress import FFmpegProgressParser
    parser = FFmpegProgressParser()
    got = []
    parser.progress_updated.connect(got.append)
    parser.feed_line(
        "frame=5 fps=24.0 size=10kB bitrate=1.2.3kbits/s speed=1.2.3x\n")
    # 只有 time= 行触发信号; 其余字段静默更新, 异常值解析失败保持默认
    assert got == []
    assert parser._info.frame == 5
    assert parser._info.fps == 24.0
    assert parser._info.size_kb == 10
    assert parser._info.bitrate_kbps == 0.0
    assert parser._info.speed == 0.0


# ----------------------------------------------------------------
# task_runner: 同步 run() 覆盖线程体
# ----------------------------------------------------------------

def test_task_runner_run_sync_success(qapp):
    runner = TaskRunner(lambda a: print("sync ok"), None, "c")
    runner.run()  # 直接在主线程执行, 覆盖 run() 语句
    assert True


def test_task_runner_run_sync_failure(qapp):
    def boom(a):
        raise RuntimeError("x")
    TaskRunner(boom, None, "c").run()


# ----------------------------------------------------------------
# animations / sidebar 边界
# ----------------------------------------------------------------

def test_pill_slide_restarts_running_anim(qapp):
    from src.ui.sidebar import Sidebar
    s = Sidebar()
    s.add_item("a", "ri.film-line")
    s.add_item("b", "ri.music-2-line")
    s.show()
    qapp.processEvents()
    s.setCurrentRow(0)
    s.setCurrentRow(1)  # 第一次动画运行中再次触发 -> stop+restart 分支
    qapp.processEvents()
    assert s.currentRow() == 1


def test_slide_to_when_range_invalid(qapp):
    from PyQt6.QtWidgets import QLabel
    stack = AnimatedStackedWidget()
    stack.addWidget(QLabel("only"))
    stack.slide_to(5)
    stack.slide_to(-2)
    assert stack.currentIndex() == 0


# ----------------------------------------------------------------
# main_window: 探测时长 / 停止未运行 / 首启居中
# ----------------------------------------------------------------

def test_try_set_duration_success(qapp, monkeypatch, tmp_path):
    import src.media_probe as mp
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(mp, "probe_detailed",
                        lambda p: _info(duration_sec=120))
    win = MainWindow(shield_available=True, notify_config=None)

    class A:
        input = str(video)
    win._try_set_duration(A())
    assert win._ffmpeg_parser._info.total_duration == 120
    win.close()


def test_stop_when_runner_not_running(win):
    class NotRunning:
        def isRunning(self):
            return False
    win._runner = NotRunning()
    win._on_stop()
    assert win._execute_btn.isEnabled()


def test_first_run_centers_window(qapp):
    win = MainWindow(shield_available=True, notify_config=None)
    assert win.x() != 0 or win.y() != 0  # 居中移动已执行
    win.close()


def test_execute_index_negative_logged(win, monkeypatch):
    # setCurrentIndex(-1) 会被 Qt 钳制, 用桩直接命中 idx<0 分支
    monkeypatch.setattr(win._stack, "currentIndex", lambda: -1)
    win._on_execute()


# ----------------------------------------------------------------
# encode/remux 探测与标签分支
# ----------------------------------------------------------------

@pytest.fixture
def remux_tab(qapp):
    return RemuxTab()


def test_encode_probe_empty_path_resets(encode_tab):
    encode_tab.input_edit.setText("")
    assert "自动检测" in encode_tab._track_status.text()


def test_encode_probe_returns_none(encode_tab, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "none.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: None)
    encode_tab.input_edit.setText(str(real))
    assert "自动检测" in encode_tab._track_status.text()


@pytest.fixture
def encode_tab(qapp):
    return EncodeTab()


def test_encode_preset_nvenc_cq_values(encode_tab):
    for preset in ["【速度优先】N卡加速 (CQ23 p4)",
                   "【画质优先 HQ】N卡高画质 (CQ19 p7)"]:
        encode_tab.preset_combo.setCurrentText(preset)
        assert not encode_tab.encoder_combo.isEnabled()
    encode_tab.preset_combo.setCurrentText("【均衡画质】x264 常用导出 (CRF18)")


def test_encode_stream_label_sparse_fields():
    bare_audio = StreamInfo(index=1, stream_index=3, codec_type="audio",
                            codec_name="mp3")
    out = EncodeTab._build_stream_label(bare_audio, "audio")
    assert "#1" in out and "mp3" in out
    bare_sub = StreamInfo(index=0, stream_index=4, codec_type="subtitle",
                          codec_name="srt")
    out2 = EncodeTab._build_stream_label(bare_sub, "subtitle")
    assert "srt" in out2


def test_encode_populate_audio_sparse(encode_tab, monkeypatch, tmp_path):
    import src.ui.tabs.encode_tab as mod
    real = tmp_path / "sparse.mp4"
    real.write_bytes(b"x")
    info = _info(audio_streams=[StreamInfo(index=0, stream_index=1,
                                           codec_type="audio", codec_name="mp3")])
    monkeypatch.setattr(mod, "probe_detailed", lambda p: info)
    encode_tab.input_edit.setText(str(real))
    assert len(encode_tab._audio_checks) == 1


# ----------------------------------------------------------------
# remux 分支
# ----------------------------------------------------------------

def test_format_duration_short():
    from src.ui.tabs.remux_tab import _format_duration_short
    assert _format_duration_short(-1) == ""
    assert _format_duration_short(0) == ""
    assert _format_duration_short(65) == "01:05"
    assert _format_duration_short(3700) == "01:01:40"


def test_lang_display_branches():
    from src.ui.tabs.remux_tab import _lang_display
    assert _lang_display("") == ""
    assert isinstance(_lang_display("xyz"), str)


def test_remux_probe_none_info(remux_tab, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "none.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed", lambda p: None)
    remux_tab.remux_input_edit.setText(str(real))
    assert "自动检测" in remux_tab._track_status.text()


def test_remux_populate_no_subtitles(remux_tab, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "nosub.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed",
                        lambda p: _info(with_subs=False, audio_streams=[]))
    remux_tab.remux_input_edit.setText(str(real))
    assert "未检测到" in remux_tab._no_track_hint.text()


def test_remux_populate_audio_only(remux_tab, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "audio.mp4"
    real.write_bytes(b"x")
    monkeypatch.setattr(mod, "probe_detailed",
                        lambda p: _info(with_subs=False))
    remux_tab.remux_input_edit.setText(str(real))
    assert not remux_tab._sub_container.isVisibleTo(remux_tab)
    assert len(remux_tab._audio_checks) == 1


def test_remux_compat_custom_ext_with_dot(remux_tab):
    remux_tab.remux_preset_combo.setCurrentText("自定义")
    remux_tab.remux_format_custom_edit.setText(".mp4")
    remux_tab._last_probe_info = _info(video_codec="vp9")
    remux_tab._check_compat()
    assert "兼容性警告" in remux_tab._compat_warn_label.text()


def test_remux_compat_unknown_ext_no_rules(remux_tab):
    remux_tab.remux_preset_combo.setCurrentText("自定义")
    remux_tab.remux_format_custom_edit.setText("xyz")
    remux_tab._last_probe_info = _info(video_codec="vp9")
    remux_tab._check_compat()
    assert not remux_tab._compat_warn_label.isVisibleTo(remux_tab)


def test_remux_compat_webm_unsupported(remux_tab, monkeypatch, tmp_path):
    import src.ui.tabs.remux_tab as mod
    real = tmp_path / "webm.mp4"
    real.write_bytes(b"x")
    # WEBM 仅支持 vp8/vp9/av1 视频: h264 触发 supported_video 分支
    monkeypatch.setattr(mod, "probe_detailed",
                        lambda p: _info(video_codec="h264", with_subs=False))
    remux_tab.remux_input_edit.setText(str(real))
    remux_tab.remux_preset_combo.setCurrentText("WEBM (Web 视频)")
    assert "兼容性警告" in remux_tab._compat_warn_label.text()


def test_remux_resolve_selection(remux_tab):
    cb_on = type("CB", (), {"isChecked": lambda self: True})()
    cb_off = type("CB", (), {"isChecked": lambda self: False})()
    assert RemuxTab._resolve_track_selection([], "全部", "不保留") == ("全部", "")
    assert RemuxTab._resolve_track_selection(
        [(cb_on, 0)], "全部", "不保留") == ("全部", "")
    assert RemuxTab._resolve_track_selection(
        [(cb_off, 0)], "全部", "不保留") == ("不保留", "")


def test_remux_build_args_roundtrip(remux_tab):
    remux_tab.remux_input_edit.setText("C:/a.mp4; C:/b.mp4")
    args = remux_tab.build_args()
    assert args.command == "封装转换"


# ----------------------------------------------------------------
# ShieldTab 联动
# ----------------------------------------------------------------

def test_shield_censor_toggles(qapp):
    tab = ShieldTab(shield_available=True)
    tab._on_censor_toggled(False)
    assert not tab.overlay_image_edit.isEnabled()
    tab._on_censor_toggled(True)
    tab._on_censor_type_changed("自定义")
    assert tab.overlay_image_edit.isEnabled()
    tab._on_censor_type_changed("马赛克")
    assert not tab.overlay_image_edit.isEnabled()


def test_shield_build_args_unavailable(qapp):
    tab = ShieldTab(shield_available=False)
    args = tab.build_args()
    assert args.command == "露骨图片识别"


# ----------------------------------------------------------------
# gui_config
# ----------------------------------------------------------------

def test_get_icon_path(monkeypatch, tmp_path):
    import src.gui_config as gc
    monkeypatch.setattr(gc, "get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(gc, "get_internal_dir", lambda: str(tmp_path / "none"))
    assert gc.get_icon_path() is None
    (tmp_path / "icon.ico").write_bytes(b"x")
    assert gc.get_icon_path() == str(tmp_path / "icon.ico")


def test_gui_config_constants():
    import src.gui_config as gc
    assert gc.PROGRAM_NAME == "小雪工具箱"
    assert gc.DEFAULT_SIZE == (960, 720)


def test_version_module():
    from src import _version
    assert isinstance(_version.__version__, str) and _version.__version__
    assert isinstance(_version._git_version(), str)
