# -*- coding: utf-8 -*-
"""首页最近任务/输出的持久化、详情与「打开文件夹」验收。"""

import json

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel, QPushButton

from src.ui.home_page import HomePage
from src.ui.task_state import TaskStatus, TaskViewState


@pytest.fixture
def home(qapp, tmp_path, monkeypatch):
    """把最近记录重定向到临时 data_dir, 避免污染真实用户目录。"""
    from src.ui import home_page as home_module

    target = tmp_path / "data" / "recent_records.json"
    monkeypatch.setattr(home_module.HomePage, "records_file",
                        lambda self: target)
    page = HomePage()
    page._records_path = target
    yield page
    page.deleteLater()


# ----------------------------------------------------------------
# 持久化
# ----------------------------------------------------------------

def test_records_persist_across_restart(home, qapp):
    home.add_task_record("视频压制", TaskStatus.SUCCESS, "任务完成",
                         outputs=[r"D:\out\clip_x264.mp4"])
    home.add_recent_outputs([r"D:\out\clip_x264.mp4"])
    assert home._records_path.is_file()

    payload = json.loads(home._records_path.read_text(encoding="utf-8"))
    assert payload["tasks"][0]["title"] == "视频压制"
    assert payload["outputs"] == [r"D:\out\clip_x264.mp4"]

    # 新页面实例 (模拟重启) 应恢复记录
    from src.ui.home_page import HomePage as Page
    rebuilt = Page()
    try:
        assert [record.title for record in rebuilt.task_records] == ["视频压制"]
        assert rebuilt.task_records[0].status is TaskStatus.SUCCESS
        assert rebuilt.recent_outputs == [r"D:\out\clip_x264.mp4"]
    finally:
        rebuilt.deleteLater()


def test_clear_records_persists_empty_state(home):
    home.add_task_record("视频压制", TaskStatus.SUCCESS)
    home.clear_records()
    payload = json.loads(home._records_path.read_text(encoding="utf-8"))
    assert payload["tasks"] == []
    assert payload["outputs"] == []


def test_corrupt_records_file_is_ignored(qapp, tmp_path, monkeypatch):
    from src.ui import home_page as home_module

    target = tmp_path / "recent_records.json"
    target.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(home_module.HomePage, "records_file",
                        lambda self: target)
    page = HomePage()  # 不得抛异常
    try:
        assert page.task_records == []
    finally:
        page.deleteLater()


# ----------------------------------------------------------------
# 打开文件夹 / 详情
# ----------------------------------------------------------------

def test_folder_button_visible_only_with_output(qapp):
    from src.ui.task_card import TaskCard

    with_output = TaskCard(TaskViewState(
        task_id="t1", title="压制", status=TaskStatus.SUCCESS,
        output_path=r"D:\out\a.mp4"))
    without = TaskCard(TaskViewState(
        task_id="t2", title="压制", status=TaskStatus.FAILED))
    try:
        assert with_output._folder_btn.isVisibleTo(with_output)
        assert not without._folder_btn.isVisibleTo(without)
    finally:
        with_output.deleteLater()
        without.deleteLater()


def test_task_area_relays_open_folder(qapp):
    from src.ui.task_card import TaskArea

    area = TaskArea()
    received = []
    area.open_folder_requested.connect(received.append)
    area.set_tasks([TaskViewState(
        task_id="t1", title="压制", status=TaskStatus.SUCCESS,
        output_path=r"D:\out\a.mp4")])
    card = area._cards["t1"]
    card._folder_btn.click()
    assert received == [r"D:\out\a.mp4"]
    area.deleteLater()


def test_open_containing_folder_opens_directory(home, monkeypatch, tmp_path):
    from src.ui import task_details

    opened = []
    monkeypatch.setattr(
        task_details.QDesktopServices, "openUrl",
        lambda url: opened.append(url) or True)

    target = tmp_path / "clip.mp4"
    target.write_bytes(b"x")
    home._open_containing_folder(str(target))
    assert opened and opened[0] == QUrl.fromLocalFile(str(tmp_path))


def test_details_dialog_opens_with_state(home, monkeypatch):
    from src.ui import task_details

    shown = []
    monkeypatch.setattr(task_details.TaskDetailsDialog, "exec",
                        lambda self: shown.append(self.state))
    record = home.add_task_record("视频压制", TaskStatus.SUCCESS, "完成",
                                  outputs=[r"D:\out\a.mp4"])
    home._show_task_details(record.task_id)
    assert shown and shown[0].title == "视频压制"
    assert shown[0].output_path == r"D:\out\a.mp4"


def test_recent_output_rows_have_folder_button(home):
    home.add_recent_outputs([r"D:\out\a.mp4"])
    buttons = [
        widget for widget in home.findChildren(QPushButton)
        if widget.objectName() == "output_folder_btn"
    ]
    assert len(buttons) == 1
    labels = [label.text() for label in home.findChildren(QLabel)]
    assert r"D:\out\a.mp4" in labels
