"""ASS/SSA 字体需求分析；字体映射仅改任务副本中的名称。"""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class FontRequest:
    name: str
    bold: int = 0
    italic: bool = False


@dataclass(frozen=True)
class SubtitleAnalysis:
    path: Path
    requests: tuple[FontRequest, ...]
    codepoints: tuple[tuple[FontRequest, frozenset[int]], ...]


def _read(path):
    data = Path(path).read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        encoding = 'utf-16'
    elif data.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8-sig'
    else:
        try:
            data.decode('utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError:
            import chardet
            encoding = chardet.detect(data).get('encoding')
            if not encoding:
                raise ValueError('无法识别字幕编码，请另存为 UTF-8')
    return data.decode(encoding), encoding


def _records(text):
    section, formats = '', {}
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('['):
            section = stripped.casefold()
        prefix, sep, body = line.partition(':')
        kind = prefix.strip().casefold()
        if sep and kind == 'format':
            formats[section] = tuple(x.strip().casefold() for x in body.split(','))
        fields = formats.get(section, ())
        if sep and kind in ('style', 'dialogue'):
            if not fields:
                raise ValueError('字幕缺少 Format 定义')
            if kind == 'dialogue' and fields[-1] != 'text':
                raise ValueError('字幕 Text 必须是 Format 的最后一列')
            values = body.rstrip('\r\n').split(',', len(fields) - 1)
            if len(values) != len(fields):
                raise ValueError('字幕字段数量与 Format 不一致')
            yield line, kind, fields, values


def _tags(block):
    """括号内的反斜杠属于当前标签，不能当作顶层 fn/r。"""
    pos = 0
    while (pos := block.find('\\', pos)) >= 0:
        start = pos + 1
        pos = start
        depth = 0
        while pos < len(block):
            char = block[pos]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == '\\' and depth == 0:
                break
            pos += 1
        if depth:
            raise ValueError('字幕覆盖标签括号不完整')
        token = block[start:pos]
        if token.startswith('t('):
            if re.search(r'\\(?:fn|[bi](?=[+\-\d]))', token):
                raise ValueError('暂不支持变换标签内的字体变化，请关闭字体增强')
        elif token.startswith('fn'):
            yield 'fn', token[2:]
        elif token.startswith('r'):
            yield 'r', token[1:]
        else:
            match = re.fullmatch(r'([bip])([+\-]?\d*)', token)
            if match:
                yield match.group(1), match.group(2)


def analyze_subtitle(path: Path) -> SubtitleAnalysis:
    path = Path(path)
    text, _ = _read(path)
    records = list(_records(text))
    styles = {}
    for _, kind, fields, values in records:
        if kind == 'style':
            style = dict(zip(fields, (v.strip() for v in values)))
            styles[style['name']] = FontRequest(style['fontname'], int(style.get('bold', 0)),
                                                bool(int(style.get('italic', 0))))
    if not styles:
        raise ValueError('字幕缺少可识别的 ASS/SSA 样式')
    chars = {}
    for _, kind, fields, values in records:
        if kind != 'dialogue':
            continue
        event = dict(zip(fields, values))
        base_name = event.get('style', '').strip()
        if base_name not in styles:
            raise ValueError(f'字幕引用不存在的样式：{base_name}')
        base = current = styles[base_name]
        drawing = 0
        for part in re.split(r'(\{[^}]*\})', event['text']):
            if part.startswith('{') and part.endswith('}'):
                for tag, arg in _tags(part[1:-1]):
                    if tag == 'r':
                        name = arg.strip() or base_name
                        if name not in styles:
                            raise ValueError(f'字幕引用不存在的样式：{name}')
                        current, drawing = styles[name], 0
                    elif tag == 'fn':
                        current = FontRequest(arg.strip() or base.name, current.bold, current.italic)
                    elif tag == 'b':
                        current = FontRequest(current.name, int(arg) if arg else base.bold, current.italic)
                    elif tag == 'i':
                        current = FontRequest(current.name, current.bold, bool(int(arg)) if arg else base.italic)
                    elif tag == 'p':
                        drawing = int(arg or 0)
            elif not drawing:
                visible = part.replace(r'\N', '\n').replace(r'\n', '\n').replace(r'\h', ' ')
                points = {ord(c) for c in visible if not c.isspace()}
                if points:
                    chars.setdefault(current, set()).update(points)
    return SubtitleAnalysis(path, tuple(chars), tuple((r, frozenset(c)) for r, c in chars.items()))


def rewrite_font_names(analysis: SubtitleAnalysis, mapping: dict[str, str], output: Path) -> Path:
    if not mapping:
        return analysis.path
    if any(not value or any(c in value for c in ',{}\\\r\n') for value in mapping.values()):
        raise ValueError('映射字体名称含不支持的 ASS 字符')
    text, encoding = _read(analysis.path)
    replacements = {}
    for line, kind, fields, values in _records(text):
        if kind == 'style':
            index = fields.index('fontname')
            value = values[index]
            if value.strip() in mapping:
                values[index] = value.replace(value.strip(), mapping[value.strip()], 1)
                prefix = line.partition(':')[0] + ':'
                newline = line[len(line.rstrip('\r\n')):]
                replacements[line] = prefix + ','.join(values) + newline
    def rewrite_block(match):
        return re.sub(r'\\fn([^\\}]*)', lambda m: r'\fn' + mapping.get(m[1].strip(), m[1]), match[0])
    result = ''.join(replacements.get(line, line) for line in text.splitlines(keepends=True))
    result = re.sub(r'\{[^}]*\}', rewrite_block, result)
    Path(output).write_bytes(result.encode(encoding))
    return Path(output)
