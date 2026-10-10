"""antimatter15 .splat format: 32 bytes per gaussian.

  float32 x, y, z | float32 sx, sy, sz (linear scale) | uint8 r, g, b, a | uint8 rot w, x, y, z  ((q*128)+128)
"""

from __future__ import annotations

import os

import numpy as np

from ..core.splat import SH_C0, SplatData, logit, sigmoid

SPLAT_DTYPE = np.dtype([('pos', '<f4', 3), ('scale', '<f4', 3), ('rgba', 'u1', 4), ('rot', 'u1', 4)])


def read_splat(path: str) -> SplatData:
    size = os.path.getsize(path)
    if size % 32 != 0:
        raise ValueError(".splat file size is not a multiple of 32 bytes")
    arr = np.fromfile(path, dtype=SPLAT_DTYPE)
    rgba = arr['rgba'].astype(np.float32) / 255.0
    rot = (arr['rot'].astype(np.float32) - 128.0) / 128.0
    nrm = np.linalg.norm(rot, axis=1, keepdims=True)
    rot = np.where(nrm > 0, rot / np.where(nrm > 0, nrm, 1), np.array([1, 0, 0, 0], np.float32))
    scale = np.log(np.maximum(arr['scale'].astype(np.float32), 1e-30))
    return SplatData(arr['pos'], scale, rot, logit(rgba[:, 3]), (rgba[:, :3] - 0.5) / SH_C0)


def write_splat(path: str, data: SplatData) -> int:
    n = data.count
    arr = np.empty(n, SPLAT_DTYPE)
    arr['pos'] = data.positions
    arr['scale'] = np.exp(data.scales)
    rgb = 0.5 + SH_C0 * data.sh0
    a = sigmoid(data.opacities)
    arr['rgba'][:, :3] = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    arr['rgba'][:, 3] = np.clip(np.round(a * 255.0), 0, 255).astype(np.uint8)
    q = data.rotations.astype(np.float64)
    q = q / np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-30)
    arr['rot'] = np.clip(np.round(q * 128.0 + 128.0), 0, 255).astype(np.uint8)
    arr.tofile(path)
    return n
