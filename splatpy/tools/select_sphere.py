"""Sphere selection (tools/sphere-selection.ts) + shared 3D-shape tool base.

A world-space sphere is placed at the selection centre (or scene centre) when the tool is
first activated. Its centre/radius are edited in the tool panel (draw_ui) and the centre
can be dragged in the camera plane by grabbing its on-screen handle; double-click places it
on the picked surface point ('scene.pickPoint'). Set / Add / Remove / Intersect buttons
apply the shape to the selected layer's editable gaussians. Other left drags pass through
to the camera."""

from __future__ import annotations

import numpy as np

from .selection_common import (KEY_ESCAPE, MOUSE_LEFT, ORANGE, SelectionToolBase, emit_selection, is_press,
                               target_splat)

HANDLE_PX = 12.0
SHAPE_COLOR = (1.0, 0.4, 0.0, 1.0)


def as_world_pos(res):
    """'scene.pickPoint' may return a world position or (splat, index, world_pos)."""
    if res is None:
        return None
    if isinstance(res, (tuple, list)) and len(res) == 3 and not np.isscalar(res[0]):
        res = res[2]
    try:
        p = np.asarray(res, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    return p[:3].copy() if p.size >= 3 and np.all(np.isfinite(p[:3])) else None


class ShapeSelectionBase(SelectionToolBase):
    """Common placement / dragging / UI for sphere and box selection."""
    title = 'Shape selection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.center = np.zeros(3)
        self.placed = False
        self.drag = None          # (plane_point, plane_normal, grab_offset)

    # ---- placement
    def _reference_bound(self):
        splat = target_splat(self.scene)
        if splat is not None and splat.num_selected > 0:
            b = splat.selection_bound().transformed(splat.world_matrix())
            if not b.empty:
                return b
        try:
            b = self.scene.bound()
        except Exception:
            b = None
        return b if b is not None and not b.empty else None

    def place_default(self):
        b = self._reference_bound()
        if b is None:
            self.center = np.zeros(3)
            self._fit(None)
        else:
            self.center = np.asarray(b.center, dtype=np.float64).copy()
            self._fit(b)
        self.placed = True

    def _fit(self, bound):
        pass

    def center_on_selection(self):
        b = self._reference_bound()
        if b is not None:
            self.center = np.asarray(b.center, dtype=np.float64).copy()

    def activate(self):
        super().activate()
        if not self.placed:
            self.place_default()

    def deactivate(self):
        self.drag = None
        super().deactivate()

    # ---- geometry (override)
    def contains(self, world: np.ndarray, pad=0.0) -> np.ndarray:
        raise NotImplementedError

    def apply(self, op='set'):
        splat = target_splat(self.scene)
        if splat is None:
            return None
        cand = splat.editable_mask()
        idx = np.flatnonzero(cand)
        mask = np.zeros(splat.count, bool)
        if len(idx):
            world = splat.world_positions(idx)
            pad = 0.0
            if self.opts.footprint > 0:
                sc = np.exp(splat.data.scales[idx].astype(np.float64)).max(axis=1)
                pad = self.opts.footprint * 2.0 * sc * float(np.max(np.abs(splat.scale)))
            mask[idx[self.contains(world, pad)]] = True
        return emit_selection(self.events, splat, mask, op)

    # ---- input
    def _handle_xy(self):
        cam = getattr(self.scene, 'camera', None)
        if cam is None:
            return None
        w, h = max(1, int(self.scene.width)), max(1, int(self.scene.height))
        xy, _, inf = cam.world_to_screen(self.center.reshape(1, 3), w, h)
        if not bool(np.asarray(inf).reshape(-1)[0]):
            return None
        return np.asarray(xy, dtype=np.float64).reshape(2)

    def _ray_plane(self, x, y):
        cam = self.scene.camera
        o, d = cam.screen_to_ray(x, y, max(1, int(self.scene.width)), max(1, int(self.scene.height)))
        pp, n, _ = self.drag
        o, d = np.asarray(o, np.float64), np.asarray(d, np.float64)
        den = float(np.dot(d, n))
        if abs(den) < 1e-9:
            return None
        t = float(np.dot(pp - o, n)) / den
        return o + d * t

    def on_mouse_down(self, ev) -> bool:
        self._track(ev)
        if ev.button != MOUSE_LEFT:
            return False
        cam = getattr(self.scene, 'camera', None)
        if ev.kind == 'double_click':
            p = as_world_pos(self.events.invoke('scene.pickPoint', ev.x, ev.y))
            if p is not None:
                self.center = p
                self.placed = True
                return True
            return False
        hxy = self._handle_xy()
        if hxy is None or cam is None or not hasattr(cam, 'screen_to_ray'):
            return False
        if np.hypot(ev.x - hxy[0], ev.y - hxy[1]) > HANDLE_PX:
            return False
        n = np.asarray(getattr(cam, 'forward', (0.0, 0.0, -1.0)), np.float64).reshape(3)
        self.drag = (self.center.copy(), n, np.zeros(3))
        hit = self._ray_plane(ev.x, ev.y)
        if hit is None:
            self.drag = None
            return False
        self.drag = (self.center.copy(), n, self.center - hit)
        return True

    def on_mouse_move(self, ev) -> bool:
        self._track(ev)
        if self.drag is None:
            return False
        hit = self._ray_plane(ev.x, ev.y)
        if hit is not None:
            self.center = hit + self.drag[2]
        return True

    def on_mouse_up(self, ev) -> bool:
        self._track(ev)
        if self.drag is None or ev.button != MOUSE_LEFT:
            return False
        self.drag = None
        return True

    def on_key(self, ev) -> bool:
        if is_press(ev, KEY_ESCAPE) and self.drag is not None:
            self.center = self.drag[0].copy()
            self.drag = None
            return True
        return False

    # ---- drawing / ui
    def draw_2d(self, ctx):
        d = ctx.draw2d
        if d is None:
            return
        hxy = self._handle_xy()
        if hxy is not None:
            d.circle_fill(hxy[0], hxy[1], 5, ORANGE if self.drag is None else (1, 1, 1, 1), 16)
            d.circle(hxy[0], hxy[1], HANDLE_PX, ORANGE, 1, 24)

    def _ui_ops(self, ui):
        if ui.button('Set'):
            self.apply('set')
        ui.same_line()
        if ui.button('Add'):
            self.apply('add')
        ui.same_line()
        if ui.button('Remove'):
            self.apply('remove')
        ui.same_line()
        if ui.button('Intersect'):
            self.apply('intersect')
        if ui.button('Centre on selection'):
            self.center_on_selection()
        ui.same_line()
        if ui.button('Reset'):
            self.place_default()
        self.opts.footprint = float(ui.slider('Footprint', self.opts.footprint, 0.0, 1.0, '%.2f'))

    def _ui_position(self, ui):
        v = ui.drag_float3('Position', tuple(float(c) for c in self.center), 0.01)
        if v is not None:
            self.center = np.asarray(v, dtype=np.float64).reshape(3)


class SphereSelection(ShapeSelectionBase):
    name = 'sphereSelection'
    title = 'Sphere selection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.radius = 1.0
        self._radius_max = 10.0

    def _fit(self, bound):
        r = bound.radius if bound is not None else 1.0
        r = r if r > 1e-6 else 1.0
        self.radius = r * 0.5
        self._radius_max = max(r * 2.0, 1.0)

    def contains(self, world, pad=0.0):
        d = world - self.center
        r = self.radius + pad
        return np.einsum('ij,ij->i', d, d) <= r * r

    def draw_3d(self, ctx):
        L = ctx.lines3d
        if L is None:
            return
        for n in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            L.circle(self.center, np.array(n, np.float64), self.radius, SHAPE_COLOR, 64)
        # silhouette ring facing the camera
        fwd = getattr(ctx.camera, 'forward', None)
        pos = getattr(ctx.camera, 'position', None)
        if fwd is not None and pos is not None:
            v = self.center - np.asarray(pos, np.float64)
            dist = float(np.linalg.norm(v))
            if dist > self.radius * 1.0001:
                r_s = self.radius * np.sqrt(1 - (self.radius / dist) ** 2)
                c_s = self.center - v / dist * (self.radius ** 2 / dist)
                L.circle(c_s, v / dist, r_s, (1.0, 0.67, 0.4, 0.6), 64)

    def draw_ui(self, ui):
        ui.label(self.title)
        self._ui_position(ui)
        self._radius_max = max(self._radius_max, self.radius)
        self.radius = max(0.01, float(ui.slider('Radius', self.radius, 0.01, self._radius_max, '%.3f')))
        self._ui_ops(ui)

