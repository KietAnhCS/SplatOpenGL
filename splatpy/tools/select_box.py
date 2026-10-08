"""Box selection (tools/box-selection.ts): an oriented world-space box (position, size,
rotation in euler degrees) edited in the tool panel; Set / Add / Remove / Intersect."""

from __future__ import annotations

import numpy as np

from ..core.math3d import AABB, mat4_trs, quat_from_euler, quat_to_mat3
from .select_sphere import SHAPE_COLOR, ShapeSelectionBase


class BoxSelection(ShapeSelectionBase):
    name = 'boxSelection'
    title = 'Box selection'

    def __init__(self, events, scene):
        super().__init__(events, scene)
        self.size = np.ones(3)            # full lengths (lenX, lenY, lenZ)
        self.euler = np.zeros(3)          # degrees

    def _fit(self, bound):
        if bound is None:
            self.size = np.ones(3)
        else:
            ext = np.asarray(bound.half_extents, np.float64) * 2.0
            ext = np.where(ext > 1e-6, ext, max(float(ext.max()), 1.0))
            self.size = ext * 0.5

    def rotation_matrix(self):
        return quat_to_mat3(quat_from_euler(*self.euler))

    def contains(self, world, pad=0.0):
        R = self.rotation_matrix()
        local = (world - self.center) @ R       # R^T (p - c), row vectors
        half = self.size * 0.5
        pad = np.asarray(pad, np.float64)
        if pad.ndim:
            pad = pad[:, None]
        return np.all(np.abs(local) <= half[None, :] + pad, axis=1)

    def draw_3d(self, ctx):
        L = ctx.lines3d
        if L is None:
            return
        h = self.size * 0.5
        m = mat4_trs(self.center, quat_from_euler(*self.euler), np.ones(3))
        L.box(AABB(-h, h), matrix=m, color=SHAPE_COLOR)

    def draw_ui(self, ui):
        ui.label(self.title)
        self._ui_position(ui)
        v = ui.drag_float3('Size', tuple(float(c) for c in self.size), 0.01)
        if v is not None:
            self.size = np.maximum(np.asarray(v, np.float64).reshape(3), 0.01)
        v = ui.drag_float3('Rotation', tuple(float(c) for c in self.euler), 0.5)
        if v is not None:
            self.euler = np.asarray(v, np.float64).reshape(3)
        self._ui_ops(ui)
