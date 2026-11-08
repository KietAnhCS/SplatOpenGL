"""Vẽ Gaussian splat bằng OpenGL 3.3, đủ nhanh cho cảnh 10-15 triệu gaussian trên máy yếu.

Ý tưởng:
1. Mỗi gaussian 3D có tâm, màu, độ đục, scale và quaternion. Dữ liệu được nén còn 32 byte /
   gaussian (2 texel RGBA32UI: tâm float32, còn lại half float / 8 bit) và đưa lên GPU một lần,
   xếp theo thứ tự Morton của LodIndex ("vị trí"), để gaussian gần nhau nằm gần nhau trong bộ nhớ.
   Hệ số SH bậc cao lượng tử 8 bit (1 texel RGBA8 / hệ số); nếu quá ngân sách bộ nhớ
   (SH_VRAM_BUDGET) thì tự hạ bậc SH.
2. LOD (xem lod.py, sorter.py): mỗi khi camera đổi, luồng nền chọn tối đa `budget` gaussian
   (bỏ khối ngoài khung nhìn, khối xa lấy ít) rồi sắp xếp xa -> gần.
3. Pass 1 (transform feedback): mỗi gaussian được chọn chạy vertex shader MỘT lần, theo thứ tự
   bộ nhớ (đọc liền mạch), chiếu Sigma = R S S^T R^T xuống màn hình thành ellipse 2D
   (Sigma' = J W Sigma W^T J^T) và tính màu (kể cả SH, vùng chọn), ghi 32 byte vào buffer.
   Camera đứng yên thì bỏ qua pass này.
4. Pass 2: theo thứ tự xa -> gần, mỗi gaussian vẽ một hình vuông (4 đỉnh, instancing) kéo theo
   2 trục ellipse; fragment shader tô theo hàm gauss exp(-r^2/2) và trộn alpha (premultiplied).
5. Trạng thái mỗi gaussian nằm ở một texture buffer riêng, 1 byte / gaussian, để cập nhật nhanh:
   bit STATE_SELECTED (đang chọn, pha màu vàng) và bit STATE_DELETED (đã xoá mềm: luồng sắp xếp
   bỏ qua, pass 1 loại bỏ). Xoá / hoàn tác chỉ gửi lại mảng này, không gửi lại dữ liệu gaussian.
"""

"""
renderer = SplatRenderer()              # cần ngữ cảnh GL
renderer.set_splats(splats, lod)        # gửi gaussian lên GPU (texture buffer) khi mở file / xoá
renderer.set_transforms(layer_matrices) # phép biến đổi mỗi lớp (đổi là xong, không gửi lại dữ liệu)
renderer.set_selection(mask)            # tô vàng các gaussian đang chọn
renderer.set_deleted(mask)              # ẩn các gaussian đã xoá

# Mỗi khung hình
renderer.draw(model_view, projection, width, height)   # glDrawArraysInstanced: 4 góc x N instance
renderer.adapt_budget(target_ms)        # chế độ Auto: chỉnh số gaussian vẽ theo thời gian GPU
renderer.use_sh = False                 # tắt màu theo hướng nhìn
"""

import ctypes 
import os 
from collections import deque 
from concurrent.futures import ThreadPoolExecutor

import numpy as np 
from OpenGL import GL

from ..core import sh
from ..core.lod import LodIndex 
from .shader import ShaderProgram 
from .sorter import DepthSorter

UPLOAD_CHUNK = 1 << 18
SH_VRAM_BUDGET = 512 * 1024 * 1024 
FEEDBACK_STRIDE = 32 
MIN_BUDGET = 200_000 
STATE_SELECTED =1 
STATE_DELETED = 2  

class SplatRenderer:
    SELECT_COLOR = (1.0, 0.8, 0.1)

    def __init__(self):
        self.prep_shader = ShaderProgram.load("splat_prep", fragment=False, 
                                              feedback_varyings=["vCenterMajor", "vMinorExtent", "vColor"])
        self.shader = ShaderProgram.load("splat")
        self.count = 0
        self.sh_degree = 0
        self.sh_scale = 0.0 
        self.use_sh = True 
        self.budget = 2_000_000
        self.prep_count = 0 
        self.draw_count = 0 
        self.last_sort_key = None 
        self.sorter = DepthSorter()
        self._slot_order = None 
        self._order_version = 0 
        self._prep_key = None 
        self._capacity = 0 
        self._state = None 
        self._slot_of = None 

        self._queries = list(GL.glGenQueries(4))
        self._query_pending = []
        self.gpu_ms = None 
        self._sample = []

        self.slot_vbo = GL.glGenBuffers(1)
        self.rank_vbo = GL.glGenBuffers(1)
        self.feedback_buffer = GL.glGenBuffers(1)
        self.feedback_texture = GL.glGenTextures(1)

        
        # pass 1: mỗi đỉnh (GL_POINTS) = một vị trí gaussian
        self.prep_vao = GL.glGenVertexArray(1)
        GL.glBindVertexArray(self.prep_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.slot_vbo)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribIPointer(0, 1, GL.GL_UNSIGNED_INT, 0,0, ctype.c_void_p(0))

        # pass 2: 4 góc hình vuông + mỗi instance một chỉ số vào kết quả pass 1
        corners = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)   # triangle strip
        self.corner_vbo = GL.glGenBuffers(1)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.corner_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, corners.nbytes, corners, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, ctypes.c_void_p(0))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.rank_vbo)
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribIPointer(1, 1, GL.GL_UNSIGNED_INT, 0, ctypes.c_void_p(0))
        GL.glVertexAttribDivisor(1, 1)
        GL.glBindVertexArray(0)

        
        # texture buffer chứa dữ liệu gaussian, vùng chọn và hệ số SH
        self.data_buffer = GL.glGenBuffers(1)
        self.data_texture = GL.glGenTextures(1)
        self.state_buffer = GL.glGenBuffers(1)
        self.state_texture = GL.glGenTextures(1)
        self.sh_buffer = GL.glGenBuffers(1)
        self.sh_texture = GL.glGenTextures(1)
        self.transform_buffer = GL.glGenBuffers(1)     # ma trận thế giới của các lớp (4 texel / lớp)
        self.transform_texture = GL.glGenTextures(1)
        self.transforms = np.identity(4)[None]

    # ------------------------------------------------------------------ dữ liệu
    @staticmethod
    def pack(splats, index=slice(None), layers=0):
        """Splats -> mảng (N,16) float32 = 4 texel RGBA / gaussian."""
        pass 

    @staticmethod 
    def _upload_chunked(buffer, count, bytes_per_item, make_chunk):
        pass



    def set_splats(self, splats):
        pass 

    def _upload_sh(self, splats, order):
        pass 

    def _upload_state(self, resize= False, lo=0, hi=None):
        pass 

    def _set_state_bit(self, bit, mask):
        pass 

    def set_selection(self, mask, resize=False):
        pass 

    def set_delete(self, mask):
        pass 

    def _upload_selection(self, order):
        pass 

    def set_transforms(self, matrices):
        pass 

    def _upload_order(self, slots, ranks):
        pass 

    def _update_order(self, model_view, projection):
        pass 

    def _prepare(self, model_view, projection, width, height):
        pass

    def _collect_timing(self):
        pass 

    def adapth_budget(self, target_ms):
        pass 

    def draw(self, model_view, projection, width, height):
        pass 

    def _draw_splats(self):
        pass

    