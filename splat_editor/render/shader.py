"""Chương trình shader OpenGL (vertex + fragment), nạp từ thư mục shaders/."""

"""
# Sau khi đã tạo Window (cần ngữ cảnh GL)
prog = ShaderProgram.load("splat")        # đọc shaders/splat.vert + splat.frag

while not win.should_close:
    Window.poll_events()
    prog.use()                             # kích hoạt trước
    prog.set_mat4("u_view", view_matrix)   # numpy 4x4
    prog.set_mat4("u_proj", proj_matrix)
    prog.set_vec2("u_viewport", w, h)
    prog.set_float("u_scale", 1.0)
    # ... glBindVertexArray, glDrawArraysInstanced ...
    win.swap_buffers()

# Chế độ transform feedback (chỉ vertex shader)
sorter = ShaderProgram.load("depth", fragment=False,
                            feedback_varyings=["out_depth", "out_index"])

"""



import ctypes
from pathlib import Path

import numpy as np
from OpenGL import GL

SHADER_DIR = Path(__file__).parent / "shaders"


class ShaderError(RuntimeError):
    pass


class ShaderProgram:
    def __init__(self, vertex_src, fragment_src=None, feedback_varyings=None):
        """fragment_src=None + feedback_varyings: chương trình chỉ chạy vertex shader và ghi
        kết quả vào buffer (transform feedback, xen kẽ theo thứ tự `feedback_varyings`)."""
        shaders = [self._compile(vertex_src, GL.GL_VERTEX_SHADER)]
        if fragment_src is not None:
            shaders.append(self._compile(fragment_src, GL.GL_FRAGMENT_SHADER))
        self.handle = GL.glCreateProgram()
        for shader in shaders:
            GL.glAttachShader(self.handle, shader)
        if feedback_varyings:
            names = (ctypes.c_char_p * len(feedback_varyings))(*(v.encode() for v in feedback_varyings))
            GL.glTransformFeedbackVaryings(self.handle, len(feedback_varyings),
                                           ctypes.cast(names, ctypes.POINTER(ctypes.POINTER(GL.GLchar))),
                                           GL.GL_INTERLEAVED_ATTRIBS)
        GL.glLinkProgram(self.handle)
        if not GL.glGetProgramiv(self.handle, GL.GL_LINK_STATUS):
            raise ShaderError(GL.glGetProgramInfoLog(self.handle).decode())
        for shader in shaders:
            GL.glDeleteShader(shader)
        self._locations = {}

    @classmethod
    def load(cls, name, fragment=True, feedback_varyings=None):
        """Nạp shaders/<name>.vert và shaders/<name>.frag (fragment=False: chỉ .vert)."""
        return cls((SHADER_DIR / f"{name}.vert").read_text(encoding="utf-8"),
                   (SHADER_DIR / f"{name}.frag").read_text(encoding="utf-8") if fragment else None,
                   feedback_varyings)

    @staticmethod
    def _compile(src, kind):
        shader = GL.glCreateShader(kind)
        GL.glShaderSource(shader, src)
        GL.glCompileShader(shader)
        if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
            raise ShaderError(GL.glGetShaderInfoLog(shader).decode())
        return shader

    def use(self):
        GL.glUseProgram(self.handle)

    def location(self, name):
        if name not in self._locations:
            self._locations[name] = GL.glGetUniformLocation(self.handle, name)
        return self._locations[name]

    # ------------------------------------------------------------------ uniform (gọi sau use())
    def set_int(self, name, value):
        GL.glUniform1i(self.location(name), int(value))

    def set_float(self, name, value):
        GL.glUniform1f(self.location(name), float(value))

    def set_vec2(self, name, x, y):
        GL.glUniform2f(self.location(name), float(x), float(y))

    def set_vec3(self, name, v):
        GL.glUniform3f(self.location(name), *(float(c) for c in v))

    def set_vec3_array(self, name, values):
        values = np.ascontiguousarray(values, np.float32).reshape(-1, 3)
        GL.glUniform3fv(self.location(name + "[0]"), len(values), values)

    def set_float_array(self, name, values):
        values = np.ascontiguousarray(values, np.float32).reshape(-1)
        GL.glUniform1fv(self.location(name + "[0]"), len(values), values)

    def set_mat3(self, name, m):
        """m: ma trận numpy theo hàng (row-major), tự chuyển vị khi gửi lên."""
        GL.glUniformMatrix3fv(self.location(name), 1, GL.GL_TRUE, np.asarray(m, np.float32))

    def set_mat4(self, name, m):
        GL.glUniformMatrix4fv(self.location(name), 1, GL.GL_TRUE, np.asarray(m, np.float32))
