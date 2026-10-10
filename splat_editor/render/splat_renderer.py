"""Gaussian splat renderer (OpenGL 3.3 core).

Port of supersplat's projected-splat renderer to a classic vertex-shader EWA splatter:

* Per layer, per-gaussian data lives in textures read with texelFetch(index):
  centre (RGB32F), 3D covariance (2 x RGB32F, local space, unit splat size), base colour +
  opacity (RGBA32F), SH rest coefficients (RGBA16F, packed k-major, `T` texels / gaussian)
  and the state byte (R8UI).
* One instanced 4-vertex triangle strip per gaussian; the per-instance attribute is the
  gaussian index in back-to-front order (uint, divisor 1) produced by `sorter.py`.
* Vertex shader: EWA projection (J * W * Sigma * W^T * J^T, +0.3 px low-pass), eigen
  decomposition, quad axes = 2*sqrt(2*lambda) (sqrt(8) sigma) clamped to
  min(1024, viewport), cull behind / off screen, SH (bands <= settings.sh_bands) evaluated
  with the view direction in the layer's local frame, colour grade, state colours.
* Fragment shader: normalised gaussian falloff exp(-4 r^2), premultiplied output
  (blend ONE, ONE_MINUS_SRC_ALPHA), no depth writes. Rings mode draws the ellipse edge.
* Centres: GL_POINTS of the selected layer (not locked / deleted), coloured by state.
"""

from __future__ import annotations

import ctypes

import numpy as np
from OpenGL import GL

from ..core.gl_utils import Program, ShaderError
from ..core.math3d import quat_to_mat3
from ..core.splat import DELETED, SH_C0, sigmoid
from .sorter import AsyncSorter, depth_axis, sort_back_to_front

TEX_W = 1024                 # texels per row (gaussians per row)
SYNC_SORT_LIMIT = 150_000    # layers with at most this many live gaussians are sorted synchronously
SH_TEXELS = {0: 0, 1: 3, 2: 6, 3: 12}   # RGBA texels needed for the first SH_COEFFS(bands) coefficients

IDENTITY_GRADE = """
vec4 applyColorGrade(vec4 rgba) { return rgba; }
"""

# ----------------------------------------------------------------------------- shaders

_COMMON = """
uniform sampler2D uCenter;
uniform sampler2D uCovA;     // c00 c01 c02
uniform sampler2D uCovB;     // c11 c12 c22
uniform sampler2D uColor;    // base rgb, opacity
uniform usampler2D uState;
uniform sampler2D uSH;
uniform int uTexW;
uniform int uSHTexels;       // texels per gaussian in uSH
uniform int uBands;          // bands evaluated (<= data bands)

uniform mat4 uModelView;
uniform mat4 uProj;
uniform mat3 uViewToLocalDir;  // view-space direction -> layer local direction
uniform int uOrtho;
uniform vec2 uViewport;
uniform float uSplatScale;
uniform int uPreviewOn;
uniform mat4 uPreview;         // local-space matrix applied to selected gaussians

layout(location = 0) in uint aIndex;

const vec4 DISCARD_POS = vec4(0.0, 0.0, 2.0, 1.0);

ivec2 texCoord(int idx) { return ivec2(idx % uTexW, idx / uTexW); }

vec3 evalSH(int idx, vec3 d) {
    int row = idx / uTexW;
    int base = (idx % uTexW) * uSHTexels;
    vec4 t0 = texelFetch(uSH, ivec2(base + 0, row), 0);
    vec4 t1 = texelFetch(uSH, ivec2(base + 1, row), 0);
    vec4 t2 = texelFetch(uSH, ivec2(base + 2, row), 0);
    vec3 c0 = t0.xyz;
    vec3 c1 = vec3(t0.w, t1.xy);
    vec3 c2 = vec3(t1.zw, t2.x);
    float x = d.x, y = d.y, z = d.z;
    vec3 result = 0.4886025119029199 * (-c0 * y + c1 * z - c2 * x);
    if (uBands > 1) {
        vec3 c3 = t2.yzw;
        vec4 t3 = texelFetch(uSH, ivec2(base + 3, row), 0);
        vec4 t4 = texelFetch(uSH, ivec2(base + 4, row), 0);
        vec4 t5 = texelFetch(uSH, ivec2(base + 5, row), 0);
        vec3 c4 = t3.xyz;
        vec3 c5 = vec3(t3.w, t4.xy);
        vec3 c6 = vec3(t4.zw, t5.x);
        vec3 c7 = t5.yzw;
        float xx = x * x, yy = y * y, zz = z * z, xy = x * y, yz = y * z, xz = x * z;
        result += c3 * (1.0925484305920792 * xy)
                + c4 * (-1.0925484305920792 * yz)
                + c5 * (0.31539156525252005 * (2.0 * zz - xx - yy))
                + c6 * (-1.0925484305920792 * xz)
                + c7 * (0.5462742152960396 * (xx - yy));
        if (uBands > 2) {
            vec4 t6 = texelFetch(uSH, ivec2(base + 6, row), 0);
            vec4 t7 = texelFetch(uSH, ivec2(base + 7, row), 0);
            vec4 t8 = texelFetch(uSH, ivec2(base + 8, row), 0);
            vec4 t9 = texelFetch(uSH, ivec2(base + 9, row), 0);
            vec4 t10 = texelFetch(uSH, ivec2(base + 10, row), 0);
            vec4 t11 = texelFetch(uSH, ivec2(base + 11, row), 0);
            vec3 c8 = t6.xyz;
            vec3 c9 = vec3(t6.w, t7.xy);
            vec3 c10 = vec3(t7.zw, t8.x);
            vec3 c11 = t8.yzw;
            vec3 c12 = t9.xyz;
            vec3 c13 = vec3(t9.w, t10.xy);
            vec3 c14 = vec3(t10.zw, t11.x);
            result += c8 * (-0.5900435899266435 * y * (3.0 * xx - yy))
                    + c9 * (2.890611442640554 * xy * z)
                    + c10 * (-0.4570457994644658 * y * (4.0 * zz - xx - yy))
                    + c11 * (0.3731763325901154 * z * (2.0 * zz - 3.0 * xx - 3.0 * yy))
                    + c12 * (-0.4570457994644658 * x * (4.0 * zz - xx - yy))
                    + c13 * (1.445305721320277 * z * (xx - yy))
                    + c14 * (-0.5900435899266435 * x * (xx - 3.0 * yy));
        }
    }
    return result;
}
"""

_SPLAT_VS = """#version 330 core
%(common)s
%(grade)s
uniform int uEditTarget;       // tints apply (selected layer in edit view)
uniform vec4 uSelectedColor;   // rgb, a = blend weight
uniform vec4 uUnselectedColor; // rgb, a = blend weight
uniform vec4 uLockedColor;     // multiplies locked gaussians
uniform int uShowGaussians;
uniform int uRings;            // rings mode for this layer
uniform float uRingBlend;      // ring colour: own colour -> unselected colour

out vec2 vUV;
flat out vec4 vColor;
flat out vec3 vRingColor;
flat out int vFlags;           // 1 = ring eligible, 2 = show gaussian

void main() {
    vec2 corner = vec2(float(gl_VertexID & 1), float((gl_VertexID >> 1) & 1)) * 2.0 - 1.0;
    vUV = corner;
    vFlags = 0;
    vColor = vec4(0.0);
    vRingColor = vec3(0.0);

    int idx = int(aIndex);
    ivec2 uv = texCoord(idx);
    uint state = texelFetch(uState, uv, 0).r;
    if ((state & 4u) != 0u) { gl_Position = DISCARD_POS; return; }
    bool locked = (state & 2u) != 0u;
    bool selected = (state & 1u) != 0u && !locked;

    vec3 center = texelFetch(uCenter, uv, 0).xyz;
    vec3 ca = texelFetch(uCovA, uv, 0).xyz;
    vec3 cb = texelFetch(uCovB, uv, 0).xyz;
    mat3 Vrk = mat3(ca.x, ca.y, ca.z,
                    ca.y, cb.x, cb.y,
                    ca.z, cb.y, cb.z) * (uSplatScale * uSplatScale);
    if (uPreviewOn != 0 && selected) {
        center = (uPreview * vec4(center, 1.0)).xyz;
        mat3 L = mat3(uPreview);
        Vrk = L * Vrk * transpose(L);
    }

    vec4 viewPos = uModelView * vec4(center, 1.0);
    vec4 clip = uProj * viewPos;
    if (clip.w <= 0.0 || clip.z < -clip.w || clip.z > clip.w) { gl_Position = DISCARD_POS; return; }

    float fx = uProj[0][0] * uViewport.x * 0.5;
    float fy = uProj[1][1] * uViewport.y * 0.5;
    mat3 J;
    if (uOrtho != 0) {
        J = mat3(fx, 0.0, 0.0,  0.0, fy, 0.0,  0.0, 0.0, 0.0);
    } else {
        float z = -viewPos.z;
        float limx = 1.3 / uProj[0][0];
        float limy = 1.3 / uProj[1][1];
        float tx = clamp(viewPos.x / z, -limx, limx) * z;
        float ty = clamp(viewPos.y / z, -limy, limy) * z;
        J = mat3(fx / z, 0.0, 0.0,
                 0.0, fy / z, 0.0,
                 fx * tx / (z * z), fy * ty / (z * z), 0.0);
    }
    mat3 T = J * mat3(uModelView);
    mat3 cov = T * Vrk * transpose(T);
    float c00 = cov[0][0] + 0.3;
    float c01 = cov[0][1];
    float c11 = cov[1][1] + 0.3;
    float det = c00 * c11 - c01 * c01;
    if (det <= 0.0) { gl_Position = DISCARD_POS; return; }

    float mid = 0.5 * (c00 + c11);
    float radius = length(vec2(0.5 * (c00 - c11), c01));
    float lambda1 = mid + radius;
    float lambda2 = max(mid - radius, 0.1);
    vec2 eig = vec2(c01, lambda1 - c00);
    float elen = length(eig);
    vec2 dir = elen > 1e-9 ? eig / elen : vec2(1.0, 0.0);
    float maxRadius = min(1024.0, min(uViewport.x, uViewport.y));
    float len1 = 2.0 * sqrt(2.0 * lambda1);
    float rscale = min(1.0, maxRadius / len1);
    vec2 axis1 = len1 * rscale * dir;
    vec2 axis2 = 2.0 * sqrt(2.0 * lambda2) * rscale * vec2(dir.y, -dir.x);

    vec2 ndc = clip.xy / clip.w;
    vec2 extent = abs(axis1) + abs(axis2);
    vec2 cpix = (ndc * 0.5 + 0.5) * uViewport;
    if (cpix.x + extent.x < 0.0 || cpix.x - extent.x > uViewport.x ||
        cpix.y + extent.y < 0.0 || cpix.y - extent.y > uViewport.y) {
        gl_Position = DISCARD_POS; return;
    }

    // colour
    vec4 col = texelFetch(uColor, uv, 0);
    if (uBands > 0) {
        vec3 vdir = uOrtho != 0 ? vec3(0.0, 0.0, -1.0) : normalize(viewPos.xyz);
        col.rgb += evalSH(idx, normalize(uViewToLocalDir * vdir));
    }
    col = applyColorGrade(col);
    col = vec4(max(col.rgb, vec3(0.0)), clamp(col.a, 0.0, 1.0));
    if (locked) col *= uLockedColor;

    bool target = uEditTarget != 0 && !locked;
    vec3 fill = col.rgb;
    if (target) {
        fill = mix(fill, uUnselectedColor.rgb, uUnselectedColor.a);
        if (selected) fill = mix(fill, uSelectedColor.rgb, uSelectedColor.a);
    }
    bool ringEligible = uRings != 0 && !locked;
    bool showGaussian = uShowGaussians != 0 || (selected && target);
    if ((col.a <= 0.0 || !showGaussian) && !ringEligible) { gl_Position = DISCARD_POS; return; }

    vec3 ring = mix(col.rgb, uUnselectedColor.rgb, uRingBlend);
    if (selected) ring = mix(ring, uSelectedColor.rgb, uSelectedColor.a);

    vColor = vec4(fill, col.a);
    vRingColor = ring;
    vFlags = (ringEligible ? 1 : 0) | (showGaussian ? 2 : 0);

    vec2 pixOff = corner.x * axis1 + corner.y * axis2;
    gl_Position = clip + vec4(pixOff * 2.0 / uViewport * clip.w, 0.0, 0.0);
}
"""

_SPLAT_FS = """#version 330 core
in vec2 vUV;
flat in vec4 vColor;
flat in vec3 vRingColor;
flat in int vFlags;
uniform float uRingSize;
out vec4 fragColor;

const float EXP4 = 0.01831563888873418;   // exp(-4)
const float INV_EXP4 = 1.0 / (1.0 - EXP4);

void main() {
    float r = dot(vUV, vUV);
    if (r > 1.0) discard;
    float norm = (exp(-4.0 * r) - EXP4) * INV_EXP4;
    float alpha = (vFlags & 2) != 0 ? norm * vColor.a : 0.0;
    vec3 color = vColor.rgb;
    if ((vFlags & 1) != 0) {
        if (r >= 1.0 - uRingSize) {
            alpha = 0.6;
            color = vRingColor;
        } else {
            alpha = max(0.05, alpha);
        }
    }
    if (alpha < 1.0 / 255.0) discard;
    fragColor = vec4(color * alpha, alpha);
}
"""

_CENTERS_VS = """#version 330 core
%(common)s
uniform vec4 uSelectedColor;
uniform vec4 uUnselectedColor;
uniform float uCenterBlend;    // 0 = own colour, 1 = unselected colour
uniform float uPointSize;
flat out vec4 vColor;

void main() {
    int idx = int(aIndex);
    ivec2 uv = texCoord(idx);
    uint state = texelFetch(uState, uv, 0).r;
    gl_PointSize = uPointSize;
    vColor = vec4(0.0);
    if ((state & 6u) != 0u) { gl_Position = DISCARD_POS; return; }
    bool selected = (state & 1u) != 0u;
    vec3 center = texelFetch(uCenter, uv, 0).xyz;
    if (uPreviewOn != 0 && selected) center = (uPreview * vec4(center, 1.0)).xyz;
    gl_Position = uProj * (uModelView * vec4(center, 1.0));
    vec3 own = clamp(texelFetch(uColor, uv, 0).rgb, 0.0, 1.0);
    vec3 c = mix(own, uUnselectedColor.rgb, uCenterBlend);
    if (selected) c = uSelectedColor.rgb;
    vColor = vec4(c, 1.0);
}
"""

_CENTERS_FS = """#version 330 core
flat in vec4 vColor;
out vec4 fragColor;
void main() { fragColor = vColor; }
"""


def _load_grade():
    try:
        from ..data.color_grade import GLSL_COLOR_GRADE, grade_uniforms
        return GLSL_COLOR_GRADE, grade_uniforms
    except Exception:
        return None, None


# ----------------------------------------------------------------------------- per-layer GPU data

def compute_covariances(data) -> tuple[np.ndarray, np.ndarray]:
    """(N,3),(N,3) float32: (c00,c01,c02), (c11,c12,c22) of the local 3D covariance R S S R^T."""
    if data.count == 0:
        z = np.zeros((0, 3), np.float32)
        return z, z
    r = quat_to_mat3(data.rotations.astype(np.float64))          # (N,3,3)
    s = np.exp(data.scales.astype(np.float64))                   # (N,3)
    m = r * s[:, None, :]                                        # R @ diag(s)
    cov = np.einsum('nij,nkj->nik', m, m)
    a = np.stack([cov[:, 0, 0], cov[:, 0, 1], cov[:, 0, 2]], axis=1).astype(np.float32)
    b = np.stack([cov[:, 1, 1], cov[:, 1, 2], cov[:, 2, 2]], axis=1).astype(np.float32)
    return a, b


def _pad_rows(arr: np.ndarray, rows: int, width: int) -> np.ndarray:
    """(N, C) -> (rows, width, C) zero padded."""
    n = arr.shape[0]
    c = arr.shape[1] if arr.ndim > 1 else 1
    out = np.zeros((rows * width, c), dtype=arr.dtype)
    out[:n] = arr.reshape(n, c)
    return out.reshape(rows, width, c)


def _make_tex(internal, fmt, typ, w, h, data):
    tex = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
    for p in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
        GL.glTexParameteri(GL.GL_TEXTURE_2D, p, GL.GL_NEAREST)
    for p in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T):
        GL.glTexParameteri(GL.GL_TEXTURE_2D, p, GL.GL_CLAMP_TO_EDGE)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, w, h, 0, fmt, typ, np.ascontiguousarray(data))
    return tex


class _Layer:
    """GPU resources + sort state of one Splat."""

    def __init__(self, splat):
        self.splat = splat
        self.data_version = None
        self.state_version = None
        self.textures: dict[str, int] = {}
        self.n = 0
        self.rows = 1
        self.data_bands = 0
        self.sh_texels = 0
        self.positions = None
        self.alive = None              # uint32 indices of non-deleted gaussians
        self.set_version = 0           # bumps when the alive set or positions change
        self.sorted_set_version = -1
        self.sorted_axis = None
        self.requested = None          # (set_version, axis) of the last request
        self.vbo = GL.glGenBuffers(1)
        self.vbo_size = 0
        self.count = 0                 # number of indices in vbo
        self.vao = GL.glGenVertexArrays(1)
        self.vao_pts = GL.glGenVertexArrays(1)
        for vao, div in ((self.vao, 1), (self.vao_pts, 0)):
            GL.glBindVertexArray(vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
            GL.glEnableVertexAttribArray(0)
            GL.glVertexAttribIPointer(0, 1, GL.GL_UNSIGNED_INT, 4, ctypes.c_void_p(0))
            GL.glVertexAttribDivisor(0, div)
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    # -- uploads
    def _free_textures(self):
        if self.textures:
            GL.glDeleteTextures(list(self.textures.values()))
        self.textures = {}

    def upload_data(self):
        sp = self.splat
        d = sp.data
        self._free_textures()
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        n = d.count
        self.n = n
        self.rows = rows = max(1, (n + TEX_W - 1) // TEX_W)
        W = TEX_W
        self.positions = d.positions
        ca, cb = compute_covariances(d)
        color = np.empty((n, 4), np.float32)
        color[:, :3] = 0.5 + SH_C0 * d.sh0
        color[:, 3] = sigmoid(d.opacities)
        t = self.textures
        t['center'] = _make_tex(GL.GL_RGB32F, GL.GL_RGB, GL.GL_FLOAT, W, rows, _pad_rows(d.positions, rows, W))
        t['covA'] = _make_tex(GL.GL_RGB32F, GL.GL_RGB, GL.GL_FLOAT, W, rows, _pad_rows(ca, rows, W))
        t['covB'] = _make_tex(GL.GL_RGB32F, GL.GL_RGB, GL.GL_FLOAT, W, rows, _pad_rows(cb, rows, W))
        t['color'] = _make_tex(GL.GL_RGBA32F, GL.GL_RGBA, GL.GL_FLOAT, W, rows, _pad_rows(color, rows, W))
        self.data_bands = d.sh_bands if n else 0
        if self.data_bands:
            m = d.sh_rest.shape[1]
            tex_per = (3 * m + 3) // 4
            flat = np.zeros((n, tex_per * 4), np.float16)
            flat[:, :3 * m] = d.sh_rest.reshape(n, 3 * m)
            self.sh_texels = tex_per
            t['sh'] = _make_tex(GL.GL_RGBA16F, GL.GL_RGBA, GL.GL_HALF_FLOAT, W * tex_per, rows,
                                _pad_rows(flat.reshape(n * tex_per, 4), rows, W * tex_per) if n else
                                np.zeros((rows, W * tex_per, 4), np.float16))
        else:
            self.sh_texels = 0
            t['sh'] = _make_tex(GL.GL_RGBA16F, GL.GL_RGBA, GL.GL_HALF_FLOAT, 1, 1, np.zeros(4, np.float16))
        t['state'] = _make_tex(GL.GL_R8UI, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_BYTE, W, rows,
                               _pad_rows(sp.state, rows, W))
        self.data_version = sp.data_version
        self.state_version = sp.state_version
        self.alive = None              # positions changed: always re-sort
        self._update_alive()
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)

    def upload_state(self):
        sp = self.splat
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textures['state'])
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, TEX_W, self.rows, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_BYTE,
                           np.ascontiguousarray(_pad_rows(sp.state, self.rows, TEX_W)))
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        self.state_version = sp.state_version
        self._update_alive()

    def _update_alive(self):
        """Recompute the non-deleted index list; bump set_version only if it changed (forces a re-sort)."""
        alive = np.flatnonzero((self.splat.state & DELETED) == 0).astype(np.uint32)
        if self.alive is None or not np.array_equal(alive, self.alive):
            self.alive = alive
            self.set_version += 1

    def upload_order(self, order: np.ndarray):
        order = np.ascontiguousarray(order, np.uint32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        nbytes = order.nbytes
        if nbytes > self.vbo_size or nbytes < self.vbo_size // 4:
            GL.glBufferData(GL.GL_ARRAY_BUFFER, max(nbytes, 4), order if nbytes else None, GL.GL_DYNAMIC_DRAW)
            self.vbo_size = max(nbytes, 4)
        elif nbytes:
            GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, nbytes, order)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self.count = len(order)

    def destroy(self):
        self._free_textures()
        if self.vbo:
            GL.glDeleteBuffers(1, [self.vbo])
            GL.glDeleteVertexArrays(2, [self.vao, self.vao_pts])
            self.vbo = 0


# ----------------------------------------------------------------------------- renderer

class SplatRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.layers: dict[int, _Layer] = {}
        self.sorter = AsyncSorter()
        self.sync_sort_limit = SYNC_SORT_LIMIT
        grade_glsl, self._grade_uniforms = _load_grade()
        common = _COMMON
        try:
            if grade_glsl is None:
                raise ShaderError("no colour grade module")
            self.prog = Program(_SPLAT_VS % dict(common=common, grade=grade_glsl), _SPLAT_FS)
        except ShaderError as e:
            if grade_glsl is not None:
                print("SplatRenderer: colour grade shader failed, using identity:", e)
            self._grade_uniforms = None
            self.prog = Program(_SPLAT_VS % dict(common=common, grade=IDENTITY_GRADE), _SPLAT_FS)
        self.prog_centers = Program(_CENTERS_VS % dict(common=common), _CENTERS_FS)
        for p in (self.prog, self.prog_centers):
            p.use()
            for unit, name in enumerate(('uCenter', 'uCovA', 'uCovB', 'uColor', 'uState', 'uSH')):
                p.set_int(name, unit)
        GL.glUseProgram(0)
        self._handles = [scene.events.on('scene.elementRemoved', self._on_removed),
                         scene.events.on('scene.cleared', self._prune)]

    # -- lifecycle
    def _on_removed(self, splat):
        layer = self.layers.pop(id(splat), None)
        if layer is not None:
            self.sorter.discard(id(splat))
            layer.destroy()

    def _prune(self, *_):
        live = {id(s) for s in self.scene.splats}
        for k in [k for k in self.layers if k not in live]:
            self.sorter.discard(k)
            self.layers.pop(k).destroy()

    def needs_redraw(self) -> bool:
        return self.sorter.pending()

    def destroy(self):
        for h in self._handles:
            h.off()
        self.sorter.shutdown()
        for layer in self.layers.values():
            layer.destroy()
        self.layers.clear()
        self.prog.delete()
        self.prog_centers.delete()

    # -- per frame
    def _sync_layer(self, splat) -> _Layer:
        layer = self.layers.get(id(splat))
        if layer is None:
            layer = self.layers[id(splat)] = _Layer(splat)
        if layer.data_version != splat.data_version or layer.n != splat.data.count:
            self.sorter.discard(id(splat))
            layer.upload_data()
            layer.sorted_set_version = -1
            layer.upload_order(layer.alive)      # unsorted until the first sort lands
        elif layer.state_version != splat.state_version:
            layer.upload_state()
        return layer

    def _update_sort(self, layer: _Layer, axis: np.ndarray):
        key = id(layer.splat)
        # collect finished async results
        res = self.sorter.poll(key)
        if res is not None:
            (set_version, data_version, req_axis), order = res
            if data_version == layer.data_version:
                layer.upload_order(order)
                layer.sorted_set_version = set_version
                layer.sorted_axis = req_axis
        n_alive = len(layer.alive)
        # is a (new) sort needed?
        cur = layer.requested
        same_axis = cur is not None and float(np.dot(cur[1], axis)) > 1.0 - 1e-7
        if cur is not None and cur[0] == layer.set_version and same_axis:
            return
        if n_alive <= self.sync_sort_limit:
            order = sort_back_to_front(layer.positions, layer.alive, axis)
            layer.upload_order(order)
            layer.sorted_set_version = layer.set_version
            layer.sorted_axis = axis
        else:
            self.sorter.request(key, layer.positions, layer.alive, axis,
                                (layer.set_version, layer.data_version, axis))
        layer.requested = (layer.set_version, axis)

    def draw(self, ctx) -> None:
        scene = self.scene
        settings = scene.settings
        self._prune()
        view = np.asarray(ctx.view, np.float64)
        proj = np.asarray(ctx.proj, np.float64)
        w, h = max(int(ctx.width), 1), max(int(ctx.height), 1)
        cam_pos = np.linalg.inv(view)[:3, 3]
        ortho = abs(proj[3, 3] - 1.0) < 1e-6 and abs(proj[3, 2]) < 1e-9

        layers = []
        for sp in scene.splats:
            if not sp.visible:
                continue
            layer = self._sync_layer(sp)
            if layer.n == 0 or len(layer.alive) == 0:
                continue
            model = sp.world_matrix()
            axis = depth_axis(view, model)
            nrm = np.linalg.norm(axis)
            axis = axis / nrm if nrm > 0 else np.array([0.0, 0.0, 1.0])
            self._update_sort(layer, axis)
            c = sp.world_bound().center
            dist = float(np.linalg.norm(np.asarray(c) - cam_pos)) if c is not None else 0.0
            layers.append((dist, sp, layer, model))
        if not layers:
            return
        layers.sort(key=lambda t: -t[0])     # far layers first

        edit_view = bool(settings.edit_view)
        selected_splat = scene.selected_splat

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_CULL_FACE)

        if settings.show_splats or not edit_view or settings.rings_mode:
            p = self.prog
            p.use()
            self._common_uniforms(p, settings, proj, ortho, w, h)
            p.set('uLockedColor', tuple(settings.locked_color))
            p.set('uSelectedColor', tuple(settings.selected_color))
            ucol = settings.unselected_color
            p.set('uUnselectedColor', (ucol[0], ucol[1], ucol[2], float(settings.extra.get('splats_color_blend', 0.0))))
            p.set('uRingSize', float(settings.extra.get('ring_size', 4)) * 0.01)
            p.set('uRingBlend', float(settings.extra.get('rings_color_blend', 0.0)))
            for _, sp, layer, model in layers:
                if layer.count == 0:
                    continue
                target = edit_view and sp is selected_splat
                p.set_int('uEditTarget', 1 if target else 0)
                p.set_int('uShowGaussians', 1 if (settings.show_splats or not edit_view) else 0)
                p.set_int('uRings', 1 if (target and settings.rings_mode) else 0)
                if not (settings.show_splats or not edit_view) and not target:
                    continue
                self._layer_uniforms(p, sp, layer, view, model, settings)
                if self._grade_uniforms is not None:
                    for k, v in self._grade_uniforms(sp.color).items():
                        p.set(k, v)
                GL.glBindVertexArray(layer.vao)
                GL.glDrawArraysInstanced(GL.GL_TRIANGLE_STRIP, 0, 4, layer.count)

        if edit_view and settings.show_centers and selected_splat is not None:
            entry = next((t for t in layers if t[1] is selected_splat), None)
            if entry is not None and entry[2].count:
                _, sp, layer, model = entry
                p = self.prog_centers
                p.use()
                self._common_uniforms(p, settings, proj, ortho, w, h)
                p.set('uSelectedColor', tuple(settings.selected_color))
                p.set('uUnselectedColor', tuple(settings.unselected_color))
                p.set('uCenterBlend', float(settings.extra.get('centers_color_blend', 1.0)))
                p.set('uPointSize', float(settings.center_point_size))
                self._layer_uniforms(p, sp, layer, view, model, settings)
                GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
                GL.glBindVertexArray(layer.vao_pts)
                GL.glDrawArrays(GL.GL_POINTS, 0, layer.count)
                GL.glDisable(GL.GL_PROGRAM_POINT_SIZE)

        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

    # -- uniform helpers
    @staticmethod
    def _common_uniforms(p, settings, proj, ortho, w, h):
        p.set_mat4('uProj', proj)
        p.set_int('uOrtho', 1 if ortho else 0)
        p.set('uViewport', (float(w), float(h)))
        p.set('uSplatScale', float(settings.splat_scale))
        p.set_int('uTexW', TEX_W)

    @staticmethod
    def _layer_uniforms(p, sp, layer, view, model, settings):
        mv = view @ model
        p.set_mat4('uModelView', mv)
        # view-space direction -> local direction: R_model^T @ R_view^T (rotation parts only)
        rv = view[:3, :3]
        rm = quat_to_mat3(sp.rotation)
        p.set_mat3('uViewToLocalDir', rm.T @ rv.T)
        bands = min(int(settings.sh_bands), layer.data_bands)
        p.set_int('uBands', bands)
        p.set_int('uSHTexels', max(layer.sh_texels, 1))
        prev = sp.selection_preview
        p.set_int('uPreviewOn', 1 if prev is not None else 0)
        if prev is not None:
            p.set_mat4('uPreview', prev)
        t = layer.textures
        for unit, name in enumerate(('center', 'covA', 'covB', 'color', 'state', 'sh')):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(GL.GL_TEXTURE_2D, t[name])
