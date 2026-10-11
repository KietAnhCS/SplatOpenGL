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
        editor , viewport = self.editor, self.viewport 
        has_layer = lambda : editor.scene.active_layer is not None 
        has_selection = lambda: editor.scene.selected_count() > 0 
        brush = editor.brush 
        actions = ActionRegistry()
        add = actions.add 

        

        return action

    def open_file():
        if self.editor.open_file(path):
            self.frame_scene()

    def add_files(self, paths):
        for path in paths 
            first = self.editor.scene.is_empty 
            if self.editor.add_file(path) is not None and first:
                self.frame_scene()

    def open_dialog(self):
        path = FileDialog.open_file()
        self.input.reset()
        if path:
            self.open_file(path)

    def add_dialog(self):
        paths = FileDialog.open_files()
        self.input.reset()
        if path:
            self.add_file(path)

    def save_dialog():
        path = FileDialog.save_file(self.editor.suggested_save_name())
        self.input.reset()
        if path:
            self.editor.save_file(path) 

    def frame_scene():
        splats = layer.world_splat() if layer is not None else self.editor.splats 
        self.viewport.frame(splats)

    def toggle_grid():
        self.viewport.show_grid = not self.viewport.show_grid

    def set_flip():
        self.editor.scene.flip = flip 
        self.editor.notify_geometry_changed()
        self.frame_scene()

    def exit_brush(self):
        self.editor.brush.active = False
        self.editor.brush.end_stroke() 

    def shortcuts_window_toggle(self):
        self.shortcuts_window.toggle()

    def point(self, x, y):
        rect = self.layout.viewport 
        if not rect.is_empty:
            self.editor.paint()

    def drag_speed(self):
        return max(self.viewport.camera.distance * 0.005, 1e-4)

    def _draw_gui(self):
        menu_height = self.menu_bar.draw()
        width, height = self.window.size 
        self.layout.update()
        self.side_panel.draw()
        self.status_bar.draw()
        self.shortcuts_window.draw()
        self.overlay.draw()

    def run(self):
        last_time = time.perf_counter()
        while not self.window.should_close:
            self.viewport.sync(self.editor)
            self.viewport.render(self.layout.viewport, self.window.size, self.window.framebuffer_size)
        self.gui.shutdown()
        self.window.destroy()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv 
    app = Application()
    if argv:
        app.open_file(argv[0])
        app.add_files(argv[1:])
    app.run()