"""Mac 硬字幕字体来源、显式映射和原片时间点效果快照。"""
from dataclasses import replace
from pathlib import Path
import hashlib
import tempfile

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QGroupBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QListWidget, QLabel, QTableWidget, QTableWidgetItem,
                              QComboBox, QCheckBox, QFileDialog, QLineEdit, QHeaderView)

from ..platform.paths import platform_paths
from ..subtitle_document import analyze_subtitle
from ..subtitle_fonts import (FontBinding, SubtitleFontOptions, scan_font_sources,
                               resolve_fonts, font_sha256)
from ..subtitle_render import prepare_subtitle, render_subtitle_preview
from ..task.context import current_task
from ..utils import get_ffmpeg_path
from .clip_editor import parse_clip_time, format_clip_time
from .subtitle_font_worker import SubtitleJobQueue


class SubtitleFontPanel(QGroupBox):
    changed = pyqtSignal()
    request_current_mark = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('字体兼容增强', parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.generation = 0
        self.report = None
        self._inputs = ('', '')
        self._sources, self._faces, self._bindings = [], (), {}
        self._available, self._running, self._closed = True, False, False
        self._resolution = None
        self._job_kind = None
        self._preview_cache = {}
        temp_dir = platform_paths().temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix='font-panel-', dir=temp_dir)
        self._queue = SubtitleJobQueue()
        self._queue.completed.connect(self.accept_result)
        outer = QVBoxLayout(self)
        self.body = QWidget()
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel('导入字体后检查实际字形；字体不会安装到系统。效果快照显示原片时间点的字幕与缩放。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        for title, slot in [('添加目录', self._choose_directory), ('添加字体/ZIP', self._choose_files),
                             ('移除', self._remove_source), ('检查字体', self.check_fonts)]:
            button = QPushButton(title)
            button.clicked.connect(slot)
            row.addWidget(button)
        layout.addLayout(row)
        self.sources_list = QListWidget()
        self.sources_list.setMaximumHeight(82)
        layout.addWidget(self.sources_list)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['字幕请求', '实际字形 / 字重（可选择替换）', '字体来源'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(180)
        layout.addWidget(self.table)
        self.allow_fallback = QCheckBox('允许字体替换（保留警告）')
        self.allow_fallback.toggled.connect(self._policy_changed)
        layout.addWidget(self.allow_fallback)
        row = QHBoxLayout()
        self.time_edit = QLineEdit('00:00:00.000')
        self.time_edit.setMaximumWidth(150)
        self.time_edit.setToolTip('原片时间，格式 HH:MM:SS.mmm')
        self.time_edit.textChanged.connect(self._preview_changed)
        self.mark_button = QPushButton('使用原片当前帧')
        self.mark_button.clicked.connect(self.request_current_mark.emit)
        self.preview_button = QPushButton('字幕效果快照')
        self.preview_button.clicked.connect(self.preview_frame)
        self.cancel_button = QPushButton('取消检查/快照')
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.time_edit); row.addWidget(self.mark_button)
        row.addWidget(self.preview_button); row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.status = QLabel('添加字体来源后点击“检查字体”。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMaximumHeight(320)
        layout.addWidget(self.image)
        outer.addWidget(self.body)
        self.body.hide()
        self.toggled.connect(self._toggle)

    def _toggle(self, enabled):
        self.body.setVisible(enabled)
        if not enabled:
            self.cancel()
        self.changed.emit()

    def options(self) -> SubtitleFontOptions:
        return SubtitleFontOptions(self.isChecked() and self._available, tuple(self._sources),
                                    tuple(FontBinding(name, face) for name, face in self._bindings.items()),
                                    self.allow_fallback.isChecked())

    def set_available(self, available, reason=''):
        self._available = available
        if not available:
            self.setChecked(False)
        self.setEnabled(available and not self._running)
        self.setToolTip(reason)

    def set_inputs(self, video: str, subtitle: str):
        if (video, subtitle) != self._inputs:
            self._inputs = video, subtitle
            self._bindings.clear()
            self._invalidate()

    def set_resolution(self, resolution):
        if resolution != self._resolution:
            self._resolution = resolution
            self._preview_changed()

    def _invalidate(self):
        self.generation += 1
        self._queue.cancel()
        self.report = None
        self._faces = ()
        self.table.setRowCount(0)
        self.image.clear()
        self.status.setText('配置已变化，请重新检查字体。')
        self.changed.emit()

    def add_sources(self, paths):
        for path in paths:
            if path not in self._sources:
                self._sources.append(path)
                self.sources_list.addItem(path)
        self._invalidate()

    def _choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, '选择字体目录')
        if path: self.add_sources([path])

    def _choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择字体或字体 ZIP', '',
                                                '字体及压缩包 (*.ttf *.otf *.ttc *.otc *.zip)')
        self.add_sources(paths)

    def _remove_source(self):
        row = self.sources_list.currentRow()
        if row >= 0:
            self._sources.pop(row)
            self.sources_list.takeItem(row)
            self._bindings.clear()
            self._invalidate()

    def check_fonts(self):
        options = self.options()
        if not options.enabled:
            return
        self.generation += 1
        self.report = None
        self.image.clear()
        self.status.setText('正在检查字体…')
        subtitle, directory = self._inputs[1], Path(self._temp.name)/'imports'
        self._job_kind = 'scan'
        def work():
            before = font_sha256(Path(subtitle))
            analysis = analyze_subtitle(Path(subtitle))
            faces = scan_font_sources(options.sources, directory, lambda: current_task().cancelled)
            report = resolve_fonts(analysis, faces, options.bindings)
            if before != font_sha256(Path(subtitle)):
                raise ValueError('字幕已变化，请重新检查')
            return {'kind': 'scan', 'faces': faces, 'report': report}
        self._queue.submit(self.generation, work)

    def accept_result(self, generation, result):
        if self._closed or generation != self.generation:
            return
        self._job_kind = None
        if isinstance(result, Exception):
            self.status.setText(str(result))
            return
        self.report = result['report']
        if result['kind'] == 'scan':
            self._faces = result['faces']
            self._show_matches()
            message = '字体文件检查通过；实际匹配以快照或导出报告为准。'
        else:
            pixmap = QPixmap(str(result['preview'].path))
            thumbnail = pixmap.scaled(760, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
            self.image.setPixmap(thumbnail)
            self.image.setMinimumHeight(thumbnail.height())
            message = '字幕效果快照 ' + format_clip_time(result['preview'].actual_us)
            message += ' · 本帧字体匹配已核对' if self.report.verified else ' · 本帧未出现全部字幕字体'
        self.status.setText('；'.join(i.message for i in self.report.issues) or message)

    def _show_matches(self):
        names = list(dict.fromkeys([r.name for r, _ in self.report.matches] +
                                   [i.font_name for i in self.report.issues if i.font_name]))
        self.table.setRowCount(len(names))
        for row, name in enumerate(names):
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            face = next((f for r, f in self.report.matches if r.name == name), None)
            combo = QComboBox()
            combo.addItem(f'自动：{face.full_name} · {face.weight}' if face else '自动：未匹配', None)
            for candidate in self._faces:
                source = candidate.source or str(candidate.path)
                combo.addItem(f'{candidate.full_name} · {candidate.weight} · {Path(source).name}', candidate)
                combo.setItemData(combo.count()-1, source, Qt.ItemDataRole.ToolTipRole)
                selected = self._bindings.get(name)
                if selected and selected.sha256 == candidate.sha256 and selected.index == candidate.index:
                    combo.setCurrentIndex(combo.count()-1)
            combo.currentIndexChanged.connect(lambda _, n=name, c=combo: self._map_font(n, c.currentData()))
            self.table.setCellWidget(row, 1, combo)
            source = QTableWidgetItem(face.source if face else '未匹配')
            source.setToolTip(source.text())
            source.setFlags(source.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, source)

    def _map_font(self, name, face):
        if face is None:
            self._bindings.pop(name, None)
        else:
            self._bindings[name] = face
        self.changed.emit()
        self.check_fonts()

    def _policy_changed(self):
        self._preview_changed()
        self.changed.emit()

    def _preview_changed(self):
        self.image.clear()
        if self._job_kind == 'preview':
            self.generation += 1
            self._queue.cancel()
            self._job_kind = None

    def require_ready(self):
        if not self.options().enabled:
            return
        if self.report is None:
            raise ValueError('字体配置尚未检查，请先点击“检查字体”')
        if not self.report.ready and not self.allow_fallback.isChecked():
            raise ValueError('字体检查未通过：' + '；'.join(i.message for i in self.report.issues))

    def set_source_time(self, us):
        if us is None:
            self.status.setText('请先展开原片预览并定位，或手动填写时间。')
        else:
            self.time_edit.setText(format_clip_time(us))

    def preview_frame(self):
        try:
            self.require_ready()
            source_us = parse_clip_time(self.time_edit.text())
            if not self.options().enabled:
                return
        except ValueError as exc:
            self.status.setText(str(exc)); return
        self.generation += 1
        self.image.clear()
        self.status.setText('正在生成字幕效果快照，可随时取消…')
        self._job_kind = 'preview'
        video, subtitle = self._inputs
        options, resolution = self.options(), self._resolution
        output, cache = Path(self._temp.name)/'previews', self._preview_cache
        def work():
            from ..core import run_ffmpeg_streaming
            stat = Path(video).stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            version = []
            run_ffmpeg_streaming([get_ffmpeg_path(), '-version'], on_line=version.append, timeout=5)
            with prepare_subtitle(subtitle, options) as prepared:
                key = (video, signature, font_sha256(Path(subtitle)), source_us, resolution,
                       tuple((r, f.sha256, f.index) for r, f in prepared.report.matches), tuple(version))
                digest = hashlib.sha256(repr(key).encode()).hexdigest()
                previous = cache.get(digest)
                if previous and previous.path.is_file():
                    preview = replace(previous, report=replace(previous.report, matches=prepared.report.matches))
                else:
                    preview = render_subtitle_preview(video, source_us, prepared, output/(digest + '.png'), resolution)
                    cache[digest] = preview
                after = Path(video).stat()
                if (after.st_size, after.st_mtime_ns) != signature:
                    raise ValueError('输入视频已变化，请重新生成快照')
            return {'kind': 'preview', 'preview': preview, 'report': preview.report}
        self._queue.submit(self.generation, work)

    def cancel(self):
        self.generation += 1
        self._queue.cancel()
        self._job_kind = None

    def set_running(self, running):
        self._running = running
        if running:
            self.cancel()
        self.setEnabled(self._available and not running)

    def release(self):
        self._closed = True
        self._queue.release()
        if self._queue.busy:
            self._queue.idle.connect(self._temp.cleanup)
        else:
            self._temp.cleanup()
