"""两遍统计文件必须独立且不触碰工作目录中的用户文件。"""
from pathlib import Path
import pytest
from src import core
from src.task.context import TaskCancelled


@pytest.mark.parametrize('outcome', ['success', 'failed', 'cancelled'])
def test_twopass_stats_are_isolated_and_always_cleaned(monkeypatch, tmp_path, outcome):
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / 'ffmpeg2pass.log'
    existing.write_text('user data')
    calls = []
    def run(cmd, **kwargs):
        calls.append(list(cmd))
        prefix = Path(cmd[cmd.index('-passlogfile') + 1])
        assert prefix.is_absolute() and prefix.parent != tmp_path
        Path(str(prefix) + '-0.log').write_text('stats')
        if outcome == 'cancelled':
            raise TaskCancelled()
        return 1 if outcome == 'failed' else 0
    monkeypatch.setattr(core, 'run_ffmpeg_command', run)
    if outcome == 'cancelled':
        with pytest.raises(TaskCancelled):
            core.run_2pass_encode(['ffmpeg', 'pass1'], ['ffmpeg', 'pass2'])
    else:
        assert core.run_2pass_encode(['ffmpeg', 'pass1'], ['ffmpeg', 'pass2']) == (1 if outcome == 'failed' else 0)
    assert existing.read_text() == 'user data'
    prefix = Path(calls[0][calls[0].index('-passlogfile') + 1])
    assert not prefix.parent.exists()
    if outcome == 'success':
        assert calls[1][calls[1].index('-passlogfile') + 1] == str(prefix)
