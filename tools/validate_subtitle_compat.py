"""使用固定 262 素材验证原生字幕字体、快照与编码时间线。"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def shift_test_subtitle(source: Path, output: Path, offset: int):
    from src.subtitle_document import _read, _records
    text, encoding = _read(source)
    replacements = {}
    for line, kind, fields, values in _records(text):
        if kind != 'dialogue':
            continue
        for field in ('start', 'end'):
            index = fields.index(field)
            h, m, s = values[index].strip().split(':')
            cs = round((int(h)*3600 + int(m)*60 + float(s) - offset) * 100)
            if cs < 0:
                raise ValueError('测试样本不能产生负字幕时间')
            values[index] = f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'
        newline = line[len(line.rstrip('\r\n')):]
        replacements[line] = line.partition(':')[0] + ':' + ','.join(values) + newline
    output.write_bytes(''.join(replacements.get(line, line) for line in text.splitlines(keepends=True)).encode(encoding))


def prepare_fonts(root, cache, manifest, download):
    from src.subtitle_fonts import font_sha256
    cache.mkdir(parents=True, exist_ok=True)
    for spec in manifest['fonts']:
        target = cache/spec['name']
        if target.exists() and font_sha256(target) == spec['sha256']:
            continue
        shared = list((root/'字体整理').glob('*/' + spec['name']))
        if shared:
            shutil.copyfile(shared[0], target)
        elif 'member' in spec:
            with ZipFile(root/'09_NotoSerifCJKsc.zip') as z:
                target.write_bytes(z.read(spec['member']))
        elif spec['name'].startswith('MiSans'):
            shutil.copyfile(root/'MiSans/MiSans 开发下载字重'/spec['name'], target)
        elif download:
            with urlopen(Request(spec['source'], headers={'User-Agent': 'XiaoXue-subtitle-validation'}), timeout=45) as r:
                data = r.read()
            import hashlib
            if hashlib.sha256(data).hexdigest() != spec['sha256']:
                raise ValueError('下载字体 SHA256 不匹配')
            target.write_bytes(data)
        else:
            raise ValueError(f"缺字体 {spec['name']}；提供文件或显式启用 --download-missing-fonts")
        if font_sha256(target) != spec['sha256']:
            raise ValueError(f"字体 SHA256 不匹配：{target}")
    return tuple(str(cache/s['name']) for s in manifest['fonts'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--font-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download-missing-fonts', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    for name in ('frames', 'outputs', 'logs'):
        (out/name).mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'tests/fixtures/subtitle_compat/262_manifest.json').read_text(encoding='utf-8'))
    for stem in ('ffmpeg', 'ffprobe'):
        bundled = ROOT/'build/macos-media/bin'/stem
        if bundled.is_file():
            os.environ['XIAOXUE_' + stem.upper()] = str(bundled)
    os.environ.update(QT_QPA_PLATFORM='offscreen', XIAOXUE_NO_UPDATE_CHECK='1')
    from PyQt6.QtWidgets import QApplication
    from src.capabilities.ffmpeg_probe import probe_ffmpeg, set_capabilities
    from src.subtitle_fonts import (SubtitleFontOptions, FontBinding, FontCheckError,
                                     scan_font_sources, font_sha256)
    from src.subtitle_render import prepare_subtitle, render_subtitle_preview
    from src.utils import get_ffmpeg_path, get_ffprobe_path
    from src.ui.tabs.encode_tab import EncodeTab
    from src.executors.video_executor import execute_encode
    from src.clip_plan import ClipSpec
    from src.presets import APPLE_H264_PRESET
    ffmpeg, ffprobe = get_ffmpeg_path(), get_ffprobe_path()
    app = QApplication.instance() or QApplication([])
    caps = probe_ffmpeg(ffmpeg); set_capabilities(caps)
    assert 'subtitles' in caps.filters
    video, ass = (args.corpus_root/manifest[key] for key in ('video', 'subtitle'))
    assert video.stat().st_size == manifest['video_bytes']
    before = {str(p): font_sha256(p) for p in (video, ass)}
    assert before[str(ass)] == manifest['subtitle_sha256']
    sources = prepare_fonts(args.corpus_root, args.font_cache.resolve(), manifest, args.download_missing_fonts)
    before.update({p: font_sha256(Path(p)) for p in sources})
    options = SubtitleFontOptions(True, sources)
    result = {'runtime': caps.version, 'cases': {}, 'font_sources': manifest['fonts']}

    def record(name, details):
        result['cases'][name] = {'status': 'pass', **details}
        (out/'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print('PASS', name, flush=True)

    def raw(command, name, timeout=240):
        run = subprocess.run(command, capture_output=True, timeout=timeout)
        (out/'logs'/f'{name}.log').write_bytes(run.stderr)
        if run.returncode:
            raise RuntimeError(run.stderr.decode(errors='replace')[-2500:])
        return run.stdout

    def probe(path):
        return json.loads(raw([ffprobe, '-v', 'error', '-show_streams', '-show_format',
                               '-of', 'json', str(path)], 'probe-' + path.stem))

    tab = EncodeTab(); tab.apply_capabilities(caps)
    def encode_case(name, input_path, subtitle_path, encoder, *, two_pass=False, clips=None):
        tab.clip_editor.enable_cb.setChecked(False)
        tab.input_edit.setText(str(input_path)); tab.subtitle_edit.setText(str(subtitle_path))
        tab.preset_combo.setCurrentText('自定义 (Custom)')
        tab.encoder_combo.setCurrentText(encoder)
        tab.rate_control_combo.setCurrentText('2-Pass VBR (两遍编码)' if two_pass else 'CRF/CQ (恒定质量)')
        tab.speed_preset_combo.setCurrentText('ultrafast')
        tab.crf_spin.setValue(65 if 'Apple' in encoder else 18)
        from src.presets import AUDIO_ENCODERS
        tab.audio_encoder_combo.setCurrentText(next(k for k,v in AUDIO_ENCODERS.items() if v=='aac'))
        tab.video_bitrate_combo.setCurrentText('2M')
        tab.output_edit.setText(str(out/'outputs'/(name + '.mp4')))
        tab.debug_mode_cb.setChecked(False)
        tab.font_panel.setChecked(True)
        tab.font_panel.add_sources(list(sources))
        if clips:
            tab.clip_editor.set_duration_us(round(manifest['duration']*1_000_000), authoritative=True)
            tab.clip_editor.enable_cb.setChecked(True)
            for a,b in clips:
                tab.clip_editor._append(ClipSpec(a,b))
        namespace = tab.build_args()
        assert namespace.subtitle_fonts.enabled
        with (out/'logs'/(name + '.log')).open('w') as stream, redirect_stdout(stream), redirect_stderr(stream):
            encoded = execute_encode(namespace)
        if not encoded.is_ok:
            raise RuntimeError(f'{name}: {encoded.message}')
        report = encoded.details['font_report']
        assert report.ready and report.verified, report
        info = probe(Path(namespace.output))
        assert any(s['codec_type']=='video' for s in info['streams'])
        assert any(s['codec_type']=='audio' for s in info['streams'])
        record(name, {'file': namespace.output, 'font_report': asdict(report), 'probe': info})
        return namespace.output, info

    try:
        try:
            with prepare_subtitle(str(ass), SubtitleFontOptions(True)):
                raise AssertionError('缺字体被误判为通过')
        except FontCheckError:
            record('missing_fonts_rejected', {})
        with prepare_subtitle(str(ass), options) as prepared:
            assert {f.weight for _,f in prepared.report.matches} == {500,900}
            for us in manifest['frames_us']:
                frame = render_subtitle_preview(str(video), us, prepared, out/'frames'/f'{us}.png')
                assert frame.report.ready
                record(f'frame_{us}', {'actual_us': frame.actual_us, 'observed': [r.name for r in frame.report.observed]})
            (out/'font-report.json').write_text(json.dumps(asdict(prepared.report), ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        faces = scan_font_sources(sources, out/'font-imports', lambda: False)
        mi = next(f for f in faces if f.postscript_name=='MiSans-Medium')
        mapping = (FontBinding('Noto Sans SC Medium', mi),)
        try:
            with prepare_subtitle(str(ass), SubtitleFontOptions(True,sources,mapping)):
                raise AssertionError('MiSans 缺少 ・ 但未被识别')
        except FontCheckError:
            record('misans_missing_middle_dot_rejected', {})
        with prepare_subtitle(str(ass), SubtitleFontOptions(True,sources,mapping,True)) as prepared:
            frame = render_subtitle_preview(str(video),19_000_000,prepared,out/'frames/misans-19000000.png')
            assert len(frame.report.observed)==2
            assert {f.postscript_name for _,f in frame.report.matches}=={'MiSans-Medium','NotoSerifCJKsc-Black'}
            record('explicit_misans_mapping_with_warning', {'font_report': asdict(frame.report)})
        sample = out/'sample-16-29.mkv'
        raw([ffmpeg,'-v','error','-y','-ss','16','-i',str(video),'-t','13',
             '-map','0:v:0','-map','0:a:0','-c:v','ffv1','-c:a','pcm_s16le',str(sample)],'sample')
        sample_ass = out/'sample-16-29.ass'; shift_test_subtitle(ass,sample_ass,16)
        encode_case('cpu_crf',sample,sample_ass,'H.264 (CPU - libx264)')
        encode_case('cpu_two_pass',sample,sample_ass,'H.264 (CPU - libx264)',two_pass=True)
        encode_case('apple',sample,sample_ass,'H.264 (Apple VideoToolbox)')
        _, info = encode_case('reordered_clips',video,ass,'H.264 (CPU - libx264)',
                               clips=[(23640000,28410000),(17770000,23640000)])
        streams = info['streams']; v = next(s for s in streams if s['codec_type']=='video')
        a = next(s for s in streams if s['codec_type']=='audio')
        assert int(v['nb_frames'])==638
        assert abs(float(v['duration'])-float(a['duration'])) <= 1/60+1024/int(a['sample_rate'])+0.01
        tab.clip_editor.enable_cb.setChecked(False)
        _, info = encode_case('complete_video',video,ass,'H.264 (Apple VideoToolbox)')
        streams = info['streams']
        v = next(s for s in streams if s['codec_type']=='video')
        a = next(s for s in streams if s['codec_type']=='audio')
        assert int(v['nb_frames']) == 22082
        assert abs(float(v['duration'])-manifest['duration']) < 1/60
        assert abs(float(v['duration'])-float(a['duration'])) <= 1/60+1024/int(a['sample_rate'])+0.01
        render_log = (out/'logs/complete_video.log').read_text(encoding='utf-8', errors='replace')
        result['libass'] = dict(re.findall(r'libass (API version|source): ([^\r\n]+)', render_log))
        assert result['libass'], '未记录 libass 版本'
        (out/'font-report.json').write_text(json.dumps(result['cases']['complete_video']['font_report'],
                                                      ensure_ascii=False, indent=2), encoding='utf-8')
        result['cases']['windows_vsfilter_reference'] = {'status':'not_run','reason':'未提供 Windows VSFilter 参考帧'}
        after = {p:font_sha256(Path(p)) for p in before}
        assert before==after
        (out/'source-checksums.json').write_text(json.dumps({'before':before,'after':after},ensure_ascii=False,indent=2), encoding='utf-8')
        result['ok'] = True
    except Exception as exc:
        result['ok'] = False
        result['error'] = str(exc)
        raise
    finally:
        tab.release()
        import time
        deadline = time.monotonic()+5
        while tab.font_panel._queue.busy and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        (out/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str), encoding='utf-8')
    print(out/'manifest.json')


if __name__ == '__main__':
    main()
