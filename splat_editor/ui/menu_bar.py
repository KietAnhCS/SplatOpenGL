"""Thanh menu trên cùng (File / Edit / View / Help), sinh từ danh sách hành động."""

"""
menu = MainMenuBar(actions)             # actions: ActionRegistry
menu_height = menu.draw()               # gọi trong khung ImGui mỗi khung hình; trả về chiều cao menu
"""

from imgui_bundle import imgui


class MainMenuBar:
    # None = đường kẻ ngăn cách
    MENUS = [
        ("File", ["open", "add", None, "save", None, "quit"]),
        ("Edit", ["undo", None, "select_all", "select_none", "invert_selection", None,
                  "delete_selected", "remove_layer"]),
        ("View", ["frame_scene", "frame_layer", None, "show_grid", "view_sh", "flip_y", None, "brush"]),
        ("Help", ["shortcuts"]),
    ]

    def __init__(self, actions):
        self.actions = actions

    def draw(self):
        """Vẽ menu, trả về chiều cao (pixel) của thanh menu."""
        height = 0
        if imgui.begin_main_menu_bar():
            for title, items in self.MENUS:
                if imgui.begin_menu(title):
                    for name in items:
                        if name is None:
                            imgui.separator()
                        else:
                            self._draw_item(name)
                    imgui.end_menu()
            height = imgui.get_window_size().y
            imgui.end_main_menu_bar()
        return height

    def _draw_item(self, name):
        action = self.actions[name]
        checked = action.checked() if action.checked else False
        clicked, _ = imgui.menu_item(action.label, action.shortcut, checked, action.enabled())
        if clicked:
            self.actions.trigger(name)
