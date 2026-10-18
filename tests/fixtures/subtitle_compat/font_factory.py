"""小型自制字体供 CI 使用，不依赖系统安装的 Noto 字体。"""
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def make_font(path, name='Demo Medium', weight=500, characters='中文甲乙丙丁正文标题ABC123', family=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    builder = FontBuilder(1000, isTTF=True)
    cmap = {ord(c): f'uni{ord(c):04X}' for c in characters}
    order = ['.notdef'] + list(dict.fromkeys(cmap.values()))
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for glyph in order:
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.lineTo((450, 700)); pen.lineTo((450, 0)); pen.closePath()
        glyphs[glyph] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({glyph: (600, 50) for glyph in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': family or name, 'styleName': 'Regular',
                            'fullName': name, 'psName': name.replace(' ', '-'),
                            'uniqueFontIdentifier': f'{name}-{weight}', 'version': 'Version 1.0'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800,
                     usWinDescent=200, usWeightClass=weight)
    builder.setupPost()
    builder.save(path)
    return path
