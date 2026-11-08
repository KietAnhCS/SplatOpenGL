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

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    app = Application()
    if argv:
        app.open_file(argv[0])
        add.add_files(argv[1:])
    app.run()