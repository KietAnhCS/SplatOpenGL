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