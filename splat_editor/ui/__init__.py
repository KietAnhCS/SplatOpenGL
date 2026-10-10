"""Immediate-mode UI toolkit: Draw2D (batched 2D renderer), FontAtlas, UI widgets, Theme."""

from .theme import Theme, hex_rgba  # noqa: F401
from .font import FontAtlas, shared_atlas  # noqa: F401


def __getattr__(name):
    # lazy: Draw2D / UI import OpenGL
    if name == 'Draw2D':
        from .draw2d import Draw2D
        return Draw2D
    if name == 'UI':
        from .ui import UI
        return UI
    raise AttributeError(name)
