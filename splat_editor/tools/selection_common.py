"""Shared helpers for the selection tools (port of supersplat's select-op.ts, the
mask / rect / point paths of editor.ts and data-processor/intersect.ts, CPU side).

Everything is vectorised numpy. Screen coordinates are framebuffer pixels with a
top-left origin (contract). Results are emitted as

    events.fire('select.byMask', splat, mask_bool_N, op)      op in 'set' | 'add' | 'remove'

'intersect' (shift+ctrl, as in supersplat) is converted here to 'set' with
``mask & currently_selected`` so consumers only ever see the three contract ops.

Shared selection options (supersplat 'selection.useDepth' / 'selection.footprint'):
  * use_depth  - only gaussians on the visible front surface (coarse CPU z-buffer of
                 projected centres, ``depth_cell`` px cells, ``depth_tolerance`` relative)
  * footprint  - 0 = test centres only; >0 = test the projected gaussian footprint
                 (disc of radius footprint * 2 sigma) against the region
Events handled: 'selection.setUseDepth'(bool), 'selection.toggleUseDepth',
'selection.setFootprint'(float), 'selection.toggleFootprint',
'tool.brushSelection.smaller', 'tool.brushSelection.bigger'.
Functions: 'selection.useDepth', 'selection.footprint', 'selection.options'.
"""

from __future__ import annotations

import math

import numpy as np

from ..core.splat import SELECTED, DELETED, LOCKED  # noqa: F401  (re-exported for tools)
from ..core.tool_base import MOUSE_LEFT, Tool  # noqa: F401

# glfw key codes (avoid importing glfw so tools are testable headless)
KEY_ESCAPE = 256
KEY_ENTER = 257
KEY_BACKSPACE = 259
KEY_DELETE = 261
KEY_KP_ENTER = 335
KEY_LEFT_BRACKET = 91
KEY_RIGHT_BRACKET = 93
PRESS, REPEAT = 1, 2

ORANGE = (1.0, 0.4, 0.0, 1.0)          # supersplat '#f60'
ORANGE_LIGHT = (1.0, 0.667, 0.4, 1.0)  # '#fa6' (closable polygon)
ORANGE_FILL = (1.0, 0.4, 0.0, 0.18)
CLOSE_DIST_PX = 8.0


# --------------------------------------------------------------------------- op / options

def op_from_mods(mods) -> str:
    """shift+ctrl = intersect, shift = add, ctrl = remove, none = set (select-op.ts)."""
    shift = bool(getattr(mods, 'shift', False))
    ctrl = bool(getattr(mods, 'ctrl', False))
    if shift and ctrl:
        return 'intersect'
    if shift:
        return 'add'
    if ctrl:
        return 'remove'
    return 'set'


OP_BADGE = {'add': '+', 'remove': '-', 'intersect': '&'}


class SelectionOptions:
    def __init__(self):
        self.use_depth = False
        self.footprint = 0.0
        self.depth_cell = 3            # px
        self.depth_tolerance = 0.02    # relative depth tolerance for the z-buffer test
        self.brush_radius = 40.0       # px, shared by brush + sphere brush
        self.flood_threshold = 0.2
        self.eyedropper_threshold = 0.2


def get_selection_options(events) -> SelectionOptions:
    """Return the shared options object (created + registered on first call)."""
    if events.has_function('selection.options'):
        return events.invoke('selection.options')
    opts = SelectionOptions()
    events.function('selection.options', lambda: opts)
    events.function('selection.useDepth', lambda: opts.use_depth)
    events.function('selection.footprint', lambda: opts.footprint)

    def set_depth(v):
        v = bool(v)
        if v != opts.use_depth:
            opts.use_depth = v
            events.fire('selection.useDepth', v)

    def set_fp(v):
        v = float(min(1.0, max(0.0, v)))
        if v != opts.footprint:
            opts.footprint = v
            events.fire('selection.footprint', v)

    events.on('selection.setUseDepth', set_depth)
    events.on('selection.toggleUseDepth', lambda: set_depth(not opts.use_depth))
    events.on('selection.setFootprint', set_fp)
    events.on('selection.toggleFootprint', lambda: set_fp(0.0 if opts.footprint > 0 else 1.0))

    def smaller():
        opts.brush_radius = max(1.0, opts.brush_radius / 1.05)

    def bigger():
        opts.brush_radius = min(500.0, opts.brush_radius * 1.05)

    events.on('tool.brushSelection.smaller', smaller)
    events.on('tool.brushSelection.bigger', bigger)
    return opts


# --------------------------------------------------------------------------- scene access

def target_splat(scene):
    """The layer selection tools operate on: scene.selected_splat if visible and non-empty."""
    s = getattr(scene, 'selected_splat', None)
    if s is None or not getattr(s, 'visible', True) or s.count == 0:
        return None
    return s


def viewport(scene):
    return max(1, int(scene.width)), max(1, int(scene.height))


class Projection:
    """Projected centres of one splat layer (computed once per gesture)."""

    def __init__(self, scene, splat):
        w, h = viewport(scene)
        self.width, self.height = w, h
        self.splat = splat
        self.world = splat.world_positions()
        xy, depth, in_front = scene.camera.world_to_screen(self.world, w, h)
        self.xy = np.asarray(xy, dtype=np.float32).reshape(-1, 2)
        self.depth = np.asarray(depth, dtype=np.float32).reshape(-1)
        self.in_front = np.asarray(in_front, dtype=bool).reshape(-1)
        self.editable = splat.editable_mask()
        x, y = self.xy[:, 0], self.xy[:, 1]
        self.on_screen = self.in_front & (x >= 0) & (x < w) & (y >= 0) & (y < h) & np.isfinite(x) & np.isfinite(y)
        # candidates: editable, in front of the camera
        self.cand = self.editable & self.in_front & np.isfinite(x) & np.isfinite(y)
        self._zbuf = None

    # ---- coarse z-buffer of projected (editable, on-screen) centres
    def zbuffer(self, cell: int):
        if self._zbuf is not None and self._zbuf[0] == cell:
            return self._zbuf
        w, h = self.width, self.height
        gw, gh = (w + cell - 1) // cell, (h + cell - 1) // cell
        valid = np.flatnonzero(self.on_screen & self.editable)
        cx = (self.xy[valid, 0] // cell).astype(np.int64)
        cy = (self.xy[valid, 1] // cell).astype(np.int64)
        cid = cy * gw + cx
        z = np.full(gw * gh, np.inf, np.float32)
        np.minimum.at(z, cid, self.depth[valid])
        owner = np.full(gw * gh, -1, np.int64)
        front = self.depth[valid] <= z[cid]
        owner[cid[front]] = valid[front]
        self._zbuf = (cell, gw, gh, z, owner)
        return self._zbuf

    def front_surface(self, cell: int, tol: float) -> np.ndarray:
        """(N,) bool: centre is within `tol` (relative) of the front-most depth in its cell."""
        cell_, gw, gh, z, _ = self.zbuffer(cell)
        out = np.zeros(len(self.depth), bool)
        idx = np.flatnonzero(self.on_screen & self.editable)
        cid = (self.xy[idx, 1] // cell).astype(np.int64) * gw + (self.xy[idx, 0] // cell).astype(np.int64)
        zf = z[cid]
        out[idx] = self.depth[idx] <= zf + np.abs(zf) * tol + 1e-6
        return out

    def pick(self, x, y, radius_px=6.0):
        """Front-most editable gaussian whose centre is within radius_px of (x, y), or None."""
        d2 = (self.xy[:, 0] - x) ** 2 + (self.xy[:, 1] - y) ** 2
        m = self.cand & (d2 <= radius_px * radius_px)
        idx = np.flatnonzero(m)
        if len(idx) == 0:
            return None
        # prefer the nearest-to-camera; break ties with screen distance
        return int(idx[np.lexsort((d2[idx], self.depth[idx]))[0]])

    def footprint_px(self, scene, footprint: float, idx: np.ndarray) -> np.ndarray:
        """Projected footprint radius (px) for gaussians idx (footprint * 2 sigma)."""
        splat = self.splat
        ls = np.exp(splat.data.scales[idx].astype(np.float64)).max(axis=1)
        rw = footprint * 2.0 * ls * float(np.max(np.abs(splat.scale)))
        cam = scene.camera
        right = np.asarray(getattr(cam, 'right', (1.0, 0.0, 0.0)), dtype=np.float64).reshape(3)
        xy2, _, _ = cam.world_to_screen(self.world[idx] + rw[:, None] * right[None, :], self.width, self.height)
        xy2 = np.asarray(xy2, dtype=np.float32).reshape(-1, 2)
        r = np.hypot(xy2[:, 0] - self.xy[idx, 0], xy2[:, 1] - self.xy[idx, 1])
        return np.where(np.isfinite(r), r, 0.0).astype(np.float32)

    def finish(self, scene, opts, mask: np.ndarray) -> np.ndarray:
        """Restrict a candidate mask to editable/in-front (+ front surface if use_depth)."""
        mask &= self.cand
        if opts is not None and opts.use_depth:
            mask &= self.front_surface(opts.depth_cell, opts.depth_tolerance)
        return mask


# --------------------------------------------------------------------------- 2D regions

def sample_image(img: np.ndarray, xy: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Look up bool image (H,W) at pixel positions xy[idx]. Returns bool (len(idx),)."""
    h, w = img.shape
    xi = np.floor(xy[idx, 0]).astype(np.int64)
    yi = np.floor(xy[idx, 1]).astype(np.int64)
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    out = np.zeros(len(idx), bool)
    out[ok] = img[yi[ok], xi[ok]]
    return out


def raster_polygon(points, width: int, height: int) -> np.ndarray:
    """Fill a (possibly concave / self-intersecting) polygon into a bool (H,W) image."""
    from PIL import Image, ImageDraw
    img = Image.new('L', (int(width), int(height)), 0)
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) >= 3:
        ImageDraw.Draw(img).polygon(pts, fill=255, outline=255)
    return np.asarray(img) > 0


def raster_stroke(samples, width: int, height: int) -> np.ndarray:
    """Rasterise a round brush stroke; samples = [(x, y, r), ...]."""
    from PIL import Image, ImageDraw
    img = Image.new('L', (int(width), int(height)), 0)
    d = ImageDraw.Draw(img)
    prev = None
    for x, y, r in samples:
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        if prev is not None:
            px, py, pr = prev
            rr = min(r, pr)
            dx, dy = x - px, y - py
            L = math.hypot(dx, dy)
            if L > 1e-6:
                nx, ny = -dy / L * rr, dx / L * rr
                d.polygon([(px + nx, py + ny), (x + nx, y + ny), (x - nx, y - ny), (px - nx, py - ny)], fill=255)
        prev = (x, y, r)
    return np.asarray(img) > 0


_RING = [(math.cos(a), math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]


def select_in_image(scene, proj: Projection, img: np.ndarray, opts) -> np.ndarray:
    """Full-length (N,) mask of candidate gaussians whose centre (or footprint) hits img."""
    n = len(proj.depth)
    mask = np.zeros(n, bool)
    idx = np.flatnonzero(proj.cand)
    if len(idx) == 0:
        return mask
    hit = sample_image(img, proj.xy, idx)
    fp = float(opts.footprint) if opts is not None else 0.0
    if fp > 0:
        rest = idx[~hit]
        if len(rest):
            r = proj.footprint_px(scene, fp, rest)
            sub = np.zeros(len(rest), bool)
            xy = proj.xy[rest]
            tmp = np.empty_like(xy)
            for cx, cy in _RING + [(0.5, 0.0), (-0.5, 0.0), (0.0, 0.5), (0.0, -0.5)]:
                tmp[:, 0] = xy[:, 0] + cx * r
                tmp[:, 1] = xy[:, 1] + cy * r
                sub |= sample_image(img, tmp, np.arange(len(rest)))
            hit[~hit] = sub
    mask[idx[hit]] = True
    return proj.finish(scene, opts, mask)


def select_in_rect(scene, proj: Projection, x0, y0, x1, y1, opts) -> np.ndarray:
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    n = len(proj.depth)
    mask = np.zeros(n, bool)
    idx = np.flatnonzero(proj.cand)
    if len(idx) == 0:
        return mask
    x, y = proj.xy[idx, 0], proj.xy[idx, 1]
    fp = float(opts.footprint) if opts is not None else 0.0
    if fp > 0:
        r = proj.footprint_px(scene, fp, idx)
        # disc vs rect: distance from centre to the rect <= r
        dx = np.maximum(np.maximum(x0 - x, 0), x - x1)
        dy = np.maximum(np.maximum(y0 - y, 0), y - y1)
        hit = dx * dx + dy * dy <= r * r
    else:
        hit = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    mask[idx[hit]] = True
    return proj.finish(scene, opts, mask)


# --------------------------------------------------------------------------- colour

def splat_colors(splat) -> np.ndarray:
    """(N,3) base colour (band 0) in 0..1 with the layer colour grade applied when available."""
    rgb = np.clip(splat.data.colors(), 0.0, 1.0)
    adj = getattr(splat, 'color', None)
    if adj is not None and not adj.is_identity():
        try:
            from ..data.color_grade import apply_grade
            rgb, _ = apply_grade(rgb, splat.data.alphas(), adj)
            rgb = np.clip(np.asarray(rgb), 0.0, 1.0)
        except Exception:
            pass
    return np.asarray(rgb, dtype=np.float32)


def color_match_mask(splat, ref_rgb, threshold: float) -> np.ndarray:
    """Per-channel absolute difference <= threshold, editable gaussians only (color-match.ts)."""
    col = splat_colors(splat)
    ref = np.asarray(ref_rgb, dtype=np.float32).reshape(1, 3)
    return np.all(np.abs(col - ref) <= float(threshold), axis=1) & splat.editable_mask()


# --------------------------------------------------------------------------- emit

def emit_selection(events, splat, mask: np.ndarray, op: str) -> np.ndarray:
    """Fire 'select.byMask'. 'intersect' becomes 'set' with mask & current selection."""
    mask = np.asarray(mask, dtype=bool) & splat.editable_mask()
    if op == 'intersect':
        mask = mask & splat.selected_mask()
        op = 'set'
    events.fire('select.byMask', splat, mask, op)
    return mask


def is_press(ev, *keys) -> bool:
    return ev.kind == 'key' and ev.action in (PRESS, REPEAT) and ev.key in keys


def draw_op_badge(d, x, y, mods):
    op = op_from_mods(mods)
    badge = OP_BADGE.get(op)
    if badge and d is not None:
        d.text(x + 12, y + 8, badge, (1, 1, 1, 1), 16)


def draw_common_options(ui, opts, show_footprint=True):
    """Use depth / footprint widgets shared by the screen-space tools."""
    opts.use_depth = bool(ui.checkbox('Use depth (front surface only)', opts.use_depth))
    if show_footprint:
        opts.footprint = float(ui.slider('Footprint', opts.footprint, 0.0, 1.0, '%.2f'))


# --------------------------------------------------------------------------- registry

def _tool_classes():
    from .select_rect import RectSelection
    from .select_lasso import LassoSelection
    from .select_polygon import PolygonSelection
    from .select_brush import BrushSelection, SphereBrushSelection
    from .select_sphere import SphereSelection
    from .select_box import BoxSelection
    from .select_flood import FloodSelection
    from .select_eyedropper import EyedropperSelection
    return {
        'rectSelection': RectSelection,
        'lassoSelection': LassoSelection,
        'polygonSelection': PolygonSelection,
        'brushSelection': BrushSelection,
        'sphereBrushSelection': SphereBrushSelection,
        'sphereSelection': SphereSelection,
        'boxSelection': BoxSelection,
        'floodSelection': FloodSelection,
        'eyedropperSelection': EyedropperSelection,
    }


def create_selection_tools(events, scene) -> dict:
    """Instantiate every selection tool. Register with ToolManager.register(name, tool)."""
    get_selection_options(events)
    return {name: cls(events, scene) for name, cls in _tool_classes().items()}


class SelectionToolBase(Tool):
    """Common state: scene, shared options, last mouse position / modifiers."""

    def __init__(self, events, scene):
        super().__init__(events)
        self.scene = scene
        self.opts = get_selection_options(events)
        self.mouse = (0.0, 0.0)
        self.mods = None

    def _track(self, ev):
        if ev.kind in ('mouse_move', 'mouse_down', 'mouse_up', 'double_click'):
            self.mouse = (ev.x, ev.y)
        self.mods = ev.mods

    def _ready(self):
        """(splat, Projection) or (None, None) when there is nothing to select."""
        splat = target_splat(self.scene)
        if splat is None or getattr(self.scene, 'camera', None) is None:
            return None, None
        return splat, Projection(self.scene, splat)

    def on_double_click(self, ev) -> bool:   # in case the app dispatches separately
        return self.on_mouse_down(ev)


def __getattr__(name):
    # TOOL_CLASSES is resolved lazily so `import select_rect` first never hits a circular import
    if name == 'TOOL_CLASSES':
        return _tool_classes()
    raise AttributeError(name)
