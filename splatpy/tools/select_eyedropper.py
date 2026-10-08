"""Eyedropper selection (tools/eyedropper-selection.ts + editor.ts 'select.colorMatch').

Click a gaussian: its colour (band 0, layer colour grade applied) becomes the reference and
every editable gaussian of the layer whose colour differs by <= threshold per channel is
selected (0 = identical colours only, 1 = everything)."""

from __future__ import annotations

from .selection_common import (MOUSE_LEFT, ORANGE, SelectionToolBase, color_match_mask, draw_op_badge,
                               emit_selection, op_from_mods, splat_colors)

PICK_RADIUS = 6.0


class EyedropperSelection(SelectionToolBase):
    name = 'eyedropperSelection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.pressed = False
        self.op = 'set'
        self.picked_color = None

    @property
    def threshold(self):
        return self.opts.eyedropper_threshold

    @threshold.setter
    def threshold(self, v):
        self.opts.eyedropper_threshold = float(min(1.0, max(0.0, v)))

    def deactivate(self):
        self.pressed = False
        super().deactivate()

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT:
            return False
        if ev.kind != 'double_click':
            self.pressed = True
            self.op = op_from_mods(ev.mods)
        return True

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        return self.pressed

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT or not self.pressed:
            return False
        self.pressed = False
        self.pick_and_select(ev.x, ev.y, self.op)
        return True

    def pick_and_select(self, x, y, op='set', threshold=None):
        splat, proj = self._ready()
        if splat is None:
            return None
        i = proj.pick(x, y, PICK_RADIUS)
        if i is None:
            return None     # supersplat: nothing under the cursor -> no-op
        ref = splat_colors(splat)[i]
        self.picked_color = tuple(float(v) for v in ref)
        thr = self.threshold if threshold is None else float(threshold)
        mask = color_match_mask(splat, ref, thr)
        return emit_selection(self.events, splat, mask, op)

    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        mx, my = self.mouse
        d.circle(mx, my, 6, ORANGE, 1, 24)
        if self.picked_color is not None:
            d.rect(mx + 10, my - 22, 14, 14, self.picked_color + (1.0,))
            d.rect_outline(mx + 10, my - 22, 14, 14, (1, 1, 1, 1), 1)
        draw_op_badge(d, mx, my, self.mods)

    def draw_ui(self, ui):
        ui.label('Eyedropper selection')
        self.threshold = ui.slider('Threshold', self.threshold, 0.0, 1.0, '%.3f')
        if self.picked_color is not None:
            ui.label('Picked colour: %.2f %.2f %.2f' % self.picked_color)

