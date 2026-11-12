"""Font và màu sắc của giao diện ImGui."""

"""
Theme.apply()                           # gọi một lần sau khi tạo ngữ cảnh ImGui: nạp font, áp màu
# Đổi màu chủ đạo: sửa Theme.ACCENT hoặc Theme.COLORS rồi gọi lại apply()
"""

import os

from imgui_bundle import imgui


class Theme:
    FONT_SIZE = 16.0
    FONT_CANDIDATES = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    ACCENT = (0.28, 0.52, 0.90)
    COLORS = {
        imgui.Col_.window_bg: (0.11, 0.11, 0.13, 1.00),
        imgui.Col_.child_bg: (0.09, 0.09, 0.11, 1.00),
        imgui.Col_.popup_bg: (0.12, 0.12, 0.14, 0.98),
        imgui.Col_.menu_bar_bg: (0.15, 0.15, 0.18, 1.00),
        imgui.Col_.border: (0.22, 0.22, 0.26, 1.00),
        imgui.Col_.frame_bg: (0.18, 0.18, 0.21, 1.00),
        imgui.Col_.frame_bg_hovered: (0.24, 0.24, 0.28, 1.00),
        imgui.Col_.frame_bg_active: (0.28, 0.28, 0.33, 1.00),
        imgui.Col_.button: (0.21, 0.21, 0.25, 1.00),
        imgui.Col_.button_hovered: (0.28, 0.40, 0.62, 1.00),
        imgui.Col_.button_active: (*ACCENT, 1.00),
        imgui.Col_.header: (0.22, 0.30, 0.45, 1.00),
        imgui.Col_.header_hovered: (0.27, 0.38, 0.58, 1.00),
        imgui.Col_.header_active: (*ACCENT, 1.00),
        imgui.Col_.check_mark: (0.45, 0.68, 1.00, 1.00),
        imgui.Col_.slider_grab: (*ACCENT, 1.00),
        imgui.Col_.slider_grab_active: (0.45, 0.68, 1.00, 1.00),
        imgui.Col_.separator: (0.22, 0.22, 0.26, 1.00),
        imgui.Col_.text_disabled: (0.55, 0.55, 0.60, 1.00),
    }

    # màu cho nút nguy hiểm (xoá)
    DANGER = (0.55, 0.20, 0.20, 1.00)
    DANGER_HOVERED = (0.70, 0.25, 0.25, 1.00)

    @classmethod
    def apply(cls):
        cls._load_font()
        imgui.style_colors_dark()
        style = imgui.get_style()
        style.window_rounding = 0.0
        style.child_rounding = 4.0
        style.frame_rounding = 4.0
        style.popup_rounding = 4.0
        style.grab_rounding = 4.0
        style.scrollbar_rounding = 4.0
        style.window_border_size = 0.0
        style.window_padding = imgui.ImVec2(10, 10)
        style.frame_padding = imgui.ImVec2(8, 4)
        style.item_spacing = imgui.ImVec2(8, 6)
        style.item_inner_spacing = imgui.ImVec2(6, 4)
        for index, color in cls.COLORS.items():
            style.set_color_(index, imgui.ImVec4(*color))

    @classmethod
    def _load_font(cls):
        io = imgui.get_io()
        for path in cls.FONT_CANDIDATES:
            if os.path.exists(path):
                io.fonts.add_font_from_file_ttf(path, cls.FONT_SIZE)
                return
