"""Vector icons drawn with Draw2D primitives (no image assets). Every icon lives in the unit square
[-1, 1]^2 centred on (cx, cy) and is scaled by `r` (half the icon size in pixels)."""

from __future__ import annotations

import math


def _arc(cx, cy, rad, a0, a1, n=24):
    return [(cx + rad * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + rad * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _dashed(d, pts, col, t, dash, gap, closed=False):
    """Dashed polyline (lengths in pixels)."""
    pts = list(pts) + ([pts[0]] if closed else [])
    on, left = True, dash
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-6:
            continue
        ux, uy, pos = (x1 - x0) / seg, (y1 - y0) / seg, 0.0
        while pos < seg:
            step = min(left, seg - pos)
            if on:
                d.line(x0 + ux * pos, y0 + uy * pos, x0 + ux * (pos + step), y0 + uy * (pos + step), col, t)
            pos += step
            left -= step
            if left <= 1e-6:
                on = not on
                left = dash if on else gap


def _arrow_head(d, tip, ang, size, col, t):
    for da in (150, -150):
        a = math.radians(ang + da)
        d.line(tip[0], tip[1], tip[0] + size * math.cos(a), tip[1] + size * math.sin(a), col, t)


def _pointer(d, x, y, r, col):
    """Small filled mouse-pointer arrow with its tip at (x, y)."""
    d.polygon_fill([(x, y), (x + r * 0.55, y + r * 0.95), (x + r * 0.22, y + r * 0.72),
                    (x - r * 0.05, y + r * 1.1), (x - r * 0.28, y + r * 0.62), (x - r * 0.5, y + r * 0.9)], col)


def draw_icon(d, name, cx, cy, size, col, thick=1.6):
    r = size * 0.5
    t = max(1.0, thick)
    dash, gap = max(2.0, r * 0.3), max(2.0, r * 0.22)
    L = d.line

    def P(x, y):
        return (cx + x * r, cy + y * r)

    if name in ('undo', 'redo'):
        s = -1 if name == 'redo' else 1
        pts = [(cx + s * (x * r), cy + y * r) for x, y in
               [(px, py) for px, py in [(math.cos(math.radians(a)) * 0.7, math.sin(math.radians(a)) * 0.7)
                                        for a in range(-150, 100, 12)]]]
        d.polyline(pts, col, t)
        tip = pts[0]
        L(tip[0], tip[1], tip[0] + s * r * 0.05, tip[1] - r * 0.55, col, t)
        L(tip[0], tip[1], tip[0] + s * r * 0.55, tip[1] + r * 0.05, col, t)
    elif name == 'focus':
        d.circle(cx, cy, r * 0.62, col, t)
        d.circle_fill(cx, cy, r * 0.24, col)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            L(cx + dx * r * 0.8, cy + dy * r * 0.8, cx + dx * r, cy + dy * r, col, t)
    elif name == 'rect':
        _dashed(d, [P(-.9, -.9), P(.9, -.9), P(.9, .9), P(-.9, .9)], col, t, dash, gap, True)
        _pointer(d, cx + r * 0.1, cy + r * 0.05, r * 0.9, col)
    elif name == 'brush':
        _dashed(d, _arc(cx, cy, r * 0.9, 0, 360, 40), col, t, dash, gap)
    elif name == 'lasso':
        pts = [P(-.8, .1), P(-.6, -.55), P(0, -.85), P(.65, -.5), P(.85, .15), P(.4, .7), P(-.2, .6),
               P(-.55, .85), P(-.4, 1.0)]
        _dashed(d, pts, col, t, dash, gap)
    elif name == 'polygon':
        pts = [P(-.85, .7), P(-.55, -.75), P(.2, -.2), P(.85, -.8), P(.7, .8)]
        d.polyline(pts, col, t)
        for x, y in pts:
            d.circle_fill(x, y, max(1.5, r * 0.14), col)
    elif name == 'eyedropper':
        L(*P(-.85, .85), *P(.1, -.1), col, t + 0.6)
        L(*P(-.1, -.1), *P(.55, .55), col, t)
        L(*P(.1, -.55), *P(.55, -.1), col, t + 1.6)
        d.polyline([P(.15, -.3), P(.35, -.95), P(.9, -.4), P(.3, -.15)], col, t, False)
    elif name == 'flood':
        d.polyline([P(-.75, -.1), P(-.05, -.8), P(.7, -.05), P(-.05, .65)], col, t, True)
        L(*P(-.75, -.1), *P(.7, -.05), col, t)
        d.polyline([P(.82, .25), P(.62, .6), P(.82, .85), P(1.0, .6)], col, t, True)
    elif name == 'sphereBrush':
        _dashed(d, _arc(cx, cy, r * 0.9, 0, 360, 40), col, t, dash, gap)
        d.circle(cx, cy, r * 0.45, col, t)
        d.circle_fill(cx, cy, r * 0.12, col)
    elif name == 'sphere':
        d.circle(cx, cy, r * 0.9, col, t)
        pts = [(cx + r * 0.9 * math.cos(a), cy + r * 0.3 * math.sin(a))
               for a in [math.radians(i * 10) for i in range(0, 37)]]
        d.polyline(pts, col, t)
        L(*P(0, -.9), *P(0, .9), col, t * 0.8)
    elif name == 'box':
        hexa = [P(0, -.95), P(.82, -.48), P(.82, .48), P(0, .95), P(-.82, .48), P(-.82, -.48)]
        d.polyline(hexa, col, t, True)
        L(*P(0, 0), *P(0, .95), col, t)
        L(*P(0, 0), *P(.82, -.48), col, t)
        L(*P(0, 0), *P(-.82, -.48), col, t)
    elif name == 'move':
        L(*P(-.9, 0), *P(.9, 0), col, t)
        L(*P(0, -.9), *P(0, .9), col, t)
        for tip, ang in ((P(.95, 0), 0), (P(-.95, 0), 180), (P(0, .95), 90), (P(0, -.95), -90)):
            _arrow_head(d, tip, ang + 180, r * 0.32, col, t)
    elif name == 'rotate':
        d.polyline(_arc(cx, cy, r * 0.7, 20, 190, 20), col, t)
        d.polyline(_arc(cx, cy, r * 0.7, 200, 370, 20), col, t)
        _arrow_head(d, P(.66, .24), 70 + 180, r * 0.4, col, t)
        _arrow_head(d, P(-.66, -.24), -110 + 180, r * 0.4, col, t)
    elif name == 'scale':
        L(*P(-.75, .75), *P(.75, -.75), col, t)
        _arrow_head(d, P(.85, -.85), -45 + 180, r * 0.5, col, t)
        _arrow_head(d, P(-.85, .85), 135 + 180, r * 0.5, col, t)
    elif name == 'measure':
        a, b = math.radians(-45), math.radians(45)
        c, s = math.cos(a), math.sin(a)
        def Rot(x, y):
            return (cx + (x * c - y * s) * r, cy + (x * s + y * c) * r)
        d.polyline([Rot(-1, -.32), Rot(1, -.32), Rot(1, .32), Rot(-1, .32)], col, t, True)
        for i in range(-3, 4):
            x = i * 0.27
            d.line(*Rot(x, -.32), *Rot(x, -.05 if i % 2 else .1), col, t * 0.8)
    elif name == 'measure2':      # triangle-style tool
        d.polyline([P(0, -.85), P(.8, .75), P(-.8, .75)], col, t, True)
    elif name == 'globe':
        d.circle(cx, cy, r * 0.9, col, t)
        d.polyline([(cx + r * 0.9 * 0.5 * math.cos(math.radians(a)), cy + r * 0.9 * math.sin(math.radians(a)))
                    for a in range(0, 361, 15)], col, t * 0.8)
        L(*P(-.9, 0), *P(.9, 0), col, t * 0.8)
        L(*P(0, -.9), *P(0, .9), col, t * 0.8)
    elif name == 'selectionbox':
        _dashed(d, [P(-.85, -.85), P(.85, -.85), P(.85, .85), P(-.85, .85)], col, t, dash, gap, True)
        d.circle(cx, cy, r * 0.3, col, t)
    elif name == 'contrast':
        d.circle(cx, cy, r * 0.88, col, t)
        d.polygon_fill([(cx + r * 0.88 * math.cos(math.radians(a)), cy + r * 0.88 * math.sin(math.radians(a)))
                        for a in range(-90, 91, 10)], col)
    elif name == 'eye':
        top = [(cx + x * r, cy - (0.55 * (1 - x * x)) * r) for x in [i / 8.0 for i in range(-8, 9)]]
        bot = [(cx + x * r, cy + (0.55 * (1 - x * x)) * r) for x in [i / 8.0 for i in range(-8, 9)]]
        d.polyline(top + bot[::-1], col, t, True)
        d.circle(cx, cy, r * 0.28, col, t)
    elif name == 'orbit':
        pts = [(cx + r * 0.95 * math.cos(a) * math.cos(0.5) - r * 0.35 * math.sin(a) * math.sin(0.5),
                cy + r * 0.95 * math.cos(a) * math.sin(0.5) + r * 0.35 * math.sin(a) * math.cos(0.5))
               for a in [math.radians(i * 10) for i in range(0, 37)]]
        d.polyline(pts, col, t)
        d.circle(cx, cy, r * 0.42, col, t)
        d.circle_fill(cx + r * 0.7, cy - r * 0.55, r * 0.12, col)
    elif name == 'cross':
        for sx in (-1, 1):
            for sy in (-1, 1):
                d.circle(cx + sx * r * 0.62, cy + sy * r * 0.62, r * 0.28, col, t)
        L(*P(-.4, -.4), *P(.4, .4), col, t)
        L(*P(-.4, .4), *P(.4, -.4), col, t)
    elif name == 'frame':
        k = r * 0.4
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = cx + sx * r * 0.9, cy + sy * r * 0.9
                L(x, y, x - sx * k, y, col, t)
                L(x, y, x, y - sy * k, col, t)
        d.rect(cx - r * 0.35, cy - r * 0.35, r * 0.7, r * 0.7, col)
    elif name == 'axes':
        L(*P(0, 0), *P(0, -.95), col, t)
        L(*P(0, 0), *P(-.85, .65), col, t)
        L(*P(0, 0), *P(.85, .65), col, t)
    elif name == 'gear':
        for i in range(8):
            a = math.radians(i * 45)
            L(cx + r * 0.55 * math.cos(a), cy + r * 0.55 * math.sin(a),
              cx + r * 0.95 * math.cos(a), cy + r * 0.95 * math.sin(a), col, t + 2.0)
        d.circle(cx, cy, r * 0.62, col, t + 1.0)
        d.circle(cx, cy, r * 0.24, col, t)
    elif name == 'list':
        for i in range(3):
            y = -.6 + i * .6
            d.rect(cx - r * 0.95, cy + (y - .12) * r, r * 0.35, r * 0.24, col)
            d.rect(cx - r * 0.45, cy + (y - .12) * r, r * 1.4, r * 0.24, col)
    elif name == 'logo':
        d.circle_fill(cx, cy, r * 0.5, col)
        for i in range(8):
            a = math.radians(i * 45 + 22)
            d.circle_fill(cx + r * 0.88 * math.cos(a), cy + r * 0.88 * math.sin(a), r * 0.13, col)
    elif name == 'colors':
        for ang in (-90, 30, 150):
            a = math.radians(ang)
            d.circle(cx + r * 0.38 * math.cos(a), cy + r * 0.38 * math.sin(a), r * 0.55, col, t)
    elif name == 'chevron_r':
        d.polyline([P(-.35, -.7), P(.35, 0), P(-.35, .7)], col, t)
    elif name == 'chevron_d':
        d.polyline([P(-.7, -.35), P(0, .35), P(.7, -.35)], col, t)
    elif name == 'save':
        d.polyline([P(-.8, -.8), P(.5, -.8), P(.8, -.5), P(.8, .8), P(-.8, .8)], col, t, True)
        d.rect_outline(cx - r * 0.4, cy + r * 0.1, r * 0.8, r * 0.7, col, t)
    elif name == 'import':
        L(*P(0, -.8), *P(0, .4), col, t)
        d.polyline([P(-.45, 0), P(0, .45), P(.45, 0)], col, t)
        d.polyline([P(-.8, .3), P(-.8, .85), P(.8, .85), P(.8, .3)], col, t)
    elif name == 'export':
        L(*P(0, .3), *P(0, -.8), col, t)
        d.polyline([P(-.45, -.35), P(0, -.8), P(.45, -.35)], col, t)
        d.polyline([P(-.8, .3), P(-.8, .85), P(.8, .85), P(.8, .3)], col, t)
    elif name == 'pencil':
        L(*P(-.8, .8), *P(-.6, .3), col, t)
        L(*P(-.8, .8), *P(-.3, .6), col, t)
        d.polyline([P(-.6, .3), P(.4, -.7), P(.7, -.4), P(-.3, .6)], col, t, True)
    elif name == 'trash':
        d.polyline([P(-.6, -.5), P(-.5, .9), P(.5, .9), P(.6, -.5)], col, t)
        L(*P(-.85, -.5), *P(.85, -.5), col, t)
        L(*P(-.3, -.5), *P(-.3, -.8), col, t)
        L(*P(.3, -.5), *P(.3, -.8), col, t)
        L(*P(-.3, -.8), *P(.3, -.8), col, t)
    elif name == 'eye_off':
        top = [(cx + x * r, cy - (0.55 * (1 - x * x)) * r) for x in [i / 8.0 for i in range(-8, 9)]]
        bot = [(cx + x * r, cy + (0.55 * (1 - x * x)) * r) for x in [i / 8.0 for i in range(-8, 9)]]
        d.polyline(top + bot[::-1], col, t, True)
        L(*P(-.8, .8), *P(.8, -.8), col, t + 0.4)
    elif name == 'plus':
        L(*P(-.7, 0), *P(.7, 0), col, t)
        L(*P(0, -.7), *P(0, .7), col, t)
    else:                           # unknown: filled dot
        d.circle_fill(cx, cy, r * 0.4, col)
