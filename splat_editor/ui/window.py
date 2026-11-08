"""Cửa sổ GLFW có ngữ cảnh OpenGL 3.3 core."""

import glfw


"""
win = Window("Splat Editor", 1280, 720)
while not win.should_close:
    Window.poll_events()
    if win.is_key_down(glfw.KEY_ESCAPE):
        win.close()
    # ... vẽ bằng OpenGL ...
    win.swap_buffers()
win.destroy()

"""

class Window:
    def __init__(self, title, width, height):
        if not glfw.init():
            raise RuntimeError("Failed to initialize GLFW")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        self.handle = glfw.create_window(width, height, title, None, None)
        if not self.handle:
            glfw.terminate()
            raise RuntimeError("Failed to create an OpenGL 3.3 window")
        glfw.make_context_current(self.handle)
        glfw.swap_interval(1)

    @property
    def should_close(self):
        return glfw.window_should_close(self.handle)

    def close(self):
        glfw.set_window_should_close(self.handle, True)

    @property
    def size(self):
        return glfw.get_window_size(self.handle)

    @property
    def framebuffer_size(self):
        return glfw.get_framebuffer_size(self.handle)

    @property
    def cursor_pos(self):
        return glfw.get_cursor_pos(self.handle)

    def is_key_down(self, key):
        return glfw.get_key(self.handle, key) == glfw.PRESS

    def is_mouse_down(self, button):
        return glfw.get_mouse_button(self.handle, button) == glfw.PRESS

    @staticmethod
    def poll_events():
        glfw.poll_events()

    def swap_buffers(self):
        glfw.swap_buffers(self.handle)

    def destroy(self):
        glfw.destroy_window(self.handle)
        glfw.terminate()
