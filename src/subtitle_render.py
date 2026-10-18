"""字体准备目录与 FFmpeg/libass 渲染报告；资源由单次任务持有。"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import tempfile

from .platform.paths import platform_paths
from .subtitle_document import analyze_subtitle, rewrite_font_names
from .subtitle_fonts import (FontCheckError, FontIssue, FontReport, SubtitleFontOptions,
                              font_sha256, resolve_fonts, scan_font_sources)
from .task.context import current_task
from .utils import get_ffmpeg_path


@dataclass(frozen=True)
class PreparedSubtitle:
    path: str
    fonts_dir: str | None
    report: FontReport


@dataclass(frozen=True)
class SubtitlePreview:
    path: Path
    report: FontReport
    actual_us: int


def _cancelled():
    context = current_task()
    return bool(context and context.cancelled)


@contextmanager
def prepare_subtitle(path: str, options: SubtitleFontOptions):
    if not options.enabled:
        yield PreparedSubtitle(path, None, FontReport())
        return
    with tempfile.TemporaryDirectory(prefix='subtitle-', dir=platform_paths().temp_dir) as tmp:
        directory = Path(tmp)
        try:
            analysis = analyze_subtitle(Path(path))
            faces = scan_font_sources(options.sources, directory/'imported', _cancelled)
            # ZIP import paths differ between UI and this task; identify the same bytes/face.
            for binding in options.bindings:
                if not any(f.sha256 == binding.face.sha256 and f.index == binding.face.index for f in faces):
                    raise FontCheckError(f'字体来源已变化，请重新检查：{binding.requested_name}')
            report = resolve_fonts(analysis, faces, options.bindings)
            if not report.ready and not options.allow_fallback:
                raise FontCheckError('；'.join(i.message for i in report.issues))
            fonts = directory/'fonts'
            fonts.mkdir()
            copied = set()
            for _, face in report.matches:
                if face.sha256 in copied:
                    continue
                target = fonts/(face.sha256[:20] + face.path.suffix.lower())
                # A block copy is cancellable even for a large TTC on a shared volume.
                with face.path.open('rb') as source, target.open('wb') as output:
                    while chunk := source.read(1024 * 1024):
                        context = current_task()
                        if context:
                            context.raise_if_cancelled()
                        output.write(chunk)
                if font_sha256(target, _cancelled) != face.sha256:
                    raise FontCheckError(f'字体来源已变化，请重新检查：{face.full_name}')
                copied.add(face.sha256)
            mapping = {b.requested_name: b.face.full_name for b in options.bindings}
            subtitle = rewrite_font_names(analysis, mapping, directory/'mapped.ass')
        except FontCheckError:
            raise
        except (ValueError, OSError) as exc:
            raise FontCheckError(str(exc)) from exc
        yield PreparedSubtitle(str(subtitle), str(fonts), report)


def _filter_value(value):
    # Option parsing consumes one escaping layer, the filter graph consumes another.
    value = ''.join('\\' + c if c in "\\':" else c for c in str(value))
    return ''.join('\\' + c if c in "\\'[],;" else c for c in value)


def build_subtitle_filter(prepared: PreparedSubtitle) -> str:
    result = 'subtitles=filename=' + _filter_value(prepared.path)
    if prepared.fonts_dir:
        result += ':fontsdir=' + _filter_value(prepared.fonts_dir)
    return result


class FontSelectionCollector:
    _selection = re.compile(r'fontselect:\s*\((.*),\s*(\d+),\s*(\d+)\)\s*->\s*(.*),\s*(-?\d+),\s*(.+)$')

    def __init__(self, prepared: PreparedSubtitle):
        self.prepared = prepared
        self.observed = set()
        self.issues = list(prepared.report.issues)

    def _issue(self, code, name, message):
        issue = FontIssue(code, name, message)
        if issue not in self.issues:
            self.issues.append(issue)

    def feed(self, line: str) -> None:
        if 'fontselect:' in line:
            match = self._selection.search(line.strip())
            if not match:
                code = 'missing_glyph' if 'fallback' in line or 'glyph' in line else 'unverified'
                self._issue(code, '', line.strip()[-350:])
                return
            name, weight, italic, _, index, actual = match.groups()
            for request, face in self.prepared.report.matches:
                expected_name = {request.name.casefold(), face.full_name.casefold(), face.postscript_name.casefold()}
                requested_weight = 700 if request.bold in (-1, 1) else request.bold or 400
                if name.casefold() not in expected_name or int(weight) != requested_weight or bool(int(italic)) != request.italic:
                    continue
                if actual.casefold() != face.postscript_name.casefold():
                    self._issue('fallback', request.name, f'字体发生替换：{request.name} → {actual}')
                else:
                    self.observed.add(request)
            # Missing fonts allowed explicitly have no expected physical face.
            unresolved = [i.font_name for i in self.prepared.report.issues if i.code == 'missing']
            if name in unresolved:
                self._issue('fallback', name, f'字体发生替换：{name} → {actual}')
        elif 'Glyph ' in line and ('not found' in line or 'fallback' in line):
            self._issue('missing_glyph', '', line.strip()[-350:])

    def report(self) -> FontReport:
        base = self.prepared.report
        ready = base.ready and not any(i.code in ('fallback', 'missing_glyph') for i in self.issues)
        verified = ready and not self.issues and bool(base.matches) and all(r in self.observed for r, _ in base.matches)
        return FontReport(base.matches, tuple(self.issues), ready, verified,
                          tuple(r for r, _ in base.matches if r in self.observed))


def render_subtitle_preview(input_path: str, source_us: int, prepared: PreparedSubtitle,
                            output: Path, resolution: str | None = None) -> SubtitlePreview:
    """保留原片时间轴解码，先渲染字幕再选帧；不使用重置字幕时钟的 input seek。"""
    from .core import run_ffmpeg_streaming
    if source_us < 0:
        raise FontCheckError('预览时间必须非负')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = [build_subtitle_filter(prepared)]
    if resolution:
        if not re.fullmatch(r'[1-9]\d*x[1-9]\d*', resolution):
            raise FontCheckError('预览分辨率应为 WxH')
        filters.append('scale=' + resolution.replace('x', ':'))
    filters.extend([f"select='gte(t,{source_us / 1_000_000:.6f})'", 'showinfo'])
    collector = FontSelectionCollector(prepared)
    timestamps = []
    def log(line):
        collector.feed(line)
        match = re.search(r'\bpts_time:([+\-\d.eE]+)', line)
        if match and not timestamps:
            timestamps.append(round(float(match[1]) * 1_000_000))
    command = [get_ffmpeg_path(), '-hide_banner', '-nostats', '-y', '-i', input_path,
               '-vf', ','.join(filters), '-frames:v', '1', '-update', '1', str(output)]
    try:
        result = run_ffmpeg_streaming(command, on_log=log, timeout=60)
        if not result.ok or not output.is_file() or not timestamps:
            raise FontCheckError('未生成预览帧，请检查时间点、视频和字体配置')
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return SubtitlePreview(output, collector.report(), timestamps[0])
