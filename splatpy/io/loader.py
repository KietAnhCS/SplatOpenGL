"""Load gaussian splat files into SplatData.

load_file(path) -> list[LoadResult]  (one entry per layer; currently always one)
Only .ply (including compressed PLY) is accepted. The loaded layer gets the initial rotation
quat_from_euler(0, 0, 180), exactly like SuperSplat.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from ..core.math3d import quat_from_euler
from ..core.splat import SplatData

SUPPORTED_LOAD_EXTS = ('.ply',)


def default_rotation() -> np.ndarray:
    return quat_from_euler(0, 0, 180)


@dataclass
class LoadResult:
    name: str
    data: SplatData
    state: np.ndarray | None = None
    rotation: np.ndarray = field(default_factory=default_rotation)


def _validate(data: SplatData, state):
    n = data.count
    if state is not None and len(state) != n:
        raise ValueError("state column length mismatch")
    # replace non-finite values so they cannot poison bounds / sorting
    for name in ('positions', 'scales', 'opacities', 'sh0'):
        a = getattr(data, name)
        if not np.isfinite(a).all():
            np.nan_to_num(a, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    if not np.isfinite(data.rotations).all():
        bad = ~np.isfinite(data.rotations).all(axis=1)
        data.rotations[bad] = (1, 0, 0, 0)
    if data.sh_rest is not None and not np.isfinite(data.sh_rest).all():
        np.nan_to_num(data.sh_rest, copy=False, nan=0.0, posinf=0.0, neginf=0.0)


def load_file(path: str, progress=None) -> list[LoadResult]:
    """Load a splat file. Raises ValueError on unsupported or corrupt input."""
    if not os.path.isfile(path):
        raise ValueError(f"file not found: {path}")
    name = os.path.basename(path)
    ext = os.path.splitext(name.lower())[1]
    if progress:
        progress(0.0)
    if ext != '.ply':
        raise ValueError(f"unsupported file type: {ext or name} (only .ply is supported)")
    state = None
    try:
        from . import compressed_ply, ply
        sub = (lambda f: progress(0.9 * f)) if progress else None
        _, elements = ply.read_ply_elements(path, wanted={'vertex', 'chunk', 'sh'}, progress=sub)
        if compressed_ply.is_compressed(elements):
            data = compressed_ply.decode(elements)
        else:
            v = elements.get('vertex')
            if v is None:
                raise ValueError("PLY file has no vertex element")
            data, state = ply.gaussians_from_vertex(v)
    except ValueError:
        raise
    except (OSError, EOFError, KeyError, IndexError, TypeError, OverflowError, MemoryError) as e:
        raise ValueError(f"failed to load {name}: {e}") from e
    _validate(data, state)
    if progress:
        progress(1.0)
    return [LoadResult(name=name, data=data, state=state, rotation=default_rotation())]
