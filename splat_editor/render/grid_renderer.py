"""Lưới sàn vô hạn trên mặt phẳng y = const (giống SuperSplat / Blender).

Vẽ một tam giác phủ kín màn hình. Với mỗi pixel, fragment shader bắn một tia từ camera,
tìm giao điểm với mặt phẳng sàn rồi tô đường lưới tại đó. Kích thước ô lưới tự đổi
theo khoảng cách camera (1, 10, 100 ...), chuyển mượt giữa các mức.
Trục X tô đỏ, trục Z tô xanh dương.
"""

import math

from OpenGL import GL

from .shader import ShaderProgram


class GridRenderer:
    def __init__(self):
        self.shader = ShaderProgram.load("grid")
        self.vao = GL.glGenVertexArrays(1)
        self.height = 0.0

    def draw(self, view, projection, camera_distance):
        cam_rot = view[:3, :3].T                      # nghịch đảo của ma trận xoay = chuyển vị
        cam_pos = -cam_rot @ view[:3, 3]
        # kích thước ô theo độ cao camera so với sàn và khoảng cách tới target
        size = max(abs(cam_pos[1] - self.height), camera_distance * 0.5, 1e-4)
        level = math.log10(size)
        cell = 10.0 ** (math.floor(level) - 1)

        s = self.shader
        s.use()
        s.set_mat3('uCamRot', cam_rot)
        s.set_vec3('uCamPos', cam_pos)
        s.set_vec2('uProjScale', projection[0, 0], projection[1, 1])
        s.set_float('uHeight', self.height)
        s.set_float('uCell', cell)
        s.set_float('uBlend', level - math.floor(level))
        s.set_float('uFade', size * 4.0)

        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)
