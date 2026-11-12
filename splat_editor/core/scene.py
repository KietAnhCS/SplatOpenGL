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
        self.layers = []
        self.active_index = -1     # lớp đang được chọn trong danh sách
        self.flip = True           # lật file COLMAP (trục Y hướng xuống)

    # ------------------------------------------------------------------ danh sách lớp
    @property
    def active_layer(self):
        return self.layers[self.active_index] if 0 <= self.active_index < len(self.layers) else None

    @property
    def is_empty(self):
        return not self.layers

    def add(self, layer):
        self.layers.append(layer)
        self.active_index = len(self.layers) - 1
        return layer

    def remove(self, index):
        layer = self.layers.pop(index)
        self.active_index = min(self.active_index, len(self.layers) - 1)
        return layer

    def clear(self):
        self.layers = []
        self.active_index = -1

    def visible_layers(self):
        return [layer for layer in self.layers if layer.visible]

    def visible_ranges(self):
        """(lớp, đầu, cuối): vị trí của mỗi lớp đang hiện trong mảng gộp của render_splats()
        (kể cả gaussian đã xoá)."""
        start = 0
        for layer in self.visible_layers():
            end = start + layer.size
            yield layer, start, end
            start = end

    # ------------------------------------------------------------------ vùng chọn
    def selection_mask(self):
        """Vùng chọn của các lớp đang hiện, gộp theo đúng thứ tự của render_splats()."""
        parts = [layer.selection for layer in self.visible_layers()]
        return np.concatenate(parts) if parts else np.zeros(0, bool)

    def deleted_mask(self):
        """Gaussian đã xoá (xoá mềm) của các lớp đang hiện, theo thứ tự của render_splats()."""
        parts = [layer.deleted for layer in self.visible_layers()]
        return np.concatenate(parts) if parts else np.zeros(0, bool)

    def apply_selection(self, mask, value):
        """Đặt vùng chọn = value cho các gaussian có mask True (mask theo mảng gộp; bỏ qua cái đã xoá)."""
        for layer, start, end in self.visible_ranges():
            layer.selection[mask[start:end] & ~layer.deleted] = value

    def apply_selection_indices(self, indices, value):
        """Đặt vùng chọn = value cho các gaussian `indices` (chỉ số theo mảng gộp). Gaussian đã xoá
        bị bỏ qua. Trả về các chỉ số thật sự được đặt."""
        changed = []
        for layer, start, end in self.visible_ranges():
            inside = indices[(indices >= start) & (indices < end)] - start
            if layer.deleted_count:
                inside = inside[~layer.deleted[inside]]
            layer.selection[inside] = value
            changed.append(inside + start)
        return np.concatenate(changed) if changed else np.zeros(0, np.int64)

    def selected_count(self):
        return sum(layer.selected_count for layer in self.visible_layers())

    # ------------------------------------------------------------------ gộp dữ liệu
    def count(self):
        """Số gaussian còn lại (chưa xoá) của các lớp đang hiện."""
        return sum(layer.count for layer in self.visible_layers())

    def render_splats(self):
        """Gộp các lớp đang hiện ở toạ độ file của từng lớp (không chép nếu chỉ có một lớp), kể cả
        gaussian đã xoá (renderer / cọ bỏ qua chúng theo deleted_mask()).
        Toạ độ thế giới = layer_matrices()[lớp] @ toạ độ file."""
        parts = [layer.splats for layer in self.visible_layers()]
        return Splats.concat(parts) if parts else None

    def layer_matrices(self):
        """Ma trận thế giới 4x4 của mỗi lớp đang hiện (theo thứ tự trong render_splats)."""
        return [layer.world_matrix(self.flip) for layer in self.visible_layers()]

    def world_positions(self, layer=None, limit=2_000_000):
        """Tâm gaussian (toạ độ thế giới) của một lớp / các lớp đang hiện, lấy thưa tối đa `limit`
        điểm (đủ để đặt camera, khỏi biến đổi cả chục triệu điểm)."""
        layers = [layer] if layer is not None else self.visible_layers()
        total = sum(l.count for l in layers)
        step = max(total // limit, 1)
        parts = []
        for l in layers:
            m = l.world_matrix(self.flip)
            parts.append(l.splats.positions[::step] @ m[:3, :3].T.astype(np.float32) + m[:3, 3].astype(np.float32))
        return np.concatenate(parts) if parts else np.zeros((0, 3), np.float32)

    def solid_positions(self, limit=3_000_000, min_alpha=0.35):
        """Tâm gaussian "rắn" (toạ độ thế giới) dùng làm bề mặt va chạm: bỏ gaussian đã xoá và gaussian
        quá mờ (thường là nhiễu / vật bay lơ lửng). Lấy thưa tối đa `limit` điểm; trả về (điểm, bước lấy thưa)."""
        layers = self.visible_layers()
        total = sum(l.size for l in layers)
        step = max(total // limit, 1)
        parts = []
        for l in layers:
            keep = (l.splats.alphas[::step] >= min_alpha) & ~l.deleted[::step]
            m = l.world_matrix(self.flip)
            pts = l.splats.positions[::step][keep]
            parts.append(pts @ m[:3, :3].T.astype(np.float32) + m[:3, 3].astype(np.float32))
        return (np.concatenate(parts) if parts else np.zeros((0, 3), np.float32)), step

    def world_splats(self):
        """Gộp các gaussian còn lại của các lớp đang hiện thành một Splats (toạ độ thế giới)."""
        parts = [layer.world_splats(self.flip) for layer in self.visible_layers()]
        return Splats.concat(parts) if parts else None

    def export_dtype(self):
        """Kiểu dữ liệu PLY khi lưu các lớp đang hiện (None nếu không có lớp nào).

        Nếu các file cùng cấu trúc thì giữ nguyên mọi thuộc tính (kể cả f_rest_*).
        Nếu khác nhau thì chuyển hết sang dạng 3DGS chuẩn (giữ f_rest_* khi tất cả đều có).
        """
        layers = self.visible_layers()
        if not layers:
            return None
        dtypes = {layer.data.dtype for layer in layers}
        if len(dtypes) == 1:
            return layers[0].data.dtype
        fields = list(CANONICAL_FIELDS)
        rest = [set(n for n in layer.data.dtype.names if n.startswith('f_rest_')) for layer in layers]
        common = set.intersection(*rest)
        if all(r == common for r in rest):
            fields[6:6] = sorted(common, key=lambda n: int(n.split('_')[-1]))
        return np.dtype([(f, '<f4') for f in fields])

    def export_blocks(self, dtype):
        """Dữ liệu PLY của các lớp đang hiện (đã áp phép biến đổi), từng khối một."""
        for layer in self.visible_layers():
            yield from layer.export_blocks(self.flip, dtype)

    def export_data(self):
        """Dữ liệu PLY của tất cả lớp đang hiện, gộp thành một mảng (None nếu không có lớp nào)."""
        dtype = self.export_dtype()
        if dtype is None:
            return None
        blocks = list(self.export_blocks(dtype))
        return np.concatenate(blocks) if blocks else np.zeros(0, dtype)
