"""Load gaussian splat files into SplatData.

load_file(path) -> list[LoadResult]  (one entry per layer; currently always one)
Every gaussian format gets the initial layer rotation quat_from_euler(0, 0, 180), exactly like
SuperSplat (splat-transform reports Transform.PLY for ply/splat/ksplat/spz/sog). .spz data is
converted from its RUB convention to PLY's RDF convention on read, so the same rotation applies.
"""

from __future__ import annotations 

import os 
from dataclass import dataclass, field

import numpy as np 

from ..core.math3d import quat_from_euler
from ..core.splat import SplatData 

SUPPORTED_LOAD_EXTS = ('.ply', '.splat', '.ksplat', '.spz', '.sog', '.json')

def default_rotation() -> np.ndarray:
    return quat_from_euler(0,0,180)

@dataclass
class LoadResult:
    pass 

def _validate(data: SplatData, state):
    pass 

def load_file(path: str, progress=None) -> List[LoadResult]:
    pass 

