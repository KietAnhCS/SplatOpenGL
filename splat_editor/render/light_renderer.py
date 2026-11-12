"""Vẽ mặt trời, các khối đèn (quả cầu phát sáng) và đom đóm bay quanh đèn (hạt, T5).

Vẽ sau các gaussian, không thử độ sâu (gaussian không ghi độ sâu): luôn thấy được để dễ đặt / chỉnh đèn.
Đom đóm tính vị trí hoàn toàn trong vertex shader theo thời gian (không có dữ liệu hạt trên CPU).
"""

"""
renderer = LightRenderer()                                       # cần ngữ cảnh GL
renderer.draw(view, projection, lighting, time_seconds)         # sau khi vẽ gaussian
"""

import numpy as np
from OpenGL import GL

from .shader import ShaderProgram

FIREFLIES_PER_LIGHT = 24


class LightRenderer:
    def __init__(self):
        self.gizmo = ShaderProgram.load("light_gizmo")
        self.firefly = ShaderProgram.load("firefly")
        corners = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)       # triangle strip
        self.vbo = GL.glGenBuffers(1)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, corners.nbytes, corners, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glBindVertexArray(0)

    def draw(self, view, projection, lighting, time, unit, physics=None):
        """unit: chiều cao người chơi (đơn vị cảnh) để chọn kích thước quả cầu."""
        if not lighting.enabled:
            return
        view = np.asarray(view, np.float32)
        projection = np.asarray(projection, np.float32)
        cam_pos = -view[:3, :3].T @ view[:3, 3]
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindVertexArray(self.vao)

        if lighting.sun_on:
            direction = lighting.sun_direction()
            above = float(np.clip((direction[1] + 0.1) / 0.2, 0.0, 1.0))
            if above > 0:
                color = np.array(lighting.sun_color_for_gizmo())
                center = lighting.center + direction * lighting.radius * 6.0
                radius = lighting.radius * 0.45
                if physics is not None:       # gaussian không ghi độ sâu: tự kiểm tra cảnh có che mặt trời không
                    right, up = view[0, :3], view[1, :3]
                    targets = [center]
                    for k in range(8):       # vòng quanh đĩa mặt trời: nhiều tia để tường thưa không làm lọt sáng
                        a = k * np.pi / 4
                        targets.append(center + (right * np.cos(a) + up * np.sin(a)) * radius * 0.8)
                    seen = physics.visibility(cam_pos, targets)
                    # chỉ hiện khi đa số tia thấy được; bị che phần lớn thì tắt hẳn (không để mờ mờ)
                    t = float(np.clip((seen - 0.5) / 0.35, 0.0, 1.0))
                    above *= t * t * (3.0 - 2.0 * t)
                if above > 0:
                    self._sphere(view, projection, center, radius, 2.6, color, above)

        visible = {}
        for light in lighting.lights:
            base = np.array(light.color)
            glow = 1.0 if light.on else 0.0
            distance = float(np.linalg.norm(light.position - cam_pos))
            radius = max(unit * 0.12, distance * 0.012)       # luôn đủ lớn để nhìn thấy
            seen = 1.0
            if physics is not None:       # khối đèn cũng bị cảnh che (bỏ qua vài ô cuối: đèn nằm sát sàn)
                right, up = view[0, :3], view[1, :3]
                targets = [light.position, light.position + right * radius, light.position - right * radius,
                           light.position + up * radius, light.position - up * radius]
                seen = physics.visibility(cam_pos, targets, skip_end=1.5)
            visible[id(light)] = seen > 0
            if seen > 0:
                self._sphere(view, projection, light.position, radius, 3.2, base / base.max(),
                             (0.15 + 0.85 * glow) * seen)
                if lighting.lights.index(light) == lighting.picked:      # viền sáng quanh đèn đang chọn
                    self._sphere(view, projection, light.position, radius * 1.9, 1.6,
                                 np.array([0.4, 0.8, 1.0]), 0.55 * seen)

        if lighting.fireflies:
            GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
            s = self.firefly
            s.use()
            s.set_mat4('uView', view)
            s.set_mat4('uProj', projection)
            s.set_float('uTime', time)
            s.set_float('uPixel', 4.0)
            for light in lighting.lights:
                if not light.on or not visible.get(id(light), True):
                    continue
                s.set_vec3('uCenter', light.position)
                s.set_float('uRadius', light.range * 0.25)
                s.set_vec3('uColor', np.array(light.color) / max(light.color))
                GL.glDrawArrays(GL.GL_POINTS, 0, FIREFLIES_PER_LIGHT)
            GL.glDisable(GL.GL_PROGRAM_POINT_SIZE)
        GL.glBindVertexArray(0)

    def _sphere(self, view, projection, center, radius, halo, color, brightness):
        s = self.gizmo
        s.use()
        s.set_mat4('uView', view)
        s.set_mat4('uProj', projection)
        s.set_vec3('uCenter', center)
        s.set_float('uRadius', radius)
        s.set_float('uHalo', halo)
        s.set_vec3('uColor', color)
        s.set_float('uBrightness', brightness)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
