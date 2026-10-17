# -*- coding: utf-8 -*-
"""UI 测试公共设施: 离屏 QApplication + QSettings 重定向到临时目录。"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 必须在 QApplication 创建前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 测试环境禁用启动时的自动更新检查 (避免真实网络请求)
os.environ["XIAOXUE_NO_UPDATE_CHECK"] = "1"

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """会话级 QApplication (离屏平台, 不显示任何窗口)。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """把 QSettings 重定向到每测试独立的临时 ini 文件。

    注意: QSettings(org, app) 双参构造在 Windows 上永远走注册表,
    因此隔离必须 monkeypatch gui_config.get_qsettings 这一个入口。
    """
    ini = tmp_path / "settings" / "config.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtCore import QSettings

    def fake_qsettings():
        return QSettings(str(ini), QSettings.Format.IniFormat)

    import src.gui_config as gc
    monkeypatch.setattr(gc, "get_qsettings", fake_qsettings)
    yield


@pytest.fixture(scope="session", autouse=True)
def _slot_exception_guard():
    """把 PyQt6 的槽异常从 qFatal-abort 转为可见的日志失败。

    PyQt6 在槽内出现未处理异常且 sys.excepthook 为默认值时会直接
    qFatal 杀死进程 (exit 127), 导致整个测试会话崩溃且丢失输出。
    安装自定义 excepthook 后异常只会被打印, 对应测试按断言失败处理。
    """
    import sys
    import traceback

    def hook(tp, val, tb):
        print("\n--- Qt 槽内未处理异常 ---")
        traceback.print_exception(tp, val, tb)
        print("--- 测试可能因此未完成预期操作 ---")

    sys.excepthook = hook
    yield
    sys.excepthook = sys.__excepthook__


@pytest.fixture(autouse=True)
def _drain_deferred_deletes(qapp):
    """每个测试结束后立即处理 deleteLater 与挂起事件。

    跨测试延迟析构 C++ 对象会引发随机原生崩溃 (access violation)。
    """
    from PyQt6.QtCore import QEvent
    yield
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def pump(app, ms: int):
    """跑事件循环 ms 毫秒, 让信号/动画/线程回调得到处理。"""
    import time

    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()


@pytest.fixture
def pump_fn(qapp):
    return lambda ms=100: pump(qapp, ms)


# ----------------------------------------------------------------
# M3.1: FFmpeg 能力探测替身
# ----------------------------------------------------------------

class _FakeSignal:
    """最小信号替身: 支持 connect / emit (同步直连)。"""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class FakeProbeWorker:
    """CapabilityProbeWorker 替身: 不创建 QThread、不跑子进程。"""

    def __init__(self, parent=None, refresh=True):
        self.parent_obj = parent
        self.refresh = refresh
        self.finished_caps = _FakeSignal()
        self.finished = _FakeSignal()  # QThread 内置信号 (主窗口连 deleteLater)
        self.running = False
        self.started = False

    def start(self):
        self.started = True
        self.running = True

    def isRunning(self):  # noqa: N802 - 模拟 QThread API
        return self.running

    def wait(self, msecs=0):
        self.running = False
        return True

    def deleteLater(self):  # noqa: N802 - 模拟 QObject API
        pass


class ProbeStub:
    """main_window.start_capability_probe 的替身, 记录每次创建。"""

    def __init__(self):
        self.workers = []

    def __call__(self, parent=None, timeout=15.0, refresh=True):
        worker = FakeProbeWorker(parent=parent, refresh=refresh)
        self.workers.append(worker)
        worker.start()
        return worker

    @property
    def calls(self):
        return len(self.workers)

    def emit_latest(self, caps):
        """向最近创建的 worker 发出 finished_caps, 模拟探测完成。"""
        assert self.workers, "尚未创建探测 worker"
        self.workers[-1].finished_caps.emit(caps)


@pytest.fixture(autouse=True)
def capability_probe_stub(monkeypatch):
    """所有 UI 测试统一替换后台能力探测。

    主窗口在 showEvent 后会自动启动探测; 测试环境不能启动真实 QThread
    (会真的跑 ffmpeg, 且线程生命周期与离屏窗口难以同步), 因此默认换成
    可手动 emit 的替身。需要真实探测行为的测试应显式 monkeypatch。
    """
    import src.ui.main_window as mw
    from src.capabilities import ffmpeg_probe

    ffmpeg_probe.set_capabilities(None)
    stub = ProbeStub()
    monkeypatch.setattr(mw, "start_capability_probe", stub)
    yield stub
    ffmpeg_probe.set_capabilities(None)


# ----------------------------------------------------------------
# M4.4: 平台路径 / 平台能力替身
# ----------------------------------------------------------------

def make_platform_paths(base):
    """构造临时目录下的 PlatformPaths 替身 (UI 测试用, 不创建真实目录)。"""
    from src.platform.paths import PlatformPaths

    return PlatformPaths(
        resource_dir=base / "resource",
        install_dir=base / "install",
        config_dir=base / "config",
        data_dir=base / "data",
        cache_dir=base / "cache",
        log_dir=base / "logs",
        temp_dir=base / "temp",
    )


def make_platform_capabilities(**overrides):
    """构造平台能力快照替身 (默认 Windows: 自更新与 AviSynth 可用)。"""
    from src.platform.capabilities import PlatformCapabilities

    values = {
        "os_name": "win32",
        "ffmpeg_path": "",
        "ffprobe_path": "",
        "ffmpeg_caps": None,
        "avisynth_available": True,
        "self_update_available": True,
        "videotoolbox_available": False,
    }
    values.update(overrides)
    return PlatformCapabilities(**values)


class MutablePlatformCapabilities:
    """可变平台能力替身 (``is_windows`` / ``is_macos`` 由 ``os_name`` 派生)。

    与 :func:`make_platform_capabilities` 的冻结快照不同, 这个替身允许用例
    中途改属性 (例如 Windows → darwin), 用于平台矩阵断言。
    """

    def __init__(self, os_name="win32", ffmpeg_path="", ffprobe_path="",
                 ffmpeg_caps=None, avisynth_available=True,
                 self_update_available=True, videotoolbox_available=False):
        self.os_name = os_name
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.ffmpeg_caps = ffmpeg_caps
        self.avisynth_available = avisynth_available
        self.self_update_available = self_update_available
        self.videotoolbox_available = videotoolbox_available

    @property
    def is_windows(self):
        return self.os_name == "win32"

    @property
    def is_macos(self):
        return self.os_name == "darwin"

    @property
    def is_linux(self):
        return self.os_name.startswith("linux")


@pytest.fixture
def platform_caps_stub():
    """返回可变平台能力替身类, 供平台矩阵用例自行实例化。"""
    return MutablePlatformCapabilities


@pytest.fixture(autouse=True)
def platform_state_stub(tmp_path, monkeypatch):
    """隔离平台路径与平台能力单例 (M4.4)。

    设置页存储位置 / 首页环境能力 / 压制页兼容模式门禁都会读取
    ``platform_paths()`` 与 ``platform_capabilities()``; 测试环境统一换成
    临时目录 + 固定 Windows 快照, 既不创建仓库内真实目录, 也不做真实
    平台探测。需要 macOS 等其它场景的用例可再次 monkeypatch ``detect``
    或直接替换页面模块里的 ``platform_capabilities``。
    """
    from src.platform import capabilities as platform_caps
    from src.platform import paths as platform_paths

    fake_paths = make_platform_paths(tmp_path)
    monkeypatch.setattr(platform_paths, "detect", lambda: fake_paths)
    monkeypatch.setattr(platform_caps, "detect", make_platform_capabilities)
    platform_paths.reset_platform_paths()
    platform_caps.reset_platform_capabilities()
    yield fake_paths
    platform_paths.reset_platform_paths()
    platform_caps.reset_platform_capabilities()
