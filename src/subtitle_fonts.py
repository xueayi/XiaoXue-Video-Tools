"""任务内字体索引与匹配，不安装或修改系统字体。"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable
import hashlib
import logging
import struct
import unicodedata
import zipfile

from fontTools.ttLib import TTFont, TTLibError

from .subtitle_document import FontRequest, SubtitleAnalysis
from .task.context import TaskCancelled


class FontCheckError(ValueError):
    pass


@dataclass(frozen=True)
class FontFace:
    path: Path
    index: int
    names: tuple[str, ...]
    full_name: str
    postscript_name: str
    weight: int
    italic: bool
    variable: bool
    sha256: str
    source: str = ''


@dataclass(frozen=True)
class FontBinding:
    requested_name: str
    face: FontFace


@dataclass(frozen=True)
class FontIssue:
    code: str
    font_name: str
    message: str


@dataclass(frozen=True)
class FontReport:
    matches: tuple[tuple[FontRequest, FontFace], ...] = ()
    issues: tuple[FontIssue, ...] = ()
    ready: bool = False
    verified: bool = False
    observed: tuple[FontRequest, ...] = ()


@dataclass(frozen=True)
class SubtitleFontOptions:
    enabled: bool = False
    sources: tuple[str, ...] = ()
    bindings: tuple[FontBinding, ...] = ()
    allow_fallback: bool = False


_SUFFIXES = {'.ttf', '.otf', '.ttc', '.otc'}


def _check(cancelled):
    if cancelled():
        raise TaskCancelled('字体检查已取消')


def font_sha256(path: Path, cancelled=lambda: False) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            _check(cancelled)
            digest.update(chunk)
    return digest.hexdigest()


def _font_paths(source: Path, cache: Path, cancelled):
    _check(cancelled)
    if source.is_dir():
        for path in source.rglob('*'):
            _check(cancelled)
            if path.is_symlink() or any(p.startswith('._') or p == '__MACOSX' for p in path.parts):
                continue
            if path.is_file() and path.suffix.lower() in _SUFFIXES | {'.zip'}:
                yield from _font_paths(path, cache, cancelled)
    elif source.suffix.lower() == '.zip':
        fingerprint = hashlib.sha256((str(source.resolve()) + str(source.stat().st_mtime_ns)
                                      + str(source.stat().st_size)).encode()).hexdigest()[:20]
        directory = cache / fingerprint
        directory.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            members = [m for m in archive.infolist() if PurePosixPath(m.filename).suffix.lower() in _SUFFIXES
                       and not PurePosixPath(m.filename).is_absolute()
                       and not any(p in ('..', '__MACOSX') or p.startswith('._')
                                   for p in PurePosixPath(m.filename).parts)]
            if len(members) > 256 or sum(m.file_size for m in members) > 512 * 1024 * 1024:
                raise FontCheckError('字体 ZIP 超过 256 个字体或 512 MB，请选择所需字体')
            for member in members:
                _check(cancelled)
                target = directory / (hashlib.sha256(member.filename.encode()).hexdigest()[:20]
                                      + PurePosixPath(member.filename).suffix.lower())
                partial = target.with_suffix('.part')
                try:
                    with archive.open(member) as src, partial.open('wb') as dst:
                        while chunk := src.read(1024 * 1024):
                            _check(cancelled)
                            dst.write(chunk)
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
                yield target, f'{source} · {member.filename}'
    elif source.suffix.lower() in _SUFFIXES:
        yield source, str(source)


def scan_font_sources(sources: tuple[str, ...], cache_dir: Path,
                      cancelled: Callable[[], bool]) -> tuple[FontFace, ...]:
    result, seen = [], set()
    for source in sources:
        try:
            path = Path(source)
            if not path.exists():
                raise OSError('路径不存在或共享卷未连接')
            for item, origin in _font_paths(path, Path(cache_dir), cancelled):
                _check(cancelled)
                try:
                    digest = font_sha256(item, cancelled)
                    with item.open('rb') as stream:
                        header = stream.read(12)
                    count = struct.unpack_from('>I', header, 8)[0] if header[:4] == b'ttcf' else 1
                    if count > 256:
                        raise TTLibError('字体集合的字形数量异常')
                    for index in range(count):
                        _check(cancelled)
                        if (digest, index) in seen:
                            continue
                        with TTFont(item, fontNumber=index, lazy=True) as font:
                            names = set()
                            for name in font['name'].names:
                                if name.nameID in (1, 2, 4, 6, 16, 17):
                                    try:
                                        names.add(name.toUnicode())
                                    except (UnicodeError, LookupError):
                                        continue
                            full = font['name'].getDebugName(4) or font['name'].getDebugName(1) or item.stem
                            ps = font['name'].getDebugName(6) or full
                            os2 = font.get('OS/2')
                            italic = bool(os2 and os2.fsSelection & 1)
                            result.append(FontFace(item.resolve(), index, tuple(sorted(names)), full, ps,
                                                   os2.usWeightClass if os2 else 400, italic,
                                                   'fvar' in font, digest, origin))
                            seen.add((digest, index))
                except (TTLibError, UnicodeError, KeyError, struct.error, AssertionError) as exc:
                    logging.getLogger(__name__).warning('无法读取字体 %s：%s', item, exc)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise FontCheckError(f'字体来源不可用：{source}：{exc}') from exc
    return tuple(result)


def _normal(name):
    return unicodedata.normalize('NFC', name).strip().casefold()


def resolve_fonts(analysis: SubtitleAnalysis, faces: tuple[FontFace, ...],
                  bindings: tuple[FontBinding, ...] = ()) -> FontReport:
    matches, issues = [], []
    explicit = {_normal(b.requested_name): b.face for b in bindings}
    for request, points in analysis.codepoints:
        name = _normal(request.name)
        selected = explicit.get(name)
        if selected:
            selected = next((f for f in faces if (f.sha256, f.index) ==
                             (selected.sha256, selected.index)), None)
            if selected is None:
                issues.append(FontIssue('source_unavailable', request.name,
                                        f'所选字体已不在当前来源中，请重新检查：{request.name}'))
                continue
        candidates = [selected] if selected else [f for f in faces if name in {_normal(n) for n in f.names}]
        if not candidates:
            issues.append(FontIssue('missing', request.name, f'未找到字体：{request.name}'))
            continue
        full = [f for f in candidates if name in (_normal(f.full_name), _normal(f.postscript_name))]
        if not selected:
            if full and request.bold == 0 and not request.italic:
                candidates = full  # Named Medium/Black is not a request for Regular.
            else:
                weight = 700 if request.bold in (-1, 1) else request.bold or 400
                styled = [f for f in candidates if f.weight == weight and f.italic == request.italic]
                if styled:
                    candidates = styled
                elif full:
                    candidates = full
                    issues.append(FontIssue('unsupported', request.name, f'字体缺少请求的真实字重/斜体：{request.name}'))
                else:
                    distance = min(abs(f.weight - weight) + (1000 if f.italic != request.italic else 0)
                                   for f in candidates)
                    candidates = [f for f in candidates if abs(f.weight - weight)
                                  + (1000 if f.italic != request.italic else 0) == distance]
                    if distance:
                        issues.append(FontIssue('fallback', request.name, f'将使用邻近字重而非请求字重：{request.name}'))
        if len(candidates) != 1:
            issues.append(FontIssue('ambiguous', request.name, f'字体同名，需选择具体文件：{request.name}'))
            continue
        face = candidates[0]
        matches.append((request, face))
        if face.variable:
            issues.append(FontIssue('unsupported', request.name, f'首版暂不支持可变字体：{request.name}'))
            continue
        try:
            with TTFont(face.path, fontNumber=face.index, lazy=True) as font:
                cmap = font.getBestCmap() or {}
                missing = sorted(p for p in points if p not in cmap and unicodedata.category(chr(p)) != 'Cf')
            if missing:
                sample = ''.join(chr(p) for p in missing[:8])
                issues.append(FontIssue('missing_glyph', request.name, f'字体缺少字符：{request.name}：{sample}'))
        except (OSError, TTLibError) as exc:
            issues.append(FontIssue('source_unavailable', request.name, f'字体来源不可用：{exc}'))
    return FontReport(tuple(matches), tuple(issues), not issues)
