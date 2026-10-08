"""Per-frame scene overlays: selected layer bound (corner brackets, like supersplat splat.ts
onPreRender), selection bound box, and optional bound dimension labels (ui/bound-dimensions-overlay.ts).
"""

from __future__ import annotations

import numpy as np

from ..core.math3d import AABB, transform_points

BOUND_COLOR = (1.0, 1.0, 1.0, 1.0)
SELECTION_BOUND_COLOR = (1.0, 1.0, 0.0, 1.0)


def _bounding_points(fraction=0.75) -> np.ndarray:
    """supersplat boundingPoints: for each of the 8 unit-cube corners, 3 segments running from the
    corner towards the neighbouring corners, ending at `fraction` of the coordinate. (48, 3)."""
    pts = []
    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                pts += [(x, y, z), (x * fraction, y, z),
                        (x, y, z), (x, y * fraction, z),
                        (x, y, z), (x, y, z * fraction)]
    return np.array(pts, dtype=np.float64)


BOUNDING_POINTS = _bounding_points()


def bound_bracket_segments(aabb: AABB, matrix=None) -> np.ndarray:
    """Corner bracket segments of `aabb` (transformed by optional 4x4 matrix): (48, 3) point pairs
    (24 segments), or (0, 3) for an empty bound."""
    if aabb is None or aabb.empty:
        return np.zeros((0, 3))
    pts = BOUNDING_POINTS * aabb.half_extents + aabb.center
    if matrix is not None:
        pts = transform_points(np.asarray(matrix, dtype=np.float64), pts)
    return pts


# corner index = sx*4 + sy*2 + sz (matches AABB.corners() ordering)
_AXIS_EDGES = [
    [(0, 4), (1, 5), (2, 6), (3, 7)],
    [(0, 2), (1, 3), (4, 6), (5, 7)],
    [(0, 1), (2, 3), (4, 5), (6, 7)],
]


def _fmt_len(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


class SceneOverlays:
    def __init__(self, events, scene):
        self.events = events
        self.scene = scene

    def _active(self, ctx):
        scene = getattr(ctx, 'scene', None) or self.scene
        s = scene.settings
        if not s.edit_view:
            return None
        splat = scene.selected_splat
        if splat is None or not splat.visible:
            return None
        return scene, splat

    def draw_3d(self, ctx):
        lines = getattr(ctx, 'lines3d', None)
        r = self._active(ctx)
        if lines is None or r is None:
            return
        scene, splat = r
        world = splat.world_matrix()
        if scene.settings.show_bound:
            seg = bound_bracket_segments(splat.local_bound(), world)
            if len(seg):
                lines.lines(seg, BOUND_COLOR)
        if splat.num_selected > 0:
            sb = splat.selection_bound()
            if not sb.empty:
                m = world
                if splat.selection_preview is not None:
                    m = world @ np.asarray(splat.selection_preview, dtype=np.float64)
                lines.box(sb, m, SELECTION_BOUND_COLOR)

    def draw_2d(self, ctx):
        """Bound dimension labels (enabled by settings.extra['show_bound_dimensions'])."""
        d = getattr(ctx, 'draw2d', None)
        cam = getattr(ctx, 'camera', None)
        r = self._active(ctx)
        if d is None or cam is None or r is None:
            return
        scene, splat = r
        if not scene.settings.show_bound or not scene.settings.extra.get('show_bound_dimensions', False):
            return
        bound = splat.local_bound()
        if bound.empty:
            return
        world = splat.world_matrix()
        corners = transform_points(world, bound.corners())
        center = transform_points(world, bound.center)
        xy, _, front = cam.world_to_screen(np.vstack([corners, center[None]]), ctx.width, ctx.height)
        xy = np.asarray(xy, dtype=np.float64)
        sc = xy[8]
        for axis in range(3):
            best, best_score = None, -np.inf
            for a, b in _AXIS_EDGES[axis]:
                if not (front[a] and front[b]):
                    continue
                m = (xy[a] + xy[b]) * 0.5
                score = float(np.sum((m - sc) ** 2))
                if score > best_score + 1:
                    best, best_score = (a, b), score
            if best is None:
                continue
            a, b = best
            length = float(np.linalg.norm(corners[b] - corners[a]))
            m = (xy[a] + xy[b]) * 0.5
            text = _fmt_len(length)
            try:
                tw, th = d.text_size(text, 13)
            except Exception:
                tw, th = 8 * len(text), 13
            col = ((1, 0.4, 0.4, 1), (0.4, 1, 0.4, 1), (0.5, 0.5, 1, 1))[axis]
            d.rect(m[0] - tw * 0.5 - 4, m[1] - th * 0.5 - 2, tw + 8, th + 4, (0, 0, 0, 0.6))
            d.text(m[0] - tw * 0.5, m[1] - th * 0.5, text, col, 13)
