"""Cảnh gồm nhiều lớp. Các lớp đang hiện được gộp thành một mảng để vẽ / chọn / lưu."""

"""
scene = Scene()
scene.add(Layer.from_file("a.ply"))    # mỗi file là một lớp
scene.add(Layer.from_file("b.ply"))
scene.active_layer                      # lớp đang chọn trong bảng Layers
scene.visible_layers()                  # các lớp đang hiện

scene.flip = True                       # lật trục Y (cho dữ liệu COLMAP)
splats = scene.world_splats()           # gộp các lớp đang hiện ở toạ độ thế giới
scene.selected_count()                  # tổng số gaussian đang chọn

dtype = scene.export_dtype()           # kiểu cột dùng khi lưu
scene.remove(0)                         # xoá lớp thứ 0
scene.clear()
"""

import numpy as np 

from ..io.codec import CANONICAL_FIELDS 
from .splats import Splats

class Scene:
    def __init__(self):
        pass 



    def world_splats(self):
        parts = [layer.world_splats(self.flip) for layer in self.visible_layers()]
        return Splats.concat(parts) if parts else None 