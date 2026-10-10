from __future__ import annotations

from dataclasses import dataclass , field 

import numpy as np 

from .math3d import AABB, QUAT_IDENTITY, mat4_trs, quat_normalize, transform_points


SH_C0 = 0.28209479177387814


# ---- state bits (uint8 per gaussian). Same values as supersplat's PLY "state" column.
SELECTED = 1
LOCKED = 2      # "hidden" in the UI (Hide selection = lock)
DELETED = 4

# number of extra SH coefficients per colour channel for 0..3 bands
SH_COEFFS_FOR_BANDS = {0: 0, 1: 3, 2: 8, 3: 15}
SH_BANDS_FOR_COEFFS = {v: k for k, v in SH_COEFFS_FOR_BANDS.items()}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float32)))


def logit(p):
    p = np.clip(np.asarray(p, dtype=np.float32), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))

@dataclass 
class SplatData:
    pass 


@dataclass
class ColorAdjust:
    pass 


class Splat:
    pass 

