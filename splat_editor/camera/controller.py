from __future__ import annotations

import math

import numpy as np

from ..core.tool_base import MOUSE_LEFT, MOUSE_MIDDLE, MOUSE_RIGHT, InputEvent

ORBIT_SENSITIVITY = 0.3
ZOOM_SENSITIVITY = 0.4
CLICK_DRAG_THRESHOLD = 4.0

# glfw key codes (avoid importing glfw so this module works headless)
KEY_W, KEY_A, KEY_S, KEY_D, KEY_Q, KEY_E = 87, 65, 83, 68, 81, 69
KEY_F, KEY_V = 70, 86
KEY_LEFT_SHIFT, KEY_RIGHT_SHIFT = 340, 344
KEY_LEFT_ALT, KEY_RIGHT_ALT = 342, 346
RELEASE, PRESS, REPEAT = 0, 1, 2

FLY_KEYS = {KEY_W: 'forward', KEY_S: 'backward', KEY_A: 'left', KEY_D: 'right', KEY_Q: 'down', KEY_E: 'up'}


class CameraController:
    def __init__(self, camera, events):
    # ------------------------------------------------------------------ helpers
    def _scene(self):

    def _viewport(self):
        scene = self._scene()

    def _set_fly_speed(self, v):

    def set_mode(self, mode: str):

    def _clear_keys(self):
    # ------------------------------------------------------------------ actions
    def orbit(self, dx, dy):
    def look(self, dx, dy):

    def pan(self, dx, dy):

    def zoom(self, amount, x=None, y=None):

    def _focal_plane_point(self, x, y, w, h):

    def fly_move(self, vec):

    def pick_focus(self, x, y) -> bool:

    # ------------------------------------------------------------------ event handlers
    def focus_selection(self):

    def reset(self):

    def set_view(self, name):

    # mouse ------------------------------------------------------------
    def on_mouse_down(self, ev: InputEvent) -> bool:

    def on_double_click(self, ev: InputEvent) -> bool:

    def on_mouse_move(self, ev: InputEvent) -> bool:

    def on_mouse_up(self, ev: InputEvent) -> bool:

    def on_scroll(self, ev: InputEvent) -> bool:

    # keyboard ---------------------------------------------------------
    def on_key(self, ev: InputEvent) -> bool:

    def release_all(self):

    # ------------------------------------------------------------------ per frame
    def update(self, dt: float) -> bool:


def _target_rotation(cam):
