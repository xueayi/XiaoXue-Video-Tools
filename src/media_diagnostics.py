"""冻结应用的原片播放诊断，可从命令行输出媒体后端检测报告。"""
import json
from pathlib import Path


def run_preview_diagnostics(input_path: str, report_path: str, target_us: int = 500_000) -> int:
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication
    from .ui.preview_panel import PreviewPanel

    app = QApplication.instance() or QApplication(["media-diagnostics"])
    panel = PreviewPanel()
    panel.audio.setMuted(True)
    loop = QEventLoop()
    frames, errors = [], []

    def frame_received(frame):
        if frame.isValid():
            frames.append(frame.startTime())
            if len(frames) >= 4:
                loop.quit()

    panel.video.videoSink().videoFrameChanged.connect(frame_received)
    panel.player.errorOccurred.connect(lambda *_: (errors.append(panel.player.errorString()), loop.quit()))
    panel.set_input(str(Path(input_path).resolve()))
    panel.play_range(target_us, target_us + 1_000_000)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(10_000)
    loop.exec()
    timeout.stop()
    report = dict(input=str(input_path), target_us=target_us, frame_pts_us=frames,
                  errors=errors, seekable=panel.player.isSeekable(), duration_ms=panel.player.duration())
    report["ok"] = bool(len(frames) >= 4 and not errors and frames[0] >= target_us - 100_000)
    panel.release()
    panel.deleteLater()
    app.processEvents()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
