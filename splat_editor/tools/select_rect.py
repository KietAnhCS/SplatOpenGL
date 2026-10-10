"""Rectangle selection (tools/rect-selection.ts). Drag a rectangle; a click without
drag picks the front-most gaussian under the cursor (select.point)."""

from __future__ import annotations

import numpy as np

from .selection_common import (KEY_ESCAPE, MOUSE_LEFT, ORANGE, ORANGE_FILL, SelectionToolBase,
                               draw_common_options, draw_op_badge, emit_selection, is_press,
                               op_from_mods, select_in_rect)

CLICK_PICK_RADIUS = 6.0
DRAG_THRESHOLD = 2.0


class RectSelection(SelectionToolBase):
    name = 'rectSelection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.start = None
        self.end = None
        self.moved = False
        self.op = 'set'

    def deactivate(self):
        self.start = None
        super().deactivate()

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT or ev.kind == 'double_click':
            return ev.button == MOUSE_LEFT and ev.kind == 'double_click'
        self.start = self.end = (ev.x, ev.y)
        self.moved = False
        self.op = op_from_mods(ev.mods)
        return True

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        if self.start is None:
            return False
        self.end = (ev.x, ev.y)
        if abs(ev.x - self.start[0]) > DRAG_THRESHOLD or abs(ev.y - self.start[1]) > DRAG_THRESHOLD:
            self.moved = True
        return True

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if self.start is None or ev.button != MOUSE_LEFT:
            return False
        self.end = (ev.x, ev.y)
        start, end, moved = self.start, self.end, self.moved
        self.start = None
        if moved:
            self.select_rect(start[0], start[1], end[0], end[1], self.op)
        else:
            self.select_point(end[0], end[1], self.op)
        return True

    def on_key(self, ev) -> bool:
        if is_press(ev, KEY_ESCAPE) and self.start is not None:
            self.start = None
            return True
        return False

    # ---- programmatic API (also used by tests)
    def select_rect(self, x0, y0, x1, y1, op='set'):
        splat, proj = self._ready()
        if splat is None:
            return None
        mask = select_in_rect(self.scene, proj, x0, y0, x1, y1, self.opts)
        return emit_selection(self.events, splat, mask, op)

    def select_point(self, x, y, op='set'):
        splat, proj = self._ready()
        if splat is None:
            return None
        mask = np.zeros(splat.count, bool)
        i = proj.pick(x, y, CLICK_PICK_RADIUS)
        if i is not None:
            mask[i] = True
        return emit_selection(self.events, splat, mask, op)

    # ---- drawing
    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        if self.start is not None and self.moved:
            x0, y0 = self.start
            x1, y1 = self.end
            x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
            d.rect(x, y, w, h, ORANGE_FILL)
            d.rect_outline(x, y, w, h, ORANGE, 1)
        draw_op_badge(d, self.mouse[0], self.mouse[1], self.mods)

    def draw_ui(self, ui):
        ui.label('Rect selection')
        draw_common_options(ui, self.opts)
