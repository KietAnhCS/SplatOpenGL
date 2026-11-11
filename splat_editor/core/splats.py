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

from dataclass import dataclass, fields 

import numpy as np 

@dataclass 
class Splats:
    position: np.ndarray 
    colors: np.ndarray 
    alphas: np.ndarray
    scales: np.ndarray 
    rotations: np.ndarray 

    @property 
    def count(self):
        return len(self.positions)

    def subset(self, mask):
        return Splats(*(getattr(self, f.name)[mask] for f in fields(self)))

    @classmethod 
    def concat(cls, parts):
        if len(parts) == 1:
            return parts[0]
        return cls(*(np.concatenate([getattr(p, f.name) for p in parts]) for f in fields(cls)))