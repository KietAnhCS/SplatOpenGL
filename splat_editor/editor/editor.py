"""Editor: giữ cảnh, lịch sử hoàn tác, cọ chọn và thực hiện mọi thao tác chỉnh sửa.

Editor không biết gì về OpenGL hay giao diện: mỗi khi dữ liệu đổi, nó tăng
`geometry_version` / `selection_version`; Viewport so sánh số này để biết khi nào gửi lại lên GPU.
"""

import os 

from ..core.history import DeleteGaussianCommand , History 
from ..core.layer import Layer 
from ..core.scene import Scene 
from ..io.ply import PlyFile 
from .brush import BrushTool 

class Editor:
    def __init__(self, max_undo=20):
        self.scene = Scene()
        self.history = History(max_undo)
        self.brush = BrushTool()
        self.status = ""
        self.geometry_version = 0 
        self.selection_version = 0 
        self._splats = None 
        self._splats_version = -1 

# ------------------------------------------------------------------ trạng thái

# ------------------------------------------------------------------ file

# ------------------------------------------------------------------ lớp

# ------------------------------------------------------------------ vùng chọn (chỉ các lớp đang hiện)

# ------------------------------------------------------------------ xoá / hoàn tác