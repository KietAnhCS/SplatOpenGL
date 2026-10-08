"""Batched 2D renderer: screen pixels (top-left origin), straight-alpha blending, one texture
(font atlas with a white block for solid shapes), scissor clip stack, sortable layers.

All primitives append textured triangles to the current layer; end() uploads everything and draws
layers in ascending order (layer numbers are arbitrary floats, default 0).
"""

from __future__ import annotations

import ctypes
import math
from array import array

import numpy as np
from OpenGL import GL

from ..core.gl_utils import Program
from .font import WHITE_UV, FontAtlas, shared_atlas

_VS = """#version 330 core
layout(location = 0) in vec2 aPos;
layout(location = 1) in vec2 aUV;
layout(location = 2) in vec4 aCol;
uniform vec2 uScreen;
uniform vec2 uTexSize;
out vec2 vUV;
out vec4 vCol;
void main() {
    vec2 p = aPos / uScreen * 2.0 - 1.0;
    gl_Position = vec4(p.x, -p.y, 0.0, 1.0);
    vUV = aUV / uTexSize;
    vCol = aCol;
}
"""

_FS = """#version 330 core
in vec2 vUV;
in vec4 vCol;
uniform sampler2D uTex;
out vec4 fragColor;
void main() {
    fragColor = vec4(vCol.rgb, vCol.a * texture(uTex, vUV).r);
}
"""

_FLOATS_PER_VERT = 8


# ----------------------------------------------------------------------------- geometry helpers
def polygon_area(pts) -> float:
    """Signed area (shoelace). Positive = counter-clockwise in a y-up frame."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a * 0.5


def triangulate(pts) -> list:
    """Ear-clipping triangulation of a simple (possibly concave) polygon.
    Returns a list of (i, j, k) index triples into pts."""
    n = len(pts)
    if n < 3:
        return []
    idx = list(range(n))
    # drop consecutive duplicates
    idx = [i for k, i in enumerate(idx) if pts[i] != pts[idx[k - 1]]] if n > 3 else idx
    if len(idx) < 3:
        return []
    sign = 1.0 if polygon_area([pts[i] for i in idx]) >= 0 else -1.0

    def cross(a, b, c):
        return ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * sign

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        m = len(idx)
        found = False
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = pts[j]
                if p == a or p == b or p == c:
                    continue
                if inside(p, a, b, c):
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                del idx[k]
                found = True
                break
        if not found:
            # degenerate / self-intersecting: clip the first remaining vertex anyway
            tris.append((idx[-1], idx[0], idx[1]))
            del idx[0]
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


class _Layer:
    __slots__ = ('verts', 'cmds', 'clips')

    def __init__(self):
        self.verts = array('f')
        self.cmds = [[None, 0]]          # [clip rect or None, start vertex]
        self.clips = []


class Draw2D:
    def __init__(self, atlas: FontAtlas | None = None):
        self.font = atlas or shared_atlas()
        self.width, self.height = 1, 1
        self._prog = Program(_VS, _FS)
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        stride = _FLOATS_PER_VERT * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(8))
        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribPointer(2, 4, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(16))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self._tex = GL.glGenTextures(1)
        self._tex_version = -1
        self._tex_shape = None
        self._layers: dict = {}
        self._layer_z = 0
        self._L = None
        self.begin(1, 1)

    # ------------------------------------------------------------------ frame
    def begin(self, width, height):
        self.width, self.height = max(1, int(width)), max(1, int(height))
        self._layers = {}
        self._layer_z = 0
        self._L = self._layers.setdefault(0, _Layer())

    def set_layer(self, z):
        """Selects the draw layer (higher = drawn later / on top). Returns the previous layer."""
        old = self._layer_z
        self._layer_z = z
        L = self._layers.get(z)
        if L is None:
            L = self._layers[z] = _Layer()
        self._L = L
        return old

    @property
    def layer(self):
        return self._layer_z

    def vertex_count(self) -> int:
        return sum(len(L.verts) for L in self._layers.values()) // _FLOATS_PER_VERT

    def _upload_texture(self):
        at = self.font
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._tex)
        if self._tex_version == at.version and self._tex_shape == at.pixels.shape:
            return
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        h, w = at.pixels.shape
        data = np.ascontiguousarray(at.pixels)
        if self._tex_shape != at.pixels.shape:
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_R8, w, h, 0, GL.GL_RED, GL.GL_UNSIGNED_BYTE, data)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        else:
            GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, w, h, GL.GL_RED, GL.GL_UNSIGNED_BYTE, data)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        self._tex_version = at.version
        self._tex_shape = at.pixels.shape

    def end(self):
        """Uploads and draws everything queued since begin(), then clears the queue."""
        draws = []
        chunks = []
        base = 0
        for z in sorted(self._layers):
            L = self._layers[z]
            nv = len(L.verts) // _FLOATS_PER_VERT
            if nv == 0:
                continue
            chunks.append(L.verts)
            cmds = L.cmds
            for i, (clip, start) in enumerate(cmds):
                stop = cmds[i + 1][1] if i + 1 < len(cmds) else nv
                if stop > start:
                    draws.append((clip, base + start, stop - start))
            base += nv
        self.begin(self.width, self.height)
        if not draws:
            return
        data = np.frombuffer(b''.join(c.tobytes() for c in chunks), dtype=np.float32)

        was_blend = GL.glIsEnabled(GL.GL_BLEND)
        was_depth = GL.glIsEnabled(GL.GL_DEPTH_TEST)
        was_cull = GL.glIsEnabled(GL.GL_CULL_FACE)
        was_scissor = GL.glIsEnabled(GL.GL_SCISSOR_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendEquation(GL.GL_FUNC_ADD)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glViewport(0, 0, self.width, self.height)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        self._upload_texture()
        self._prog.use()
        self._prog.set('uScreen', (float(self.width), float(self.height)))
        h, w = self.font.pixels.shape
        self._prog.set('uTexSize', (float(w), float(h)))
        self._prog.set_int('uTex', 0)
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STREAM_DRAW)
        cur_clip = 'none'
        for clip, start, count in draws:
            if clip != cur_clip:
                if clip is None:
                    GL.glDisable(GL.GL_SCISSOR_TEST)
                else:
                    x0, y0, x1, y1 = clip
                    GL.glEnable(GL.GL_SCISSOR_TEST)
                    GL.glScissor(int(x0), int(self.height - y1), max(0, int(x1 - x0)), max(0, int(y1 - y0)))
                cur_clip = clip
            GL.glDrawArrays(GL.GL_TRIANGLES, start, count)
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glUseProgram(0)
        (GL.glEnable if was_scissor else GL.glDisable)(GL.GL_SCISSOR_TEST)
        (GL.glEnable if was_blend else GL.glDisable)(GL.GL_BLEND)
        (GL.glEnable if was_depth else GL.glDisable)(GL.GL_DEPTH_TEST)
        (GL.glEnable if was_cull else GL.glDisable)(GL.GL_CULL_FACE)

    flush = end

    def destroy(self):
        try:
            GL.glDeleteBuffers(1, [self._vbo])
            GL.glDeleteVertexArrays(1, [self._vao])
            GL.glDeleteTextures([self._tex])
            self._prog.delete()
        except Exception:
            pass

    # ------------------------------------------------------------------ clipping
    def _set_clip(self, clip):
        L = self._L
        nv = len(L.verts) // _FLOATS_PER_VERT
        last = L.cmds[-1]
        if last[1] == nv:
            last[0] = clip
        elif last[0] != clip:
            L.cmds.append([clip, nv])

    def push_clip(self, x, y, w, h):
        x0, y0, x1, y1 = math.floor(x), math.floor(y), math.ceil(x + w), math.ceil(y + h)
        L = self._L
        if L.clips:
            px0, py0, px1, py1 = L.clips[-1]
            x0, y0, x1, y1 = max(x0, px0), max(y0, py0), min(x1, px1), min(y1, py1)
        x1, y1 = max(x0, x1), max(y0, y1)
        c = (x0, y0, x1, y1)
        L.clips.append(c)
        self._set_clip(c)

    def pop_clip(self):
        L = self._L
        if L.clips:
            L.clips.pop()
        self._set_clip(L.clips[-1] if L.clips else None)

    def current_clip(self):
        """(x0, y0, x1, y1) of the active clip on the current layer, or None."""
        return self._L.clips[-1] if self._L.clips else None

    # ------------------------------------------------------------------ primitives
    def _quad(self, x0, y0, x1, y1, u0, v0, u1, v1, c):
        r, g, b, a = c
        self._L.verts.extend((x0, y0, u0, v0, r, g, b, a, x1, y0, u1, v0, r, g, b, a,
                              x1, y1, u1, v1, r, g, b, a, x0, y0, u0, v0, r, g, b, a,
                              x1, y1, u1, v1, r, g, b, a, x0, y1, u0, v1, r, g, b, a))

    def _tri(self, x0, y0, x1, y1, x2, y2, c0, c1=None, c2=None):
        u, v = WHITE_UV
        c1 = c1 or c0
        c2 = c2 or c0
        self._L.verts.extend((x0, y0, u, v, *c0, x1, y1, u, v, *c1, x2, y2, u, v, *c2))

    def triangle(self, x0, y0, x1, y1, x2, y2, color):
        self._tri(x0, y0, x1, y1, x2, y2, _c(color))

    def rect(self, x, y, w, h, color, radius=0):
        if w <= 0 or h <= 0:
            return
        c = _c(color)
        if radius > 0.5:
            self._convex_fill(_rounded_pts(x, y, w, h, radius), c)
            return
        u, v = WHITE_UV
        self._quad(x, y, x + w, y + h, u, v, u, v, c)

    def rect_multicolor(self, x, y, w, h, c_tl, c_tr, c_br, c_bl):
        """Rectangle with per-corner colours (gradients)."""
        a, b, c, d = _c(c_tl), _c(c_tr), _c(c_br), _c(c_bl)
        self._tri(x, y, x + w, y, x + w, y + h, a, b, c)
        self._tri(x, y, x + w, y + h, x, y + h, a, c, d)

    def rect_outline(self, x, y, w, h, color, thickness=1, radius=0):
        if w <= 0 or h <= 0:
            return
        if radius > 0.5:
            t = thickness * 0.5
            self.polyline(_rounded_pts(x + t, y + t, w - 2 * t, h - 2 * t, max(0.0, radius - t)),
                          color, thickness, closed=True)
            return
        t = min(thickness, w * 0.5, h * 0.5)
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y + t, t, h - 2 * t, color)
        self.rect(x + w - t, y + t, t, h - 2 * t, color)

    def line(self, x0, y0, x1, y1, color, thickness=1):
        self.polyline([(x0, y0), (x1, y1)], color, thickness)

    def polyline(self, pts, color, thickness=1, closed=False):
        """Anti-aliased thick polyline (core quad + 1px alpha fringe, mitered joins)."""
        pts = [(float(p[0]), float(p[1])) for p in pts]
        n = len(pts)
        if n < 2:
            return
        c = _c(color)
        if thickness < 1.0:
            c = (c[0], c[1], c[2], c[3] * max(thickness, 0.0))
            thickness = 1.0
        c0 = (c[0], c[1], c[2], 0.0)
        nseg = n if closed else n - 1
        # segment normals
        segn = []
        last = (0.0, 1.0)
        for i in range(nseg):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            ln = math.hypot(dx, dy)
            if ln > 1e-9:
                last = (-dy / ln, dx / ln)
            segn.append(last)
        # per-point miter normals
        pn = []
        for i in range(n):
            if closed:
                na, nb = segn[i - 1], segn[i % nseg]
            else:
                na = segn[max(0, i - 1)]
                nb = segn[min(i, nseg - 1)]
            mx, my = (na[0] + nb[0]) * 0.5, (na[1] + nb[1]) * 0.5
            d2 = mx * mx + my * my
            if d2 > 1e-6:
                inv = min(1.0 / d2, 4.0)
                mx, my = mx * inv, my * inv
            else:
                mx, my = na
            pn.append((mx, my))
        core = (thickness - 1.0) * 0.5
        outer = core + 1.0
        for i in range(nseg):
            j = (i + 1) % n
            ax, ay = pts[i]
            bx, by = pts[j]
            anx, any_ = pn[i]
            bnx, bny = pn[j]
            # left fringe
            a_in = (ax + anx * core, ay + any_ * core)
            b_in = (bx + bnx * core, by + bny * core)
            a_out = (ax + anx * outer, ay + any_ * outer)
            b_out = (bx + bnx * outer, by + bny * outer)
            a_in2 = (ax - anx * core, ay - any_ * core)
            b_in2 = (bx - bnx * core, by - bny * core)
            a_out2 = (ax - anx * outer, ay - any_ * outer)
            b_out2 = (bx - bnx * outer, by - bny * outer)
            self._tri(*a_out, *b_out, *b_in, c0, c0, c)
            self._tri(*a_out, *b_in, *a_in, c0, c, c)
            if core > 0:
                self._tri(*a_in, *b_in, *b_in2, c, c, c)
                self._tri(*a_in, *b_in2, *a_in2, c, c, c)
            self._tri(*a_in2, *b_in2, *b_out2, c, c, c0)
            self._tri(*a_in2, *b_out2, *a_out2, c, c0, c0)

    def _convex_fill(self, pts, c):
        if len(pts) < 3:
            return
        x0, y0 = pts[0]
        for i in range(1, len(pts) - 1):
            self._tri(x0, y0, *pts[i], *pts[i + 1], c)

    def polygon_fill(self, pts, color):
        pts = [(float(p[0]), float(p[1])) for p in pts]
        c = _c(color)
        for i, j, k in triangulate(pts):
            self._tri(*pts[i], *pts[j], *pts[k], c)

    def circle(self, cx, cy, r, color, thickness=1, segments=48):
        segments = max(3, int(segments))
        pts = [(cx + r * math.cos(2 * math.pi * i / segments), cy + r * math.sin(2 * math.pi * i / segments))
               for i in range(segments)]
        self.polyline(pts, color, thickness, closed=True)

    def circle_fill(self, cx, cy, r, color, segments=48):
        if r <= 0:
            return
        segments = max(3, int(segments))
        c = _c(color)
        c0 = (c[0], c[1], c[2], 0.0)
        ri, ro = max(r - 0.5, 0.0), r + 0.5
        prev_i = prev_o = None
        for i in range(segments + 1):
            a = 2 * math.pi * (i % segments) / segments
            ca, sa = math.cos(a), math.sin(a)
            pi = (cx + ri * ca, cy + ri * sa)
            po = (cx + ro * ca, cy + ro * sa)
            if prev_i is not None:
                self._tri(cx, cy, *prev_i, *pi, c)
                self._tri(*prev_i, *prev_o, *po, c, c0, c0)
                self._tri(*prev_i, *po, *pi, c, c0, c)
            prev_i, prev_o = pi, po

    # ------------------------------------------------------------------ text
    def face(self, size=14, bold=False, style=None):
        return self.font.face(size, style or ('bold' if bold else 'regular'))

    def text(self, x, y, s, color=(1, 1, 1, 1), size=14, bold=False, style=None) -> float:
        """Draws s with its line box top-left at (x, y). Returns the advance width (widest line)."""
        if not s:
            return 0.0
        f = self.face(size, bold, style)
        c = _c(color)
        verts = self._L.verts
        r, g_, b, a = c
        x0 = round(x)
        yy = round(y)
        lh = f.line_height
        clip = self._L.clips[-1] if self._L.clips else None
        pen = 0.0
        best = 0.0
        glyphs = f.glyphs
        skip = clip is not None and (yy > clip[3] or yy + lh < clip[1])
        for ch in s:
            if ch == '\n':
                best = max(best, pen)
                pen = 0.0
                yy += lh
                skip = clip is not None and (yy > clip[3] or yy + lh < clip[1])
                continue
            gl = glyphs.get(ch) or f.bake(ch)
            if gl.w and not skip:
                gx0 = x0 + round(pen) + gl.ox
                gy0 = yy + gl.oy
                gx1, gy1 = gx0 + gl.w, gy0 + gl.h
                u0, v0 = gl.u, gl.v
                u1, v1 = u0 + gl.w, v0 + gl.h
                verts.extend((gx0, gy0, u0, v0, r, g_, b, a, gx1, gy0, u1, v0, r, g_, b, a,
                              gx1, gy1, u1, v1, r, g_, b, a, gx0, gy0, u0, v0, r, g_, b, a,
                              gx1, gy1, u1, v1, r, g_, b, a, gx0, gy1, u0, v1, r, g_, b, a))
            pen += gl.advance
        return max(best, pen)

    def text_size(self, s, size=14, bold=False, style=None) -> tuple:
        return self.font.text_size(s, size, style or ('bold' if bold else 'regular'))

    def text_width(self, s, size=14, bold=False) -> float:
        return self.face(size, bold).width(s)

    def line_height(self, size=14, bold=False) -> float:
        return float(self.face(size, bold).line_height)

    def text_centered(self, cx, cy, s, color=(1, 1, 1, 1), size=14, bold=False) -> float:
        """Draws s centred (horizontally and on cap height) on (cx, cy)."""
        f = self.face(size, bold)
        w = f.width(s)
        return self.text(cx - w * 0.5, cy - f.mid, s, color, size, bold)


def _c(color) -> tuple:
    if len(color) == 3:
        return (float(color[0]), float(color[1]), float(color[2]), 1.0)
    return (float(color[0]), float(color[1]), float(color[2]), float(color[3]))


def _rounded_pts(x, y, w, h, r):
    r = max(0.0, min(r, w * 0.5, h * 0.5))
    if r <= 0.5:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts = []
    seg = max(2, int(r * 0.6) + 2)
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
