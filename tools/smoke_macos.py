# -*- coding: utf-8 -*-
"""用应用包内媒体依赖验证 UI → executor → FFmpeg，并检查打包启动。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_smoke_font(path):
    """生成独立测试字体，冻结烟测不依赖系统已安装字体。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder = FontBuilder(1000, isTTF=True)
    order = ['.notdef', 'A']
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({65: 'A'})
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0)); pen.lineTo((250, 700)); pen.lineTo((450, 0)); pen.closePath()
    glyph = pen.glyph()
    builder.setupGlyf({name: glyph for name in order})
    builder.setupHorizontalMetrics({name: (600, 50) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'XiaoXue Smoke Medium', 'styleName': 'Regular',
                            'fullName': 'XiaoXue Smoke Medium', 'psName': 'XiaoXueSmoke-Medium'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800,
                     usWinDescent=200, usWeightClass=500)
    builder.setupPost()
    builder.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=ROOT / 'dist/小雪工具箱.app')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/macos-smoke')
    args = parser.parse_args()
    app_path = args.app.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    media = app_path / 'Contents/Frameworks/bin'
    ffmpeg, ffprobe = (str(media / name) for name in ('ffmpeg', 'ffprobe'))
    os.environ.update(XIAOXUE_FFMPEG=ffmpeg, XIAOXUE_FFPROBE=ffprobe,
                      XIAOXUE_NO_UPDATE_CHECK='1', QT_QPA_PLATFORM='offscreen')
    from PyQt6.QtWidgets import QApplication
    from src.capabilities.ffmpeg_probe import probe_ffmpeg, set_capabilities
    from src.platform.capabilities import platform_capabilities
    from src.presets import APPLE_H264_PRESET
    from src.ui.tabs.encode_tab import EncodeTab
    from src.executors.video_executor import execute_encode
    from src.core import build_remux_command, run_ffmpeg_command
    from src.process.subprocess_runner import SubprocessRunner
    from src.process.qprocess_runner import QProcessRunner

    def raw(command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr[-2000:])
        return result.stdout

    source = output / '输入 空格.mp4'
    raw([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
         'testsrc2=size=640x360:rate=24:duration=2', '-f', 'lavfi', '-i',
         'sine=frequency=440:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', str(source)])
    caps = probe_ffmpeg(ffmpeg)
    assert not caps.probe_error, caps.probe_error
    assert 'subtitles' in caps.filters
    set_capabilities(caps)
    platform_capabilities(refresh=True)
    app = QApplication(['smoke'])
    tab = EncodeTab()
    tab.apply_capabilities(caps)
    tab.input_edit.setText(str(source))
    tab.preset_combo.setCurrentText(APPLE_H264_PRESET)
    report = {'ffmpeg_version': caps.version, 'scenarios': {}}
    subtitle = output / '字幕.srt'
    subtitle.write_text('1\n00:00:00,100 --> 00:00:01,900\n小雪工具箱字幕验证\n', encoding='utf-8')
    for name, encoder, mode in [
        ('apple_preset', None, None),
        ('apple_hevc', 'H.265/HEVC (Apple VideoToolbox)', 'CRF/CQ (恒定质量)'),
        ('apple_vbr', 'H.264 (Apple VideoToolbox)', 'VBR (可变码率)'),
        ('cpu_twopass', 'H.264 (CPU - libx264)', '2-Pass VBR (两遍编码)'),
        ('cpu_hevc_twopass', 'H.265/HEVC (CPU - libx265)', '2-Pass VBR (两遍编码)'),
        ('subtitle', 'H.264 (CPU - libx264)', 'CRF/CQ (恒定质量)'),
    ]:
        if encoder:
            tab.preset_combo.setCurrentText('自定义 (Custom)')
            tab.encoder_combo.setCurrentText(encoder)
            tab.rate_control_combo.setCurrentText(mode)
            tab.video_bitrate_combo.setCurrentText('2M')
        tab.subtitle_edit.setText(str(subtitle) if name == 'subtitle' else '')
        tab.output_edit.setText(str(output / f'{name}.mp4'))
        namespace = tab.build_args()
        namespace.debug_mode = False
        old_cwd = Path.cwd()
        try:
            os.chdir('/')  # 真实只读工作目录；统计文件应在平台临时目录。
            result = execute_encode(namespace)
        finally:
            os.chdir(old_cwd)
        assert result.status.value == 'success', (name, result)
        probe = json.loads(raw([ffprobe, '-v', 'error', '-show_entries',
                               'stream=codec_name:format=duration', '-of', 'json', namespace.output]))
        expected = 'hevc' if name in ('apple_hevc', 'cpu_hevc_twopass') else 'h264'
        assert probe['streams'][0]['codec_name'] == expected
        assert float(probe['format']['duration']) >= 1.9
        report['scenarios'][name] = probe
    # UI片段快照 -> executor -> 包内FFmpeg；两种编码器各导出两个0.5秒片段。
    editor = tab.clip_editor
    editor.enable_cb.setChecked(True)
    for start, end in [('00:00:00.250', '00:00:00.750'), ('00:00:01.000', '00:00:01.500')]:
        editor.in_edit.setText(start)
        editor.out_edit.setText(end)
        editor.add_btn.click()
    tab.subtitle_edit.clear()
    for name, encoder, mode in [
        ('clips_apple', 'H.264 (Apple VideoToolbox)', 'CRF/CQ (恒定质量)'),
        ('clips_cpu_twopass', 'H.264 (CPU - libx264)', '2-Pass VBR (两遍编码)'),
    ]:
        tab.encoder_combo.setCurrentText(encoder)
        tab.rate_control_combo.setCurrentText(mode)
        tab.output_edit.setText(str(output / f'{name}.mp4'))
        tab.prepare_execution()
        namespace = tab.build_args()
        namespace.debug_mode = False
        result = execute_encode(namespace)
        assert result.is_ok, result
        probe = json.loads(raw([ffprobe, '-v', 'error', '-show_entries',
                               'stream=codec_name,nb_frames:format=duration', '-of', 'json', namespace.output]))
        assert 0.95 <= float(probe['format']['duration']) <= 1.10
        assert int(probe['streams'][0]['nb_frames']) == 24
        report['scenarios'][name] = probe
    editor.enable_cb.setChecked(False)
    # 保留一帧，供字体渲染人工核对。
    raw([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', '1', '-i',
         str(output / 'subtitle.mp4'), '-frames:v', '1', str(output / 'subtitle.png')])
    remux = output / 'remux.mkv'
    assert run_ffmpeg_command(build_remux_command(str(source), str(remux))) == 0
    report['remux_exists'] = remux.stat().st_size > 0
    report['cancel'] = {}
    for runner_type in (SubprocessRunner, QProcessRunner):
        runner = runner_type()
        lines = []
        runner.on_stdout = lines.append
        runner.start([ffmpeg, '-hide_banner', '-loglevel', 'error', '-re', '-f', 'lavfi',
                      '-i', 'testsrc2=size=320x180:rate=24', '-progress', 'pipe:1',
                      '-stats_period', '0.1', '-f', 'null', '-'], stdin_pipe=True)
        handle = runner._process
        pid = handle.pid if runner_type is SubprocessRunner else int(handle.processId())
        timer = threading.Timer(0.7, runner.cancel)
        timer.start()
        result = runner.wait(timeout=10)
        timer.join()
        assert result.cancelled and not runner.is_running()
        assert any('out_time_' in line for line in lines)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError(f'取消后进程仍在运行: {pid}')
        report['cancel'][runner_type.__name__] = 'passed'
    tab.release()
    tab.close()
    # 直接运行冻结入口，PATH 无 Homebrew，不依赖构建环境中的 python。
    env = dict(os.environ, PATH='/usr/bin:/bin:/usr/sbin:/sbin')
    env.pop('XIAOXUE_FFMPEG', None)
    env.pop('XIAOXUE_FFPROBE', None)
    preview_report = output / 'frozen-preview.json'
    with (output / 'frozen-preview.log').open('w') as log:
        completed = subprocess.run([str(app_path / 'Contents/MacOS/XiaoXueToolbox'),
                                    '--media-diagnostics', str(source), '--report', str(preview_report)],
                                   cwd='/', env=env, stdout=log, stderr=log, timeout=20)
    assert completed.returncode == 0, (output / 'frozen-preview.log').read_text()
    report['frozen_preview'] = json.loads(preview_report.read_text())
    assert report['frozen_preview']['ok']
    smoke_font = output / '独立测试字体.ttf'
    make_smoke_font(smoke_font)
    ass = output / '字体烟测.ass'
    ass.write_text('''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name,Fontname,Fontsize,Bold,Italic,PrimaryColour,Alignment
Style: Default,XiaoXue Smoke Medium,40,0,0,&H00FFFFFF,2
[Events]
Format: Start,End,Style,Text
Dialogue: 0:00:00.00,0:00:02.00,Default,AAA
''', encoding='utf-8')
    font_report = output / 'frozen-fonts.json'
    with (output / 'frozen-fonts.log').open('w') as log:
        completed = subprocess.run([str(app_path / 'Contents/MacOS/XiaoXueToolbox'),
                                    '--subtitle-diagnostics', str(source), '--subtitle', str(ass),
                                    '--font-source', str(smoke_font), '--time', '1',
                                    '--report', str(font_report)],
                                   cwd='/', env=env, stdout=log, stderr=log, timeout=80)
    assert completed.returncode == 0, (output / 'frozen-fonts.log').read_text()
    report['frozen_fonts'] = json.loads(font_report.read_text(encoding='utf-8'))
    assert report['frozen_fonts']['font_report']['verified']
    with (output / 'app-startup.log').open('w') as log:
        process = subprocess.Popen([str(app_path / 'Contents/MacOS/XiaoXueToolbox')],
                                   cwd='/', env=env, stdout=log, stderr=log)
        try:
            time.sleep(3)
            assert process.poll() is None, (output / 'app-startup.log').read_text()
            report['frozen_startup'] = 'passed (offscreen, restricted PATH, cwd=/)'
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
