"""Font atlas: glyphs rasterised with Pillow at exact pixel sizes, shelf-packed into one 8-bit
CPU-side atlas (uploaded to GL by Draw2D). Advance metrics only (no kerning) so measuring and
drawing are trivially consistent.

The atlas also holds a 4x4 white block at (0,0) used for solid shapes (sample at WHITE_UV).
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_DIRS = [
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
    os.path.expanduser('~/.fonts'),
    '/usr/share/fonts/truetype/dejavu',
    '/usr/share/fonts/TTF',
    '/Library/Fonts',
    '/System/Library/Fonts/Supplemental',
]
_CANDIDATES = {
    'regular': ['segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf', 'Arial.ttf'],
    'bold': ['segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf'],
    'mono': ['consola.ttf', 'cour.ttf', 'DejaVuSansMono.ttf'],
}

# ASCII, Latin-1, Latin Extended-A, Vietnamese (O/U horn + U+1EA0..1EF9) and a few symbols
CHAR_RANGES = [(0x20, 0x7E), (0xA0, 0xFF), (0x100, 0x17F), (0x1A0, 0x1B0), (0x1EA0, 0x1EF9)]
EXTRA_CHARS = ('\u2026\u2013\u2014\u2018\u2019\u201C\u201D\u2022\u2190\u2191\u2192\u2193'
               '\u00D7\u2713\u25B2\u25BC\u25B6\u20AC\u2318\u21E7')

WHITE_UV = (2.0, 2.0)
MIN_SIZE, MAX_SIZE = 5, 160


def find_font(style: str = 'regular') -> str | None:
    for name in _CANDIDATES.get(style, _CANDIDATES['regular']):
        for d in _FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    if style != 'regular':
        return find_font('regular')
    return None


def preset_chars() -> str:
    out = [chr(c) for a, b in CHAR_RANGES for c in range(a, b + 1)]
    return ''.join(out) + EXTRA_CHARS


class Glyph:
    __slots__ = ('advance', 'ox', 'oy', 'w', 'h', 'u', 'v')

    def __init__(self):
        self.advance = 0.0
        self.ox = self.oy = self.w = self.h = 0
        self.u = self.v = 0


class Face:
    """One font file at one integer pixel size. y offsets are relative to the top of the line box."""

    def __init__(self, atlas: 'FontAtlas', path: str | None, size: int):
        self.atlas = atlas
        self.size = size
        if path:
            try:
                self.font = ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)
            except Exception:
                self.font = ImageFont.load_default(size)
        else:
            self.font = ImageFont.load_default(size)
        try:
            asc, desc = self.font.getmetrics()
        except Exception:
            asc, desc = size, size // 4
        self.ascent, self.descent = int(asc), int(desc)
        self.line_height = self.ascent + self.descent
        try:
            cap_top = self.font.getbbox('H')[1]
        except Exception:
            cap_top = self.ascent * 0.3
        # offset from line top to the visual middle of capital letters (for vertical centring)
        self.mid = (cap_top + self.ascent) * 0.5
        self.glyphs: dict[str, Glyph] = {}
        for ch in preset_chars():
            self.bake(ch)

    def bake(self, ch: str) -> Glyph:
        g = Glyph()
        try:
            l, t, r, b = self.font.getbbox(ch)
            g.advance = float(self.font.getlength(ch))
        except Exception:
            l = t = r = b = 0
            g.advance = self.size * 0.5
        w, h = int(r - l), int(b - t)
        g.ox, g.oy = int(l), int(t)
        if w > 0 and h > 0 and not ch.isspace():
            img = Image.new('L', (w, h), 0)
            ImageDraw.Draw(img).text((-l, -t), ch, font=self.font, fill=255)
            u, v = self.atlas.alloc(w, h)
            self.atlas.pixels[v:v + h, u:u + w] = np.asarray(img, dtype=np.uint8)
            self.atlas.version += 1
            g.w, g.h, g.u, g.v = w, h, u, v
        self.glyphs[ch] = g
        return g

    def glyph(self, ch: str) -> Glyph:
        g = self.glyphs.get(ch)
        return g if g is not None else self.bake(ch)

    def width(self, s: str) -> float:
        gl = self.glyphs
        best = pen = 0.0
        for ch in s:
            if ch == '\n':
                best = max(best, pen)
                pen = 0.0
                continue
            g = gl.get(ch) or self.bake(ch)
            pen += g.advance
        return max(best, pen)

    def offsets(self, s: str) -> list:
        """Caret x positions (len(s)+1 entries, single line), rounded exactly like drawing."""
        out = [0]
        pen = 0.0
        for ch in s:
            pen += self.glyph(ch).advance
            out.append(int(round(pen)))
        return out


class FontAtlas:
    def __init__(self, width: int = 1024, height: int = 512, paths: dict | None = None):
        self.width = width
        self.pixels = np.zeros((height, width), np.uint8)
        self.pixels[0:4, 0:4] = 255
        self.version = 1
        self._x, self._y, self._row_h = 6, 0, 4
        self.paths = {k: find_font(k) for k in _CANDIDATES}
        if paths:
            self.paths.update(paths)
        self.faces: dict = {}

    @property
    def height(self) -> int:
        return self.pixels.shape[0]

    def reset(self):
        self.pixels[:] = 0
        self.pixels[0:4, 0:4] = 255
        self._x, self._y, self._row_h = 6, 0, 4
        self.faces = {}
        self.version += 1

    def alloc(self, w: int, h: int) -> tuple:
        if w + 2 > self.width:
            w = self.width - 2
        if self._x + w + 1 > self.width:
            self._y += self._row_h + 1
            self._x, self._row_h = 1, 0
        while self._y + h + 1 > self.height:
            if self.height >= 8192:
                raise MemoryError('font atlas full')
            grown = np.zeros((self.height * 2, self.width), np.uint8)
            grown[:self.height] = self.pixels
            self.pixels = grown
        u, v = self._x, self._y
        self._x += w + 1
        self._row_h = max(self._row_h, h)
        return u, v

    def face(self, size: float, style: str = 'regular') -> Face:
        isz = int(round(min(max(size, MIN_SIZE), MAX_SIZE)))
        key = (style, isz)
        f = self.faces.get(key)
        if f is None:
            try:
                f = Face(self, self.paths.get(style) or self.paths.get('regular'), isz)
            except MemoryError:
                self.reset()
                f = Face(self, self.paths.get(style) or self.paths.get('regular'), isz)
            self.faces[key] = f
        return f

    def text_size(self, s: str, size: float = 14, style: str = 'regular') -> tuple:
        f = self.face(size, style)
        lines = s.count('\n') + 1
        return f.width(s), float(f.line_height * lines)


_shared: FontAtlas | None = None


def shared_atlas() -> FontAtlas:
    global _shared
    if _shared is None:
        _shared = FontAtlas()
    return _shared
