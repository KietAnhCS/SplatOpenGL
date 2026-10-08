"""Infinite grid — port of supersplat infinite-grid.ts / shaders/infinite-grid-shader.ts.

Full-screen pass: each pixel's view ray is intersected with the enabled grid planes (default XZ,
y=0), three decade levels of anti-aliased lines fade in by pixel footprint, X (red) / Z (blue) axis
lines are drawn with exact screen-space distance, and gl_FragDepth is written (dithered by line
coverage) so later depth-tested geometry interacts with the grid lines.
"""

from __future__ import annotations

import numpy as np
from OpenGL import GL

VERTEX_SHADER = """#version 330 core
uniform mat4 uInvViewProj;
out vec3 worldNear;
out vec3 worldFar;
void main() {
    // full screen triangle
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)) * 2.0 - 1.0;
    gl_Position = vec4(p, 0.0, 1.0);
    vec4 n = uInvViewProj * vec4(p, -1.0, 1.0);
    vec4 f = uInvViewProj * vec4(p, 1.0, 1.0);
    worldNear = n.xyz / n.w;
    worldFar = f.xyz / f.w;
}
"""

FRAGMENT_SHADER = """#version 330 core
uniform mat4 matrix_viewProjection;
uniform vec3 grid_view_position;
uniform vec2 grid_viewport_size;
// bit i enables plane i: 0 = x (the yz plane), 1 = y (xz), 2 = z (xy)
uniform int planeMask;

in vec3 worldNear;
in vec3 worldFar;
out vec4 fragColor;

const vec3 NORMALS[3] = vec3[3](vec3(1.0, 0.0, 0.0), vec3(0.0, 1.0, 0.0), vec3(0.0, 0.0, 1.0));
const vec3 COLORS[3] = vec3[3](vec3(1.0, 0.2, 0.2), vec3(0.2, 1.0, 0.2), vec3(0.2, 0.2, 1.0));
const int AXIS0[3] = int[3](1, 0, 0);
const int AXIS1[3] = int[3](2, 2, 1);

const float MIN_CELL_PIXELS = 7.0;
const float OCCLUDE_CELL_PIXELS = 8.0;

struct GridSample {
    vec3 color;     // premultiplied
    float alpha;
    float depthAlpha;
};

float intersectPlane(vec3 pos, vec3 dir, vec3 normal) {
    float d = dot(dir, normal);
    if (abs(d) < 1e-6) return -1.0;
    return -dot(pos, normal) / d;
}

vec3 hitDerivative(vec3 nearP, vec3 dNear, vec3 dir, vec3 dDir, vec3 normal) {
    float denom = dot(dir, normal);
    if (abs(denom) < 1e-12) denom = 1e-12;
    float num = -dot(nearP, normal);
    float t = num / denom;
    float dt = (-dot(dNear, normal) * denom - num * dot(dDir, normal)) / (denom * denom);
    return dNear + dDir * t + dir * dt;
}

float pristineGrid(vec2 uv, vec2 ddxValue, vec2 ddyValue, vec2 lineWidth) {
    vec2 uvDeriv = vec2(length(vec2(ddxValue.x, ddyValue.x)), length(vec2(ddxValue.y, ddyValue.y)));
    bvec2 invertLine = greaterThan(lineWidth, vec2(0.5));
    vec2 targetWidth = mix(lineWidth, vec2(1.0) - lineWidth, invertLine);
    vec2 drawWidth = clamp(targetWidth, uvDeriv, vec2(0.5));
    vec2 lineAA = uvDeriv * 1.5;
    vec2 gridUv = abs(fract(uv) * 2.0 - vec2(1.0));
    gridUv = mix(vec2(1.0) - gridUv, gridUv, invertLine);
    vec2 grid = vec2(1.0) - smoothstep(drawWidth - lineAA, drawWidth + lineAA, gridUv);
    grid *= clamp(targetWidth / drawWidth, vec2(0.0), vec2(1.0));
    grid = mix(grid, targetWidth, clamp(uvDeriv * 2.0 - vec2(1.0), vec2(0.0), vec2(1.0)));
    grid = mix(grid, vec2(1.0) - grid, invertLine);
    return mix(grid.x, 1.0, grid.y);
}

float log10f(float x) { return log2(x) * 0.30102999566; }

float calcDepth(vec3 position) {
    vec4 projected = matrix_viewProjection * vec4(position, 1.0);
    return clamp(projected.z / projected.w * 0.5 + 0.5, 0.0, 1.0);
}

// dithered depth write (interleaved gradient noise instead of the blue noise texture)
bool writeDepth(float alpha) {
    float n = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    return alpha > n;
}

vec2 gridPosition(vec3 position, int plane) {
    if (plane == 0) return position.yz;
    if (plane == 1) return position.xz;
    return position.xy;
}

void over(inout GridSample dst, vec3 color, float alpha) {
    float remaining = 1.0 - dst.alpha;
    dst.color += color * alpha * remaining;
    dst.alpha += alpha * remaining;
}

// homogeneous framebuffer pixel coordinates (y up, matching gl_FragCoord)
vec3 pixelPoint(vec4 clip) {
    return vec3((clip.x + clip.w) * 0.5 * grid_viewport_size.x, (clip.y + clip.w) * 0.5 * grid_viewport_size.y, clip.w);
}

float axisPixelDistance(vec3 dir) {
    vec3 p0 = pixelPoint(matrix_viewProjection * vec4(0.0, 0.0, 0.0, 1.0));
    vec3 p1 = pixelPoint(matrix_viewProjection * vec4(dir, 0.0));
    vec3 l = cross(p0, p1);
    float len = length(l.xy);
    if (len < 1e-6) return 1e6;
    return abs(dot(l, vec3(gl_FragCoord.xy, 1.0))) / len;
}

GridSample shadePlane(vec2 position, vec2 ddxValue, vec2 ddyValue, int plane, float distance) {
    GridSample result = GridSample(vec3(0.0), 0.0, 0.0);

    vec2 pixel = max(vec2(length(vec2(ddxValue.x, ddyValue.x)), length(vec2(ddxValue.y, ddyValue.y))), vec2(1e-8));
    float footprint = max(pixel.x, pixel.y);

    float sum = dot(ddxValue, ddxValue) + dot(ddyValue, ddyValue);
    float det = abs(ddxValue.x * ddyValue.y - ddxValue.y * ddyValue.x);
    float sMax2 = 0.5 * (sum + sqrt(max(sum * sum - 4.0 * det * det, 0.0)));
    float grazing = smoothstep(0.005, 0.02, det / max(sMax2, 1e-16));

    float horizon = 1.0 - smoothstep(0.2, 0.6, footprint / max(distance, 1e-12));

    float base = ceil(log10f(footprint * MIN_CELL_PIXELS));

    vec2 axisCoverage = clamp(vec2(1.5) - vec2(axisPixelDistance(NORMALS[AXIS0[plane]]),
                                               axisPixelDistance(NORMALS[AXIS1[plane]])), vec2(0.0), vec2(1.0));
    float axisAlpha = max(axisCoverage.x, axisCoverage.y) * horizon;
    vec3 axisColor = COLORS[AXIS0[plane]];
    if (axisCoverage.y > axisCoverage.x) axisColor = COLORS[AXIS1[plane]];
    if (axisCoverage.x > 0.5 && axisCoverage.y > 0.5) axisColor = vec3(1.0);
    over(result, axisColor, axisAlpha);
    result.depthAlpha = axisAlpha;

    for (int i = 2; i >= 0; i--) {
        float cell = pow(10.0, base + float(i));
        float s = log10f(cell / (footprint * MIN_CELL_PIXELS));
        float minor = smoothstep(0.0, 1.0, s);
        float sOcclude = s - log10f(OCCLUDE_CELL_PIXELS / MIN_CELL_PIXELS);
        float occlude = smoothstep(0.0, 1.0, sOcclude);
        float major = smoothstep(1.0, 2.0, sOcclude);
        float line = pristineGrid(position / cell, ddxValue / cell, ddyValue / cell, pixel / cell);
        vec3 levelColor = mix(vec3(0.4), vec3(0.65), major);
        over(result, levelColor, line * minor * horizon);
        result.depthAlpha = max(result.depthAlpha, line * occlude * grazing);
    }
    return result;
}

void main() {
    vec3 rayOrigin = worldNear;
    vec3 rayDirection = worldFar - worldNear;

    vec3 dNearX = dFdx(worldNear);
    vec3 dNearY = dFdy(worldNear);
    vec3 dDirX = dFdx(worldFar) - dNearX;
    vec3 dDirY = dFdy(worldFar) - dNearY;

    float t[3];
    vec3 worldPosition[3];
    vec2 position[3];
    vec2 derivativeX[3];
    vec2 derivativeY[3];
    for (int i = 0; i < 3; i++) {
        t[i] = intersectPlane(rayOrigin, rayDirection, NORMALS[i]);
        worldPosition[i] = rayOrigin + rayDirection * max(t[i], 0.0);
        position[i] = gridPosition(worldPosition[i], i);
        derivativeX[i] = gridPosition(hitDerivative(rayOrigin, dNearX, rayDirection, dDirX, NORMALS[i]), i);
        derivativeY[i] = gridPosition(hitDerivative(rayOrigin, dNearY, rayDirection, dDirY, NORMALS[i]), i);
    }

    int order[3] = int[3](0, 1, 2);
    if (t[order[0]] > t[order[1]]) { int tmp = order[0]; order[0] = order[1]; order[1] = tmp; }
    if (t[order[1]] > t[order[2]]) { int tmp = order[1]; order[1] = order[2]; order[2] = tmp; }
    if (t[order[0]] > t[order[1]]) { int tmp = order[0]; order[0] = order[1]; order[1] = tmp; }

    GridSample result = GridSample(vec3(0.0), 0.0, 0.0);
    float depth = 1.0;
    bool depthWritten = false;
    for (int k = 0; k < 3; k++) {
        int i = order[k];
        if ((planeMask & (1 << i)) == 0 || t[i] <= 0.0) continue;
        bool behind = false;
        for (int j = 0; j < 3; j++) {
            if (j != i && (planeMask & (1 << j)) != 0 &&
                dot(worldPosition[i], NORMALS[j]) * dot(grid_view_position, NORMALS[j]) < 0.0) {
                behind = true;
            }
        }
        if (behind) continue;
        GridSample s = shadePlane(position[i], derivativeX[i], derivativeY[i], i,
                                  length(worldPosition[i] - grid_view_position));
        over(result, s.color / max(s.alpha, 1e-6), s.alpha);
        if (!depthWritten && writeDepth(s.depthAlpha)) {
            depth = calcDepth(worldPosition[i]);
            depthWritten = true;
        }
    }

    if (result.alpha < 1.0 / 255.0) discard;

    fragColor = vec4(result.color / result.alpha, result.alpha);
    gl_FragDepth = depth;
}
"""

# plane name -> shader bit (0: x (yz), 1: y (xz), 2: z (xy))
PLANE_INDICES = {'yz': 0, 'xz': 1, 'xy': 2}


def plane_mask(planes) -> int:
    m = 0
    for p in planes:
        m |= 1 << PLANE_INDICES[p]
    return m


class InfiniteGrid:
    """Draw with draw(ctx) after clearing and before the splats.

    Honours ctx.scene.settings.show_grid and settings.edit_view (overlays hidden in clean view).
    Planes: self.planes (default ['xz']) or settings.extra['grid_planes'] if present.
    """

    def __init__(self, planes=('xz',)):
        self.planes = list(planes)
        self.visible = True
        self._program = None
        self._vao = 0

    def _ensure_gl(self):
        if self._program is None:
            from ..core.gl_utils import Program
            self._program = Program(VERTEX_SHADER, FRAGMENT_SHADER)
            self._vao = GL.glGenVertexArrays(1)

    def _camera_position(self, ctx):
        cam = getattr(ctx, 'camera', None)
        pos = getattr(cam, 'position', None) if cam is not None else None
        if pos is not None:
            pos = pos() if callable(pos) else pos
            return np.asarray(pos, dtype=np.float64)
        return np.linalg.inv(np.asarray(ctx.view, dtype=np.float64))[:3, 3]

    def draw(self, ctx):
        settings = getattr(getattr(ctx, 'scene', None), 'settings', None)
        planes = self.planes
        if settings is not None:
            if not settings.show_grid or not settings.edit_view:
                return
            planes = settings.extra.get('grid_planes', planes)
        if not self.visible or not planes:
            return
        self._ensure_gl()

        vp = np.asarray(ctx.view_proj, dtype=np.float64)
        try:
            inv_vp = np.linalg.inv(vp)
        except np.linalg.LinAlgError:
            return

        p = self._program
        p.use()
        p.set_mat4('uInvViewProj', inv_vp)
        p.set_mat4('matrix_viewProjection', vp)
        p.set('grid_view_position', tuple(self._camera_position(ctx)))
        p.set('grid_viewport_size', (float(ctx.width), float(ctx.height)))
        p.set_int('planeMask', plane_mask(planes))

        depth_was = GL.glIsEnabled(GL.GL_DEPTH_TEST)
        blend_was = GL.glIsEnabled(GL.GL_BLEND)
        cull_was = GL.glIsEnabled(GL.GL_CULL_FACE)
        depth_func_was = int(np.asarray(GL.glGetIntegerv(GL.GL_DEPTH_FUNC)).reshape(-1)[0])
        depth_mask_was = GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendEquation(GL.GL_FUNC_ADD)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_DEPTH_TEST)       # needed for depth writes
        GL.glDepthFunc(GL.GL_ALWAYS)
        GL.glDepthMask(GL.GL_TRUE)

        GL.glBindVertexArray(self._vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)

        GL.glDepthFunc(depth_func_was)
        GL.glDepthMask(bool(depth_mask_was))
        (GL.glEnable if depth_was else GL.glDisable)(GL.GL_DEPTH_TEST)
        (GL.glEnable if blend_was else GL.glDisable)(GL.GL_BLEND)
        (GL.glEnable if cull_was else GL.glDisable)(GL.GL_CULL_FACE)

    def destroy(self):
        if self._program is not None:
            self._program.delete()
            GL.glDeleteVertexArrays(1, [self._vao])
            self._program = None
