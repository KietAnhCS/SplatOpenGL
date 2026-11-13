"""Vẽ nhân vật người chơi (zombie skin 64x64) khi xem góc nhìn thứ ba (F5).

Port từ voxel-engine (PlayerMesh.java): sáu hộp (đầu, thân, hai tay, hai chân), mỗi hộp là một khối riêng
để xoay quanh khớp, cộng lớp áo ngoài phồng nhẹ (mũ, áo, tay áo, quần) bỏ điểm ảnh trong suốt.
Mesh dựng theo điểm ảnh skin; kích thước thật do ma trận model (có scale) quyết định.
Gaussian không ghi độ sâu nên nhân vật tự có độ sâu riêng: xoá độ sâu rồi mới vẽ.
"""

"""
renderer = AvatarRenderer()                                    # cần ngữ cảnh GL
renderer.draw(view, projection, limb_matrices, brightness, light_dir)
"""

import ctypes
import struct
import zlib
from pathlib import Path

import numpy as np
from OpenGL import GL

from ..core.avatar_pose import LIMBS
from .shader import ShaderProgram

SKIN_PATH = Path(__file__).parent / "textures" / "skinzom.png"
LIMB_INFLATE = 0.25      # lớp áo của thân / tay / chân phồng hơn lớp nền nửa điểm ảnh (như Minecraft)
HAT_INFLATE = 0.5        # mũ trên đầu phồng gấp đôi
SKIN_SIZE = 64.0         # ảnh skin 64x64 điểm ảnh (chia toạ độ pixel cho số này ra UV 0..1)

# 4 góc mỗi mặt (dấu +/-1 trên x, y, z), thứ tự: trái-trên, phải-trên, phải-dưới, trái-dưới của ô skin.
# Mặt: trước (+Z), sau (-Z), phải (+X), trái (-X), trên (+Y), dưới (-Y).
_FACES = (
    ((1, 1, 1), (-1, 1, 1), (-1, -1, 1), (1, -1, 1)),
    ((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)),
    ((1, 1, 1), (1, 1, -1), (1, -1, -1), (1, -1, 1)),
    ((-1, 1, -1), (-1, 1, 1), (-1, -1, 1), (-1, -1, -1)),
    ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)),
    ((1, -1, 1), (-1, -1, 1), (-1, -1, -1), (1, -1, -1)),
)
_NORMALS = ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))

# uv nền, tâm (x, y, z), kích thước (w, h, d), uv lớp áo, độ phồng
_LIMB_SPECS = {
    "legLeft": ((16, 48), (-2, 6, 0), (4, 12, 4), (0, 48), LIMB_INFLATE),
    "legRight": ((0, 16), (2, 6, 0), (4, 12, 4), (0, 32), LIMB_INFLATE),
    "body": ((16, 16), (0, 18, 0), (8, 12, 4), (16, 32), LIMB_INFLATE),
    "armLeft": ((32, 48), (-6, 18, 0), (4, 12, 4), (48, 48), LIMB_INFLATE),
    "armRight": ((40, 16), (6, 18, 0), (4, 12, 4), (40, 32), LIMB_INFLATE),
    "head": ((0, 0), (0, 28, 0), (8, 8, 8), (32, 0), HAT_INFLATE),
}


def load_png(path):
    """Đọc PNG 8 bit RGB / RGBA không xen kẽ -> mảng (h, w, 4) uint8 (không cần thư viện ảnh)."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: không phải file PNG")
    pos, idat, header = 8, [], None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        pos += 12 + length
    width, height, depth, color, _, _, interlace = header
    if depth != 8 or color not in (2, 6) or interlace:
        raise ValueError(f"{path}: chỉ hỗ trợ PNG 8 bit RGB / RGBA không xen kẽ")
    channels = 4 if color == 6 else 3
    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    rows = np.zeros((height, stride), np.int32)
    previous = np.zeros(stride, np.int32)
    for y in range(height):
        base = y * (stride + 1)
        kind = raw[base]
        line = np.frombuffer(raw, np.uint8, stride, base + 1).astype(np.int32)
        if kind == 0:
            current = line
        elif kind == 2:
            current = (line + previous) & 255
        else:                                    # 1 (Sub), 3 (Average), 4 (Paeth): phụ thuộc điểm ảnh bên trái
            current = line.copy()
            for i in range(stride):
                left = int(current[i - channels]) if i >= channels else 0
                up = int(previous[i])
                if kind == 1:
                    predictor = left
                elif kind == 3:
                    predictor = (left + up) >> 1
                else:
                    corner = int(previous[i - channels]) if i >= channels else 0
                    p = left + up - corner
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                    predictor = left if pa <= pb and pa <= pc else up if pb <= pc else corner
                current[i] = (int(line[i]) + predictor) & 255
        rows[y] = current
        previous = current
    image = rows.reshape(height, width, channels).astype(np.uint8)
    if channels == 3:
        image = np.concatenate([image, np.full((height, width, 1), 255, np.uint8)], axis=2)
    return image


def _uv_region(face, ox, oy, w, h, d):
    """Ô skin của một mặt hộp theo kiểu trải chữ thập của Minecraft: (x, y, rộng, cao).

    (ox, oy): góc trên trái của hộp trong ảnh skin; w, h, d: rộng, cao, sâu của hộp.
    Thứ tự `face`: 0 trước (+Z), 1 sau (-Z), 2 phải (+X), 3 trái (-X), 4 trên (+Y), 5 dưới (-Y).
    """
    return ((ox + d, oy + d, w, h),              # 0: +Z
            (ox + 2 * d + w, oy + d, w, h),      # 1: -Z
            (ox, oy + d, d, h),                  # 2: +X
            (ox + d + w, oy + d, d, h),          # 3: -X
            (ox + d, oy, w, d),                  # 4: +Y
            (ox + d + w, oy, w, d))[face]        # 5: -Y


def _box(ox, oy, centre, size, inflate):
    """Đỉnh (x, y, z, nx, ny, nz, u, v) của một hộp: 6 mặt x 4 đỉnh."""
    (cx, cy, cz), (w, h, d) = centre, size
    hx, hy, hz = w / 2 + inflate, h / 2 + inflate, d / 2 + inflate    # nửa kích thước (đã phồng)
    vertices = []
    for face in range(6):
        rx, ry, rw, rh = _uv_region(face, ox, oy, w, h, d)
        uvs = ((rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh))   # 4 góc ô skin
        # sx, sy, sz là dấu +1/-1: đỉnh = tâm +/- nửa kích thước theo từng trục
        for (sx, sy, sz), (u, v) in zip(_FACES[face], uvs):
            vertices.append((cx + sx * hx, cy + sy * hy, cz + sz * hz, *_NORMALS[face], u / SKIN_SIZE, v / SKIN_SIZE))
    return vertices


def build_mesh():
    """(đỉnh float32 (n, 8), chỉ số uint32, [(offset byte, số chỉ số)] cho từng khối theo LIMBS)."""
    vertices, indices, ranges = [], [], []
    for name in LIMBS:
        base_uv, centre, size, overlay_uv, inflate = _LIMB_SPECS[name]
        start = len(indices)
        for uv, grow in ((base_uv, 0.0), (overlay_uv, inflate)):
            first = len(vertices)
            vertices += _box(uv[0], uv[1], centre, size, grow)
            for quad in range(6):
                q = first + quad * 4
                indices += [q, q + 1, q + 2, q, q + 2, q + 3]
        ranges.append((start * 4, len(indices) - start))
    return np.array(vertices, np.float32), np.array(indices, np.uint32), ranges


class AvatarRenderer:
    def __init__(self):
        self.shader = ShaderProgram.load("avatar")
        vertices, indices, self.ranges = build_mesh()
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL.GL_STATIC_DRAW)
        self.ebo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)
        for location, size, offset in ((0, 3, 0), (1, 3, 12), (2, 2, 24)):
            GL.glEnableVertexAttribArray(location)
            GL.glVertexAttribPointer(location, size, GL.GL_FLOAT, GL.GL_FALSE, 32, ctypes.c_void_p(offset))
        GL.glBindVertexArray(0)

        image = np.ascontiguousarray(load_png(SKIN_PATH))
        self.texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, image.shape[1], image.shape[0], 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image)
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST), (GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE), (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def draw(self, view, projection, matrices, brightness=(1.0, 1.0, 1.0), light_dir=(0.4, 0.8, 0.45)):
        """matrices: 6 ma trận model theo LIMBS (core.avatar_pose.limb_matrices)."""
        s = self.shader
        s.use()
        s.set_mat4('uView', view)
        s.set_mat4('uProj', projection)
        s.set_vec3('uLight', light_dir)
        s.set_vec3('uBright', brightness)
        s.set_int('uSkin', 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LESS)
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glBindVertexArray(self.vao)
        for matrix, (offset, count) in zip(matrices, self.ranges):
            s.set_mat4('uModel', matrix)
            GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT, ctypes.c_void_p(offset))
        GL.glBindVertexArray(0)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
