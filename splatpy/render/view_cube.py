"""Axes gizmo ("view cube") — port of supersplat ui/view-cube.ts drawn with the Draw2D API.

Six circles for +X/+Y/+Z (filled, labelled) and -X/-Y/-Z (dark fill, coloured outline), with lines
from the centre to the positive circles, painter-sorted by view-space depth. Clicking a circle fires
events.fire('camera.setView', name) where (as in supersplat editor.ts camera.align):
    +X -> 'right', -X -> 'left', +Y -> 'top', -Y -> 'bottom', +Z -> 'front', -Z -> 'back'
"""

from __future__ import annotations

import numpy as np

AXIS_VIEW_NAMES = {'px': 'right', 'nx': 'left', 'py': 'top', 'ny': 'bottom', 'pz': 'front', 'nz': 'back'}

RED = (1.0, 0.267, 0.267, 1.0)      # #f44
GREEN = (0.267, 1.0, 0.267, 1.0)    # #4f4
BLUE = (0.467, 0.467, 1.0, 1.0)     # #77f
DARK = (0.133, 0.133, 0.133, 1.0)   # #222
AXIS_COLORS = {'x': RED, 'y': GREEN, 'z': BLUE}


class ViewCube:
    def __init__(self, events=None, scene=None):
        self.events = events
        self.scene = scene
        # last layout, painter order (back to front):
        # list of dict(name, kind 'circle'|'line', x, y, r, ...)
        self.layout: list[dict] = []
        self.hover: str | None = None

    # ------------------------------------------------------------------ layout
    @staticmethod
    def _view_matrix(ctx):
        v = getattr(ctx, 'view', None)
        if v is None:
            v = ctx.camera.view_matrix()
        return np.asarray(v, dtype=np.float64)

    def compute_layout(self, view, x, y, size) -> list[dict]:
        """Returns the painter-ordered items for a gizmo in screen rect (x, y, size, size)."""
        view = np.asarray(view, dtype=np.float64)
        cx, cy = x + size * 0.5, y + size * 0.5
        radius = max(size / 12.0, 6.0)
        arm = size * 0.5 - radius - 1.0
        items = []
        groups = []
        for i, a in enumerate('xyz'):
            v = view[:3, i]          # world axis expressed in view space
            v = v / max(np.linalg.norm(v), 1e-30)
            col = AXIS_COLORS[a]
            px, py = cx + v[0] * arm, cy - v[1] * arm
            nx, ny = cx - v[0] * arm, cy + v[1] * arm
            groups.append((v[2], [
                dict(name=a + 'axis', kind='line', x0=cx, y0=cy, x=px, y=py, color=col),
                dict(name='p' + a, kind='circle', x=px, y=py, r=radius, color=col, fill=True,
                     label=a.upper(), depth=v[2]),
            ]))
            groups.append((-v[2], [
                dict(name='n' + a, kind='circle', x=nx, y=ny, r=radius, color=col, fill=False,
                     label=None, depth=-v[2]),
            ]))
        groups.sort(key=lambda g: g[0])   # back (most negative z) first
        for _, g in groups:
            items.extend(g)
        return items

    # ------------------------------------------------------------------ drawing
    def draw(self, ctx, x, y, size):
        settings = getattr(getattr(ctx, 'scene', None), 'settings', None)
        if settings is not None and not getattr(settings, 'show_axes_gizmo', True):
            self.layout = []
            return
        self.layout = self.compute_layout(self._view_matrix(ctx), x, y, size)
        d = getattr(ctx, 'draw2d', None)
        if d is None:
            return
        mx, my = getattr(ctx, 'mouse_x', -1e9), getattr(ctx, 'mouse_y', -1e9)
        hit = self.hit_test(mx, my)
        self.hover = hit
        for it in self.layout:
            if it['kind'] == 'line':
                d.line(it['x0'], it['y0'], it['x'], it['y'], it['color'], 2)
                continue
            r = it['r']
            hovered = it['name'] == hit
            if it['fill']:
                fill = it['color'] if not hovered else tuple(min(1.0, c * 1.25) for c in it['color'][:3]) + (1.0,)
                d.circle_fill(it['x'], it['y'], r, fill)
            else:
                d.circle_fill(it['x'], it['y'], r, DARK if not hovered else (0.3, 0.3, 0.3, 1.0))
            d.circle(it['x'], it['y'], r, it['color'], 2)
            if it['label']:
                tsize = max(10, int(round(r * 1.1)))
                try:
                    tw, th = d.text_size(it['label'], tsize)
                except Exception:
                    tw, th = tsize * 0.6, tsize
                d.text(it['x'] - tw * 0.5, it['y'] - th * 0.5, it['label'], (0.0, 0.0, 0.0, 1.0), tsize)

    # ------------------------------------------------------------------ input
    def hit_test(self, mx, my) -> str | None:
        """Topmost circle under (mx, my) -> 'px'..'nz' or None."""
        for it in reversed(self.layout):
            if it['kind'] != 'circle':
                continue
            if (mx - it['x']) ** 2 + (my - it['y']) ** 2 <= (it['r'] + 1.0) ** 2:
                return it['name']
        return None

    def on_mouse_down(self, ev) -> bool:
        if getattr(ev, 'button', 0) not in (0, -1):   # left button only
            return False
        hit = self.hit_test(ev.x, ev.y)
        if hit is None:
            return False
        if self.events is not None:
            self.events.fire('camera.setView', AXIS_VIEW_NAMES[hit])
        return True
