"""Các widget ImGui nhỏ dùng lại nhiều nơi."""

"""
if full_width_button("Reset"):          # nút rộng hết bảng
    ...
if danger_button("Delete"):             # nút màu đỏ
    ...
clicked = button_row(["All", "None", "Invert"])   # một hàng nút; trả về chỉ số nút được bấm hoặc None
tooltip("Giải thích hiện khi rê chuột")
color = color_u32((1.0, 0.8, 0.2, 1.0))   # RGBA 0..1 -> số nguyên cho draw list của ImGui
"""

from imgui_bundle import imgui

from .theme import Theme


def full_width_button(label):
    return imgui.button(label, imgui.ImVec2(-1, 0))


def button_row(labels):
    """Một hàng nút chia đều chiều ngang. Trả về chỉ số nút được bấm hoặc None."""
    spacing = imgui.get_style().item_spacing.x
    width = (imgui.get_content_region_avail().x - spacing * (len(labels) - 1)) / len(labels)
    clicked = None
    for i, label in enumerate(labels):
        if i:
            imgui.same_line()
        if imgui.button(label, imgui.ImVec2(width, 0)):
            clicked = i
    return clicked


def danger_button(label):
    """Nút toàn chiều ngang màu đỏ (thao tác xoá)."""
    imgui.push_style_color(imgui.Col_.button, imgui.ImVec4(*Theme.DANGER))
    imgui.push_style_color(imgui.Col_.button_hovered, imgui.ImVec4(*Theme.DANGER_HOVERED))
    clicked = full_width_button(label)
    imgui.pop_style_color(2)
    return clicked


def tooltip(text):
    """Hiện tooltip cho widget vừa vẽ khi rê chuột lên."""
    imgui.set_item_tooltip(text.replace('%', '%%'))


def color_u32(rgba):
    return imgui.color_convert_float4_to_u32(imgui.ImVec4(*rgba))
