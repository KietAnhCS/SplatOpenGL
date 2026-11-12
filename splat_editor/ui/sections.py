"""Các mục trong bảng bên trái. Mỗi mục là một lớp con của PanelSection."""

"""
# Mỗi mục là một lớp con của PanelSection, SidePanel gọi draw() lần lượt
sections = [LayersSection(app), TransformSection(app), SelectionSection(app),
            ViewSection(app)]
for s in sections:
    if s.is_visible():                  # ví dụ Transform chỉ hiện khi có lớp đang chọn
        s.draw()

# Thêm một mục mới:
class MySection(PanelSection):
    @property
    def header(self):
        return "My Section"

    def draw(self):
        ...                              # dùng self.editor, self.scene và imgui.*
"""

import math
from abc import ABC, abstractmethod

from imgui_bundle import imgui

from ..core.math3d import axis_angle_matrix
from . import widgets


class PanelSection(ABC):
    title = ""

    def __init__(self, app):
        self.app = app

    @property
    def editor(self):
        return self.app.editor

    @property
    def scene(self):
        return self.app.editor.scene

    @property
    def header(self):
        """Nhãn tiêu đề; phần sau '###' giữ ID cố định khi chữ thay đổi."""
        return f"{self.title}###{type(self).__name__}"

    def is_visible(self):
        return True

    @abstractmethod
    def draw(self):
        ...


# ----------------------------------------------------------------------------- lớp

class LayersSection(PanelSection):
    title = "Layers"
    MAX_VISIBLE_ROWS = 6

    @property
    def header(self):
        return f"Layers ({len(self.scene.layers)})###layers"

    def draw(self):
        scene = self.scene
        if scene.is_empty:
            imgui.text_disabled("No layers loaded yet.")
            imgui.text_disabled("Open a .ply file, or drag and drop\nfiles into the window.")
            if widgets.full_width_button("Open File..."):
                self.app.actions.trigger("open")
            return

        self._draw_list()
        clicked = widgets.button_row(["Add...", "Frame", "Remove"])
        if clicked == 0:
            self.app.actions.trigger("add")
        elif clicked == 1:
            self.app.actions.trigger("frame_layer")
        elif clicked == 2:
            self.app.actions.trigger("remove_layer")

    def _draw_list(self):
        scene = self.scene
        padding = imgui.ImVec2(6, 6)
        # tự co giãn theo số lớp, quá MAX_VISIBLE_ROWS dòng thì cuộn
        max_height = self.MAX_VISIBLE_ROWS * imgui.get_frame_height_with_spacing() + 2 * padding.y
        imgui.set_next_window_size_constraints(imgui.ImVec2(0, 0), imgui.ImVec2(1e9, max_height))

        imgui.push_style_var(imgui.StyleVar_.window_padding, padding)
        imgui.push_style_var(imgui.StyleVar_.selectable_text_align, imgui.ImVec2(0, 0.5))
        imgui.begin_child("##layer_list", imgui.ImVec2(-1, 0),
                          imgui.ChildFlags_.borders | imgui.ChildFlags_.auto_resize_y)
        for i, layer in enumerate(scene.layers):
            imgui.push_id(str(i))
            changed, layer.visible = imgui.checkbox("##visible", layer.visible)
            if changed:
                self.editor.notify_geometry_changed()
            widgets.tooltip("Show / hide this layer")

            imgui.same_line()
            count = f"{layer.count:,}"
            count_width = imgui.calc_text_size(count).x
            name_width = imgui.get_content_region_avail().x - count_width - imgui.get_style().item_spacing.x
            clicked, _ = imgui.selectable(layer.name, i == scene.active_index, 0,
                                          imgui.ImVec2(name_width, imgui.get_frame_height()))
            if clicked:
                scene.active_index = i
            if imgui.is_item_hovered() and imgui.is_mouse_double_clicked(imgui.MouseButton_.left):
                self.app.frame_scene(layer)
            widgets.tooltip(f"{layer.path or layer.name}\nDouble-click to frame")

            imgui.same_line()
            imgui.align_text_to_frame_padding()
            imgui.text_disabled(count)
            imgui.pop_id()
        imgui.end_child()
        imgui.pop_style_var(2)


# ----------------------------------------------------------------------------- biến đổi

class TransformSection(PanelSection):
    title = "Transform"
    LABEL_WIDTH = 70

    def is_visible(self):
        return self.scene.active_layer is not None

    def draw(self):
        layer = self.scene.active_layer
        t = layer.transform
        imgui.text_disabled(layer.name)

        imgui.push_item_width(-self.LABEL_WIDTH)
        changed = False
        c, t.position = imgui.drag_float3("Position", t.position, self.app.drag_speed(), format="%.3f")
        changed |= c
        c, t.rotation = imgui.drag_float3("Rotation", t.rotation, 0.5, format="%.1f")
        changed |= c
        widgets.tooltip("Degrees around the X, Y and Z axes")
        c, t.scale = imgui.drag_float("Scale", t.scale, 0.005, 0.001, 1000.0, format="%.3f")
        changed |= c
        imgui.pop_item_width()

        changed |= self._draw_level(t)

        if widgets.full_width_button("Reset Transform"):
            t.reset()
            changed = True
        if changed:
            self.editor.notify_transform_changed()

    def _draw_level(self, t):
        """Chỉnh cho model nằm ngang: xoay theo hướng đang nhìn, quanh điểm camera đang nhìn vào.

        Roll: quanh trục nhìn tới (nằm ngang)  -> đường chân trời nghiêng trái / phải trên màn hình.
        Pitch: quanh trục ngang của màn hình   -> mặt sàn chúi về phía mình / ngửa ra xa.
        """
        camera = self.app.viewport.camera
        s, c = math.sin(camera.yaw), math.cos(camera.yaw)
        axes = {"Roll": ([-s, 0.0, -c], "Tilt left / right as seen on screen.\n"
                                         "Drag right: clockwise."),
                "Pitch": ([-c, 0.0, s], "Tip forward / backward as seen on screen.\n"
                                         "Drag right: top tips away from you.")}

        imgui.separator_text("Level (relative to view)")
        spacing = imgui.get_style().item_spacing.x
        button_width = imgui.calc_text_size("-90").x + 2 * imgui.get_style().frame_padding.x
        changed = False
        for label, (axis, help_text) in axes.items():
            imgui.push_id(label)
            imgui.set_next_item_width(imgui.get_content_region_avail().x - self.LABEL_WIDTH
                                      - 2 * (button_width + spacing))
            # giá trị luôn bắt đầu từ 0 mỗi khung hình, phần kéo được chính là góc cần xoay thêm
            _, degrees = imgui.drag_float("##drag", 0.0, 0.1, format="<  drag  >",
                                          flags=imgui.SliderFlags_.no_input)
            widgets.tooltip(help_text + "\nShift: faster, Alt: finer")
            for step in (-90.0, 90.0):
                imgui.same_line()
                if imgui.button(f"{step:+.0f}", imgui.ImVec2(button_width, 0)):
                    degrees = step
            imgui.same_line()
            imgui.text(label)
            if degrees:
                t.rotate_about(axis_angle_matrix(axis, degrees), camera.target)
                changed = True
            imgui.pop_id()
        imgui.spacing()
        return changed


# ----------------------------------------------------------------------------- cọ chọn

class SelectionSection(PanelSection):
    title = "Selection"
    LABEL_WIDTH = 70

    def draw(self):
        brush = self.editor.brush
        _, brush.active = imgui.checkbox("Brush tool (B)", brush.active)
        imgui.push_item_width(-self.LABEL_WIDTH)
        _, brush.radius = imgui.slider_float("Size", brush.radius, brush.MIN_RADIUS, brush.MAX_RADIUS,
                                             "%.0f px", imgui.SliderFlags_.logarithmic)
        imgui.pop_item_width()
        widgets.tooltip("Brush radius in pixels  ( [ / ] )")
        if brush.active:
            imgui.text_disabled("Left drag: select     Ctrl + drag: deselect\n"
                                "Middle drag: orbit    Right drag: pan")

        imgui.spacing()
        selected = self.scene.selected_count()
        imgui.text(f"{selected:,} gaussians selected")
        clicked = widgets.button_row(["All", "None", "Invert"])
        if clicked is not None:
            self.app.actions.trigger(("select_all", "select_none", "invert_selection")[clicked])

        imgui.begin_disabled(selected == 0)
        if widgets.danger_button("Delete Selected"):
            self.app.actions.trigger("delete_selected")
        imgui.end_disabled()
        imgui.begin_disabled(not self.editor.history.can_undo)
        if widgets.full_width_button("Undo (Ctrl+Z)"):
            self.app.actions.trigger("undo")
        imgui.end_disabled()


# ----------------------------------------------------------------------------- hiển thị

class ViewSection(PanelSection):
    title = "View"
    LABEL_WIDTH = 90

    def draw(self):
        viewport = self.app.viewport
        _, viewport.show_grid = imgui.checkbox("Show grid (G)", viewport.show_grid)
        imgui.push_item_width(-self.LABEL_WIDTH)
        imgui.begin_disabled(not viewport.show_grid)
        _, viewport.grid.height = imgui.drag_float("Grid height", viewport.grid.height,
                                                   self.app.drag_speed(), format="%.3f")
        imgui.end_disabled()
        _, viewport.background = imgui.color_edit3("Background", viewport.background)
        imgui.pop_item_width()

        if widgets.full_width_button("Frame Scene (F)"):
            self.app.actions.trigger("frame_scene")
