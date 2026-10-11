"""Cửa sổ GLFW có ngữ cảnh OpenGL 3.3 core."""

import glfw 

class Window:
    def __init__():
        pass 

    @property 
    def should_close(self):
        pass 

    def close(self):
        glfw.set_window_should_close(self.handle, True)

    @property 
    def size(self):
        pass 

    @property
    def framebuffer_size():
        pass 

    @property 
    def cursor_pos():
        pass 

    def is_key_down(self, key):
        pass 

    def is_mouse_down(self, button):
        pass 

    @staticmethod 
    def poll_events():
        pass 

    def swap_buffers(self):
        pass 

    def destroy():
        pass 


