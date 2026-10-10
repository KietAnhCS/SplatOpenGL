from __future__ import annotations

import math
import time

import numpy as np

from . import stats

NUM_BINS = 256
CAMERA_SETTLE = 0.15     
CONTROLS_WIDTH = 230


def format_value(v: float) -> str:


class DataPanel:

    # ------------------------------------------------------------------ events
    def _on_splat_changed(self, splat=None, *_):

    def _on_selection_changed(self, *_):

    def invalidate(self):

    # ------------------------------------------------------------------ data
    def properties(self, splat) -> list[str]:

    def _camera_key(self, splat):

    def _settled_camera_key(self, splat):

    def counted_mask(self, splat) -> np.ndarray:

    def update(self, force=False) -> stats.HistogramResult | None:

    def select_bins(self, start_bin: int, end_bin: int, op: str = 'set'):
        return mask

    def _t_to_bin(self, t: float) -> int:

    def _current_op(self, ui) -> str:
    def draw(self, ui, x, y, w, h):
