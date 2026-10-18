"""冻结应用内验证字体导入和单帧 UI 链路，供打包烟测调用。"""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time


def run_font_diagnostics(video: str, subtitle: str, sources: tuple[str, ...],
                          report_path: str, source_us: int = 19_000_000) -> int:
    from PyQt6.QtWidgets import QApplication
    from .ui.subtitle_font_panel import SubtitleFontPanel
    app = QApplication.instance() or QApplication([])
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    panel = SubtitleFontPanel()
    result = {'ok': False}
    def wait_job():
        deadline = time.monotonic()+65
        while panel._job_kind is not None and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.01)
        if panel._job_kind is not None or panel.report is None:
            raise RuntimeError(panel.status.text())
    try:
        panel.set_inputs(video, subtitle)
        panel.set_available(True)
        panel.setChecked(True)
        panel.add_sources(list(sources))
        panel.check_fonts(); wait_job(); panel.require_ready()
        panel.set_source_time(source_us)
        panel.preview_frame(); wait_job()
        if not panel.report.ready:
            raise RuntimeError(panel.status.text())
        image = next(iter(panel._preview_cache.values())).path
        shutil.copyfile(image, path.with_suffix('.png'))
        panel.resize(860, 900); panel.show(); app.processEvents()
        panel.grab().save(str(path.with_name(path.stem + '-panel.png')))
        result = {'ok': True, 'font_report': asdict(panel.report), 'status': panel.status.text(),
                  'image': str(path.with_suffix('.png'))}
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        panel.release()
        deadline = time.monotonic()+5
        while panel._queue.busy and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.01)
        panel.close()
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return 0 if result['ok'] else 1
