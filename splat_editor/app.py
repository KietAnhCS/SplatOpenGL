"""Application: ghép cửa sổ, giao diện, Editor và khung nhìn 3D lại với nhau, chạy vòng lặp chính."""

"""
# Cách dùng thông thường (main.py làm đúng như vậy)
from splat_editor.app import main
main()                                  # đọc đường dẫn file từ sys.argv rồi chạy vòng lặp chính

# Hoặc dùng trực tiếp
app = Application(1500, 900)
app.open_file("scene.ply")             # mở file (thay cảnh hiện tại) và đưa camera về nhìn toàn cảnh
app.add_files(["a.ply", "b.ply"])      # thêm mỗi file thành một lớp
app.actions.trigger("save")            # chạy một hành động theo tên (giống bấm menu / phím tắt)
app.run()                              # vòng lặp: poll_events -> input.update -> vẽ GUI -> viewport -> swap_buffers

# Mỗi khung hình:
#   input.update(dt)           điều khiển camera / cọ
#   gui.begin_frame() ... gui.end_frame()   dựng giao diện ImGui
#   viewport.sync(editor)      gửi dữ liệu mới lên GPU nếu Editor đã đổi
#   viewport.render(...)       vẽ cảnh 3D vào vùng giữa
#   gui.draw()                 vẽ ImGui đè lên
"""

import sys
import time 

import glfw 

from .editor.editor import Editor
from .render.viewport import Viewport
from .ui.actions import Action, ActionRegistry
from .ui.file_dialog import FileDialog
from .ui.gui import Gui
from .ui.input import InputController
from .ui.layout import Layout
from .ui.menu_bar import MainMenuBar
from .ui.shortcuts_window import ShortcutsWindow
from .ui.side_panel import SidePanel
from .ui.status_bar import StatusBar
from .ui.viewport_overlay import ViewportOverlay
from .ui.window import Window

class FpsCounter:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.value = 0.0
        self._frame =0
        self._start = time.perf_counter()

    def tick(self, now):
        self._frames += 1
        if now - self._start >= self.interval:
            self.value = self._frame / ( now - self._start)
            self._frame, self._start = 0, now 

class Application:
    TITLE = "Splat Editor"

    def __init__(self, width=1500, height=900):
        self.window = Window(self.TITLE, width, height)
        self.gui = Gui(self.window)
        self.editor = Editor()
        self.viewport = Viewport()
        self.layout = Layout()
        self.fps = FpsCounter()
        self.actions = self._create_actions()

        self.menu_bar = MainMenuBar(self.actions)
        self.side_panel = SidePanel(self)
        self.status_bar = StatusBar(self)
        self.shortcuts_window = ShortcutsWindow(self.actions)
        self.overlay = ViewportOverlay(self)
        self.input = InputController(self)

    # ------------------------------------------------------------------ hành động

    def _create_actions(self):
        pass

    # ------------------------------------------------------------------ lệnh
    def open_file(self, path):
        pass 

    def add_files(self, paths):
        pass 

    def open_dialog(self):
        pass 

    def add_dialog(self):
        pass

    def save_dialog(self):
        pass

    def frame_scene(self, layer=None):
        pass 

    def toggle_grid(self):
        pass 

    def toggle_sh(self): 
        pass

    def exit_brush(self):
        pass 

    def shortcuts_window_toggle(self):
        pass 

    def paint(self, x, y):
        pass 

    def drag_speed(self):
        pass 

    # ------------------------------------------------------------------ vòng lặp chính

    def _draw_gui(self):
        pass 

    def run(self):
        pass 

    


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    app = Application()
    if argv:
        app.open_file(argv[0])
        add.add_files(argv[1:])
    app.run()