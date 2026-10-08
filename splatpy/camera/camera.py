from __future__ import annotations

import math

import numpy as np

from ..core.math3d import AABB, ortho as ortho_matrix, perspective
from .tween import Tween

DAMPING = 0.2                 # supersplat controls.dampingFactor (seconds of the quintic tween)
INITIAL_AZIM = -45.0
INITIAL_ELEV = -10.0
MIN_ELEV = -90.0
MAX_ELEV = 90.0

VIEWS = {
    # name: (azim, elev)  -- supersplat 'camera.align' values
    'front': (0.0, 0.0), 'pz': (0.0, 0.0),
    'back': (180.0, 0.0), 'nz': (180.0, 0.0),
    'right': (90.0, 0.0), 'px': (90.0, 0.0),
    'left': (270.0, 0.0), 'nx': (270.0, 0.0),
    'top': (0.0, -90.0), 'py': (0.0, -90.0),
    'bottom': (0.0, 90.0), 'ny': (0.0, 90.0),
}


def _rot(azim_deg: float, elev_deg: float) -> np.ndarray:
    pass


def _back_vec(azim_deg: float, elev_deg: float) -> np.ndarray:
    pass


def azim_elev_from_dir(back: np.ndarray) -> tuple[float, float]:
    pass


class Camera:
    def __init__(self, events=None):
        pass

    # ------------------------------------------------------------------ events
    def _notify(self):
        if self.events is None:
            pass

    def _check_changed(self):
        pass

    # ------------------------------------------------------------------ parameters (current values)
    @property
    def azim(self) -> float:
        pass

    @azim.setter
    def azim(self, v):
        pass

    @property
    def elev(self) -> float:
        pass

    @elev.setter
    def elev(self, v):
        pass

    @property
    def distance(self) -> float:
        pass

    @distance.setter
    def distance(self, v):
        pass

    @property
    def focal_point(self) -> np.ndarray:
        pass

    @focal_point.setter
    def focal_point(self, p):
        pass

    @property
    def target_azim(self) -> float:
        pass

    @property
    def target_elev(self) -> float:
        pass

    @property
    def target_distance(self) -> float:
        pass

    @property
    def target_focal_point(self) -> np.ndarray:
        pass

    @property
    def ortho(self) -> bool:
        pass

    @ortho.setter
    def ortho(self, v):
        pass

    @property
    def fov_factor(self) -> float:
        pass

    # ------------------------------------------------------------------ derived pose
    @property
    def rotation(self) -> np.ndarray:
        pass

    @property
    def position(self) -> np.ndarray:
        pass

    @property
    def forward(self) -> np.ndarray:
        pass

    @property
    def right(self) -> np.ndarray:
        pass

    @property
    def up(self) -> np.ndarray:
        pass

    def world_matrix(self) -> np.ndarray:
        pass

    def view_matrix(self) -> np.ndarray:
        pass

    def ortho_half_height(self) -> float:
        pass

    def proj_matrix(self, aspect: float) -> np.ndarray:
        pass

    def view_proj(self, aspect: float) -> np.ndarray:
        pass

    # ------------------------------------------------------------------ projection helpers
    def world_to_screen(self, pts, width, height):
        pass

    def screen_to_ray(self, x, y, width, height):
        pass

    def screen_to_world(self, x, y, depth, width, height) -> np.ndarray:
        pass

    def world_units_per_pixel(self, height, depth=None) -> float:
        pass

    # ------------------------------------------------------------------ setters (supersplat API)
    def _transition(self, animate) -> float:
        pass

    def set_focal_point(self, p, animate=True):
        pass

    def set_azim_elev(self, azim, elev, animate=True, keep_ortho=False):
        pass

    def set_distance(self, d, animate=True):
        pass 

    def _after_set(self, animate):
        pass 

    def set_pose(self, position, target, animate=False):
        pass 

    def look(self, dx, dy, sensitivity=0.3):
        pass 

    def focus_distance(self, radius: float) -> float:
        pass 

    def focus(self, center, radius, animate=True):
        pass

    def set_view(self, name: str, animate=True, ortho=True):
        pass 

    def set_fov(self, deg: float):
        pass 

    def reset(self, animate=True):
        pass 

    # ------------------------------------------------------------------ clipping
    def auto_near_far(self, scene_bound: AABB | None):
        pass 

    def _update_clip(self):
        pass

    # ------------------------------------------------------------------ animation
    @property
    def animating(self) -> bool:
        pass 

    # ------------------------------------------------------------------ serialisation
    def to_dict(self) -> dict:
        pass

    def from_dict(self, d: dict):
        pass
