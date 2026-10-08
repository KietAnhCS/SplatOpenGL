"""Shared layout constants and small helpers for the app's immediate-mode panels."""

from __future__ import annotations

from contextlib import contextmanager

MARGIN = 24             # gap between floating panels and the window edge
MENUBAR_H = 52          # floating menu bar (top-left)
LEFT_W = 400            # left card: scene manager / transform / colours
STRIP_W = 60            # right vertical icon strip
STATUS_H = 38           # bottom tab / stats bar
DATA_PANEL_H = 240      # bottom data panel (Ctrl+D)
TOOL_BTN = 44           # bottom toolbar button size
TOOL_OPTS_W = 250
VIEW_CUBE_SIZE = 110
SETTINGS_W = 320        # settings popover (view / camera), opens left of the strip
TOOLBAR_W = 0           # legacy name: no left tool strip any more
RIGHT_W = 0             # legacy name: no right side panel any more


def menu_height(ui) -> float:
    return float(MARGIN + MENUBAR_H)


@contextmanager
def panel(ui, id, x, y, w, h, title=None, scroll=True, **kw):
    """begin_panel/end_panel pair; end_panel is only called when begin_panel returned True
    (ImGui-style 'collapsed returns False' semantics are handled by the UI toolkit)."""
    opened = ui.begin_panel(id, x, y, w, h, title=title, scroll=scroll, **kw)
    try:
        yield opened
    finally:
        if opened:
            ui.end_panel()


def fmt_count(n: int) -> str:
    return f"{int(n):,}"
