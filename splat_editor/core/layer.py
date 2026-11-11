"""Một lớp (layer) = một file PLY đã mở, kèm phép biến đổi và vùng chọn riêng.

Quy ước toạ độ:
- "toạ độ file": toạ độ gốc trong file PLY.
- "toạ độ thế giới": toạ độ dùng để hiển thị (trục Y hướng lên, lưới nằm trên mặt y = 0).
  Nếu bật `flip`, toạ độ file được xoay 180 độ quanh trục Z (F = diag(-1,-1,1)) trước,
  vì phần lớn file 3DGS (từ COLMAP) có trục Y hướng xuống.
- Phép biến đổi của lớp (vị trí / góc xoay / tỉ lệ) tính trong toạ độ thế giới:
      p_thế_giới = s * R * F * p_file + t
- Khi lưu, ta đổi ngược về toạ độ file: p_lưu = F * p_thế_giới, nên file lưu ra vẫn
  cùng quy ước với file gốc (mở bằng phần mềm khác vẫn đúng chiều).
- Hệ số SH bậc cao (màu theo hướng nhìn) xoay cùng gaussian, cả khi vẽ lẫn khi lưu. Khi vẽ,
  phép xoay được ghi lại (Splats.sh_frames) và renderer xoay lúc gửi lên GPU, không giữ bản sao.
- Dữ liệu lớn (hàng chục triệu gaussian) được xử lý từng đoạn CHUNK hàng để RAM tạm nhỏ.

Xoá "mềm" (giống SuperSplat): xoá gaussian chỉ bật cờ `deleted`, mảng dữ liệu giữ nguyên, nên xoá /
hoàn tác gần như tức thì (không chép mảng, không dựng lại LOD, không gửi lại dữ liệu lên GPU).
Gaussian đã xoá bị bỏ qua khi vẽ, khi chọn và khi lưu file. `size` = số hàng của mảng (kể cả đã
xoá, dùng để đánh chỉ số); `count` = số gaussian còn lại.
"""

"""
layer = Layer.from_file("scene.ply")   # đọc PLY (memmap) + giải mã thành layer.splats
layer.count                             # số gaussian còn lại (chưa xoá)

layer.transform.position = [0, 1, 0]   # kéo lớp lên 1 đơn vị (không phải gửi lại dữ liệu lên GPU)
layer.transform.rotation = [0, 90, 0]  # xoay 90 độ quanh Y
layer.transform.scale = 2.0

layer.select_all()                      # chọn tất cả (trừ cái đã xoá)
layer.invert_selection()
indices = layer.delete_selected()      # xoá mềm; trả về chỉ số để hoàn tác (None nếu không chọn gì)
layer.restore(indices)                 # hoàn tác

world = layer.world_splats(flip=False) # gaussian ở toạ độ thế giới (đã áp biến đổi, bỏ cái đã xoá)
M = layer.world_matrix(flip=False)     # ma trận 4x4: p_thế_giới = M @ (p_file, 1)
"""

import math
import os 
from typing import NamedTuple 

import numpy as np 

from ..io.codec import SplatCodec 
from ..io.ply import PlyFile 
from .math3d import matrix_to_quat, quat_mul 
from .splats import Splats 
from .transform import Transform 

FLIP = np.diag([-1.0, -1.0, 1.0])

class LayerSnapshot(NameTuple):
    pass 

class Layer:
    def __init__(self, name, data, path= None):
        self.name = name 
        self.path = path 
        self.data = data 
        self.splats = SplatCodec.decode(data)
        self.selection = np.zeros(self.splat.count, bool)
        self.visible = True 
        self.transform = Transform()

    @classmethod 
    def from_file(cls, path):
        return cls(os.path.basename(path), PlyFile.read(path), path)

    @property 
    def count(self):
        return self.splats.count 

    # ------------------------------------------------------------------ vùng chọn

    # ------------------------------------------------------------------ biến đổi