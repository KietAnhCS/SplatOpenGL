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
        seft.value = 0.0
        self._frame = 0
        self._start = time.perf_counter()

    def tick(self, now):
        self._frames += 1
        if now - self._start >= self.interval:
            self.value = self._frames / (now - self._start)
            self._frame, self._start = 0, now

class Application:
    TITLE = "Splat Editor"

    def __init__(self, width=1500, height =900):
        self.window = Window(self.TITLE, width, height):
        self.gui = Gui(self.window)
        self.editor = Editor()
        self.viewport = Viewport()
        self.layout = Layout()
        self.fps = FpsCounter()
        self.actions = self._create_actions()

        self.menu_bar = MainMenuBar(self.action)
        self.side_panel = SidePanel(self)
        self.status_bar = StatusBar(self)
        self.shortcuts_window = ShortcutsWindow(self.action)
        self.overlay = ViewportOverlay(self)
        self.input = InputController(self)

    def _create_action(self):
        pass 

    def open_file():
        pass 

    def add_files():
        pass 

    def open_dialog():
        pass 

    def add_dialog():
        pass 

    def save_dialog():
        pass 

    def frame_scene():
        pass 

    def toggle_grid():
        pass 

    def set_flip():
        pass

    def exit_brush(self):
        pass 

    def shortcuts_window_toggle(self):
        pass 

    def point():
        pass

    def drag_speed():
        pass 

    def _draw_gui():
        pass 

    def run(self):
        pass 


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv 
    app = Application()
    if argv:
        app.open_file(argv[0])
        app.add_files(argv[1:])
    app.run()