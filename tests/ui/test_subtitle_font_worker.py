import threading
import time

from src.ui.subtitle_font_worker import SubtitleJobQueue
from src.task.context import current_task,TaskCancelled


def pump_until(app,predicate,timeout=3):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(0.005)
    assert predicate()


def test_stale_scan_or_preview_is_discarded(qapp):
    queue=SubtitleJobQueue()
    entered=threading.Event();results=[];runs=[]
    queue.completed.connect(lambda generation,result:results.append((generation,result)))
    def slow():
        entered.set();runs.append('first')
        while not current_task().cancelled:time.sleep(0.005)
        raise TaskCancelled()
    queue.submit(1,slow)
    assert entered.wait(1)
    queue.submit(2,lambda:runs.append('second') or 'second')
    queue.submit(3,lambda:runs.append('third') or 'third')
    pump_until(qapp,lambda:not queue.busy)
    assert runs==['first','third'] and results==[(3,'third')]
    queue.release()


def test_export_and_close_cancel_preview_without_late_ui_write(qapp):
    queue=SubtitleJobQueue();entered=threading.Event();results=[]
    queue.completed.connect(lambda *r:results.append(r))
    def slow():
        entered.set()
        while not current_task().cancelled:time.sleep(0.005)
        return 'late result'
    queue.submit(1,slow);assert entered.wait(1)
    queue.release()
    pump_until(qapp,lambda:not queue.busy)
    assert not results
