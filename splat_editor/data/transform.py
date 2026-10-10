from __future__ import annotations

import numpy as np

from ..core.math3d import mat4_decompose, quat_mul, quat_normalize, quat_to_mat3, transform_points
from ..core.splat import SplatData
from .sh_utils import rotate_sh


def _decompose(m):


def _apply(data: SplatData, m: np.ndarray, sel) -> None:


def _normalize_sel(indices, n):


def deep_copy(data: SplatData) -> SplatData:


def transform_data(data: SplatData, m: np.ndarray, indices=None) -> SplatData:


def transform_data_inplace(data: SplatData, m: np.ndarray, indices) -> None:
