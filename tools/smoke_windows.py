"""检查 Windows 冻结包的原片解码、定位与主窗口启动。"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("dist/小雪工具箱"))
    parser.add_argument("--output", type=Path, default=Path("build/windows-smoke"))
    args = parser.parse_args()
    app = args.app.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    executable = app / "小雪工具箱.exe"
    ffmpeg = app / "_internal/bin/ffmpeg.exe"
    if not ffmpeg.is_file():
        ffmpeg = app / "bin/ffmpeg.exe"
    source = output / "输入 空格.mp4"
    subprocess.run([str(ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=24:duration=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", str(source)],
                   check=True, timeout=45)
    env = dict(os.environ, XIAOXUE_NO_UPDATE_CHECK="1", QT_QPA_PLATFORM="offscreen")
    env.pop("XIAOXUE_FFMPEG", None)
    env.pop("XIAOXUE_FFPROBE", None)
    report = output / "frozen-preview.json"
    with (output / "frozen-preview.log").open("wb") as log:
        completed = subprocess.run([str(executable), "--media-diagnostics", str(source), "--report", str(report)],
                                   cwd=output, env=env, stdout=log, stderr=log, timeout=20)
    assert completed.returncode == 0, (output / "frozen-preview.log").read_text(encoding="utf-8", errors="replace")
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["ok"], result
    with (output / "app-startup.log").open("wb") as log:
        process = subprocess.Popen([str(executable)], cwd=output, env=env, stdout=log, stderr=log)
        try:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                result["frozen_startup"] = "passed"
            else:
                raise AssertionError((output / "app-startup.log").read_text(encoding="utf-8", errors="replace"))
        finally:
            process.terminate()
            process.wait(timeout=10)
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
