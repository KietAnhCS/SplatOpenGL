from __future__ import annotations

import numpy as np

from ..core.history import MultiOp
from ..core.math3d import mat4_inverse
from ..core.splat import DELETED, LOCKED, SELECTED, ColorAdjust, Splat, SplatData
from .ops import (AddSplatOp, ColorAdjustOp, EntityTransformOp, RemoveSplatOp, RenameOp, StateOp, VisibilityOp,
                  splat_trs, state_op_from_new_state)

_U8 = np.uint8


def _mask_from(mask, count: int) -> np.ndarray:


def select_by_mask_state(state: np.ndarray, hit: np.ndarray, op: str) -> np.ndarray:


def make_layer_from(splat: Splat, indices, name: str | None = None) -> Splat:


def register_edit_commands(events, scene) -> None:
    def add(op):

    def target(splat=None):

    # remember initial layer transforms for scene.reset
    def on_added(splat):

    # ------------------------------------------------------------------ selection
    def state_edit(splat, new_state, name):

    def select_all():

    def select_none():

    def select_invert():

    def select_by_mask(splat, mask, op='set'):

    def select_hide():

    def select_unhide():

    def select_delete():

    def selected_indices(s):

    def duplicate():

    def separate():

    def has_selection():
        s = scene.selected_splat
        return s is not None and s.num_selected > 0
    events.function('select.canDuplicate', has_selection)
    events.function('select.hasSelection', has_selection)
    events.function('selection.splats', has_selection)
    events.function('select.canUnhide', lambda: any(s.num_locked > 0 for s in scene.splats))

    # ------------------------------------------------------------------ merge
    def merge_candidates():
        return [s for s in scene.splats if s.visible and s.num_visible > 0]

    events.function('scene.canMerge', lambda: len(merge_candidates()) >= 2)

    def merge_layers():

    # ------------------------------------------------------------------ layer commands
    def splat_delete(splat=None):
        s = target(splat)
        if s is not None and s in scene.splats:
            add(RemoveSplatOp(scene, s))

    def splat_rename(splat, name):
        s = target(splat)
        if s is not None and name is not None and str(name) != s.name:
            add(RenameOp(s, s.name, str(name)))

    def splat_set_visible(splat, visible):
        s = target(splat)
        if s is not None and bool(visible) != s.visible:
            add(VisibilityOp(s, s.visible, bool(visible)))

    def splat_preview_color(splat, adj):
        s = target(splat)
        if s is None:
            return
        preview_origin.setdefault(id(s), s.color.copy())
        s.set_color(adj)

    def splat_set_color(splat, adj):
        s = target(splat)
        if s is None:
            return
        old = preview_origin.pop(id(s), None) or s.color.copy()
        if adj == old:
            if s.color != adj:
                s.set_color(adj)      # preview reverted to the original value
            return
        add(ColorAdjustOp(s, old, adj))

    def splat_set_transform(splat, trs):
        s = target(splat)
        if s is None:
            return
        old = splat_trs(s)
        new = tuple(np.asarray(a, dtype=np.float64) for a in trs)
        if all(np.allclose(a, b, atol=0, rtol=0) for a, b in zip(old, new)):
            return
        add(EntityTransformOp(s, old, new))

    def scene_reset():
        s = target()
        if s is None:
            return
        init = getattr(s, 'initial_trs', None) or (np.zeros(3), np.array([1.0, 0.0, 0.0, 0.0]), np.ones(3))
        splat_set_transform(s, init)

    events.function('splat.initialTransform', lambda s: getattr(s, 'initial_trs', None))
    events.on('splat.delete', splat_delete)
    events.on('splat.rename', splat_rename)
    events.on('splat.setVisible', splat_set_visible)
    events.on('splat.previewColor', splat_preview_color)
    events.on('splat.setColor', splat_set_color)
    events.on('splat.setTransform', splat_set_transform)
    events.on('scene.reset', scene_reset)
    events.on('scene.cleared', lambda *a: preview_origin.clear())


__all__ = ['register_edit_commands', 'select_by_mask_state', 'make_layer_from']
