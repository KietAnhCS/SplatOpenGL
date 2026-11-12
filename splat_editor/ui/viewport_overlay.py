"""Vẽ chồng lên vùng 3D: gợi ý khi cảnh trống, nhãn chế độ cọ và vòng tròn cọ quanh chuột."""

"""
overlay = ViewportOverlay(app)
overlay.draw(layout.viewport)           # gọi mỗi khung hình: gợi ý khi cảnh trống, nhãn "Brush", vòng tròn cọ
"""

from imgui_bundle import imgui

from .widgets import color_u32


class ViewportOverlay:
    SELECT_COLOR = (1.0, 0.8, 0.1, 1.0)
    DESELECT_COLOR = (1.0, 0.35, 0.3, 1.0)
    HINT_COLOR = (0.75, 0.75, 0.8, 1.0)
    EMPTY_HINT = ["No scene loaded",
                  "File > Open (Ctrl+O), or drag and drop .ply files here"]
    BRUSH_HINT = "BRUSH   Left drag: select   Ctrl: deselect   [ ]: size   Esc: exit"

    def __init__(self, app):
        self.app = app

    def draw(self, rect):
        if rect.is_empty:
            return
        if self.app.editor.scene.is_empty:
            self._draw_empty_hint(rect)
        if self.app.editor.brush.active:
            self._draw_brush_hint(rect)
            self._draw_brush_cursor(rect)
        if self.app.mode == "survival":
            self._draw_survival(rect)
        if not self.app.editor.scene.is_empty:
            self._draw_coords(rect)
        lighting = self.app.lighting
        if lighting.enabled and lighting.sun_on:
            self._draw_clock(rect, lighting)

    def _draw_empty_hint(self, rect):
        draw_list = imgui.get_background_draw_list()
        cx, cy = rect.center
        line_height = imgui.get_text_line_height_with_spacing()
        y = cy - line_height * len(self.EMPTY_HINT) / 2
        for i, line in enumerate(self.EMPTY_HINT):
            width = imgui.calc_text_size(line).x
            color = self.HINT_COLOR if i == 0 else (0.5, 0.5, 0.55, 1.0)
            draw_list.add_text(imgui.ImVec2(cx - width / 2, y), color_u32(color), line)
            y += line_height

    def _draw_brush_hint(self, rect):
        draw_list = imgui.get_background_draw_list()
        size = imgui.calc_text_size(self.BRUSH_HINT)
        pos = imgui.ImVec2(rect.left + (rect.width - size.x) / 2, rect.top + 10)
        pad = 6
        draw_list.add_rect_filled(imgui.ImVec2(pos.x - pad * 2, pos.y - pad),
                                  imgui.ImVec2(pos.x + size.x + pad * 2, pos.y + size.y + pad),
                                  color_u32((0.0, 0.0, 0.0, 0.55)), 4.0)
        draw_list.add_text(pos, color_u32(self.SELECT_COLOR), self.BRUSH_HINT)

    def _draw_brush_cursor(self, rect):
        io = imgui.get_io()
        brush = self.app.editor.brush
        if io.want_capture_mouse or not rect.contains(io.mouse_pos.x, io.mouse_pos.y):
            return
        erase = brush.painting is False or (brush.painting is None and io.key_ctrl)
        color = self.DESELECT_COLOR if erase else self.SELECT_COLOR
        imgui.get_foreground_draw_list().add_circle(io.mouse_pos, brush.radius, color_u32(color), 0, 1.5)

    def _draw_survival(self, rect):
        draw_list = imgui.get_background_draw_list()
        cx, cy = rect.center
        white = color_u32((1.0, 1.0, 1.0, 0.85))
        draw_list.add_line(imgui.ImVec2(cx - 8, cy), imgui.ImVec2(cx + 8, cy), white, 1.5)      # tâm ngắm
        draw_list.add_line(imgui.ImVec2(cx, cy - 8), imgui.ImVec2(cx, cy + 8), white, 1.5)
        if self.app.physics.ready:
            return
        text = "WALK   " + self.app.physics.status
        size = imgui.calc_text_size(text)
        pos = imgui.ImVec2(rect.left + (rect.width - size.x) / 2, rect.top + 10)
        pad = 6
        draw_list.add_rect_filled(imgui.ImVec2(pos.x - pad * 2, pos.y - pad),
                                  imgui.ImVec2(pos.x + size.x + pad * 2, pos.y + size.y + pad),
                                  color_u32((0.0, 0.0, 0.0, 0.55)), 4.0)
        draw_list.add_text(pos, color_u32((0.55, 0.9, 0.55, 1.0)), text)

    def _draw_coords(self, rect):
        """Tọa độ XYZ của người đang đứng (vị trí camera) ở góc dưới trái vùng 3D."""
        x, y, z = self.app.viewport.camera.position()
        text = f"X {x:8.2f}   Y {y:8.2f}   Z {z:8.2f}"
        size = imgui.calc_text_size(text)
        pos = imgui.ImVec2(rect.left + 14, rect.top + rect.height - size.y - 14)
        draw_list = imgui.get_background_draw_list()
        draw_list.add_rect_filled(imgui.ImVec2(pos.x - 8, pos.y - 5),
                                  imgui.ImVec2(pos.x + size.x + 8, pos.y + size.y + 5),
                                  color_u32((0.0, 0.0, 0.0, 0.55)), 4.0)
        draw_list.add_text(pos, color_u32((0.9, 0.95, 1.0, 1.0)), text)

    def _draw_clock(self, rect, lighting):
        hours, minutes = int(lighting.hour), int((lighting.hour % 1) * 60)
        text = f"{hours:02d}:{minutes:02d}  {lighting.cycle.state.value}"
        size = imgui.calc_text_size(text)
        pos = imgui.ImVec2(rect.left + rect.width - size.x - 20, rect.top + 10)
        draw_list = imgui.get_background_draw_list()
        draw_list.add_rect_filled(imgui.ImVec2(pos.x - 10, pos.y - 5),
                                  imgui.ImVec2(pos.x + size.x + 10, pos.y + size.y + 5),
                                  color_u32((0.0, 0.0, 0.0, 0.55)), 4.0)
        draw_list.add_text(pos, color_u32((1.0, 0.9, 0.6, 1.0)), text)
