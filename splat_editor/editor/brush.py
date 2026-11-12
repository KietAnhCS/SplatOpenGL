"""Cọ chọn gaussian (brush): tô lên màn hình, gaussian nào có tâm nằm trong nét cọ thì được chọn.

Cọ chọn xuyên qua mọi độ sâu (giống SuperSplat): mọi gaussian có tâm chiếu vào vòng tròn
đều bị chọn, kể cả những cái nằm khuất phía sau.

Để nhanh với hàng chục triệu gaussian, cọ dùng chỉ mục khối của LodIndex: chiếu 8 đỉnh hộp bao
của mỗi khối (~15 nghìn khối với 15 triệu gaussian) ra một hình chữ nhật trên màn hình, chỉ
những khối chạm nét cọ mới phải chiếu và kiểm tra từng gaussian (chia cho nhiều luồng).
"""

"""
brush = BrushTool()
brush.toggle()                          # bật / tắt cọ (phím B)
brush.resize(1.2)                       # to lên 20% (phím ]); radius nằm trong [MIN_RADIUS, MAX_RADIUS]

brush.begin_stroke(select=True)        # bắt đầu tô (False: bỏ chọn)
indices = brush.hit(lod, view_proj, viewport_rect, start=(x0, y0), end=(x1, y1), transforms=layer_matrices)
brush.end_stroke()                      # nhả chuột
"""

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

# 8 đỉnh của hộp: chọn lo (0) hoặc hi (1) cho từng trục
_WORKERS = min(max((os.cpu_count() or 2) - 1, 1), 6)
_CORNERS = np.array([[(i >> axis) & 1 for axis in range(3)] for i in range(8)], bool)


class BrushTool:
    MIN_RADIUS = 2.0
    MAX_RADIUS = 500.0

    def __init__(self):
        self.active = False       # đang ở chế độ cọ (phím B)
        self.radius = 40.0        # bán kính (pixel)
        self.painting = None      # None: không tô; True: đang chọn; False: đang bỏ chọn
        self.last = None          # vị trí chuột lần tô trước

    # ------------------------------------------------------------------ trạng thái
    @property
    def is_painting(self):
        return self.painting is not None

    def toggle(self):
        self.active = not self.active

    def resize(self, factor):
        self.radius = min(max(self.radius * factor, self.MIN_RADIUS), self.MAX_RADIUS)

    def begin_stroke(self, select):
        """select=True: tô để chọn; False: tô để bỏ chọn."""
        self.painting = select
        self.last = None

    def end_stroke(self):
        self.painting = None

    # ------------------------------------------------------------------ chiếu / kiểm tra
    @staticmethod
    def _to_screen(clip, viewport):
        left, top, width, height = viewport
        x = left + (clip[..., 0] / clip[..., 3] + 1) * 0.5 * width
        y = top + (1 - clip[..., 1] / clip[..., 3]) * 0.5 * height
        return x, y

    @staticmethod
    def _segment_dist2(p, a, b):
        """Bình phương khoảng cách từ các điểm p (...,2) tới đoạn thẳng a -> b."""
        ab = b - a
        length2 = float(ab @ ab)
        t = np.clip((p - a) @ ab / length2, 0, 1) if length2 > 0 else np.zeros(p.shape[:-1])
        d = p - (a + t[..., None] * ab)
        return (d * d).sum(axis=-1)

    def _candidate_chunks(self, lod, matrices, viewport, a, b):
        """(khối phải kiểm tra từng gaussian, khối nằm trọn trong nét cọ) theo hình chữ nhật bao
        hình chiếu hộp bao của khối. matrices: (số nhóm, 4, 4) chiếu * thế giới của từng nhóm."""
        r = self.radius
        lo, hi = np.minimum(a, b) - r, np.maximum(a, b) + r
        corners = np.where(_CORNERS[None], lod.box_hi[:, None], lod.box_lo[:, None])   # (C,8,3)
        m = matrices[lod.chunk_group]                                                    # (C,4,4)
        clip = np.einsum('cij,ckj->cki', m[:, :, :3], corners) + m[:, None, :, 3]       # (C,8,4)
        w = clip[..., 3]
        front = (w > 1e-6).all(axis=1)
        crosses = ~front & (w > 1e-6).any(axis=1)        # hộp cắt mặt phẳng camera: luôn xét
        # hộp lồi -> hình chiếu nằm trong bao của 8 đỉnh chiếu
        x, y = self._to_screen(clip[front], viewport)
        x0, x1, y0, y1 = x.min(axis=1), x.max(axis=1), y.min(axis=1), y.max(axis=1)
        touch = (x1 >= lo[0]) & (x0 <= hi[0]) & (y1 >= lo[1]) & (y0 <= hi[1])
        # nét cọ (hình viên thuốc) là hình lồi: 4 góc hình chữ nhật nằm trong -> cả khối nằm trong
        rect = np.stack([np.stack([x0, y0], -1), np.stack([x1, y0], -1),
                         np.stack([x0, y1], -1), np.stack([x1, y1], -1)], axis=1)[touch]   # (T,4,2)
        inside = (self._segment_dist2(rect, a, b) <= r * r).all(axis=1)
        ids = np.flatnonzero(front)[touch]
        return np.concatenate([ids[~inside], np.flatnonzero(crosses)]), ids[inside]

    def hit(self, lod, view_proj, viewport, start, end, transforms=None):
        """Chỉ số các gaussian có tâm cách đoạn thẳng start -> end (pixel) không quá `radius`.
        transforms: ma trận thế giới 4x4 của từng nhóm trong lod (None: đơn vị)."""
        vp = np.asarray(view_proj, np.float64)
        transforms = [np.identity(4)] * lod.group_count if transforms is None else transforms
        matrices = np.array([vp @ np.asarray(t, np.float64) for t in transforms]).reshape(-1, 4, 4)
        a = np.asarray(start, np.float64)
        b = np.asarray(end, np.float64)
        r = self.radius
        chunks, inside = self._candidate_chunks(lod, matrices, viewport, a, b)
        # khối nằm trọn trong nét cọ: lấy cả khối, khỏi chiếu từng gaussian
        sizes = lod.sizes[inside]
        ends = np.cumsum(sizes)
        whole = lod.order[np.arange(int(ends[-1]) if len(ends) else 0) +
                          np.repeat(lod.starts[inside] - (ends - sizes), sizes)].astype(np.int64)
        if len(chunks) == 0:
            return whole
        matrices32 = matrices.astype(np.float32)

        def test(group):
            """Chỉ số gốc của các gaussian trong nhóm khối `group` (cùng một lớp) nằm dưới nét cọ."""
            m32 = matrices32[lod.chunk_group[group[0]]]
            sizes = lod.sizes[group]
            ends = np.cumsum(sizes)
            slots = np.arange(int(ends[-1])) + np.repeat(lod.starts[group] - (ends - sizes), sizes)
            clip = lod.positions[slots] @ m32[:, :3].T + m32[:, 3]
            front = clip[:, 3] > 1e-6
            slots, clip = slots[front], clip[front]
            p = np.stack(self._to_screen(clip, viewport), axis=1)
            return lod.order[slots[self._segment_dist2(p, a, b) <= r * r]]

        # chia việc cho nhiều luồng; mỗi phần chỉ gồm khối của cùng một lớp (cùng ma trận)
        groups = []
        for layer in np.unique(lod.chunk_group[chunks]):
            mine = chunks[lod.chunk_group[chunks] == layer]
            groups += np.array_split(mine, min(_WORKERS, max(len(mine) // 16, 1)))
        if len(groups) == 1:
            parts = [test(groups[0])]
        else:
            with ThreadPoolExecutor(min(len(groups), _WORKERS)) as pool:
                parts = list(pool.map(test, groups))
        return np.concatenate([whole] + [p.astype(np.int64) for p in parts])
