"""Bố cục màn hình: menu trên cùng, bảng bên trái, thanh trạng thái dưới cùng, phần còn lại là vùng 3D.

    +--------------------------------------+
    | menu bar                             |
    +-----------+--------------------------+
    | side      |                          |
    | panel     |      3D viewport         |
    |           |                          |
    +-----------+--------------------------+
    | status bar                           |
    +--------------------------------------+
"""

"""
layout = Layout()
layout.update(width, height, menu_height, status_height)   # gọi mỗi khung hình
layout.side_panel                       # Rect bảng bên trái
layout.viewport                         # Rect vùng 3D
layout.status_bar                       # Rect thanh trạng thái
"""

from ..core.rect import Rect


class Layout:
    SIDE_PANEL_WIDTH = 330

    def __init__(self):
        self.width = 0
        self.height = 0
        self.menu_height = 0
        self.status_height = 0

    def update(self, width, height, menu_height, status_height):
        self.width, self.height = width, height
        self.menu_height, self.status_height = menu_height, status_height

    @property
    def _body_height(self):
        return max(self.height - self.menu_height - self.status_height, 0)

    @property
    def side_panel(self):
        return Rect(0, self.menu_height, min(self.SIDE_PANEL_WIDTH, self.width), self._body_height)

    @property
    def viewport(self):
        left = self.side_panel.width
        return Rect(left, self.menu_height, max(self.width - left, 0), self._body_height)

    @property
    def status_bar(self):
        return Rect(0, self.height - self.status_height, self.width, self.status_height)
