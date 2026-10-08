from __future__ import annotations 

import os 
import time 
import trackback

import numpy as np
from OpenGL import GL 

from splatpy.core.events import Events 
from splatpy.core.math3d import look_at, perspective, ortho as ortho_matrix
from splatpy.core.scene import Scene
from splatpy.core.settings import ViewSettings
from splatpy.core.tool_base import RenderContext, ToolManager


from .file_ops import FileOps, PROJECT_EXT, unpremultiply
from .layout import MARGIN, VIEW_CUBE_SIZE
from .preferences import Preferences
from .shortcuts import ShortcutManager
from .toolbar import SHORTCUT_TOOLS
from .window import Window


IDLE_REDRAW_INTERVAL = 1.0    # seconds: refresh status bar / toasts while idle

class _FallbackCamera:

    def __init__(self):
        pass 
    def view_matrix(self):
        pass 

    def proj_matrix(self, aspect):
        pass 

    def focus():
        pass 

    def update():
        pass

class App:
    def __init__():
        pass

    def _new_camera(self):
        pass

    def _new_controller():
        pass 

    def _register_tools():
        pass 

    def _make():
        pass 

    def log_error_once():
        pass

    def _safe():
        pass 

    def defer():
        pass 

    def fire_later():
        pass 

    def notify():
        pass 

    def _register_event(self):
        pass

        def toggle(attr):
            pass

    def _shortcut_tool():
        pass

    def _mark_dirty():
        pass 

    def pick_splat():
        pass 

    def pick_point():
        pass 

    def focus_scene():
        pass 

    def viewport_size():
        pass 

    def handle_event():
        pass 

    def render_scene():
        pass 

    def draw_frame():
        pass 

    def _draw_ui():
        pass 

    def render_offscreen():
        pass 

    def update_title():
        pass 

    def request_exit():
        pass 

    def _ui_animating(self) -> bool: 
        pass 

    def step() -> bool:
        pass 

    def busy(self) -> bool:
        pass 

    def run(self):
        pass

    def shutdown(self):
        pass 

def _imp(name):
    pass