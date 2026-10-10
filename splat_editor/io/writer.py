"""Export splat layers to a file.

export_splats(splats, path, options) merges every visible layer into one file:
  * DELETED gaussians are skipped (and with selected_only, everything not exactly SELECTED),
  * the layer transform is baked: inv(quat_from_euler(0,0,180)) @ world_matrix (undoes the load
    rotation, like supersplat's mat.setFromEulerAngles(0,0,-180)) or world_matrix alone when
    keep_world_transform; skipped entirely when the matrix is identity,
  * the layer colour grade is baked when not identity,
  * SH bands are limited to options.sh_bands.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from ..core.math3d import mat4_from_quat, quat_from_euler
from ..core.splat import DELETED, LOCKED, SELECTED, SH_COEFFS_FOR_BANDS, Splat, SplatData

SUPPORTED_SAVE_FORMATS = {
    'ply': '.ply',
    'compressed-ply': '.compressed.ply',
    'splat': '.splat',
    'spz': '.spz',
}


@dataclass
class ExportOptions:
    format: str = 'ply'
    sh_bands: int = 3                   # max SH bands written
    selected_only: bool = False         # only SELECTED gaussians
    keep_world_transform: bool = False  # False = undo the load rotation (default, like supersplat)
    include_state: bool = False         # write 'state' column (ply only)
    include_extra: bool = True          # write unknown per-vertex PLY properties (ply only)
    spz_version: int = 3                # 2 or 3


def format_for_path(path: str) -> str:
    """Guess export format from a filename."""
    p = path.lower()
    if p.endswith('.compressed.ply'):
        return 'compressed-ply'
    for fmt, ext in SUPPORTED_SAVE_FORMATS.items():
        if p.endswith(ext):
            return fmt
    raise ValueError(f"unsupported export extension: {os.path.splitext(p)[1]}")


def export_matrix(splat: Splat, keep_world_transform: bool) -> np.ndarray:
    world = splat.world_matrix()
    if keep_world_transform:
        return world
    return np.linalg.inv(mat4_from_quat(quat_from_euler(0, 0, 180))) @ world


def _truncate_sh(data: SplatData, bands: int) -> SplatData:
    if data.sh_rest is None:
        return data
    m = SH_COEFFS_FOR_BANDS[max(0, min(3, int(bands)))]
    if m >= data.sh_rest.shape[1]:
        return data
    return SplatData(data.positions, data.scales, data.rotations, data.opacities, data.sh0,
                     data.sh_rest[:, :m, :] if m else None, data.extra)


def prepare_export(splats: list[Splat], options: ExportOptions) -> tuple[SplatData, np.ndarray]:
    """Returns (merged SplatData in export space, merged state uint8)."""
    parts, states = [], []
    for s in splats:
        if not s.visible or s.count == 0:
            continue
        st = s.state
        if options.selected_only:
            mask = (st & (SELECTED | DELETED | LOCKED)) == SELECTED
        else:
            mask = (st & DELETED) == 0
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            continue
        d = s.data.subset(idx)
        d = _truncate_sh(d, options.sh_bands)
        m = export_matrix(s, options.keep_world_transform)
        if not np.allclose(m, np.eye(4), atol=1e-9):
            from ..data.transform import transform_data
            d = transform_data(d, m)
        if not s.color.is_identity():
            from ..data.color_grade import apply_grade_to_data
            d = apply_grade_to_data(d, s.color)
        parts.append(d)
        states.append(st[idx])
    if not parts:
        return SplatData.empty(), np.zeros(0, np.uint8)
    data = parts[0] if len(parts) == 1 else SplatData.concat(parts)
    return data, np.concatenate(states)


def export_splats(splats: list[Splat], path: str, options: ExportOptions | None = None, progress=None) -> int:
    """Write visible layers to `path`. Returns number of gaussians written."""
    options = options or ExportOptions()
    fmt = options.format
    if fmt not in SUPPORTED_SAVE_FORMATS:
        raise ValueError(f"unsupported export format: {fmt}")
    if progress:
        progress(0.0)
    data, state = prepare_export(splats, options)
    if progress:
        progress(0.4)
    sub = (lambda f: progress(0.4 + 0.6 * f)) if progress else None
    if fmt == 'ply':
        from .ply import write_ply
        n = write_ply(path, data, (state & ~np.uint8(DELETED)).astype(np.uint8) if options.include_state else None,
                      sh_bands=options.sh_bands, include_extra=options.include_extra)
    elif fmt == 'compressed-ply':
        from .compressed_ply import write_compressed_ply
        n = write_compressed_ply(path, data, sh_bands=options.sh_bands, progress=sub)
    elif fmt == 'splat':
        from .splat_format import write_splat
        n = write_splat(path, data)
    else:
        from .spz import write_spz
        n = write_spz(path, data, sh_bands=options.sh_bands, version=options.spz_version)
    if progress:
        progress(1.0)
    return n
