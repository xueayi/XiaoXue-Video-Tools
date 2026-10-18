import subprocess
import time


def test_range_preview_waits_for_seek_before_playing(qapp, tmp_path, media_binaries):
    from src.ui.preview_panel import PreviewPanel
    source = tmp_path / "preview.mp4"
    subprocess.run([media_binaries[0], "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=24:duration=3", "-c:v", "libx264", str(source)], check=True)
    panel = PreviewPanel()
    panel.audio.setMuted(True)
    seen = []
    panel.video.videoSink().videoFrameChanged.connect(
        lambda f: seen.append(f.startTime()) if f.isValid() else None)
    panel.set_input(str(source))
    panel.play_range(1_000_000, 1_500_000)
    deadline = time.monotonic() + 8
    while not seen and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    panel.release()
    assert seen, "没有解码到视频帧"
    assert seen[0] >= 950_000, seen[:5]
