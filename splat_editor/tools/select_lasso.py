"""Lasso selection (tools/lasso-selection.ts): freehand closed polygon while dragging."""

from __future__ import annotations

import math
import time

from .selection_common import (KEY_ESCAPE, MOUSE_LEFT, ORANGE, ORANGE_FILL, ORANGE_LIGHT, CLOSE_DIST_PX,
                               SelectionToolBase, draw_common_options, draw_op_badge, emit_selection,
                               is_press, op_from_mods, raster_polygon, select_in_image)


class LassoSelection(SelectionToolBase):
    name = 'lassoSelection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.points: list[tuple[float, float]] = []
        self.dragging = False
        self.current = None
        self.last_time = 0.0
        self.op = 'set'

    def deactivate(self):
        self._reset()
        super().deactivate()

    def _reset(self):
        self.points = []
        self.dragging = False
        self.current = None

    def _add(self, x, y, force=False):
        """Point spacing heuristics from lasso-selection.ts."""
        self.current = (x, y)
        now = time.monotonic()
        if not self.points:
            self.points.append((x, y))
            self.last_time = now
            return
        lx, ly = self.points[-1]
        dist = math.hypot(x - lx, y - ly)
        ms = (now - self.last_time) * 1000.0
        if force or dist > 20 or (ms > 500 and dist > 2) or (ms > 200 and dist > 10) or dist > 3:
            if dist > 0:
                self.points.append((x, y))
                self.last_time = now

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT:
            return False
        if ev.kind == 'double_click':
            return True
        self._reset()
        self.dragging = True
        self.op = op_from_mods(ev.mods)
        self._add(ev.x, ev.y)
        return True

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        if not self.dragging:
            return False
        self._add(ev.x, ev.y)
        return True

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if not self.dragging or ev.button != MOUSE_LEFT:
            return False
        self._add(ev.x, ev.y, force=True)
        pts = list(self.points)
        self._reset()
        if len(pts) >= 3:
            self.select_polygon(pts, self.op)
        return True

    def on_key(self, ev) -> bool:
        if is_press(ev, KEY_ESCAPE) and self.dragging:
            self._reset()
            return True
        return False

    def select_polygon(self, points, op='set'):
        splat, proj = self._ready()
        if splat is None:
            return None
        img = raster_polygon(points, proj.width, proj.height)
        mask = select_in_image(self.scene, proj, img, self.opts)
        return emit_selection(self.events, splat, mask, op)

    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        if self.dragging and self.points:
            pts = self.points + ([self.current] if self.current else [])
            closed = len(self.points) > 1 and self.current and \
                math.hypot(self.current[0] - self.points[0][0], self.current[1] - self.points[0][1]) < CLOSE_DIST_PX
            if len(pts) >= 3:
                d.polygon_fill(pts, ORANGE_FILL)
            d.polyline(pts, ORANGE_LIGHT if closed else ORANGE, 1, closed=True)
        draw_op_badge(d, self.mouse[0], self.mouse[1], self.mods)

    def draw_ui(self, ui):
        ui.label('Lasso selection')
        draw_common_options(ui, self.opts)
