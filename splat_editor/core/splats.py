"""Tập gaussian đã giải mã sẵn để render."""

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