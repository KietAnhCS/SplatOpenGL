"""Move / Rotate / Scale tools (supersplat tools/transform-tool.ts + splats/entity transform handlers).

Target = scene.selected_splat.
* If it has selected gaussians: the gizmo pivots on the world-space centre of the selection bound
  (oriented like the layer); during a drag `splat.selection_preview` holds the LOCAL-space delta
  ``inv(W) @ D_world @ W``; on release it is cleared and ``SplatsTransformOp`` (which bakes the
  data) is added to the history.
* Otherwise the whole layer entity is moved live with ``splat.move`` and an ``EntityTransformOp``
  is recorded on release (added with execute=False since the entity is already in place).
Escape during a drag cancels it. Left-button events are consumed only when the press hits a handle.

Coordinate space: event 'tool.toggleCoordSpace' / 'tool.setCoordSpace'(space), function
'tool.coordSpace' -> 'local'|'world', fires 'tool.coordSpace'(space) on change (registered here
unless something else already provides the function). Scale always uses local axes (a world-axis
scale of a rotated layer can't be represented by a TRS transform).
"""

from __future__ import annotations

import numpy as np

from splat_editor.core.math3d import quat_mul, quat_normalize, quat_to_mat3, transform_points
from splat_editor.core.tool_base import MOUSE_LEFT, InputEvent, RenderContext, Tool

from .gizmo import Gizmo, GizmoDelta

KEY_ESCAPE = 256


def register_coord_space(events):
    """Register the shared world/local coordinate space state (idempotent)."""
    if events.has_function('tool.coordSpace'):
        return
    state = {'space': 'local'}

    def set_space(space):
        if space in ('local', 'world') and space != state['space']:
            state['space'] = space
            events.fire('tool.coordSpace', space)

    events.function('tool.coordSpace', lambda: state['space'])
    events.on('tool.setCoordSpace', set_space)
    events.on('tool.toggleCoordSpace', lambda *_: set_space('world' if state['space'] == 'local' else 'local'))


class TransformTool(Tool):
    gizmo_mode = 'translate'

    def __init__(self, events, scene, mode: str | None = None):
        super().__init__(events)
        self.scene = scene
        self.gizmo = Gizmo(mode or self.gizmo_mode)
        self._drag = None
        self._pivot_cache = None      # (key, world pivot)
        self._pivot_override = None   # (key, world pivot) kept after a selection commit
        self._mouse = (0.0, 0.0)
        register_coord_space(events)
        events.on('selection.changed', self._on_selection_changed)

    # ------------------------------------------------------------------ helpers
    @property
    def local_space(self) -> bool:
        if self.gizmo.mode == 'scale':
            return True
        return self.events.invoke('tool.coordSpace') != 'world'

    def _camera(self):
        return getattr(self.scene, 'camera', None)

    def _size(self):
        return max(int(self.scene.width), 1), max(int(self.scene.height), 1)

    def _target(self):
        splat = self.scene.selected_splat
        if splat is None or not getattr(splat, 'visible', True):
            return None
        return splat

    def _selection_pivot(self, splat):
        key = (id(splat), splat.data_version, splat.state_version, splat.transform_version)
        if self._pivot_override is not None and self._pivot_override[0] == key:
            return self._pivot_override[1]
        if self._pivot_cache is not None and self._pivot_cache[0] == key:
            return self._pivot_cache[1]
        c = transform_points(splat.world_matrix(), splat.selection_bound().center)
        self._pivot_cache = (key, c)
        return c

    def frame(self):
        """-> (splat, selection_mode, pivot_world (3,), axes (3,3)) or None."""
        splat = self._target()
        if splat is None:
            return None
        sel = splat.num_selected > 0
        pivot = self._selection_pivot(splat) if sel else np.asarray(splat.position, np.float64).copy()
        axes = quat_to_mat3(splat.rotation) if self.local_space else np.eye(3)
        return splat, sel, pivot, axes

    def _sync_gizmo(self) -> bool:
        if self._drag is not None:
            return True
        f = self.frame()
        if f is None:
            return False
        self.gizmo.set_frame(f[2], f[3])
        return True

    def _on_selection_changed(self, *_):
        if self._drag is not None:
            self.cancel()

    # ------------------------------------------------------------------ tool lifecycle
    def deactivate(self):
        if self._drag is not None:
            self.cancel()
        self.gizmo.hover = None
        super().deactivate()

    # ------------------------------------------------------------------ input
    def on_mouse_down(self, ev: InputEvent) -> bool:
        if ev.button != MOUSE_LEFT or self._drag is not None:
            return self._drag is not None
        cam = self._camera()
        if cam is None or not self._sync_gizmo():
            return False
        w, h = self._size()
        handle = self.gizmo.hit_test(ev.x, ev.y, cam, w, h)
        if handle is None:
            return False
        f = self.frame()
        if not self.gizmo.begin_drag(handle, ev.x, ev.y, cam, w, h):
            return False
        splat, sel, pivot, axes = f
        self._drag = dict(
            splat=splat, selection=sel, W0=splat.world_matrix(),
            old_trs=(splat.position.copy(), splat.rotation.copy(), splat.scale.copy()),
            pivot=pivot.copy(), axes=axes.copy(), delta=GizmoDelta())
        self._mouse = (ev.x, ev.y)
        return True

    def on_mouse_move(self, ev: InputEvent) -> bool:
        self._mouse = (ev.x, ev.y)
        cam = self._camera()
        if self._drag is None:
            if cam is not None and self._sync_gizmo():
                w, h = self._size()
                hov = self.gizmo.hit_test(ev.x, ev.y, cam, w, h)
                if hov != self.gizmo.hover:
                    self.gizmo.hover = hov
                    self.scene.force_render = True
            return False
        w, h = self._size()
        delta = self.gizmo.drag(ev.x, ev.y, cam, w, h, snap=ev.mods.ctrl)
        self.apply_delta(delta)
        return True

    def on_mouse_up(self, ev: InputEvent) -> bool:
        if self._drag is None:
            return False
        if ev.button != MOUSE_LEFT:
            return True
        self.commit()
        return True

    def on_key(self, ev: InputEvent) -> bool:
        if self._drag is not None and ev.key == KEY_ESCAPE and ev.action == 1:
            self.cancel()
            return True
        return False

    # ------------------------------------------------------------------ transform application
    def apply_delta(self, delta: GizmoDelta):
        d = self._drag
        if d is None:
            return
        d['delta'] = delta
        splat = d['splat']
        D = delta.matrix
        if d['selection']:
            W0 = d['W0']
            splat.selection_preview = np.linalg.inv(W0) @ D @ W0
        else:
            pos, rot, scl = self.entity_trs(delta)
            splat.move(pos, rot, scl)
        self.gizmo.apply_display_delta(delta, self.local_space)
        self.scene.force_render = True

    def entity_trs(self, delta: GizmoDelta):
        """New (position, rotation, scale) of the dragged layer for a given delta."""
        d = self._drag
        pos0, rot0, scl0 = d['old_trs']
        P = d['pivot']
        mode = self.gizmo.mode
        if mode == 'translate':
            return pos0 + delta.translation, rot0.copy(), scl0.copy()
        if mode == 'rotate':
            R = quat_to_mat3(delta.rotation)
            return P + R @ (pos0 - P), quat_normalize(quat_mul(delta.rotation, rot0)), scl0.copy()
        # scale (local axes == layer rotation)
        A = d['axes'] @ np.diag(delta.scale) @ d['axes'].T
        return P + A @ (pos0 - P), rot0.copy(), scl0 * delta.scale

    def cancel(self):
        d = self._drag
        if d is None:
            return
        self._drag = None
        self.gizmo.end_drag()
        splat = d['splat']
        if d['selection']:
            splat.selection_preview = None
        else:
            splat.move(*d['old_trs'])
        self.scene.force_render = True

    def commit(self):
        d = self._drag
        if d is None:
            return
        self._drag = None
        self.gizmo.end_drag()
        splat = d['splat']
        delta = d['delta']
        changed = not np.allclose(delta.matrix, np.eye(4), atol=1e-12)
        if d['selection']:
            splat.selection_preview = None
            if changed:
                from splat_editor.edit.ops import SplatsTransformOp
                W0 = d['W0']
                m_local = np.linalg.inv(W0) @ delta.matrix @ W0
                indices = np.nonzero(splat.selected_mask())[0]
                self.scene.history.add(SplatsTransformOp(splat, indices, m_local))
                new_pivot = transform_points(delta.matrix, d['pivot'])
                key = (id(splat), splat.data_version, splat.state_version, splat.transform_version)
                self._pivot_override = (key, new_pivot)
        else:
            if changed:
                from splat_editor.edit.ops import EntityTransformOp
                new_trs = (splat.position.copy(), splat.rotation.copy(), splat.scale.copy())
                self.scene.history.add(EntityTransformOp(splat, d['old_trs'], new_trs), execute=False)
            else:
                splat.move(*d['old_trs'])
        self.scene.force_render = True

    # ------------------------------------------------------------------ drawing
    def draw_3d(self, ctx: RenderContext):
        if not self.active or not self._sync_gizmo():
            return
        self.gizmo.draw_3d(ctx)

    def draw_2d(self, ctx: RenderContext):
        if not self.active or not self._sync_gizmo():
            return
        self.gizmo.draw_2d(ctx, mouse=self._mouse)

    def draw_ui(self, ui) -> None:
        space = self.events.invoke('tool.coordSpace') or 'local'
        if self.gizmo.mode == 'scale':
            ui.label('Space: local (scale)')
        elif ui.button('Space: %s (Shift+C)' % space):
            self.events.fire('tool.toggleCoordSpace')
        ui.label('Ctrl: snap')


class MoveTool(TransformTool):
    gizmo_mode = 'translate'


class RotateTool(TransformTool):
    gizmo_mode = 'rotate'


class ScaleTool(TransformTool):
    gizmo_mode = 'scale'


def create_transform_tools(events, scene) -> dict:
    from .measure_tool import MeasureTool
    tools = {
        'move': MoveTool(events, scene),
        'rotate': RotateTool(events, scene),
        'scale': ScaleTool(events, scene),
        'measure': MeasureTool(events, scene),
    }
    for name, t in tools.items():
        t.name = name
    return tools
