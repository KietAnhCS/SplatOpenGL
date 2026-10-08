"""Brush selection (tools/brush-selection.ts) and sphere brush (sphere-brush-selection.ts).

Brush: paint a round stroke while dragging; the stroke mask is applied on release.
Sphere brush: each stroke sample is depth-picked (front-most gaussian centre under the
sample, from a coarse z-buffer of the layer's projected centres) to a world position;
the on-screen brush radius is converted to a world radius at that depth, and a gaussian
is selected when its centre lies inside the 2D stroke AND within one of those spheres.

'[' / ']' (events 'tool.brushSelection.smaller' / '.bigger') change the shared radius;
alt+wheel too.
"""

from __future__ import annotations

import math

import numpy as np

from .selection_common import (KEY_ESCAPE, KEY_LEFT_BRACKET, KEY_RIGHT_BRACKET, MOUSE_LEFT, ORANGE,
                               SelectionToolBase, draw_common_options, draw_op_badge, emit_selection,
                               is_press, op_from_mods, raster_stroke, select_in_image)

STROKE_COLOR = (1.0, 0.4, 0.0, 0.35)


class BrushSelection(SelectionToolBase):
    name = 'brushSelection'
    title = 'Brush selection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.samples: list[tuple[float, float, float]] = []
        self.dragging = False
        self.op = 'set'
        self.proj = None

    @property
    def radius(self) -> float:
        return self.opts.brush_radius

    @radius.setter
    def radius(self, v):
        self.opts.brush_radius = float(min(500.0, max(1.0, v)))

    def deactivate(self):
        self._reset()
        super().deactivate()

    def _reset(self):
        self.samples = []
        self.dragging = False
        self.proj = None

    def _append(self, x, y, force=False):
        """Interpolate samples so consecutive ones are <= radius/4 apart (sphere-brush-selection.ts)."""
        r = self.radius
        if not self.samples:
            self.samples.append((x, y, r))
            return
        lx, ly, lr = self.samples[-1]
        dx, dy = x - lx, y - ly
        dist = math.hypot(dx, dy)
        spacing = max(2.0, min(lr, r) * 0.25)
        steps = int(dist // spacing)
        for i in range(1, steps + 1):
            t = i * spacing / dist
            self.samples.append((lx + dx * t, ly + dy * t, lr + (r - lr) * t))
        if force:
            tx, ty, tr = self.samples[-1]
            if (tx, ty, tr) != (x, y, r):
                self.samples.append((x, y, r))

    # ---- input
    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT:
            return False
        if ev.kind == 'double_click':
            return True
        self._reset()
        self.dragging = True
        self.op = op_from_mods(ev.mods)
        self._begin()
        self._append(ev.x, ev.y)
        return True

    def _begin(self):
        pass

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        if not self.dragging:
            return False
        self._append(ev.x, ev.y)
        return True

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if not self.dragging or ev.button != MOUSE_LEFT:
            return False
        self._append(ev.x, ev.y, force=True)
        samples = list(self.samples)
        proj = self.proj
        self._reset()
        self.apply_stroke(samples, self.op, proj)
        return True

    def on_scroll(self, ev) -> bool:
        if getattr(ev.mods, 'alt', False) and ev.scroll_y:
            self.events.fire('tool.brushSelection.bigger' if ev.scroll_y > 0 else 'tool.brushSelection.smaller')
            return True
        return False

    def on_key(self, ev) -> bool:
        self.mods = ev.mods
        if is_press(ev, KEY_LEFT_BRACKET):
            self.events.fire('tool.brushSelection.smaller')
            return True
        if is_press(ev, KEY_RIGHT_BRACKET):
            self.events.fire('tool.brushSelection.bigger')
            return True
        if is_press(ev, KEY_ESCAPE) and self.dragging:
            self._reset()
            return True
        return False

    # ---- selection
    def apply_stroke(self, samples, op='set', proj=None):
        """samples: [(x, y, radius_px), ...] in screen pixels."""
        splat, p = self._ready()
        if splat is None or not samples:
            return None
        proj = proj if proj is not None and proj.splat is splat else p
        img = raster_stroke(samples, proj.width, proj.height)
        mask = select_in_image(self.scene, proj, img, self.opts)
        return emit_selection(self.events, splat, mask, op)

    # ---- drawing
    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        if self.dragging and self.samples:
            pts = [(x, y) for x, y, _ in self.samples]
            r = self.samples[-1][2]
            if len(pts) > 1:
                d.polyline(pts, STROKE_COLOR, max(1.0, 2 * r))
            d.circle_fill(pts[0][0], pts[0][1], self.samples[0][2], STROKE_COLOR, 48)
            if len(pts) > 1:
                d.circle_fill(pts[-1][0], pts[-1][1], r, STROKE_COLOR, 48)
        mx, my = self.mouse
        d.circle(mx, my, self.radius, ORANGE, 1, 64)
        draw_op_badge(d, mx, my, self.mods)

    def draw_ui(self, ui):
        ui.label(self.title)
        self.radius = ui.slider('Brush size', self.radius, 1.0, 500.0, '%.0f')
        draw_common_options(ui, self.opts)


class SphereBrushSelection(BrushSelection):
    name = 'sphereBrushSelection'
    title = 'Sphere brush selection'
    PICK_CELL = 4      # z-buffer cell size (px)
    PICK_RANGE = 2     # search +-cells around a sample

    def _begin(self):
        # the camera does not move during the stroke (left button is ours), so project once
        splat, self.proj = self._ready()

    def pick_samples(self, proj, samples):
        """Front-most centre near each sample -> (hit index array (S,), -1 for none)."""
        cell = self.PICK_CELL
        _, gw, gh, z, owner = proj.zbuffer(cell)
        s = np.asarray(samples, dtype=np.float64).reshape(-1, 3)
        cx = np.floor(s[:, 0] / cell).astype(np.int64)
        cy = np.floor(s[:, 1] / cell).astype(np.int64)
        k = self.PICK_RANGE
        off = np.arange(-k, k + 1)
        ox, oy = np.meshgrid(off, off)
        ox, oy = ox.ravel(), oy.ravel()
        # prefer the centre cell, then nearest rings: add a small ring penalty to depth
        ring = np.maximum(np.abs(ox), np.abs(oy)).astype(np.float64)
        X = cx[:, None] + ox[None, :]
        Y = cy[:, None] + oy[None, :]
        ok = (X >= 0) & (X < gw) & (Y >= 0) & (Y < gh)
        cid = np.where(ok, Y * gw + X, 0)
        zz = np.where(ok, z[cid], np.inf)
        oo = np.where(ok, owner[cid], -1)
        zz = np.where(oo >= 0, zz, np.inf)
        # first ring that contains anything wins, front-most inside it
        key = np.where(np.isfinite(zz), ring[None, :] * 1e30 + 0.0, np.inf)
        best_ring = key.min(axis=1)
        zz2 = np.where(key == best_ring[:, None], zz, np.inf)
        j = np.argmin(zz2, axis=1)
        hit = oo[np.arange(len(s)), j]
        hit[~np.isfinite(zz2[np.arange(len(s)), j])] = -1
        return hit

    def world_radii(self, proj, centers, radii_px):
        """Convert on-screen radii at world centres to world radii."""
        cam = self.scene.camera
        right = np.asarray(getattr(cam, 'right', (1.0, 0.0, 0.0)), dtype=np.float64).reshape(3)
        _, depth, _ = cam.world_to_screen(centers, proj.width, proj.height)
        step = np.maximum(np.abs(np.asarray(depth, dtype=np.float64)), 1.0) * 1e-2
        xy0, _, _ = cam.world_to_screen(centers, proj.width, proj.height)
        xy1, _, _ = cam.world_to_screen(centers + step[:, None] * right[None, :], proj.width, proj.height)
        px = np.hypot(*(np.asarray(xy1, np.float64) - np.asarray(xy0, np.float64)).T) / step
        px = np.where(px > 1e-9, px, 1e-9)
        return np.asarray(radii_px, dtype=np.float64) / px

    def apply_stroke(self, samples, op='set', proj=None):
        splat, p = self._ready()
        if splat is None or not samples:
            return None
        proj = proj if proj is not None and proj.splat is splat else p
        img = raster_stroke(samples, proj.width, proj.height)
        mask2d = select_in_image(self.scene, proj, img, self.opts)
        hits = self.pick_samples(proj, samples)
        good = hits >= 0
        mask = np.zeros(splat.count, bool)
        if good.any():
            centers = proj.world[hits[good]]
            radii = self.world_radii(proj, centers, np.asarray(samples, np.float64)[good, 2])
            idx = np.flatnonzero(mask2d)
            if len(idx):
                pts = proj.world[idx]
                extra = 0.0
                if self.opts.footprint > 0:
                    sc = np.exp(splat.data.scales[idx].astype(np.float64)).max(axis=1)
                    extra = self.opts.footprint * 2.0 * sc * float(np.max(np.abs(splat.scale)))
                inside = np.zeros(len(idx), bool)
                for c, r in zip(centers, radii):
                    rem = np.flatnonzero(~inside)
                    if len(rem) == 0:
                        break
                    d = pts[rem] - c
                    rr = r + (extra[rem] if np.ndim(extra) else extra)
                    inside[rem[np.einsum('ij,ij->i', d, d) <= rr * rr]] = True
                mask[idx[inside]] = True
        return emit_selection(self.events, splat, mask, op)

    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is not None:
            mx, my = self.mouse
            d.circle_fill(mx, my, self.radius, (1.0, 0.4, 0.0, 0.12), 48)
        super().draw_2d(ctx)
