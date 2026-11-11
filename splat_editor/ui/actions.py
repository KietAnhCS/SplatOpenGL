"""Hành động (mẫu Command): một nơi khai báo nhãn, phím tắt và hàm xử lý.

Menu, nút bấm, phím tắt và bảng "Keyboard Shortcuts" đều dùng chung danh sách này,
nên không bao giờ bị lệch nhau.
"""

"""
actions = ActionRegistry()
actions.add("open", Action("Open...", open_dialog, "File", "Ctrl+O", glfw.KEY_O, ctrl=True, deferred=True))
actions.add("grid", Action("Show Grid", toggle_grid, "View", "G", glfw.KEY_G,
                           checked=lambda: viewport.show_grid))

actions.trigger("open")                 # từ menu hoặc nút bấm
actions.handle_key(glfw.KEY_O, ctrl=True)   # từ bàn phím; True nếu có hành động khớp
actions.run_pending()                   # cuối mỗi khung hình: chạy các hành động deferred (hộp thoại file)
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Action:
    label: str
    callback: Callable[[], None]
    category: str = "General"
    shortcut: str = ""                          # chữ hiển thị, ví dụ "Ctrl+O"
    key: Optional[int] = None                   # phím GLFW
    ctrl: bool = False
    description: str = ""                       # mô tả trong bảng phím tắt (mặc định = label)
    deferred: bool = False                      # chạy sau khung hình (mở hộp thoại hệ thống)
    enabled: Callable[[], bool] = lambda: True
    checked: Optional[Callable[[], bool]] = None  # mục bật / tắt trong menu


class ActionRegistry:
    def __init__(self):
        self._actions = {}
        self._pending = []

    def add(self, name, action):
        self._actions[name] = action

    def __getitem__(self, name):
        return self._actions[name]

    def __iter__(self):
        return iter(self._actions.values())

    def trigger(self, name):
        action = self._actions[name]
        if not action.enabled():
            return
        if action.deferred:
            # hộp thoại chọn file chạy ngoài khung hình để không làm hỏng trạng thái ImGui
            self._pending.append(action.callback)
        else:
            action.callback()

    def handle_key(self, key, ctrl):
        """Chạy hành động gắn với phím. Trả về True nếu có hành động khớp."""
        for name, action in self._actions.items():
            if action.key == key and action.ctrl == bool(ctrl):
                self.trigger(name)
                return True
        return False

    def run_pending(self):
        while self._pending:
            self._pending.pop(0)()
