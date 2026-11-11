"""Thanh trạng thái dưới cùng: thông báo gần nhất bên trái, thống kê bên phải."""

"""
bar = StatusBar(app)
height = bar.height()                   # chiều cao để Layout chừa chỗ
bar.draw(layout.status_bar)             # trái: thông báo; phải: số gaussian | đã chọn | FPS
"""

from imgui_bundle import imgui


class StatusBar:
    PADDING = imgui.ImVec2(10, 5)
    FLAGS = (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_move |
             imgui.WindowFlags_.no_saved_settings | imgui.WindowFlags_.no_bring_to_front_on_focus |
             imgui.WindowFlags_.no_nav)

    def __init__(self, app):
        self.app = app

    def height(self):
        return imgui.get_text_line_height() + 2 * self.PADDING.y

    def draw(self, rect):
        editor = self.app.editor
        imgui.set_next_window_pos(imgui.ImVec2(rect.left, rect.top))
        imgui.set_next_window_size(imgui.ImVec2(rect.width, rect.height))
        imgui.push_style_var(imgui.StyleVar_.window_padding, self.PADDING)
        imgui.push_style_color(imgui.Col_.window_bg, imgui.get_style().color_(imgui.Col_.menu_bar_bg))
        imgui.begin("##status_bar", None, self.FLAGS)

        stats = (f"{editor.total_count:,} gaussians    |    "
                 f"{editor.scene.selected_count():,} selected    |    "
                 f"{self.app.fps.value:.0f} FPS")
        stats_width = imgui.calc_text_size(stats).x
        message_width = rect.width - stats_width - 4 * self.PADDING.x
        imgui.text(self._fit(editor.status, message_width))
        imgui.same_line(rect.width - stats_width - self.PADDING.x)
        imgui.text_disabled(stats)

        imgui.end()
        imgui.pop_style_color()
        imgui.pop_style_var()

    @staticmethod
    def _fit(text, width):
        """Cắt bớt chữ (thêm '...') cho vừa `width` pixel."""
        text = text.replace('%', '%%')
        if imgui.calc_text_size(text).x <= width:
            return text
        while text and imgui.calc_text_size(text + "...").x > width:
            text = text[:-1]
        return text + "..."
