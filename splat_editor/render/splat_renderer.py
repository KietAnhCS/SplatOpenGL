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

UPLOAD_CHUNK = 1 << 18              # gửi lên GPU từng đoạn 262144 gaussian (RAM tạm nhỏ)
SH_VRAM_BUDGET = 512 * 1024 * 1024  # bộ nhớ GPU tối đa cho hệ số SH
FEEDBACK_STRIDE = 32                # byte / gaussian trong buffer kết quả pass 1 (2 texel RGBA32UI)
MIN_BUDGET = 200_000                # chế độ tự động không hạ budget thấp hơn mức này
STATE_SELECTED = 1                  # các bit trạng thái (1 byte / gaussian, xem splat_prep.vert)
STATE_DELETED = 2
SHADOW_SIZE = 2048                  # độ phân giải bản đồ bóng của mặt trời


class SplatRenderer:
    SELECT_COLOR = (1.0, 0.8, 0.1)

    def __init__(self):
        self.prep_shader = ShaderProgram.load("splat_prep", fragment=False,
                                              feedback_varyings=["vCenterMajor", "vMinorExtent", "vColor"])
        self.shader = ShaderProgram.load("splat")
        self.shadow_shader = ShaderProgram.load("shadow")
        self.lighting = {'enabled': False, 'signature': (False,)}   # xem core/lighting.py
        self._shadow_fbo = None
        self._shadow_texture = None
        self._shadow_key = None
        self.count = 0
        self.sh_degree = 0           # bậc SH của dữ liệu đang có trên GPU
        self.file_sh_degree = 0      # bậc SH của dữ liệu gốc (có thể cao hơn nếu bị hạ cho đỡ tốn bộ nhớ)
        self.sh_scale = 0.0
        self.use_sh = True           # tắt: chỉ dùng màu bậc 0 (không đổi theo hướng nhìn)
        self.budget = 2_000_000      # số gaussian tối đa vẽ mỗi khung hình (None: không giới hạn)
        self.prep_count = 0          # số gaussian pass 1 xử lý (đã chọn theo LOD)
        self.draw_count = 0          # số gaussian pass 2 vẽ (bỏ cái sau camera)
        self.last_sort_key = None
        self.sorter = DepthSorter()
        self._slot_order = None      # vị trí trên GPU -> chỉ số gaussian gốc
        self._order_version = 0      # tăng khi danh sách gaussian / vùng chọn đổi -> phải chạy lại pass 1
        self._prep_key = None
        self._capacity = 0
        self._state = None           # trạng thái theo vị trí (uint8, STATE_*), bản sao trên CPU
        self._slot_of = None
        # đo thời gian GPU (GL_TIME_ELAPSED) không chặn: vòng các query, đọc kết quả khi đã sẵn sàng
        self._queries = list(GL.glGenQueries(4))
        self._query_pending = []     # [(query, có chạy pass 1 không)]
        self.gpu_ms = None           # thời gian GPU gần nhất của khung hình có chạy pass 1 (xấu nhất)
        self._samples = []

        self.slot_vbo = GL.glGenBuffers(1)        # vị trí các gaussian được chọn (đầu vào pass 1)
        self.rank_vbo = GL.glGenBuffers(1)        # thứ tự vẽ xa -> gần (đầu vào pass 2)
        self.feedback_buffer = GL.glGenBuffers(1)  # kết quả pass 1
        self.feedback_texture = GL.glGenTextures(1)

        # pass 1: mỗi đỉnh (GL_POINTS) = một vị trí gaussian
        self.prep_vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.prep_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.slot_vbo)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribIPointer(0, 1, GL.GL_UNSIGNED_INT, 0, ctypes.c_void_p(0))

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
        """Gaussian `index` -> mảng (n,8) uint32 = 2 texel RGBA32UI / gaussian:
        texel 0: x y z (float32, toạ độ file của lớp), r g (half)
        texel 1: b alpha (half), sx sy (half), sz (half) | số thứ tự lớp (16 bit),
                 quaternion w x y z (4 x snorm8)."""
        half = lambda a: np.ascontiguousarray(a, np.float16).view(np.uint16).astype(np.uint32)  # noqa: E731
        pair = lambda lo, hi: half(lo) | (half(hi) << np.uint32(16))                           # noqa: E731
        positions, colors, scales = splats.positions[index], splats.colors[index], splats.scales[index]
        q = np.clip(np.rint(splats.rotations[index] * 127.0) + 128, 1, 255).astype(np.uint32)
        packed = np.empty((len(positions), 8), np.uint32)
        packed[:, 0:3] = np.ascontiguousarray(positions, np.float32).view(np.uint32)
        packed[:, 3] = pair(colors[:, 0], colors[:, 1])
        packed[:, 4] = pair(colors[:, 2], splats.alphas[index])
        packed[:, 5] = pair(scales[:, 0], scales[:, 1])
        packed[:, 6] = half(scales[:, 2]) | (np.asarray(layers, np.uint32) << np.uint32(16))
        packed[:, 7] = q[:, 0] | (q[:, 1] << 8) | (q[:, 2] << 16) | (q[:, 3] << 24)
        return packed

    @staticmethod
    def _upload_chunked(buffer, count, bytes_per_item, make_chunk):
        """Cấp buffer rồi gửi dữ liệu từng đoạn (make_chunk(start, end) -> mảng numpy).
        Các đoạn được chuẩn bị song song ở nhiều luồng (numpy nhả GIL), luồng chính chỉ gửi lên GPU."""
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, buffer)
        GL.glBufferData(GL.GL_TEXTURE_BUFFER, max(count * bytes_per_item, 16), None, GL.GL_STATIC_DRAW)

        def _upload(start, future):
            chunk = future.result()
            GL.glBufferSubData(GL.GL_TEXTURE_BUFFER, start * bytes_per_item, chunk.nbytes, chunk)

        workers = min(max((os.cpu_count() or 2) - 1, 1), 6)
        make = lambda a: np.ascontiguousarray(make_chunk(a, min(a + UPLOAD_CHUNK, count)))  # noqa: E731
        with ThreadPoolExecutor(workers) as pool:
            pending = deque()
            for start in range(0, count, UPLOAD_CHUNK):
                pending.append((start, pool.submit(make, start)))
                if len(pending) > workers:     # giới hạn số đoạn đang chờ để RAM tạm không phình
                    _upload(*pending.popleft())
            while pending:
                _upload(*pending.popleft())


    def set_splats(self, splats, lod=None):
        """lod: LodIndex của splats (None: tự dựng)."""
        if splats is None or splats.count == 0:
            self.count = 0
            return
        n = splats.count
        if lod is None:
            lod = LodIndex(splats.positions, splats.scales, splats.alphas)
        order = self._slot_order = lod.order
        self._slot_of = np.empty(n, np.uint32)                 # chỉ số gaussian gốc -> vị trí trên GPU
        self._slot_of[order] = np.arange(n, dtype=np.uint32)
        # lớp của mỗi vị trí: các lớp chiếm những đoạn vị trí liên tiếp (lod.group_slots)
        layer_of = lambda a, b: (np.searchsorted(lod.group_slots, np.arange(a, b), side='right') - 1)  # noqa: E731
        self._upload_chunked(self.data_buffer, n, 32,
                             lambda a, b: self.pack(splats, order[a:b], layer_of(a, b)))
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.data_texture)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32UI, self.data_buffer)
        self.count = n
        self.prep_count = self.draw_count = 0
        self._samples.clear()
        self.last_sort_key = None
        self._state = np.zeros(n, np.uint8)
        self._upload_state(resize=True)
        self.sorter.set_splats(lod, self._state)
        self.set_transforms([np.identity(4)] * lod.group_count)
        self._upload_sh(splats, order)

    def _upload_sh(self, splats, order):
        """(N,K,3) hệ số SH -> K' texel RGBA8 / gaussian (lượng tử 8 bit, thành phần A bỏ trống).
        K' <= K: hạ bậc SH nếu không đủ SH_VRAM_BUDGET. Hệ số giữ ở toạ độ file: shader xoay
        hướng nhìn ngược về toạ độ file thay vì xoay hệ số."""
        n, k = splats.sh_rest.shape[:2]
        self.file_sh_degree = sh.degree_for_coeffs(k) or 0
        degree = self.file_sh_degree
        while degree > 0 and n * sh.COEFFS_FOR_DEGREE[degree] * 4 > SH_VRAM_BUDGET:
            degree -= 1
        self.sh_degree = degree
        k = sh.COEFFS_FOR_DEGREE[degree]
        if k:
            sample = splats.sh_rest[::max(n // 100_000, 1), :k].astype(np.float32)
            self.sh_scale = max(float(np.percentile(np.abs(sample), 99.9)), 1e-6) / 127.0

        def chunk(a, b):
            out = np.zeros((b - a, k, 4), np.uint8)
            coeffs = splats.sh_rest[order[a:b], :k].astype(np.float32)
            out[:, :, :3] = np.clip(np.rint(coeffs / self.sh_scale) + 128, 1, 255)
            return out

        # không có SH: buffer tối thiểu để texture vẫn hợp lệ
        self._upload_chunked(self.sh_buffer, n if k else 0, k * 4, chunk)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.sh_texture)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA8, self.sh_buffer)

    def _upload_state(self, resize=False, lo=0, hi=None):
        """Gửi self._state[lo:hi] lên GPU (resize: cấp lại cả buffer)."""
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.state_buffer)
        if resize:
            GL.glBufferData(GL.GL_TEXTURE_BUFFER, max(self._state.nbytes, 16), self._state, GL.GL_DYNAMIC_DRAW)
            GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.state_texture)
            GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_R8UI, self.state_buffer)
        else:
            hi = len(self._state) if hi is None else hi
            GL.glBufferSubData(GL.GL_TEXTURE_BUFFER, lo, hi - lo, self._state[lo:hi])
        self._order_version += 1

    def _set_state_bit(self, bit, mask):
        """Đặt bit `bit` của mọi gaussian theo mask (N,) bool theo chỉ số gaussian gốc. Sửa tại chỗ:
        luồng sắp xếp dùng chung mảng này."""
        if self.count == 0:
            return
        self._state &= np.uint8(~bit & 255)
        self._state |= mask[self._slot_order].view(np.uint8) * np.uint8(bit)
        self._upload_state()

    def set_selection(self, mask):
        """mask: (N,) bool theo chỉ số gaussian gốc, gaussian nào đang được chọn."""
        self._set_state_bit(STATE_SELECTED, mask)

    def set_deleted(self, mask):
        """mask: (N,) bool theo chỉ số gaussian gốc, gaussian nào đã bị xoá (xoá mềm). Rẻ: chỉ gửi
        1 byte / gaussian rồi chọn + sắp xếp lại, không gửi lại dữ liệu gaussian."""
        self._set_state_bit(STATE_DELETED, mask)
        self.last_sort_key = None

    def update_selection(self, indices, value):
        """Đặt vùng chọn = value cho các gaussian `indices` (chỉ số gốc). Chỉ gửi lên GPU đoạn bị
        đổi: nét cọ chạm các gaussian gần nhau, mà gần nhau trong không gian thì cũng gần nhau
        trên GPU (thứ tự Morton), nên đoạn này thường rất nhỏ."""
        if self.count == 0 or len(indices) == 0:
            return
        slots = self._slot_of[indices]
        if value:
            self._state[slots] |= np.uint8(STATE_SELECTED)
        else:
            self._state[slots] &= np.uint8(~STATE_SELECTED & 255)
        self._upload_state(lo=int(slots.min()), hi=int(slots.max()) + 1)

    def set_transforms(self, matrices):
        """Ma trận thế giới 4x4 của từng lớp (thứ tự như trong splats). Rất rẻ: kéo / xoay / phóng to
        lớp chỉ gọi hàm này, không gửi lại dữ liệu gaussian."""
        self.transforms = np.array(matrices, np.float64).reshape(-1, 4, 4)
        data = np.ascontiguousarray(self.transforms.transpose(0, 2, 1), np.float32)   # 4 cột / lớp
        GL.glBindBuffer(GL.GL_TEXTURE_BUFFER, self.transform_buffer)
        GL.glBufferData(GL.GL_TEXTURE_BUFFER, max(data.nbytes, 64), data, GL.GL_DYNAMIC_DRAW)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.transform_texture)
        GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32F, self.transform_buffer)
        self._order_version += 1

    def set_lighting(self, params):
        """params: Lighting.params(). Đổi chữ ký -> pass 1 phải tính lại màu của mọi gaussian."""
        self.lighting = params

    # ------------------------------------------------------------------ thứ tự vẽ
    def _upload_order(self, slots, ranks):
        if len(slots) > self._capacity:
            # cấp dư một chút để không phải cấp lại mỗi lần số gaussian được chọn nhích lên
            self._capacity = int(len(slots) * 1.25)
            for buffer, size in ((self.slot_vbo, 4), (self.rank_vbo, 4), (self.feedback_buffer, FEEDBACK_STRIDE)):
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buffer)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, self._capacity * size, None, GL.GL_DYNAMIC_DRAW)
            GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.feedback_texture)
            GL.glTexBuffer(GL.GL_TEXTURE_BUFFER, GL.GL_RGBA32UI, self.feedback_buffer)
        for buffer, values in ((self.slot_vbo, slots), (self.rank_vbo, ranks)):
            if len(values):
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buffer)
                GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, values.nbytes, values)
        self.prep_count, self.draw_count = len(slots), len(ranks)
        self._order_version += 1

    def _update_order(self, model_view, projection):
        result = self.sorter.take_result()
        if result is not None:
            self._upload_order(*result)
        key = (model_view.tobytes(), projection.tobytes(), self.budget, self.transforms.tobytes())
        if key != self.last_sort_key:
            self.sorter.request(model_view, projection, self.budget, self.transforms)
            self.last_sort_key = key

    # ------------------------------------------------------------------ vẽ
    def _prepare(self, model_view, projection, width, height):
        """Pass 1: tính ellipse + màu cho mọi gaussian được chọn, ghi vào feedback_buffer."""
        degree = self.sh_degree if self.use_sh else 0
        light = self.lighting
        key = (model_view.tobytes(), projection.tobytes(), width, height, degree, self._order_version,
               light['signature'])
        if key == self._prep_key:
            return                     # không có gì đổi: dùng lại kết quả khung hình trước
        self._prep_key = key
        if light['enabled'] and light['shadows']:
            self._render_shadow_map(light)

        s = self.prep_shader
        s.use()
        s.set_mat4('uModelView', model_view)
        s.set_mat4('uProjection', projection)
        s.set_vec2('uViewport', width, height)
        s.set_float('uFocal', height / 2 * projection[1, 1])   # projection[1,1] = 1/tan(fov/2)
        s.set_vec3('uSelectColor', self.SELECT_COLOR)
        rot, t = model_view[:3, :3].astype(np.float64), model_view[:3, 3].astype(np.float64)
        s.set_vec3('uCamPos', -rot.T @ t)                      # vị trí camera trong toạ độ thế giới
        s.set_int('uShDegree', degree)
        s.set_int('uShCount', sh.COEFFS_FOR_DEGREE[self.sh_degree])
        s.set_float('uShScale', self.sh_scale)
        self._set_light_uniforms(s, light)
        for unit, (name, texture) in enumerate((('uData', self.data_texture), ('uState', self.state_texture),
                                                 ('uSh', self.sh_texture), ('uLayers', self.transform_texture))):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(GL.GL_TEXTURE_BUFFER, texture)
            s.set_int(name, unit)
        GL.glActiveTexture(GL.GL_TEXTURE0)

        GL.glEnable(GL.GL_RASTERIZER_DISCARD)
        GL.glBindBufferBase(GL.GL_TRANSFORM_FEEDBACK_BUFFER, 0, self.feedback_buffer)
        GL.glBindVertexArray(self.prep_vao)
        GL.glBeginTransformFeedback(GL.GL_POINTS)
        GL.glDrawArrays(GL.GL_POINTS, 0, self.prep_count)
        GL.glEndTransformFeedback()
        GL.glBindBufferBase(GL.GL_TRANSFORM_FEEDBACK_BUFFER, 0, 0)
        GL.glDisable(GL.GL_RASTERIZER_DISCARD)

    # ------------------------------------------------------------------ ánh sáng
    MAX_POINT_LIGHTS = 8
    SHADOW_UNIT = 4

    def _set_light_uniforms(self, s, light):
        s.set_int('uLightingOn', 1 if light['enabled'] else 0)
        if not light['enabled']:
            return
        n = min(len(light['point_range']), self.MAX_POINT_LIGHTS)

        def pad(values):
            values = np.asarray(values, np.float32).reshape(-1, 3)[:n]
            return np.vstack([values, np.zeros((self.MAX_POINT_LIGHTS - n, 3), np.float32)])

        s.set_vec3('uAmbient', light['ambient'])
        s.set_int('uSunOn', 1 if light['sun_on'] else 0)
        s.set_vec3('uSunDir', light['sun_dir'])
        s.set_vec3('uSunColor', light['sun_color'])
        s.set_float('uSpecular', light['specular'])
        s.set_float('uShininess', light['shininess'])
        s.set_int('uPointCount', n)
        s.set_vec3_array('uPointPos', pad(light['point_pos']))
        s.set_vec3_array('uPointColor', pad(light['point_color']))
        ranges = np.ones(self.MAX_POINT_LIGHTS, np.float32)
        ranges[:n] = light['point_range'][:n]
        s.set_float_array('uPointRange', ranges)
        s.set_int('uShadowOn', 1 if light['shadows'] else 0)
        if light['shadows']:
            s.set_mat4('uLightVP', light['shadow_vp'])
            s.set_float('uShadowTexel', light['shadow_texel'])
            s.set_float('uShadowBias', light['shadow_bias'])
            s.set_float('uShadowInv', 1.0 / SHADOW_SIZE)
            GL.glActiveTexture(GL.GL_TEXTURE0 + self.SHADOW_UNIT)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._shadow_texture)
            s.set_int('uShadowMap', self.SHADOW_UNIT)
            GL.glActiveTexture(GL.GL_TEXTURE0)

    def _create_shadow_map(self):
        self._shadow_texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._shadow_texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_DEPTH_COMPONENT24, SHADOW_SIZE, SHADOW_SIZE, 0,
                        GL.GL_DEPTH_COMPONENT, GL.GL_FLOAT, None)
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST), (GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE), (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        self._shadow_fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._shadow_fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_TEXTURE_2D,
                                  self._shadow_texture, 0)
        GL.glDrawBuffer(GL.GL_NONE)
        GL.glReadBuffer(GL.GL_NONE)

    def _render_shadow_map(self, light):
        """Shadow mapping: vẽ tâm các gaussian đã chọn vào bản đồ độ sâu nhìn từ mặt trời. Chỉ vẽ lại khi
        mặt trời hoặc tập gaussian được chọn đổi (không vẽ lại mỗi lần camera nhúc nhích nhẹ)."""
        key = (self._order_version, light['signature'])
        if key == self._shadow_key and self._shadow_texture is not None:
            return
        self._shadow_key = key
        previous_fbo = int(GL.glGetIntegerv(GL.GL_DRAW_FRAMEBUFFER_BINDING))
        viewport = [int(v) for v in GL.glGetIntegerv(GL.GL_VIEWPORT)]
        if self._shadow_fbo is None:
            self._create_shadow_map()
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._shadow_fbo)
        GL.glViewport(0, 0, SHADOW_SIZE, SHADOW_SIZE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LESS)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)

        s = self.shadow_shader
        s.use()
        s.set_mat4('uLightVP', light['shadow_vp'])
        s.set_float('uPointSize', 3.0)
        for unit, name, texture in ((0, 'uData', self.data_texture), (1, 'uState', self.state_texture),
                                    (3, 'uLayers', self.transform_texture)):
            GL.glActiveTexture(GL.GL_TEXTURE0 + unit)
            GL.glBindTexture(GL.GL_TEXTURE_BUFFER, texture)
            s.set_int(name, unit)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindVertexArray(self.prep_vao)
        GL.glDrawArrays(GL.GL_POINTS, 0, self.prep_count)
        GL.glBindVertexArray(0)

        GL.glDisable(GL.GL_PROGRAM_POINT_SIZE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, previous_fbo)
        GL.glViewport(*viewport)

    # ------------------------------------------------------------------ đo thời gian / tự chỉnh budget
    def _collect_timings(self):
        while self._query_pending:
            query, count = self._query_pending[0]
            if not GL.glGetQueryObjectiv(query, GL.GL_QUERY_RESULT_AVAILABLE):
                break
            self._query_pending.pop(0)
            self._queries.append(query)
            ns = GL.glGetQueryObjectuiv(query, GL.GL_QUERY_RESULT)   # 32 bit: đủ cho < 4 giây
            if count:
                self.gpu_ms = ns / 1e6
                self._samples.append((self.gpu_ms, count))

    def adapt_budget(self, target_ms):
        """Chỉnh budget để thời gian GPU lúc camera di chuyển (khung hình có chạy pass 1, nặng nhất)
        gần target_ms. Ước lượng chi phí mỗi gaussian = ms / số gaussian thật sự xử lý ở khung hình
        đó (không dùng budget: kết quả sắp xếp đến trễ vài khung hình), rồi đổi budget từ từ."""
        if self.count == 0 or len(self._samples) < 8:
            return
        cost = float(np.median([ms / count for ms, count in self._samples]))
        self._samples.clear()
        current = self.budget or self.count
        wanted = target_ms / max(cost, 1e-9)
        if abs(wanted / current - 1) < 0.1:
            return                                   # đủ gần: giữ nguyên để khỏi dao động
        step = min(max(wanted / current, 0.75), 1.33) ** 0.5   # mỗi lần đổi tối đa ~15%
        self.budget = int(min(max(current * step, MIN_BUDGET), self.count))

    def draw(self, model_view, projection, width, height):
        if self.count == 0:
            return
        model_view = np.asarray(model_view, np.float32)
        projection = np.asarray(projection, np.float32)
        self._collect_timings()
        self._update_order(model_view, projection)
        if self.draw_count == 0:
            return
        query = self._queries.pop() if self._queries else None
        if query is not None:
            GL.glBeginQuery(GL.GL_TIME_ELAPSED, query)
        prep_key = self._prep_key
        self._prepare(model_view, projection, width, height)
        self._draw_splats()
        if query is not None:
            GL.glEndQuery(GL.GL_TIME_ELAPSED)
            # chỉ khung hình có chạy pass 1 mới dùng để chỉnh budget (0: bỏ qua)
            self._query_pending.append((query, self.prep_count if self._prep_key is not prep_key else 0))

    def _draw_splats(self):
        """Pass 2: vẽ hình vuông xa -> gần."""
        s = self.shader
        s.use()
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_BUFFER, self.feedback_texture)
        s.set_int('uPrep', 0)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArraysInstanced(GL.GL_TRIANGLE_STRIP, 0, 4, self.draw_count)
        GL.glBindVertexArray(0)
