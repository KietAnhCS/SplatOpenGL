from __future__ import annotations

import numpy as np

from ..core.history import EditOp
from ..core.math3d import quat_normalize
from ..core.splat import ColorAdjust, Splat


def _as_indices(indices, count: int | None = None) -> np.ndarray:


# --------------------------------------------------------------------------- state

class StateOp(EditOp):

    def __init__(self, splat: Splat, indices, old_state, new_state, name: str = "state"):
        self.name = name

    def _apply(self, values):

    def do(self):

    def undo(self):

    @property
    def empty(self) -> bool:


def state_op_from_new_state(splat: Splat, new_state: np.ndarray, name: str) -> StateOp | None:


# --------------------------------------------------------------------------- per-gaussian transform

class SplatsTransformOp(EditOp):

    def __init__(self, splat: Splat, indices, matrix_local):

    def _save(self):

    def do(self):

    def undo(self):

    def destroy(self):


# --------------------------------------------------------------------------- layer ops

def _trs_copy(trs):


def splat_trs(splat: Splat):


class EntityTransformOp(EditOp):
    """Layer transform change. Safe to add when the entity is already at new_trs."""

    name = "entityTransform"

    def __init__(self, splat: Splat, old_trs, new_trs):

    def do(self):

    def undo(self):


class ColorAdjustOp(EditOp):
    name = "colorAdjust"

    def __init__(self, splat: Splat, old: ColorAdjust, new: ColorAdjust):

    def do(self):

    def undo(self):


class AddSplatOp(EditOp):
    """Add a layer to the scene. Undo removes it but keeps the object alive for redo."""

    name = "addSplat"

    def __init__(self, scene, splat: Splat):

    def do(self):

    def undo(self):


class RemoveSplatOp(EditOp):
    """Remove a layer; undo re-inserts it at its original list position (and re-selects it)."""

    name = "removeSplat"

    def __init__(self, scene, splat: Splat):

    def do(self):

    def undo(self):


class RenameOp(EditOp):
    name = "splatRename"

    def __init__(self, splat: Splat, old: str, new: str):

    def do(self):

    def undo(self):


class VisibilityOp(EditOp):
    name = "splatVisibility"

    def __init__(self, splat: Splat, old: bool, new: bool):

    def do(self):

    def undo(self):


__all__ = ['StateOp', 'state_op_from_new_state', 'SplatsTransformOp', 'EntityTransformOp', 'ColorAdjustOp',
           'AddSplatOp', 'RemoveSplatOp', 'RenameOp', 'VisibilityOp', 'splat_trs']
