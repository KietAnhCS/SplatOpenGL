"""World-space line batcher (immediate mode) — replacement for PlayCanvas app.drawLine.

Lines are queued each frame (line/lines/box/circle) and drawn by flush(view_proj) as GL_LINES with
per-vertex colour. Two queues: depth-tested lines first, then 'on_top' lines (depth test disabled).
"""

from __future__ import annotations

import ctypes
import math

import numpy as np
from OpenGL import GL

from ..core.math3d import AABB, transform_points

_VS = """#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec4 aColor;
uniform mat4 uViewProj;
out vec4 vColor;
void main() {
    vColor = aColor;
    gl_Position = uViewProj * vec4(aPos, 1.0);
}
"""

_FS = """#version 330 core
in vec4 vColor;
out vec4 fragColor;
void main() {
    fragColor = vColor;
}
"""

# the 12 edges of a box whose corners are ordered like AABB.corners():
# index = ix*4 + iy*2 + iz
BOX_EDGES = np.array([
    (0, 4), (1, 5), (2, 6), (3, 7),     # along x
    (0, 2), (1, 3), (4, 6), (5, 7),     # along y
    (0, 1), (2, 3), (4, 5), (6, 7),     # along z
], dtype=np.int32)


def _box_corners(aabb_or_corners, matrix=None) -> np.ndarray:
    if isinstance(aabb_or_corners, AABB):
        if aabb_or_corners.empty:
            return np.zeros((0, 3))
        c = aabb_or_corners.corners()
    else:
        c = np.asarray(aabb_or_corners, dtype=np.float64).reshape(8, 3)
    if matrix is not None:
        c = transform_points(np.asarray(matrix, dtype=np.float64), c)
    return c


class Lines3D:
    """World space line batcher. Needs a current GL context for flush() (queueing does not)."""

    def __init__(self):
        self._queues = {False: ([], []), True: ([], [])}   # on_top -> (point arrays, colour arrays)
        self._program = None
        self._vao = 0
        self._vbo = 0
        self._capacity = 0
        self.line_width = 1.0

    # ------------------------------------------------------------------ queueing
    def _push(self, pts, color, on_top):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 3)
        if len(pts) < 2:
            return
        if len(pts) % 2:
            pts = pts[:-1]
        col = np.asarray(color, dtype=np.float32).reshape(-1)
        if col.size == 3:
            col = np.append(col, 1.0).astype(np.float32)
        if col.size == 4:
            cols = np.broadcast_to(col, (len(pts), 4))
        else:   # per-vertex colours
            cols = col.reshape(-1, 4)[:len(pts)]
        p, c = self._queues[bool(on_top)]
        p.append(pts)
        c.append(np.ascontiguousarray(cols, dtype=np.float32))

    def line(self, p0, p1, color, on_top=False):
        self._push(np.array([p0, p1], dtype=np.float32), color, on_top)

    def lines(self, pts, color, on_top=False):
        """pts (2K,3): segment pairs. color: rgba or per-vertex (2K,4)."""
        self._push(pts, color, on_top)

    def box(self, aabb_or_corners, matrix=None, color=(1, 1, 1, 1), on_top=False):
        """Wireframe box from an AABB or 8 corners (ordered like AABB.corners()), optionally transformed."""
        c = _box_corners(aabb_or_corners, matrix)
        if len(c) != 8:
            return
        self._push(c[BOX_EDGES.reshape(-1)], color, on_top)

    def circle(self, center, normal, radius, color, segments=64, on_top=False):
        center = np.asarray(center, dtype=np.float64)
        n = np.asarray(normal, dtype=np.float64)
        n = n / max(np.linalg.norm(n), 1e-30)
        a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(n, a)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        t = np.linspace(0, 2 * math.pi, segments + 1)
        ring = center + radius * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * v)
        pts = np.empty((segments * 2, 3))
        pts[0::2] = ring[:-1]
        pts[1::2] = ring[1:]
        self._push(pts, color, on_top)

    def clear(self):
        for p, c in self._queues.values():
            p.clear()
            c.clear()

    def count(self, on_top=None) -> int:
        """Number of queued segments (both queues when on_top is None)."""
        keys = (False, True) if on_top is None else (bool(on_top),)
        return sum(len(a) for k in keys for a in self._queues[k][0]) // 2

    # ------------------------------------------------------------------ GL
    def _ensure_gl(self):
        if self._program is not None:
            return
        from ..core.gl_utils import Program
        self._program = Program(_VS, _FS)
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        stride = 7 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 4, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(12))
        GL.glBindVertexArray(0)

    def flush(self, view_proj):
        """Draw queued lines (depth-tested first, then on-top) and clear the queues."""
        groups = []
        for on_top in (False, True):
            p, c = self._queues[on_top]
            if p:
                groups.append((on_top, np.concatenate(p), np.concatenate(c)))
        self.clear()
        if not groups:
            return
        self._ensure_gl()

        data = np.ascontiguousarray(np.concatenate(
            [np.hstack([g[1], g[2]]) for g in groups]), dtype=np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        if data.nbytes > self._capacity:
            self._capacity = max(data.nbytes, self._capacity * 2, 64 * 1024)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, self._capacity, None, GL.GL_STREAM_DRAW)
        GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, data.nbytes, data)

        depth_was = GL.glIsEnabled(GL.GL_DEPTH_TEST)
        blend_was = GL.glIsEnabled(GL.GL_BLEND)
        depth_mask_was = GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)
        depth_func_was = GL.glGetIntegerv(GL.GL_DEPTH_FUNC)

        self._program.use()
        self._program.set_mat4('uViewProj', view_proj)
        GL.glBindVertexArray(self._vao)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDepthMask(GL.GL_FALSE)
        try:
            GL.glLineWidth(self.line_width)   # core profile only guarantees 1.0
        except Exception:
            pass
        first = 0
        for on_top, pts, _ in groups:
            if on_top:
                GL.glDisable(GL.GL_DEPTH_TEST)
            else:
                GL.glEnable(GL.GL_DEPTH_TEST)
                GL.glDepthFunc(GL.GL_LEQUAL)
            GL.glDrawArrays(GL.GL_LINES, first, len(pts))
            first += len(pts)
        GL.glBindVertexArray(0)

        # restore state
        GL.glDepthMask(bool(depth_mask_was))
        GL.glDepthFunc(int(np.asarray(depth_func_was).reshape(-1)[0]))
        (GL.glEnable if depth_was else GL.glDisable)(GL.GL_DEPTH_TEST)
        (GL.glEnable if blend_was else GL.glDisable)(GL.GL_BLEND)

    def destroy(self):
        if self._program is not None:
            self._program.delete()
            GL.glDeleteBuffers(1, [self._vbo])
            GL.glDeleteVertexArrays(1, [self._vao])
            self._program = None
