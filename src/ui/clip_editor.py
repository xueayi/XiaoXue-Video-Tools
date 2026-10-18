"""同一输入视频的片段列表与可选原片预览。"""
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QCheckBox,
    QWidget, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QToolButton)

from ..clip_plan import ClipPlan, ClipSpec
from .base_tab import set_label_kind


def format_clip_time(us: int) -> str:
    ms = us // 1000
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def parse_clip_time(text: str) -> int:
    match = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)(?:\.(\d{1,3}))?", text.strip())
    if not match:
        raise ValueError("时间格式应为 HH:MM:SS.mmm，如 00:01:23.500")
    h, m, s, fraction = match.groups()
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1_000_000 + int((fraction or "").ljust(3, "0")) * 1000


class ClipEditor(QGroupBox):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("视频片段截取", parent)
        self._input_path = ""
        self._duration_us = None
        self.preview = None
        self._precise_marks = {}
        layout = QVBoxLayout(self)
        self.enable_cb = QCheckBox("启用片段导出")
        layout.addWidget(self.enable_cb)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        self.preview_toggle = QToolButton()
        self.preview_toggle.setText("展开原片预览")
        self.preview_toggle.setCheckable(True)
        body.addWidget(self.preview_toggle)
        self.preview_box = QVBoxLayout()
        body.addLayout(self.preview_box)
        inputs = QHBoxLayout()
        self.in_edit = QLineEdit("00:00:00.000")
        self.out_edit = QLineEdit("00:00:00.000")
        self.in_btn = QPushButton("入点 I")
        self.out_btn = QPushButton("出点 O")
        self.add_btn = QPushButton("添加片段")
        for label, edit, button in (("入点", self.in_edit, self.in_btn), ("出点", self.out_edit, self.out_btn)):
            inputs.addWidget(QLabel(label))
            edit.setMinimumWidth(108)
            inputs.addWidget(edit, 1)
            inputs.addWidget(button)
        inputs.addWidget(self.add_btn)
        body.addLayout(inputs)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["入点", "出点（不包含）", "时长"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(132)
        self.table.setMaximumHeight(240)
        body.addWidget(self.table)
        buttons = QHBoxLayout()
        self.copy_btn = QPushButton("复制")
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        self.delete_btn = QPushButton("删除")
        self.play_clip_btn = QPushButton("预览选中片段")
        for button in (self.copy_btn, self.up_btn, self.down_btn, self.delete_btn, self.play_clip_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        body.addLayout(buttons)
        self.total_label = QLabel("合计 0 段，导出 0.000 秒")
        body.addWidget(self.total_label)
        hint = QLabel("仅截取当前视频，按列表顺序拼接。双击表格可修改时间；出点不包含当前帧。\n"
                      "音频需重新编码（复制模式改为 AAC）；暂不支持保留软字幕流及 AviSynth 兼容模式。")
        hint.setWordWrap(True)
        hint.setObjectName("group_desc")
        body.addWidget(hint)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        layout.addWidget(self.body)
        self.body.setVisible(False)
        self.enable_cb.toggled.connect(self._toggle_enabled)
        self.preview_toggle.toggled.connect(self._toggle_preview)
        self.add_btn.clicked.connect(self._add)
        self.copy_btn.clicked.connect(self._copy)
        self.delete_btn.clicked.connect(self._delete)
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.play_clip_btn.clicked.connect(self._play_clip)
        self.table.itemChanged.connect(self._item_changed)
        self.in_btn.clicked.connect(lambda: self._mark(self.in_edit))
        self.out_btn.clicked.connect(lambda: self._mark(self.out_edit))
        self.in_edit.textEdited.connect(lambda: self._precise_marks.pop(self.in_edit, None))
        self.out_edit.textEdited.connect(lambda: self._precise_marks.pop(self.out_edit, None))
        for key, edit in (("I", self.in_edit), ("O", self.out_edit)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda field=edit: self._mark(field))

    def _toggle_enabled(self, enabled):
        self.body.setVisible(enabled)
        if not enabled and self.preview:
            self.preview.pause()
        self._update()

    def set_input(self, path):
        path = path.strip()
        if path == self._input_path:
            return
        had_clips = self.table.rowCount() > 0
        self._input_path = path
        self._duration_us = None
        self._precise_marks.clear()
        self.table.setRowCount(0)
        self.in_edit.setText("00:00:00.000")
        self.out_edit.setText("00:00:00.000")
        if self.preview:
            self.preview.set_input(path)
        self._update()
        if had_clips:
            self.status.setText("已更换输入视频，旧片段已清空，请重新添加。")

    def set_duration_us(self, us):
        self._duration_us = us if us > 0 else None
        self._update()

    def _time_value(self, item):
        marked = item.data(Qt.ItemDataRole.UserRole)
        if marked is not None and format_clip_time(marked) == item.text():
            return marked
        return parse_clip_time(item.text())

    def plan(self):
        if not self.enable_cb.isChecked():
            return None
        return ClipPlan(self._input_path, tuple(ClipSpec(
            self._time_value(self.table.item(row, 0)), self._time_value(self.table.item(row, 1)))
            for row in range(self.table.rowCount())))

    def validate_inputs(self):
        plan = self.plan()
        if plan is not None:
            try:
                plan.validate(self._duration_us)
            except ValueError as exc:
                self.status.setText(str(exc))
                set_label_kind(self.status, "error")
                raise

    def _append(self, clip, row=None):
        row = self.table.rowCount() if row is None else row
        self.table.blockSignals(True)
        self.table.insertRow(row)
        for col, us in enumerate((clip.in_us, clip.out_us)):
            item = QTableWidgetItem(format_clip_time(us))
            item.setData(Qt.ItemDataRole.UserRole, us)
            self.table.setItem(row, col, item)
        duration = QTableWidgetItem()
        duration.setFlags(duration.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 2, duration)
        self.table.blockSignals(False)
        self.table.selectRow(row)
        self._update()

    def _add(self):
        try:
            values = [self._precise_marks.get(edit, (edit.text(), None)) for edit in (self.in_edit, self.out_edit)]
            times = [us if text == edit.text() and us is not None else parse_clip_time(edit.text())
                     for edit, (text, us) in zip((self.in_edit, self.out_edit), values)]
            clip = ClipSpec(*times)
            ClipPlan(self._input_path, (clip,)).validate(self._duration_us)
            self._append(clip)
        except ValueError as exc:
            self.status.setText(str(exc))
            set_label_kind(self.status, "error")

    def _copy(self):
        row = self.table.currentRow()
        if row >= 0:
            try:
                self._append(self.plan().clips[row], row + 1)
            except ValueError as exc:
                self.status.setText(str(exc))

    def _delete(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._update()

    def _move(self, delta):
        row = self.table.currentRow()
        target = row + delta
        if not 0 <= row < self.table.rowCount() or not 0 <= target < self.table.rowCount():
            return
        self.table.blockSignals(True)
        for column in range(3):
            current = self.table.takeItem(row, column)
            other = self.table.takeItem(target, column)
            self.table.setItem(row, column, other)
            self.table.setItem(target, column, current)
        self.table.blockSignals(False)
        self.table.selectRow(target)
        self._update()

    def _item_changed(self, item):
        # 用户编辑过的时间以新文本为准，清除旧的微秒级打点值。
        if item.column() < 2:
            self.table.blockSignals(True)
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.table.blockSignals(False)
        self._update()

    def _update(self):
        try:
            plan = self.plan()
            if plan is not None:
                plan.validate(self._duration_us)
                self.table.blockSignals(True)
                for row, clip in enumerate(plan.clips):
                    self.table.item(row, 2).setText(f"{(clip.out_us - clip.in_us) / 1_000_000:.3f} 秒")
                self.table.blockSignals(False)
            self.total_label.setText(f"合计 {len(plan.clips) if plan else 0} 段，导出 {plan.total_duration_us / 1_000_000 if plan else 0:.3f} 秒")
            self.status.setText("")
            set_label_kind(self.status, "muted")
        except ValueError as exc:
            self.status.setText(str(exc))
            self.total_label.setText("片段尚未设置完整")
            set_label_kind(self.status, "error")
        self.changed.emit()

    def _toggle_preview(self, expanded):
        if expanded and self.preview is None:
            from .preview_panel import PreviewPanel
            self.preview = PreviewPanel(self)
            self.preview_box.addWidget(self.preview)
            self.preview.duration_ready.connect(self.set_duration_us)
            self.preview.set_input(self._input_path)
        if self.preview:
            self.preview.setVisible(expanded)
            if not expanded:
                self.preview.pause()
        self.preview_toggle.setText("收起原片预览" if expanded else "展开原片预览")

    def _mark(self, edit):
        us = self.preview.mark_us() if self.preview else None
        if us is None:
            self.status.setText("请先展开预览并定位到画面，或手动填写时间。")
            return
        edit.setText(format_clip_time(us))
        self._precise_marks[edit] = (edit.text(), us)

    def _play_clip(self):
        row = self.table.currentRow()
        if row < 0:
            return
        try:
            self.validate_inputs()
            clip = self.plan().clips[row]
            self.preview_toggle.setChecked(True)
            self.preview.play_range(clip.in_us, clip.out_us)
        except ValueError:
            pass

    def set_running(self, running):
        if running and self.preview:
            self.preview.pause()
        self.setEnabled(not running)

    def release(self):
        if self.preview:
            self.preview.release()

    def hideEvent(self, event):
        if self.preview:
            self.preview.pause()
        super().hideEvent(event)
