"""Cửa sổ "Keyboard Shortcuts" (F1). Danh sách phím lấy trực tiếp từ ActionRegistry."""

"""
shortcuts = ShortcutsWindow(actions)    # danh sách phím lấy từ ActionRegistry
shortcuts.toggle()                      # F1 bật / tắt
shortcuts.draw()                        # gọi mỗi khung hình
"""

from imgui_bundle import imgui


class ShortcutsWindow:
    MOUSE = [
        ("Right drag", "Look around (fly mode, like Minecraft)"),
        ("W A S D", "Fly forward / left / back / right"),
        ("Space", "Fly up"),
        ("Shift", "Fly down"),
        ("Ctrl (in fly mode)", "Fly faster"),
        ("Left drag", "Orbit around the target"),
        ("Middle drag", "Pan"),
        ("Drop .ply files", "Add files to the scene"),
    ]
    BRUSH_MOUSE = [
        ("Left drag", "Select gaussians"),
        ("Ctrl + left drag", "Deselect gaussians"),
        ("Middle drag", "Orbit (while the brush is on)"),
    ]
    KEY_COLUMN_WIDTH = 150

    def __init__(self, actions):
        self.actions = actions
        self.visible = False

    def toggle(self):
        self.visible = not self.visible

    def draw(self):
        if not self.visible:
            return
        center = imgui.get_main_viewport().get_center()
        imgui.set_next_window_pos(center, imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        imgui.set_next_window_size(imgui.ImVec2(500, 640), imgui.Cond_.appearing)
        expanded, self.visible = imgui.begin("Keyboard Shortcuts", self.visible,
                                             imgui.WindowFlags_.no_collapse | imgui.WindowFlags_.no_saved_settings)
        if expanded:
            self._table("Camera", self.MOUSE)
            self._table("Brush", self.BRUSH_MOUSE)
            categories = {}
            for action in self.actions:
                if action.key is not None:
                    categories.setdefault(action.category, []).append(
                        (action.shortcut, action.description or action.label))
            for category, rows in categories.items():
                self._table(category, rows)
        imgui.end()

    def _table(self, title, rows):
        imgui.separator_text(title)
        if imgui.begin_table(title, 2, imgui.TableFlags_.row_bg):
            imgui.table_setup_column("Key", imgui.TableColumnFlags_.width_fixed, self.KEY_COLUMN_WIDTH)
            imgui.table_setup_column("Action", imgui.TableColumnFlags_.width_stretch)
            for key, description in rows:
                imgui.table_next_row()
                imgui.table_next_column()
                imgui.text(key)
                imgui.table_next_column()
                imgui.text_disabled(description)
            imgui.end_table()
