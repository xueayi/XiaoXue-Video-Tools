"""片段编辑器的用户操作和页面接线。"""
import pytest
from PyQt6.QtWidgets import QTableWidgetItem


def editor(qapp):
    from src.ui.clip_editor import ClipEditor
    result = ClipEditor()
    result.set_input("当前视频.mp4")
    result.enable_cb.setChecked(True)
    return result


def add(e, start, end):
    e.in_edit.setText(start)
    e.out_edit.setText(end)
    e.add_btn.click()


def test_add_reorder_duplicate_and_remove(qapp):
    e = editor(qapp)
    add(e, "00:00:01.000", "00:00:01.500")
    add(e, "00:00:00.000", "00:00:00.500")
    e.table.selectRow(1)
    e.up_btn.click()
    assert e.plan().clips[0].in_us == 0
    e.copy_btn.click()
    assert e.plan().total_duration_us == 1_500_000
    e.delete_btn.click()
    assert len(e.plan().clips) == 2
    assert "1.000" in e.total_label.text()


def test_editing_table_changes_snapshot_and_preserves_old_plan(qapp):
    e = editor(qapp)
    add(e, "00:00:00.000", "00:00:01.000")
    snapshot = e.plan()
    e.table.setItem(0, 1, QTableWidgetItem("00:00:02.000"))
    assert snapshot.total_duration_us == 1_000_000
    assert e.plan().total_duration_us == 2_000_000


def test_switch_input_clears_old_times(qapp):
    e = editor(qapp)
    add(e, "00:00:00.000", "00:00:01.000")
    e.set_input("另一个视频.mp4")
    assert e.table.rowCount() == 0
    assert e.plan().input_path == "另一个视频.mp4"
    with pytest.raises(ValueError, match="片段"):
        e.validate_inputs()


def test_invalid_draft_and_duration_are_not_silently_exported(qapp):
    e = editor(qapp)
    add(e, "00:00:00.000", "00:00:01.000")
    e.set_duration_us(500_000)
    with pytest.raises(ValueError):
        e.validate_inputs()
    e.table.setItem(0, 0, QTableWidgetItem("坏时间"))
    with pytest.raises(ValueError):
        e.plan()
    e.enable_cb.setChecked(False)
    assert e.plan() is None


def test_running_disables_editor_without_dropping_plan(qapp):
    e = editor(qapp)
    add(e, "00:00:00.000", "00:00:01.000")
    e.set_running(True)
    assert not e.add_btn.isEnabled()
    assert e.plan().total_duration_us == 1_000_000
    e.set_running(False)
    assert e.add_btn.isEnabled()


def test_module_is_before_advanced_and_summary_tracks_clips(qapp, tmp_path):
    from src.ui.tabs.encode_tab import EncodeTab
    tab = EncodeTab()
    tab.input_edit.setText(str(tmp_path / "missing.mp4"))
    e = tab.clip_editor
    e.enable_cb.setChecked(True)
    add(e, "00:00:00.000", "00:00:02.000")
    widgets = [tab._main_layout.itemAt(i).widget() for i in range(tab._main_layout.count())]
    assert widgets.index(tab.transfer_group) < widgets.index(e) < widgets.index(tab.advanced_header)
    assert tab.build_args().clip_plan.total_duration_us == 2_000_000
    assert "2.000" in tab.summary_card.row_text("clips")
    assert "aac" in tab.summary_card.row_text("audio")


def test_preview_records_displayed_pts_and_invalidates_on_seek(qapp):
    from src.ui.preview_panel import PreviewPanel
    from PyQt6.QtMultimedia import QVideoFrame, QVideoFrameFormat
    from PyQt6.QtCore import QSize
    panel = PreviewPanel()
    # 无显示帧时不能伪造精细打点。
    assert panel.mark_us() is None
    frame = QVideoFrame()
    panel._on_frame(frame)
    assert panel.mark_us() is None
    frame = QVideoFrame(QVideoFrameFormat(QSize(16, 16), QVideoFrameFormat.PixelFormat.Format_YUV420P))
    frame.setStartTime(1_166_667)
    panel._on_frame(frame)
    assert panel.mark_us() == 1_166_667
    panel.seek(1_500_000)
    assert panel.mark_us() is None
    panel.release()


def test_marked_microseconds_survive_display_rounding(qapp):
    e = editor(qapp)
    class DisplayedFrame:
        def mark_us(self):
            return 1_166_667
    e.preview = DisplayedFrame()
    e.in_btn.click()
    e.out_edit.setText("00:00:02.000")
    e.add_btn.click()
    assert e.plan().clips[0].in_us == 1_166_667


def test_probe_duration_overrides_container_player_duration(qapp):
    e = editor(qapp)
    e.set_duration_us(3_000_000, authoritative=True)
    e.set_duration_us(13_000_000)
    add(e, "00:00:11.000", "00:00:12.000")
    assert not e.plan().clips


def test_stale_probe_cannot_overwrite_current_input(qapp, tmp_path, monkeypatch):
    from src.ui.tabs import encode_tab as module
    from src.media_probe import DetailedMediaInfo
    pending = []
    monkeypatch.setattr(module, "start_media_probe", lambda path, generation, callback, probe:
                        pending.append((path, generation, callback)))
    paths = [tmp_path / "first.mp4", tmp_path / "second.mp4"]
    for path in paths:
        path.touch()
    tab = module.EncodeTab()
    tab.input_edit.setText(str(paths[0]))
    tab.input_edit.setText(str(paths[1]))
    old, current = pending
    current[2]((current[0], current[1], DetailedMediaInfo(current[0], duration_sec=20)))
    old[2]((old[0], old[1], DetailedMediaInfo(old[0], duration_sec=99)))
    assert tab._last_probe_info.path == str(paths[1])
    assert tab._last_probe_info.duration_sec == 20
