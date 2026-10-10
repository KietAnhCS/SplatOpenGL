"""Dark theme modelled on SuperSplat's ui/scss/colors.scss (+ pcui grey theme)."""

from __future__ import annotations


def hex_rgba(h: str, a: float = 1.0) -> tuple:
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return (r, g, b, a)


# unscaled metrics (logical pixels)
BASE_METRICS = dict(
    font_size=14.0,
    font_size_small=11.0,
    item_h=26.0,
    pad=8.0,
    spacing_x=6.0,
    spacing_y=4.0,
    header_h=30.0,
    menu_bar_h=28.0,
    menu_item_h=26.0,
    menu_gutter=24.0,
    radius=4.0,
    panel_radius=10.0,
    scrollbar_w=6.0,
    checkbox=14.0,
    label_min_w=60.0,
    tooltip_pad=6.0,
    combo_max_h=300.0,
)


class Theme:
    # colours (straight alpha RGBA floats)
    text = hex_rgba('#ffffff')
    text_secondary = hex_rgba('#b3aaac')      # $clr-default
    text_disabled = hex_rgba('#7c7678')       # $clr-disabled
    accent = hex_rgba('#ff6600')              # $clr-hilight
    accent_hover = hex_rgba('#ff9900')
    accent_soft = hex_rgba('#ff6600', 0.35)
    icon_hilight = hex_rgba('#ffaf50')        # $clr-icon-hilight
    error = hex_rgba('#d34141')

    bg_window = hex_rgba('#2c2c2c', 0.97)     # $bcg-primary
    bg_header = hex_rgba('#262626')           # $bcg-dark
    header_hover = hex_rgba('#303030')
    bg_darker = hex_rgba('#1e1e1e')           # $bcg-darker
    bg_darkest = hex_rgba('#181818')          # $bcg-darkest
    bg_lighter = hex_rgba('#444444')          # $bcg-lighter
    bg_light = hex_rgba('#555555')            # $bcg-light

    frame = hex_rgba('#1e1e1e')
    frame_hover = hex_rgba('#2a2a2a')
    frame_active = hex_rgba('#333333')
    border = hex_rgba('#3c3c3c')
    button = hex_rgba('#3a3a3a')
    button_hover = hex_rgba('#4a4a4a')
    button_active = hex_rgba('#555555')
    separator = hex_rgba('#3e3e3e')
    menu_bg = hex_rgba('#232323', 0.98)
    menu_hover = hex_rgba('#3d3d3d')
    dim = (0.0, 0.0, 0.0, 0.45)               # modal background darken
    tooltip_bg = hex_rgba('#181818', 0.96)
    toast_bg = hex_rgba('#232323', 0.95)
    scrollbar = hex_rgba('#555555', 0.8)
    selection = hex_rgba('#ff6600', 0.40)
    histogram_bar = hex_rgba('#b3aaac', 0.85)
    histogram_sel = hex_rgba('#ff6600', 0.95)
    axis_colors = (hex_rgba('#e54f4f'), hex_rgba('#5cc45c'), hex_rgba('#4f86e5'))

    def __init__(self, scale: float = 1.0):
        self.scale = 1.0
        self.set_scale(scale)

    def set_scale(self, scale: float):
        self.scale = max(0.5, float(scale))
        for k, v in BASE_METRICS.items():
            setattr(self, k, v * self.scale)

    def s(self, v: float) -> float:
        """Scale a logical size into framebuffer pixels."""
        return v * self.scale
