"""Flood selection (tools/flood-selection.ts).

supersplat floods the rendered offscreen image from the clicked pixel and selects through
the resulting mask. Here the "image" is a coarse grid (FLOOD_CELL px) holding the colour of
the front-most gaussian centre per cell (empty cells are bridged from neighbours). The
connected region of cells whose colour is within `threshold` (per channel) of the clicked
cell is flooded, then every editable gaussian projecting into it is selected (all depths,
or only the visible surface with 'use depth').

A click (no drag) selects; drags pass through to the camera like in supersplat.
"""

from __future__ import annotations

import numpy as np

from .selection_common import (MOUSE_LEFT, ORANGE, SelectionToolBase, draw_common_options, draw_op_badge,
                               emit_selection, op_from_mods, splat_colors)

FLOOD_CELL = 4
CLICK_SLOP = 3.0


def _dilate4(r):
    n = r.copy()
    n[1:] |= r[:-1]
    n[:-1] |= r[1:]
    n[:, 1:] |= r[:, :-1]
    n[:, :-1] |= r[:, 1:]
    return n


def flood_region(similar: np.ndarray, seed: tuple[int, int]) -> np.ndarray:
    """Connected (4-neighbour) component of bool grid `similar` containing seed (row, col)."""
    region = np.zeros_like(similar)
    if not similar[seed]:
        return region
    region[seed] = True
    while True:
        prev = region
        for _ in range(8):
            region = _dilate4(region) & similar
        if np.array_equal(region, prev):
            return region


class FloodSelection(SelectionToolBase):
    name = 'floodSelection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.down = None
        self.op = 'set'
        self.last_region = None

    @property
    def threshold(self):
        return self.opts.flood_threshold

    @threshold.setter
    def threshold(self, v):
        self.opts.flood_threshold = float(min(0.999, max(0.001, v)))

    def deactivate(self):
        self.down = None
        super().deactivate()

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button == MOUSE_LEFT and ev.kind != 'double_click':
            self.down = (ev.x, ev.y)
            self.op = op_from_mods(ev.mods)
        return False     # let the camera orbit on drag (supersplat behaviour)

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        if self.down and (abs(ev.x - self.down[0]) > CLICK_SLOP or abs(ev.y - self.down[1]) > CLICK_SLOP):
            self.down = None
        return False

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT or self.down is None:
            return False
        self.down = None
        self.flood_select(ev.x, ev.y, self.op)
        return True

    def flood_select(self, x, y, op='set', threshold=None):
        splat, proj = self._ready()
        if splat is None:
            return None
        thr = self.threshold if threshold is None else float(threshold)
        cell = FLOOD_CELL
        _, gw, gh, z, owner = proj.zbuffer(cell)
        owner = owner.reshape(gh, gw).copy()
        # bridge small gaps between projected centres
        for _ in range(2):
            empty = owner < 0
            if not empty.any():
                break
            fill = owner.copy()
            for sl_dst, sl_src in (((slice(1, None),), (slice(None, -1),)), ((slice(None, -1),), (slice(1, None),)),
                                   ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                                   ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
                dst = fill[sl_dst]
                src = owner[sl_src]
                upd = (dst < 0) & (src >= 0)
                dst[upd] = src[upd]
            owner = fill
        r0, c0 = int(y // cell), int(x // cell)
        mask = np.zeros(splat.count, bool)
        if not (0 <= r0 < gh and 0 <= c0 < gw) or owner[r0, c0] < 0:
            self.last_region = None
            return emit_selection(self.events, splat, mask, op)
        colors = splat_colors(splat)
        ref = colors[owner[r0, c0]]
        valid = owner >= 0
        cg = np.zeros((gh, gw, 3), np.float32)
        cg[valid] = colors[owner[valid]]
        similar = valid & np.all(np.abs(cg - ref) <= thr, axis=2)
        region = flood_region(similar, (r0, c0))
        self.last_region = region
        idx = np.flatnonzero(proj.cand & proj.on_screen)
        cx = (proj.xy[idx, 0] // cell).astype(np.int64)
        cy = (proj.xy[idx, 1] // cell).astype(np.int64)
        mask[idx[region[cy, cx]]] = True
        mask = proj.finish(self.scene, self.opts, mask)
        return emit_selection(self.events, splat, mask, op)

    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        mx, my = self.mouse
        d.line(mx - 8, my, mx + 8, my, ORANGE, 1)
        d.line(mx, my - 8, mx, my + 8, ORANGE, 1)
        draw_op_badge(d, mx, my, self.mods)

    def draw_ui(self, ui):
        ui.label('Flood selection')
        self.threshold = ui.slider('Threshold', self.threshold, 0.001, 0.999, '%.3f')
        draw_common_options(ui, self.opts, show_footprint=False)
