"""Polygon selection (tools/polygon-selection.ts).

Click to add points; close by clicking the first point, double-click or Enter.
Backspace removes the last point, Escape cancels the polygon. The op comes from the
modifiers held on the closing click / key (like supersplat)."""

from __future__ import annotations

import math

from .selection_common import (KEY_BACKSPACE, KEY_ENTER, KEY_ESCAPE, KEY_KP_ENTER, MOUSE_LEFT, ORANGE,
                               ORANGE_FILL, ORANGE_LIGHT, CLOSE_DIST_PX, SelectionToolBase,
                               draw_common_options, draw_op_badge, emit_selection, is_press, op_from_mods,
                               raster_polygon, select_in_image)


class PolygonSelection(SelectionToolBase):
    name = 'polygonSelection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.points: list[tuple[float, float]] = []
        self.current = None
        self._pressed = False

    def deactivate(self):
        self.points = []
        self.current = None
        super().deactivate()

    def _is_closed(self):
        return (len(self.points) > 1 and self.current is not None and
                math.hypot(self.current[0] - self.points[0][0], self.current[1] - self.points[0][1]) < CLOSE_DIST_PX)

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT:
            return False
        if ev.kind == 'double_click':
            if len(self.points) > 2:
                self.commit(op_from_mods(ev.mods))
            return True
        self._pressed = True
        return True

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        self.current = (ev.x, ev.y)
        return self._pressed

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT or not self._pressed:
            return False
        self._pressed = False
        self.current = (ev.x, ev.y)
        if self._is_closed():
            self.commit(op_from_mods(ev.mods))
        elif not self.points or self.points[-1] != self.current:
            self.points.append(self.current)
        return True

    def on_key(self, ev) -> bool:
        self.mods = ev.mods
        if is_press(ev, KEY_ENTER, KEY_KP_ENTER) and len(self.points) > 2:
            if ev.action == 1:
                self.commit(op_from_mods(ev.mods))
            return True
        if is_press(ev, KEY_BACKSPACE) and self.points:
            self.points.pop()
            return True
        if is_press(ev, KEY_ESCAPE) and self.points:
            self.points = []
            return True
        return False

    def commit(self, op='set'):
        pts = list(self.points)
        self.points = []
        if len(pts) < 3:
            return None
        return self.select_polygon(pts, op)

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
        if self.points:
            pts = self.points + ([self.current] if self.current else [])
            col = ORANGE_LIGHT if self._is_closed() else ORANGE
            if len(pts) >= 3:
                d.polygon_fill(pts, ORANGE_FILL)
            d.polyline(pts, col, 1, closed=False)
            for x, y in self.points:
                d.circle_fill(x, y, 3, col, 12)
            if self._is_closed():
                d.circle(self.points[0][0], self.points[0][1], CLOSE_DIST_PX, col, 1, 24)
        draw_op_badge(d, self.mouse[0], self.mouse[1], self.mods)

    def draw_ui(self, ui):
        ui.label('Polygon selection')
        ui.label('Click points; Enter / double-click / first point closes')
        draw_common_options(ui, self.opts)
