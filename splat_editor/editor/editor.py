"""Editor: giữ cảnh, lịch sử hoàn tác, cọ chọn và thực hiện mọi thao tác chỉnh sửa.

Editor không biết gì về OpenGL hay giao diện: mỗi khi dữ liệu đổi, nó tăng
`geometry_version` / `deleted_version` / `selection_version`; Viewport so sánh số này để biết khi nào gửi lại lên GPU.
"""

"""
editor = Editor(max_undo=20)
editor.open_file("scene.ply")          # thay cảnh bằng một file (lỗi thì giữ nguyên cảnh cũ)
editor.add_file("other.ply")           # thêm thành lớp mới

editor.brush.toggle()                   # bật cọ
editor.brush.begin_stroke(select=True)
editor.paint(x, y, view_proj, rect)    # tô từ vị trí cũ tới (x, y)
editor.brush.end_stroke()

editor.delete_selected()                # xoá gaussian đang chọn, đẩy vào lịch sử
editor.undo()                           # Ctrl+Z
editor.save_file("out.ply")            # gộp các lớp đang hiện rồi ghi

# Mỗi lần dữ liệu đổi, Editor tăng một số phiên bản (geometry/deleted/selection/transform)
# để Viewport.sync() biết phần nào cần gửi lại GPU.
"""

import os

import numpy as np

from ..core.history import DeleteGaussiansCommand, History
from ..core.layer import Layer
from ..core.lod import LodIndex
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
        self.deleted_version = 0       # tăng khi xoá / hoàn tác xoá gaussian (xoá mềm: không đổi geometry)
        self.selection_version = 0
        self.transform_version = 0
        self._splats = None
        self._splats_version = -1
        self._lod = None
        self._lod_version = -1
        self._selection_log = []     # [(selection_version, chỉ số, giá trị)]: các lần tô gần đây

    # ------------------------------------------------------------------ trạng thái
    @property
    def splats(self):
        """Tất cả lớp đang hiện, gộp lại, ở toạ độ file của từng lớp (tính lại khi dữ liệu đổi).
        Toạ độ thế giới = layer_matrices()[lớp] @ toạ độ file."""
        if self._splats_version != self.geometry_version:
            self._splats = self.scene.render_splats()
            self._splats_version = self.geometry_version
        return self._splats

    @property
    def lod(self):
        """Chỉ mục không gian (khối + LOD) của self.splats, mỗi lớp một nhóm; dùng chung cho
        renderer và cọ chọn. Chỉ dựng lại khi dữ liệu đổi, không phải khi kéo / xoay lớp."""
        if self._lod_version != self.geometry_version:
            splats = self.splats
            ranges = [(start, end) for _, start, end in self.scene.visible_ranges()]
            self._lod = LodIndex(splats.positions, splats.scales, splats.alphas, ranges=ranges)                 if splats is not None else None
            self._lod_version = self.geometry_version
        return self._lod

    def layer_matrices(self):
        return self.scene.layer_matrices()

    @property
    def total_count(self):
        """Số gaussian còn lại (chưa xoá) của các lớp đang hiện."""
        return self.scene.count()

    def notify_geometry_changed(self):
        """Dữ liệu gaussian đổi (mở / xoá / ẩn lớp...): phải dựng lại và gửi lại lên GPU."""
        self.geometry_version += 1
        self.notify_deleted_changed()
        self.transform_version += 1

    def notify_deleted_changed(self):
        """Tập gaussian đã xoá đổi (xoá / hoàn tác): renderer chỉ gửi lại cờ, không gửi lại dữ liệu."""
        self.deleted_version += 1
        self.notify_selection_changed()

    def notify_transform_changed(self):
        """Chỉ phép biến đổi của lớp (hoặc lật trục) đổi: renderer chỉ cần cập nhật ma trận."""
        self.transform_version += 1

    def notify_selection_changed(self, indices=None, value=None):
        """indices / value: thay đổi chỉ gồm `vùng chọn[indices] = value` (để gửi GPU từng phần)."""
        self.selection_version += 1
        if indices is None:
            self._selection_log.clear()
        else:
            self._selection_log.append((self.selection_version, indices, value))
            del self._selection_log[:-64]

    def selection_changes_since(self, version):
        """[(chỉ số, giá trị)] đã tô kể từ `version`, hoặc None nếu có thay đổi khác (phải gửi lại cả)."""
        if version is None:
            return None
        changes = [(i, v) for ver, i, v in self._selection_log if ver > version]
        return changes if len(changes) == self.selection_version - version else None

    def set_status(self, text):
        self.status = text
        print(text)

    # ------------------------------------------------------------------ file
    def _load_layer(self, path):
        try:
            return Layer.from_file(path)
        except Exception as e:   # noqa: BLE001
            self.set_status(f"Failed to open {os.path.basename(path)}: {e}")
            return None

    def open_file(self, path):
        """Mở file mới, thay thế toàn bộ cảnh. Mở lỗi thì giữ nguyên cảnh cũ."""
        layer = self._load_layer(path)
        if layer is None:
            return False
        self.scene.clear()
        self.scene.add(layer)
        self.history.clear()
        self.notify_geometry_changed()
        self.set_status(f"Opened {layer.name}: {layer.count:,} gaussians")
        return True

    def add_file(self, path):
        """Thêm file vào cảnh đang có. Trả về lớp mới hoặc None."""
        layer = self._load_layer(path)
        if layer is None:
            return None
        self.scene.add(layer)
        self.notify_geometry_changed()
        self.set_status(f"Added {layer.name}: {layer.count:,} gaussians")
        return layer

    def can_save(self):
        return bool(self.scene.visible_layers())

    def suggested_save_name(self):
        layers = self.scene.visible_layers()
        return layers[0].name if len(layers) == 1 else "merged.ply"

    def save_file(self, path):
        dtype = self.scene.export_dtype()
        if dtype is None:
            self.set_status("No visible layers to save")
            return False
        layers = self.scene.visible_layers()
        count = sum(layer.count for layer in layers)
        try:
            self._release_file(path)
            PlyFile.write_blocks(path, dtype, count, self.scene.export_blocks(dtype))
        except Exception as e:   # noqa: BLE001
            self.set_status(f"Failed to save: {e}")
            return False
        self.set_status(f"Saved {path} ({count:,} gaussians, {len(layers)} layer{'s' * (len(layers) != 1)})")
        return True

    def _release_file(self, path):
        """File PLY đang mở được ánh xạ thẳng vào bộ nhớ (memmap); Windows không cho ghi đè file
        đang ánh xạ. Nếu lưu đè lên chính nó thì chép dữ liệu đó vào RAM trước."""
        if not os.path.exists(path):
            return

        def load(data):
            if isinstance(data, np.memmap) and data.filename and os.path.samefile(data.filename, path):
                return np.array(data)
            return data

        for layer in self.scene.layers:
            layer.data = load(layer.data)
        for command in self.history:
            command.release(load)

    # ------------------------------------------------------------------ lớp
    def remove_layer(self, index=None):
        index = self.scene.active_index if index is None else index
        if 0 <= index < len(self.scene.layers):
            layer = self.scene.remove(index)
            self.notify_geometry_changed()
            self.set_status(f"Removed layer {layer.name}")

    # ------------------------------------------------------------------ vùng chọn (chỉ các lớp đang hiện)
    def select_all(self):
        for layer in self.scene.visible_layers():
            layer.select_all()
        self.notify_selection_changed()

    def select_none(self):
        for layer in self.scene.visible_layers():
            layer.clear_selection()
        self.notify_selection_changed()

    def invert_selection(self):
        for layer in self.scene.visible_layers():
            layer.invert_selection()
        self.notify_selection_changed()

    def paint(self, x, y, view_proj, rect):
        """Tô cọ từ vị trí lần trước tới (x, y): chọn hoặc bỏ chọn gaussian."""
        splats = self.splats
        if splats is None or rect.is_empty or not self.brush.is_painting:
            return
        indices = self.brush.hit(self.lod, view_proj, rect, self.brush.last or (x, y), (x, y),
                                 self.layer_matrices())
        self.brush.last = (x, y)
        if len(indices):
            indices = self.scene.apply_selection_indices(indices, self.brush.painting)
            if len(indices):
                self.notify_selection_changed(indices, self.brush.painting)

    # ------------------------------------------------------------------ xoá / hoàn tác
    def delete_selected(self):
        snapshots = []
        for layer in self.scene.visible_layers():
            snapshot = layer.delete_selected()
            if snapshot is not None:
                snapshots.append((layer, snapshot))
        if not snapshots:
            self.set_status("Nothing selected (press B for the brush, then paint over what to delete)")
            return
        command = DeleteGaussiansCommand(snapshots)
        self.history.push(command)
        self.notify_deleted_changed()
        self.set_status(f"Deleted {command.count:,} gaussians (Ctrl+Z to undo)")

    def delete(self):
        """Phím Delete: xoá gaussian đang chọn nếu có, nếu không thì xoá lớp đang chọn."""
        if self.scene.selected_count():
            self.delete_selected()
        else:
            self.remove_layer()

    def undo(self):
        command = self.history.undo()
        if command is None:
            self.set_status("Nothing to undo")
            return
        self.notify_deleted_changed()
        self.set_status(f"Undid {command.description}")
