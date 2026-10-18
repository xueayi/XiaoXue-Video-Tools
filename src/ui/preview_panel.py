"""原片播放器；只用实际显示帧时间戳打点，不模拟导出效果。"""
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel


class PreviewPanel(QWidget):
    duration_ready = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_us = None
        self._range_end_us = None
        self._pending_seek_us = None
        self._play_when_seekable = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(180)
        self.video.setMaximumHeight(320)
        layout.addWidget(self.video)
        row = QHBoxLayout()
        self.play_btn = QPushButton("播放")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        self.time_label = QLabel("00:00.000 / 00:00.000")
        row.addWidget(self.play_btn)
        row.addWidget(self.slider, 1)
        row.addWidget(self.time_label)
        layout.addLayout(row)
        self.status = QLabel("原片预览；字幕、缩放和压缩效果以导出为准")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.5)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.seekableChanged.connect(self._seekable_changed)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(self._error)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.video.videoSink().videoFrameChanged.connect(self._on_frame)
        self.play_btn.clicked.connect(self._toggle_play)
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(80)
        self._seek_timer.timeout.connect(lambda: self.seek(self.slider.value() * 1000))
        self.slider.sliderMoved.connect(lambda _: self._seek_timer.start())
        self.slider.sliderReleased.connect(lambda: self.seek(self.slider.value() * 1000))

    def set_input(self, path):
        self.release()
        self.status.setText("原片预览；字幕、缩放和压缩效果以导出为准")
        self.player.setSource(QUrl.fromLocalFile(path) if path else QUrl())

    def _on_frame(self, frame):
        self._frame_us = frame.startTime() if frame.isValid() and frame.startTime() >= 0 else None

    def mark_us(self):
        return self._frame_us

    def seek(self, us):
        self._seek_timer.stop()
        self._frame_us = None
        if self._ready_to_seek():
            self.player.setPosition(max(0, us // 1000))
        else:
            self._pending_seek_us = us

    def play_range(self, start_us, end_us):
        self._range_end_us = end_us
        self.seek(start_us)
        if self._ready_to_seek():
            self.player.play()
        else:
            self._play_when_seekable = True

    def pause(self):
        self._play_when_seekable = False
        self.player.pause()
        self._seek_timer.stop()

    def release(self):
        self._seek_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self._frame_us = None
        self._range_end_us = None
        self._pending_seek_us = None
        self._play_when_seekable = False
        self.slider.setEnabled(False)

    def _seekable_changed(self, seekable):
        self.slider.setEnabled(seekable)
        self._apply_pending_seek()

    def _ready_to_seek(self):
        return self.player.isSeekable() and self.player.mediaStatus() not in (
            QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.NoMedia,
            QMediaPlayer.MediaStatus.InvalidMedia)

    def _media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            # seekableChanged 可先于 LoadedMedia；后端完成加载后再定位和播放。
            QTimer.singleShot(0, self._apply_pending_seek)

    def _apply_pending_seek(self):
        if not self._ready_to_seek():
            return
        if self._pending_seek_us is not None:
            pending, self._pending_seek_us = self._pending_seek_us, None
            self.seek(pending)
        if self._play_when_seekable:
            self._play_when_seekable = False
            self.player.play()

    def _toggle_play(self):
        self._range_end_us = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.player.play()

    def _position_changed(self, ms):
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{ms / 1000:.3f}s / {self.player.duration() / 1000:.3f}s")
        if self._range_end_us is not None and ms * 1000 >= self._range_end_us:
            self.pause()
            self._range_end_us = None

    def _duration_changed(self, ms):
        self.slider.setRange(0, min(ms, 2_147_483_647))
        if ms > 0:
            self.duration_ready.emit(ms * 1000)

    def _state_changed(self, state):
        self.play_btn.setText("暂停" if state == QMediaPlayer.PlaybackState.PlayingState else "播放")

    def _error(self, *_):
        self._frame_us = None
        self.status.setText(f"预览不可用：{self.player.errorString()}。仍可手动填写时间并导出。")

    def hideEvent(self, event):
        self.pause()
        super().hideEvent(event)
