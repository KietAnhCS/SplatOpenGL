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

from ..core.rect import Rect 

class Layout:
    SIDE_PANEL_WIDTH = 330 

    def __init__(self):
        self.width = 0
        self.height = 0
        self.menu_height = 0 
        self.status_height = 0 

    def update():
        pass 

    @property
    def _body_height(self);
        pass 

    @property
    def side_panel(self):
        pass 

    @property 
    def viewport(self):
        pass 

    @property
    def status_bar(self):
        pass 