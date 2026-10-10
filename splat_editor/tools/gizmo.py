"""Screen-space transform gizmo (translate / rotate / scale) drawn with Lines3D + Draw2D.

Replacement for PlayCanvas's TranslateGizmo / RotateGizmo / ScaleGizmo used by supersplat.

* The gizmo lives at a world-space pivot `position` with an orthonormal frame `axes` (3x3, columns
  are the gizmo X/Y/Z axes - identity in world space, the pivot rotation in local space).
* It keeps a constant on-screen size (``size_px`` pixels): the world length of one gizmo unit is
  measured by projecting a short segment through the camera, so it works for perspective and ortho.
* Hit testing is done in screen space with ``camera.world_to_screen``; drags use
  ``camera.screen_to_ray``:
    - axis translate / scale : closest point between the mouse ray and the axis line
    - plane translate        : ray / plane intersection
    - centre translate       : ray / camera-facing plane intersection
    - rotate (axis or view)  : signed angle on the ring plane (tangent drag when the ring is edge-on)
    - uniform scale          : horizontal/vertical mouse motion
  Snapping (``snap=True``, the tools pass ctrl): 0.1 units, 15 degrees, 0.1 scale steps.

Usage::

    g = Gizmo('translate')
    g.set_frame(pivot_world, axes3x3)
    h = g.hit_test(x, y, camera, w, h)          # handle name or None
    g.begin_drag(h, x, y, camera, w, h)
    d = g.drag(x, y, camera, w, h, snap)        # GizmoDelta (matrix = world-space delta about pivot)
    g.end_drag()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from splat_editor.core.math3d import mat3_to_quat, mat4_translate, quat_from_axis_angle, quat_to_mat3

MODES = ('translate', 'rotate', 'scale')

AXIS_COLORS = (
    (1.0, 0.32, 0.32, 1.0),
    (0.35, 0.95, 0.35, 1.0),
    (0.35, 0.55, 1.0, 1.0),
)
HOVER_COLOR = (1.0, 1.0, 0.25, 1.0)
VIEW_RING_COLOR = (0.85, 0.85, 0.85, 1.0)
CENTER_COLOR = (0.95, 0.95, 0.95, 1.0)

AXIS_INDEX = {'x': 0, 'y': 1, 'z': 2}
PLANE_AXES = {'yz': (1, 2, 0), 'xz': (0, 2, 1), 'xy': (0, 1, 2)}  # (u axis, v axis, normal axis)

HIT_RADIUS_PX = 9.0
RING_SEGMENTS = 64


def _norm(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _seg_dist(p, a, b):
    """Distance from 2D point p to segment ab."""
    ab = b - a
    l2 = float(ab @ ab)
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, float((p - a) @ ab) / l2))
    return float(np.linalg.norm(a + ab * t - p))


def _point_in_poly(p, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]):
            xi = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < xi:
                inside = not inside
    return inside


def _with_alpha(c, a):
    return (c[0], c[1], c[2], c[3] * a)


def closest_param_on_line(origin, axis, ray_o, ray_d):
    """Parameter t of the point origin + t*axis closest to the ray (axis, ray_d unit). None if parallel."""
    axis = _norm(axis)
    ray_d = _norm(ray_d)
    w0 = np.asarray(origin, np.float64) - np.asarray(ray_o, np.float64)
    b = float(axis @ ray_d)
    denom = 1.0 - b * b
    if denom < 1e-9:
        return None
    return (b * float(ray_d @ w0) - float(axis @ w0)) / denom


def ray_plane(ray_o, ray_d, point, normal):
    """Intersection point of a ray with a plane, None when parallel or behind."""
    normal = _norm(normal)
    dn = float(np.asarray(ray_d) @ normal)
    if abs(dn) < 1e-9:
        return None
    t = float((np.asarray(point) - np.asarray(ray_o)) @ normal) / dn
    if t < 0:
        return None
    return np.asarray(ray_o, np.float64) + np.asarray(ray_d, np.float64) * t


def signed_angle(v0, v1, n):
    """Angle rotating v0 onto v1 about n (radians, -pi..pi)."""
    return math.atan2(float(np.cross(v0, v1) @ n), float(v0 @ v1))


def snap_value(v, step):
    return round(v / step) * step if step > 0 else v


@dataclass
class GizmoDelta:
    """Result of a drag step. All relative to the drag start."""
    matrix: np.ndarray = field(default_factory=lambda: np.eye(4))   # world-space delta (about the pivot)
    translation: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rotation: np.ndarray = field(default_factory=lambda: np.array([1.0, 0, 0, 0]))  # world quat (w,x,y,z)
    scale: np.ndarray = field(default_factory=lambda: np.ones(3))   # per gizmo axis
    label: str = ''


class Gizmo:
    def __init__(self, mode: str = 'translate', size_px: float = 110.0):
        assert mode in MODES
        self.mode = mode
        self.size_px = size_px
        self.position = np.zeros(3)
        self.axes = np.eye(3)
        self.hover: str | None = None
        self.active: str | None = None      # handle being dragged
        self.visible = True
        self.snap_translate = 0.1
        self.snap_rotate = 15.0              # degrees
        self.snap_scale = 0.1
        self._unit = 1.0
        self._handles: dict = {}
        self._drag: dict | None = None
        self.last_delta: GizmoDelta | None = None

    # ------------------------------------------------------------------ frame / layout
    def set_frame(self, position, axes=None):
        self.position = np.asarray(position, dtype=np.float64).copy()
        self.axes = np.eye(3) if axes is None else np.asarray(axes, dtype=np.float64).copy()

    @property
    def dragging(self) -> bool:
        return self._drag is not None

    @staticmethod
    def _to_camera(camera, p):
        d = np.asarray(camera.position, np.float64) - p
        if getattr(camera, 'ortho', False) or np.linalg.norm(d) < 1e-9:
            return -_norm(camera.forward)
        return _norm(d)

    def world_unit(self, camera, width, height) -> float | None:
        """World length that projects to size_px pixels at the pivot. None when behind the camera."""
        p = self.position
        dist = float(np.linalg.norm(np.asarray(camera.position, np.float64) - p))
        s = max(dist * 0.05, 1e-6)
        up = _norm(camera.up)
        xy, _, front = camera.world_to_screen(np.array([p, p + up * s]), width, height)
        if not bool(np.all(front)):
            return None
        px = float(np.linalg.norm(np.asarray(xy[1]) - np.asarray(xy[0])))
        if px < 1e-9:
            return None
        return s / px * self.size_px

    def layout(self, camera, width, height) -> bool:
        """Build world-space handle geometry. Returns False when the gizmo can't be shown."""
        self._handles = {}
        if camera is None or not self.visible:
            return False
        unit = self.world_unit(camera, width, height)
        if unit is None:
            return False
        self._unit = L = unit
        P = self.position
        to_cam = self._to_camera(camera, P)
        H = {}
        if self.mode in ('translate', 'scale'):
            for name, i in AXIS_INDEX.items():
                a = self.axes[:, i]
                # hide axes pointing (nearly) at the camera
                if abs(float(a @ to_cam)) > 0.985:
                    continue
                H[name] = dict(kind='line', pts=np.array([P + a * 0.18 * L, P + a * L]), axis=i)
            if self.mode == 'translate':
                for name, (iu, iv, inorm) in PLANE_AXES.items():
                    n = self.axes[:, inorm]
                    if abs(float(n @ to_cam)) < 0.2:
                        continue
                    u = self.axes[:, iu] * (1.0 if self.axes[:, iu] @ to_cam >= 0 else -1.0)
                    v = self.axes[:, iv] * (1.0 if self.axes[:, iv] @ to_cam >= 0 else -1.0)
                    a0, a1 = 0.25 * L, 0.45 * L
                    quad = np.array([P + u * a0 + v * a0, P + u * a1 + v * a0, P + u * a1 + v * a1, P + u * a0 + v * a1])
                    H[name] = dict(kind='quad', pts=quad, axis=inorm)
            H['xyz'] = dict(kind='point', pts=np.array([P]), radius=8.0 if self.mode == 'translate' else 10.0)
        else:
            ang = np.linspace(0, 2 * math.pi, RING_SEGMENTS + 1)
            for name, i in AXIS_INDEX.items():
                n = self.axes[:, i]
                u = self.axes[:, (i + 1) % 3]
                v = self.axes[:, (i + 2) % 3]
                r = 0.85 * L
                pts = P + r * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v)
                H[name] = dict(kind='ring', pts=pts, axis=i, normal=n, radius=r)
            n = to_cam
            u = _norm(np.cross(n, camera.up)) if abs(float(n @ _norm(camera.up))) < 0.99 else _norm(camera.right)
            v = np.cross(n, u)
            r = 1.05 * L
            pts = P + r * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v)
            H['view'] = dict(kind='ring', pts=pts, axis=-1, normal=n, radius=r, view=True)
        self._handles = H
        return True

    # ------------------------------------------------------------------ hit testing
    def hit_test(self, x, y, camera, width, height):
        if not self.layout(camera, width, height):
            return None
        m = np.array([x, y], dtype=np.float64)
        to_cam = self._to_camera(camera, self.position)
        best, best_d = None, HIT_RADIUS_PX
        for name, h in self._handles.items():
            xy, _, front = camera.world_to_screen(h['pts'], width, height)
            xy = np.asarray(xy, np.float64)
            kind = h['kind']
            if kind == 'point':
                if not front[0]:
                    continue
                d = float(np.linalg.norm(xy[0] - m))
                if d <= h['radius']:
                    d = -2.0                                  # centre has priority
                else:
                    continue
            elif kind == 'quad':
                if not np.all(front):
                    continue
                if _point_in_poly(m, xy):
                    d = -1.0
                else:
                    continue
            else:
                d = math.inf
                for k in range(len(xy) - 1):
                    if not (front[k] and front[k + 1]):
                        continue
                    sd = _seg_dist(m, xy[k], xy[k + 1])
                    if kind == 'ring' and not h.get('view'):
                        mid = (h['pts'][k] + h['pts'][k + 1]) * 0.5 - self.position
                        if float(mid @ to_cam) < -1e-6 * self._unit:
                            sd += 4.0                         # back half is less pickable
                    d = min(d, sd)
            if d < best_d:
                best, best_d = name, d
        return best

    # ------------------------------------------------------------------ dragging
    def begin_drag(self, handle, x, y, camera, width, height) -> bool:
        if handle is None:
            return False
        if not self._handles:
            self.layout(camera, width, height)
        h = self._handles.get(handle)
        if h is None:
            return False
        o, d = camera.screen_to_ray(x, y, width, height)
        P = self.position.copy()
        st = dict(handle=handle, kind=h['kind'], P=P, axes=self.axes.copy(), unit=self._unit,
                  mouse0=np.array([x, y], np.float64))
        to_cam = self._to_camera(camera, P)
        if self.mode == 'translate':
            if h['kind'] == 'line':
                a = self.axes[:, h['axis']]
                t0 = closest_param_on_line(P, a, o, d)
                if t0 is None:
                    return False
                st.update(axis=a, t0=t0)
            else:
                n = self.axes[:, h['axis']] if h['kind'] == 'quad' else to_cam
                hit = ray_plane(o, d, P, n)
                if hit is None:
                    return False
                st.update(normal=n, hit0=hit)
        elif self.mode == 'scale':
            if h['kind'] == 'line':
                a = self.axes[:, h['axis']]
                t0 = closest_param_on_line(P, a, o, d)
                if t0 is None:
                    return False
                st.update(axis=a, t0=t0)
        else:  # rotate
            n = h['normal']
            st['normal'] = n.copy()
            # grab point on the ring closest to the cursor (screen space)
            xy, _, front = camera.world_to_screen(h['pts'], width, height)
            dd = np.linalg.norm(np.asarray(xy, np.float64) - st['mouse0'], axis=1)
            dd[~np.asarray(front, bool)] = np.inf
            g = h['pts'][int(np.argmin(dd))]
            edge_on = abs(float(n @ to_cam)) < 0.2
            hit = None if edge_on else ray_plane(o, d, P, n)
            if hit is None or np.linalg.norm(hit - P) < 1e-9 * max(self._unit, 1e-9):
                # tangent drag: screen-space motion along the projected ring tangent
                t = _norm(np.cross(n, g - P))
                s_xy, _, _ = camera.world_to_screen(np.array([g, g + t * self._unit * 0.1]), width, height)
                tdir = np.asarray(s_xy[1], np.float64) - np.asarray(s_xy[0], np.float64)
                tl = float(np.linalg.norm(tdir))
                tdir = tdir / tl if tl > 1e-9 else np.array([1.0, 0.0])
                st.update(method='tangent', tdir=tdir, radius_px=self.size_px * h['radius'] / self._unit)
            else:
                st.update(method='plane', v0=hit - P, prev=0.0, accum=0.0)
        self._drag = st
        self.active = handle
        self.last_delta = GizmoDelta()
        return True

    def drag(self, x, y, camera, width, height, snap: bool = False) -> GizmoDelta:
        st = self._drag
        if st is None:
            return GizmoDelta()
        o, d = camera.screen_to_ray(x, y, width, height)
        P, axes = st['P'], st['axes']
        res = GizmoDelta()
        if self.mode == 'translate':
            if st['kind'] == 'line':
                t = closest_param_on_line(P, st['axis'], o, d)
                if t is None:
                    return self.last_delta or res
                dt = t - st['t0']
                if snap:
                    dt = snap_value(dt, self.snap_translate)
                delta = st['axis'] * dt
            else:
                hit = ray_plane(o, d, P, st['normal'])
                if hit is None:
                    return self.last_delta or res
                delta = hit - st['hit0']
                if snap:
                    if st['kind'] == 'quad':
                        local = axes.T @ delta
                        delta = axes @ np.array([snap_value(c, self.snap_translate) for c in local])
                    else:
                        delta = np.array([snap_value(c, self.snap_translate) for c in delta])
            res.translation = delta
            res.matrix = mat4_translate(delta)
            res.label = '%.3f, %.3f, %.3f' % tuple(delta)
        elif self.mode == 'rotate':
            n = st['normal']
            if st['method'] == 'plane':
                hit = ray_plane(o, d, P, n)
                if hit is not None and np.linalg.norm(hit - P) > 1e-12:
                    a = signed_angle(st['v0'], hit - P, n)
                    da = a - st['prev']
                    da = (da + math.pi) % (2 * math.pi) - math.pi        # unwrap
                    st['accum'] += da
                    st['prev'] = a
                angle = st['accum']
            else:
                mv = np.array([x, y], np.float64) - st['mouse0']
                angle = float(mv @ st['tdir']) / max(st['radius_px'], 1e-6)
            deg = math.degrees(angle)
            if snap:
                deg = snap_value(deg, self.snap_rotate)
            angle = math.radians(deg)
            q = quat_from_axis_angle(n, angle)
            R = np.eye(4)
            R[:3, :3] = quat_to_mat3(q)
            res.rotation = q
            res.matrix = mat4_translate(P) @ R @ mat4_translate(-P)
            res.label = '%.1f°' % deg
        else:  # scale
            if st['kind'] == 'line':
                t = closest_param_on_line(P, st['axis'], o, d)
                if t is None:
                    return self.last_delta or res
                f = 1.0 + (t - st['t0']) / st['unit']
                s = np.ones(3)
                i = AXIS_INDEX[st['handle']]
                f = snap_value(f, self.snap_scale) if snap else f
                s[i] = f
            else:
                mv = np.array([x, y], np.float64) - st['mouse0']
                f = 1.0 + (mv[0] - mv[1]) / max(self.size_px, 1.0)
                f = snap_value(f, self.snap_scale) if snap else f
                s = np.full(3, f)
            s = np.where(np.abs(s) < 1e-3, np.copysign(1e-3, s + 1e-12), s)
            res.scale = s
            A = np.eye(4)
            A[:3, :3] = axes @ np.diag(s) @ axes.T
            res.matrix = mat4_translate(P) @ A @ mat4_translate(-P)
            res.label = 'x%.3f' % s[AXIS_INDEX.get(st['handle'], 0)] if st['kind'] == 'line' else 'x%.3f' % s[0]
        self.last_delta = res
        return res

    def end_drag(self):
        self._drag = None
        self.active = None

    # ------------------------------------------------------------------ display frame during drag
    def apply_display_delta(self, delta: GizmoDelta, local_space: bool):
        """Move the drawn gizmo with the drag (pivot follows translation; axes follow rotation in local space)."""
        st = self._drag
        if st is None:
            return
        P = st['P']
        self.position = P + delta.translation
        if self.mode == 'rotate' and local_space:
            self.axes = quat_to_mat3(delta.rotation) @ st['axes']
        else:
            self.axes = st['axes'].copy()

    # ------------------------------------------------------------------ drawing
    def _color(self, name, base):
        if name == self.active or (self.active is None and name == self.hover):
            return HOVER_COLOR
        if self.active is not None:
            return _with_alpha(base, 0.45)
        return base

    def draw_3d(self, ctx):
        lines = getattr(ctx, 'lines3d', None)
        if lines is None or not self.layout(ctx.camera, ctx.width, ctx.height):
            return
        L = self._unit
        P = self.position
        to_cam = self._to_camera(ctx.camera, P)
        st = self._drag
        # guide line along the dragged axis
        if st is not None and 'axis' in st and self.mode in ('translate', 'scale'):
            a = st['axis']
            c = AXIS_COLORS[AXIS_INDEX[st['handle']]] if st['handle'] in AXIS_INDEX else CENTER_COLOR
            lines.line(st['P'] - a * L * 1000, st['P'] + a * L * 1000, _with_alpha(c, 0.5), on_top=True)
        for name, h in self._handles.items():
            kind = h['kind']
            base = AXIS_COLORS[h['axis']] if h.get('axis', -1) >= 0 and kind != 'point' else (
                VIEW_RING_COLOR if kind == 'ring' else CENTER_COLOR)
            col = self._color(name, base)
            pts = h['pts']
            if kind == 'line':
                a = self.axes[:, h['axis']]
                lines.line(P, pts[1] - a * (0.18 * L if self.mode == 'translate' else 0.0), col, on_top=True)
                if self.mode == 'translate':
                    self._cone(lines, pts[1] - a * 0.18 * L, pts[1], 0.06 * L, col)
                else:
                    self._cube(lines, pts[1], a, 0.05 * L, col)
            elif kind == 'quad':
                for k in range(4):
                    lines.line(pts[k], pts[(k + 1) % 4], col, on_top=True)
            elif kind == 'ring':
                view = h.get('view', False)
                for k in range(len(pts) - 1):
                    c = col
                    if not view:
                        mid = (pts[k] + pts[k + 1]) * 0.5 - P
                        if float(mid @ to_cam) < -1e-6 * L:
                            c = _with_alpha(col, 0.25)
                    lines.line(pts[k], pts[k + 1], c, on_top=True)
        if self.mode == 'rotate' and st is not None and st.get('method') == 'plane':
            # show the swept angle start / current spokes
            lines.line(st['P'], st['P'] + _norm(st['v0']) * 0.85 * L, _with_alpha(HOVER_COLOR, 0.6), on_top=True)

    def _cone(self, lines, base, tip, r, col):
        a = _norm(tip - base)
        u = _norm(np.cross(a, [0, 1, 0] if abs(a[1]) < 0.9 else [1, 0, 0]))
        v = np.cross(a, u)
        ring = [base + r * (math.cos(t) * u + math.sin(t) * v) for t in np.linspace(0, 2 * math.pi, 9)]
        for k in range(8):
            lines.line(ring[k], ring[k + 1], col, on_top=True)
            lines.line(ring[k], tip, col, on_top=True)

    def _cube(self, lines, c, a, r, col):
        u = _norm(np.cross(a, [0, 1, 0] if abs(a[1]) < 0.9 else [1, 0, 0]))
        v = np.cross(a, u)
        corners = [c + r * (sx * a + sy * u + sz * v) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        for i in range(8):
            for j in range(i + 1, 8):
                if bin(i ^ j).count('1') == 1:
                    lines.line(corners[i], corners[j], col, on_top=True)

    def draw_2d(self, ctx, mouse=None):
        d2 = getattr(ctx, 'draw2d', None)
        if d2 is None or not self._handles:
            return
        cam = ctx.camera
        for name, h in self._handles.items():
            if h['kind'] == 'quad':
                xy, _, front = cam.world_to_screen(h['pts'], ctx.width, ctx.height)
                if np.all(front):
                    col = self._color(name, AXIS_COLORS[h['axis']])
                    d2.polygon_fill([tuple(map(float, p)) for p in xy], _with_alpha(col, 0.35))
            elif h['kind'] == 'point':
                xy, _, front = cam.world_to_screen(h['pts'], ctx.width, ctx.height)
                if front[0]:
                    col = self._color(name, CENTER_COLOR)
                    d2.circle(float(xy[0][0]), float(xy[0][1]), h['radius'] - 2, col, thickness=2)
        if self._drag is not None and self.last_delta is not None and self.last_delta.label:
            mx, my = mouse if mouse is not None else (ctx.mouse_x, ctx.mouse_y)
            d2.text(float(mx) + 16, float(my) + 12, self.last_delta.label, (1, 1, 1, 1), 14)


# convenience for callers that need a rotation quaternion from a delta matrix
def delta_rotation(delta: GizmoDelta):
    return mat3_to_quat(delta.matrix[:3, :3])
