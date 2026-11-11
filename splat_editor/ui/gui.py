"""Ngữ cảnh Dear ImGui gắn với cửa sổ GLFW."""

"""
gui = Gui(window)                       # sau khi tạo Window

while not window.should_close:
    Window.poll_events()
    gui.begin_frame()
    # ... gọi các hàm imgui.* dựng giao diện ...
    gui.end_frame()
    # ... vẽ cảnh 3D ...
    gui.draw()                          # vẽ ImGui đè lên cảnh
    window.swap_buffers()

if gui.wants_mouse:                     # chuột đang ở trên ImGui: đừng điều khiển camera
    pass
gui.shutdown()
"""

from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

from .theme import Theme


class Gui:
    def __init__(self, window):
        imgui.create_context()
        imgui.get_io().set_ini_filename("")          # không ghi file imgui.ini
        # tự đăng ký callback ở InputController để vừa chuyển cho ImGui vừa xử lý camera / cọ
        self.backend = GlfwRenderer(window.handle, attach_callbacks=False)
        Theme.apply()

    @property
    def io(self):
        return imgui.get_io()

    @property
    def wants_mouse(self):
        return imgui.get_io().want_capture_mouse

    @property
    def wants_text(self):
        return imgui.get_io().want_text_input

    def begin_frame(self):
        self.backend.process_inputs()
        imgui.new_frame()

    def end_frame(self):
        """Kết thúc khung hình ImGui (chưa vẽ ra màn hình)."""
        imgui.render()

    def draw(self):
        self.backend.render(imgui.get_draw_data())

    def shutdown(self):
        self.backend.shutdown()
