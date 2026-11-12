"""Tập gaussian đã giải mã sẵn để render."""

"""
splats = SplatCodec.decode(data)        # từ cột PLY ra Splats (xem io/codec.py)
splats.count                            # số gaussian
splats.positions.shape                  # (N, 3)
splats.sh_count                         # K = 0, 3, 8 hoặc 15

kept = splats.subset(~deleted_mask)     # bản mới chỉ gồm các gaussian được giữ
merged = Splats.concat([a, b, c])       # gộp nhiều Splats thành một
sh_world = splats.world_sh(index=None)  # hệ số SH đã xoay về toạ độ thế giới (float32)
"""

from dataclasses import dataclass

import numpy as np

from . import sh


@dataclass
class Splats:
    positions: np.ndarray   # (N,3) tâm
    colors: np.ndarray      # (N,3) màu bậc 0 = 0.5 + C0 * f_dc (chưa cắt về 0..1)
    alphas: np.ndarray      # (N,)  độ đục 0..1
    scales: np.ndarray      # (N,3) bán kính theo 3 trục (đã exp)
    rotations: np.ndarray   # (N,4) quaternion (w,x,y,z) đã chuẩn hoá
    sh_rest: np.ndarray     # (N,K,3) hệ số SH bậc 1..3 (K = 0, 3, 8, 15), xem core/sh.py; thường là float16
    # ((đầu, cuối, R), ...): sh_rest[đầu:cuối] vẫn ở toạ độ file, phải xoay theo R mới ra toạ độ
    # thế giới. Xoay lười như vậy để khỏi giữ thêm một bản sao SH (bản sao lớn nhất: ~1.4 GB với
    # 15 triệu gaussian); cần SH thế giới thì gọi world_sh. (Renderer không dùng: nó giữ SH ở toạ
    # độ file và xoay hướng nhìn trong shader.)
    sh_frames: tuple = ()

    ARRAYS = ('positions', 'colors', 'alphas', 'scales', 'rotations', 'sh_rest')

    @property
    def count(self):
        return len(self.positions)

    @property
    def sh_count(self):
        return self.sh_rest.shape[1]

    def world_sh(self, index=None, k=None):
        """Hệ số SH (float32, toạ độ thế giới) của các gaussian `index` (mảng chỉ số; None: tất cả).
        k: chỉ lấy k hệ số đầu (mỗi bậc SH xoay độc lập nên cắt bớt bậc cao vẫn đúng)."""
        rows = np.arange(self.count) if index is None else np.asarray(index)
        out = self.sh_rest[rows, :k].astype(np.float32)
        for start, end, rot in self.sh_frames:
            inside = (rows >= start) & (rows < end)
            if inside.any():
                out[inside] = sh.rotate(out[inside], rot)
        return out

    def subset(self, mask):
        """Splats mới chỉ gồm các gaussian có mask True (chỉ dùng cho dữ liệu chưa xoay)."""
        assert not self.sh_frames
        if isinstance(mask, np.ndarray) and mask.dtype == bool:
            # np.compress nhanh hơn a[mask] khoảng 2 lần với mảng lớn (vd. sh_rest ~900 MB)
            return Splats(*(np.compress(mask, getattr(self, name), axis=0) for name in self.ARRAYS))
        return Splats(*(getattr(self, name)[mask] for name in self.ARRAYS))

    @classmethod
    def concat(cls, parts):
        """Gộp nhiều Splats thành một (giữ thứ tự). Lớp có ít hệ số SH hơn được thêm 0."""
        if len(parts) == 1:
            return parts[0]
        k = max(p.sh_count for p in parts)
        sh_parts = [np.pad(p.sh_rest, ((0, 0), (0, k - p.sh_count), (0, 0))) for p in parts]
        frames, offset = [], 0
        for p in parts:
            frames += [(offset + start, offset + end, rot) for start, end, rot in p.sh_frames]
            offset += p.count
        arrays = [np.concatenate([getattr(p, name) for p in parts]) for name in cls.ARRAYS[:-1]]
        return cls(*arrays, np.concatenate(sh_parts), tuple(frames))

