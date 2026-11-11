"""Bảng cố định bên trái, gồm các mục thu gọn được (Layers, Transform, Selection, View)."""

"""
panel = SidePanel(app)                  # Layers / Transform / Selection / View
panel.draw(layout.side_panel)           # gọi mỗi khung hình với Rect bảng bên trái
"""

from imgui_bundle import imgui

from .sections import (LayersSection, SelectionSection, TransformSection, ViewSection)


class SidePanel:
    FLAGS = (imgui.WindowFlags_.no_move | imgui.WindowFlags_.no_resize | imgui.WindowFlags_.no_collapse |
             imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_saved_settings |
             imgui.WindowFlags_.no_bring_to_front_on_focus)

    def __init__(self, app):
        self.sections = [LayersSection(app), TransformSection(app), SelectionSection(app), ViewSection(app)]

    def draw(self, rect):
        imgui.set_next_window_pos(imgui.ImVec2(rect.left, rect.top))
        imgui.set_next_window_size(imgui.ImVec2(rect.width, rect.height))
        imgui.begin("##side_panel", None, self.FLAGS)
        for section in self.sections:
            if not section.is_visible():
                continue
            if imgui.collapsing_header(section.header, imgui.TreeNodeFlags_.default_open):
                imgui.spacing()
                section.draw()
                imgui.spacing()
        imgui.end()
