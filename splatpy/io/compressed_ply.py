"""PlayCanvas / SuperSplat compressed PLY.

Layout:
  element chunk C        (float) min_x min_y min_z max_x max_y max_z
                          min_scale_x.. max_scale_z  [min_r min_g min_b max_r max_g max_b]
  element vertex N       (uint) packed_position (11-10-11), packed_rotation (2-10-10-10 smallest three),
                          packed_scale (11-10-11), packed_color (8-8-8-8 rgba)
  [element sh N]         (uchar) f_rest_0 .. f_rest_{3M-1}   (channel-major, like PLY)
256 gaussians per chunk; gaussian i belongs to chunk i // 256.
"""

from __future__ import annotations

import numpy as np

from ..core.splat import SH_BANDS_FOR_COEFFS, SH_C0, SH_COEFFS_FOR_BANDS, SplatData, sigmoid

CHUNK_SIZE = 256
_SQRT2 = np.sqrt(2.0)
# positions of the three stored components for each "largest" index (quat order x,y,z,w)
_ROT_SLOTS = np.array([[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]])


def is_compressed(elements: dict) -> bool:
    v = elements.get('vertex')
    return elements.get('chunk') is not None and v is not None and 'packed_position' in (v.dtype.names or ())


def _unorm(v: np.ndarray, shift: int, bits: int) -> np.ndarray:
    mask = (1 << bits) - 1
    return ((v >> np.uint32(shift)) & np.uint32(mask)).astype(np.float32) / np.float32(mask)


def _unpack_111011(v):
    return np.stack([_unorm(v, 21, 11), _unorm(v, 11, 10), _unorm(v, 0, 11)], axis=1)


def _unpack_8888(v):
    return np.stack([_unorm(v, 24, 8), _unorm(v, 16, 8), _unorm(v, 8, 8), _unorm(v, 0, 8)], axis=1)


def _unpack_rot(v):
    norm = np.float32(_SQRT2)   # 1 / (sqrt(2) * 0.5)
    abc = np.stack([(_unorm(v, 20, 10) - 0.5) * norm, (_unorm(v, 10, 10) - 0.5) * norm,
                    (_unorm(v, 0, 10) - 0.5) * norm], axis=1)
    m = np.sqrt(np.maximum(0.0, 1.0 - np.sum(abc * abc, axis=1)))
    mode = (v >> np.uint32(30)).astype(np.int64)
    n = len(v)
    xyzw = np.empty((n, 4), np.float32)
    rows = np.arange(n)
    xyzw[rows, mode] = m
    xyzw[rows[:, None], _ROT_SLOTS[mode]] = abc
    return xyzw[:, [3, 0, 1, 2]]   # -> w,x,y,z


def decode(elements: dict) -> SplatData:
    chunk = elements['chunk']
    vert = elements['vertex']
    n = len(vert)
    if len(chunk) * CHUNK_SIZE < n:
        raise ValueError("compressed PLY: not enough chunks for vertex count")
    ci = np.arange(n) // CHUNK_SIZE
    cn = chunk.dtype.names

    def cvec(prefix, suffixes):
        return np.stack([np.asarray(chunk[prefix + s], np.float32) for s in suffixes], axis=1)[ci]

    def lerp(a, b, t):
        return a + (b - a) * t

    pos = lerp(cvec('min_', 'xyz'), cvec('max_', 'xyz'), _unpack_111011(np.asarray(vert['packed_position'], np.uint32)))
    scl = lerp(cvec('min_scale_', 'xyz'), cvec('max_scale_', 'xyz'),
               _unpack_111011(np.asarray(vert['packed_scale'], np.uint32)))
    rot = _unpack_rot(np.asarray(vert['packed_rotation'], np.uint32))
    col = _unpack_8888(np.asarray(vert['packed_color'], np.uint32))
    rgb = col[:, :3]
    if all(k in cn for k in ('min_r', 'min_g', 'min_b', 'max_r', 'max_g', 'max_b')):
        rgb = lerp(cvec('min_', 'rgb'), cvec('max_', 'rgb'), rgb)
    sh0 = (rgb - 0.5) / SH_C0
    a = np.clip(col[:, 3], 1e-6, 1 - 1e-6)
    opac = -np.log(1.0 / a - 1.0)

    sh_rest = None
    sh = elements.get('sh')
    if sh is not None and len(sh) == n:
        names = [k for k in sh.dtype.names if k.startswith('f_rest_')]
        per = len(names) // 3
        m = max(c for c in SH_BANDS_FOR_COEFFS if c <= per)
        if m:
            sh_rest = np.empty((n, m, 3), np.float32)
            for c in range(3):
                for k in range(m):
                    q = np.asarray(sh[f'f_rest_{c * per + k}'], np.float32)
                    nv = np.where(q == 0, 0.0, (q + 0.5) / 256.0)
                    sh_rest[:, k, c] = (nv - 0.5) * 8.0
    return SplatData(pos, scl, rot, opac, sh0, sh_rest)


# ----------------------------------------------------------------------------- writing

def _part1by2(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.uint32) & np.uint32(0x3ff)
    x = (x | (x << np.uint32(16))) & np.uint32(0xff0000ff)
    x = (x | (x << np.uint32(8))) & np.uint32(0x0300f00f)
    x = (x | (x << np.uint32(4))) & np.uint32(0x030c30c3)
    x = (x | (x << np.uint32(2))) & np.uint32(0x09249249)
    return x


def morton_order(positions: np.ndarray) -> np.ndarray:
    if len(positions) == 0:
        return np.zeros(0, np.int64)
    p = np.nan_to_num(positions.astype(np.float64))
    lo = p.min(axis=0)
    ext = np.maximum(p.max(axis=0) - lo, 1e-12)
    q = np.clip(((p - lo) / ext * 1023.0), 0, 1023).astype(np.uint32)
    code = _part1by2(q[:, 0]) | (_part1by2(q[:, 1]) << np.uint32(1)) | (_part1by2(q[:, 2]) << np.uint32(2))
    return np.argsort(code, kind='stable')


def _pack_unorm(v: np.ndarray, bits: int) -> np.ndarray:
    t = (1 << bits) - 1
    return np.clip(np.floor(v * t + 0.5), 0, t).astype(np.uint32)


def _norm(v, lo, hi):
    d = hi - lo
    return np.where(d > 0, (v - lo) / np.where(d > 0, d, 1.0), 0.0)


def _pack_111011(t):
    return (_pack_unorm(t[:, 0], 11) << np.uint32(21)) | (_pack_unorm(t[:, 1], 10) << np.uint32(11)) | \
        _pack_unorm(t[:, 2], 11)


def _pack_rot(q_wxyz: np.ndarray) -> np.ndarray:
    q = q_wxyz[:, [1, 2, 3, 0]].astype(np.float64)    # x,y,z,w
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-30)
    n = len(q)
    largest = np.argmax(np.abs(q), axis=1)
    rows = np.arange(n)
    sign = np.where(q[rows, largest] < 0, -1.0, 1.0)
    q *= sign[:, None]
    abc = q[rows[:, None], _ROT_SLOTS[largest]] * (_SQRT2 * 0.5) + 0.5
    return (largest.astype(np.uint32) << np.uint32(30)) | (_pack_unorm(abc[:, 0], 10) << np.uint32(20)) | \
        (_pack_unorm(abc[:, 1], 10) << np.uint32(10)) | _pack_unorm(abc[:, 2], 10)


def write_compressed_ply(path: str, data: SplatData, sh_bands: int = 3, progress=None) -> int:
    n = data.count
    order = morton_order(data.positions)
    d = data.subset(order)
    nchunks = (n + CHUNK_SIZE - 1) // CHUNK_SIZE
    pad = nchunks * CHUNK_SIZE - n

    def chunked(a):
        a = np.asarray(a, np.float64)
        if pad and n:
            a = np.concatenate([a, np.repeat(a[-1:], pad, axis=0)])
        return a.reshape(nchunks, CHUNK_SIZE, -1)

    pos = d.positions.astype(np.float64)
    scl = np.clip(d.scales.astype(np.float64), -20, 20)
    rgb = 0.5 + SH_C0 * d.sh0.astype(np.float64)
    pc, sc, cc = chunked(pos), chunked(scl), chunked(rgb)
    pmin, pmax = pc.min(axis=1), pc.max(axis=1)
    smin, smax = sc.min(axis=1), sc.max(axis=1)
    cmin, cmax = cc.min(axis=1), cc.max(axis=1)
    if progress:
        progress(0.3)

    chunk_names = ['min_x', 'min_y', 'min_z', 'max_x', 'max_y', 'max_z',
                   'min_scale_x', 'min_scale_y', 'min_scale_z', 'max_scale_x', 'max_scale_y', 'max_scale_z',
                   'min_r', 'min_g', 'min_b', 'max_r', 'max_g', 'max_b']
    chunk_arr = np.concatenate([pmin, pmax, smin, smax, cmin, cmax], axis=1).astype('<f4')
    # make the stored float32 bounds the ones used for quantisation
    b = chunk_arr.astype(np.float64)
    ci = np.arange(n) // CHUNK_SIZE
    pmin, pmax = b[ci, 0:3], b[ci, 3:6]
    smin, smax = b[ci, 6:9], b[ci, 9:12]
    cmin, cmax = b[ci, 12:15], b[ci, 15:18]

    vdt = np.dtype([('packed_position', '<u4'), ('packed_rotation', '<u4'), ('packed_scale', '<u4'),
                    ('packed_color', '<u4')])
    vert = np.empty(n, vdt)
    vert['packed_position'] = _pack_111011(_norm(pos, pmin, pmax))
    vert['packed_scale'] = _pack_111011(_norm(scl, smin, smax))
    vert['packed_rotation'] = _pack_rot(d.rotations)
    cn = _norm(rgb, cmin, cmax)
    alpha = sigmoid(d.opacities).astype(np.float64)
    vert['packed_color'] = (_pack_unorm(cn[:, 0], 8) << np.uint32(24)) | (_pack_unorm(cn[:, 1], 8) << np.uint32(16)) | \
        (_pack_unorm(cn[:, 2], 8) << np.uint32(8)) | _pack_unorm(alpha, 8)
    if progress:
        progress(0.7)

    m = 0
    if d.sh_rest is not None:
        m = min(d.sh_rest.shape[1], SH_COEFFS_FOR_BANDS[max(0, min(3, sh_bands))])
    sh_arr = None
    if m:
        sh_arr = np.empty((n, 3 * m), np.uint8)
        for c in range(3):
            nv = d.sh_rest[:, :m, c].astype(np.float64) / 8.0 + 0.5
            sh_arr[:, c * m:(c + 1) * m] = np.clip(np.trunc(nv * 256.0), 0, 255).astype(np.uint8)

    lines = ['ply', 'format binary_little_endian 1.0', 'comment generated by splatpy',
             f'element chunk {nchunks}']
    lines += [f'property float {k}' for k in chunk_names]
    lines.append(f'element vertex {n}')
    lines += [f'property uint {k}' for k in vdt.names]
    if m:
        lines.append(f'element sh {n}')
        lines += [f'property uchar f_rest_{i}' for i in range(3 * m)]
    lines.append('end_header')
    with open(path, 'wb') as f:
        f.write(('\n'.join(lines) + '\n').encode('ascii'))
        f.write(np.ascontiguousarray(chunk_arr).tobytes())
        vert.tofile(f)
        if m:
            f.write(np.ascontiguousarray(sh_arr).tobytes())
    if progress:
        progress(1.0)
    return n
