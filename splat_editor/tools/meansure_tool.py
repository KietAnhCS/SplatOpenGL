"""Measure tool (supersplat tools/measure-tool.ts, simplified).

Click two points on the splats (picked with events.invoke('scene.pickPoint', x, y) -> world pos | None);
a line and the distance label are drawn. A third click starts a new measurement. Escape clears.
Clicks are detected on mouse-up (movement under CLICK_TOLERANCE px) so left-drag still orbits.
Fires 'measure.changed'(distance | None). Function 'measure.distance' -> float | None.
"""

from __future__ import annotations

import numpy as np

from splat_editor.core.tool_base import MOUSE_LEFT, InputEvent, RenderContext, Tool

KEY_ESCAPE = 256
CLICK_TOLERANCE = 4.0

POINT_COLOR = (1.0, 0.85, 0.2, 1.0)
LINE_COLOR = (1.0, 0.85, 0.2, 1.0)


class MeasureTool(Tool):
    def __init__(self, events, scene):
        super().__init__(events)
        self.scene = scene
        self.points: list[np.ndarray] = []
        self._down = None
        events.function('measure.distance', lambda: self.distance)
        events.on('measure.clear', self.clear)

    @property
    def distance(self):
        if len(self.points) == 2:
            return float(np.linalg.norm(self.points[1] - self.points[0]))
        return None

    def clear(self, *_):
        if self.points:
            self.points = []
            self.scene.force_render = True
            self.events.fire('measure.changed', None)

    def add_point(self, p):
        if len(self.points) >= 2:
            self.points = []
        self.points.append(np.asarray(p, dtype=np.float64).reshape(3).copy())
        self.scene.force_render = True
        self.events.fire('measure.changed', self.distance)

    def deactivate(self):
        self._down = None
        super().deactivate()

    # ------------------------------------------------------------------ input
    def on_mouse_down(self, ev: InputEvent) -> bool:
        if ev.button == MOUSE_LEFT:
            self._down = (ev.x, ev.y)
        return False                      # let the camera orbit on drag

    def on_mouse_up(self, ev: InputEvent) -> bool:
        if ev.button != MOUSE_LEFT or self._down is None:
            return False
        x0, y0 = self._down
        self._down = None
        if abs(ev.x - x0) > CLICK_TOLERANCE or abs(ev.y - y0) > CLICK_TOLERANCE:
            return False
        p = self.events.invoke('scene.pickPoint', ev.x, ev.y)
        if p is not None:
            self.add_point(p)
        return False

    def on_key(self, ev: InputEvent) -> bool:
        if ev.key == KEY_ESCAPE and ev.action == 1 and self.points:
            self.clear()
            return True
        return False

    # ------------------------------------------------------------------ drawing
    def draw_3d(self, ctx: RenderContext):
        if not self.active or ctx.lines3d is None or len(self.points) < 2:
            return
        ctx.lines3d.line(self.points[0], self.points[1], LINE_COLOR, on_top=True)

    def draw_2d(self, ctx: RenderContext):
        if not self.active or ctx.draw2d is None or not self.points or ctx.camera is None:
            return
        d2 = ctx.draw2d
        xy, _, front = ctx.camera.world_to_screen(np.array(self.points), ctx.width, ctx.height)
        for i in range(len(self.points)):
            if front[i]:
                d2.circle_fill(float(xy[i][0]), float(xy[i][1]), 5.0, POINT_COLOR)
                d2.circle(float(xy[i][0]), float(xy[i][1]), 6.0, (0, 0, 0, 1), thickness=1)
        dist = self.distance
        if dist is not None and front[0] and front[1]:
            mx = float(xy[0][0] + xy[1][0]) * 0.5
            my = float(xy[0][1] + xy[1][1]) * 0.5
            s = '%.3f' % dist
            tw, th = d2.text_size(s, 14)
            d2.rect(mx - tw / 2 - 4, my - th / 2 - 3, tw + 8, th + 6, (0, 0, 0, 0.7))
            d2.text(mx - tw / 2, my - th / 2, s, (1, 1, 1, 1), 14)

    def draw_ui(self, ui) -> None:
        ui.label('Click two points to measure')
        d = self.distance
        ui.label('Length: %s' % ('%.4f' % d if d is not None else '-'))
        if ui.button('Clear'):
            self.clear()
