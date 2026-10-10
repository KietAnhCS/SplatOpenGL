"""Niantic .spz (gzip-compressed), versions 1-3.

Header (16 bytes, little endian): magic 0x5053474e ('NGSP'), version u32, numPoints u32,
shDegree u8, fractionalBits u8, flags u8, reserved u8.
Then, in this order:
  positions  N*3 * 24-bit signed fixed point (v1: float16)
  alphas     N   u8  (sigmoid(opacity) * 255)
  colors     N*3 u8  (f_dc * 0.15 + 0.5) * 255
  scales     N*3 u8  (log_scale + 10) * 16
  rotations  v1/v2: N*3 u8 (x,y,z)*127.5+127.5, w >= 0 ; v3: N*4 bytes smallest-three (2-bit index + 3x(sign+9bit))
  sh         N * coeffs * 3 u8, per gaussian [coeff][channel], (v-128)/128

SPZ data is in RUB (OpenGL) coordinates whereas PLY is RDF; we convert on read/write
(rotation of 180 degrees about X: y -> -y, z -> -z), so loaded data matches the PLY convention.
"""

from __future__ import annotations

import gzip
import struct

import numpy as np

from ..core.splat import SH_COEFFS_FOR_BANDS, SplatData, logit, sigmoid

MAGIC = 0x5053474e
COLOR_SCALE = 0.15
_SQRT_HALF = np.sqrt(0.5)

# sign of each SH coefficient (k=0..14) under (x,y,z) -> (x,-y,-z)
_SH_FLIP = np.array([-1, -1, 1,
                     -1, 1, 1, -1, 1,
                     -1, 1, -1, -1, 1, -1, 1], np.float32)


def flip_yz(data: SplatData) -> SplatData:
    """Apply the 180-degree X rotation (x,y,z)->(x,-y,-z) to all attributes (self-inverse)."""
    pos = data.positions * np.array([1, -1, -1], np.float32)
    rot = data.rotations * np.array([1, 1, -1, -1], np.float32)
    sh = None
    if data.sh_rest is not None:
        sh = data.sh_rest * _SH_FLIP[:data.sh_rest.shape[1], None]
    return SplatData(pos, data.scales.copy(), rot, data.opacities.copy(), data.sh0.copy(), sh, dict(data.extra))


def read_spz(path: str) -> SplatData:
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        buf = gzip.decompress(raw)
    except Exception as e:
        raise ValueError(f"spz: not a gzip stream ({e})") from None
    if len(buf) < 16:
        raise ValueError("spz: truncated header")
    magic, version, n, sh_deg, frac, flags, _ = struct.unpack_from('<IIIBBBB', buf, 0)
    if magic != MAGIC:
        raise ValueError("spz: bad magic")
    if version not in (1, 2, 3):
        raise ValueError(f"spz: unsupported version {version}")
    if sh_deg > 3:
        raise ValueError("spz: bad sh degree")
    m = SH_COEFFS_FOR_BANDS[sh_deg]
    off = 16

    def take(nbytes):
        nonlocal off
        if off + nbytes > len(buf):
            raise ValueError("spz: truncated data")
        b = np.frombuffer(buf, np.uint8, nbytes, off)
        off += nbytes
        return b

    if version == 1:
        pos = take(n * 6).view('<f2').astype(np.float32).reshape(n, 3)
    else:
        b = take(n * 9).reshape(n * 3, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - (1 << 24), v)
        pos = (v.astype(np.float64) / float(1 << frac)).astype(np.float32).reshape(n, 3)
    alpha = take(n).astype(np.float32) / 255.0
    col = take(n * 3).reshape(n, 3).astype(np.float32)
    sh0 = (col / 255.0 - 0.5) / COLOR_SCALE
    scales = take(n * 3).reshape(n, 3).astype(np.float32) / 16.0 - 10.0
    if version == 3:
        comp = take(n * 4).view('<u4').astype(np.uint32)
        largest = (comp >> np.uint32(30)).astype(np.int64)
        q = np.zeros((n, 4), np.float64)   # x,y,z,w
        rows = np.arange(n)
        c = comp.copy()
        mask = np.uint32(511)
        acc = np.zeros(n)
        for i in (3, 2, 1, 0):
            sel = largest != i
            mag = (c & mask).astype(np.float64)
            neg = ((c >> np.uint32(9)) & np.uint32(1)) == 1
            val = _SQRT_HALF * mag / 511.0
            val = np.where(neg, -val, val)
            q[sel, i] = val[sel]
            acc += np.where(sel, val * val, 0.0)
            c = np.where(sel, c >> np.uint32(10), c)
        q[rows, largest] = np.sqrt(np.maximum(0.0, 1.0 - acc))
    else:
        xyz = take(n * 3).reshape(n, 3).astype(np.float64) / 127.5 - 1.0
        w = np.sqrt(np.maximum(0.0, 1.0 - np.sum(xyz * xyz, axis=1)))
        q = np.concatenate([xyz, w[:, None]], axis=1)
    rot = q[:, [3, 0, 1, 2]]
    rot /= np.maximum(np.linalg.norm(rot, axis=1, keepdims=True), 1e-30)
    sh_rest = None
    if m:
        sh_rest = (take(n * m * 3).reshape(n, m, 3).astype(np.float32) - 128.0) / 128.0
    data = SplatData(pos, scales, rot, logit(alpha), sh0, sh_rest)
    return flip_yz(data)


def _quantize_sh(x: np.ndarray, bits: int) -> np.ndarray:
    q = np.round(x.astype(np.float64) * 128.0) + 128.0
    bucket = 1 << (8 - bits)
    q = np.floor((q + bucket / 2) / bucket) * bucket
    return np.clip(q, 0, 255).astype(np.uint8)


def write_spz(path: str, data: SplatData, sh_bands: int = 3, version: int = 3) -> int:
    if version not in (2, 3):
        raise ValueError("spz writer supports versions 2 and 3")
    d = flip_yz(data)
    n = d.count
    m = 0 if d.sh_rest is None else min(d.sh_rest.shape[1], SH_COEFFS_FOR_BANDS[max(0, min(3, sh_bands))])
    sh_deg = {0: 0, 3: 1, 8: 2, 15: 3}[m]
    maxabs = float(np.abs(d.positions).max()) if n else 0.0
    frac = 12
    while frac > 0 and maxabs * (1 << frac) >= (1 << 23) - 1:
        frac -= 1
    parts = [struct.pack('<IIIBBBB', MAGIC, version, n, sh_deg, frac, 0, 0)]
    fixed = np.clip(np.round(d.positions.astype(np.float64) * (1 << frac)), -(1 << 23), (1 << 23) - 1)
    fixed = fixed.astype(np.int64).reshape(-1) & 0xffffff
    pb = np.stack([fixed & 0xff, (fixed >> 8) & 0xff, (fixed >> 16) & 0xff], axis=1).astype(np.uint8)
    parts.append(pb.tobytes())
    parts.append(np.clip(np.round(sigmoid(d.opacities) * 255.0), 0, 255).astype(np.uint8).tobytes())
    col = (d.sh0.astype(np.float64) * COLOR_SCALE + 0.5) * 255.0
    parts.append(np.clip(np.round(col), 0, 255).astype(np.uint8).tobytes())
    parts.append(np.clip(np.round((d.scales.astype(np.float64) + 10.0) * 16.0), 0, 255).astype(np.uint8).tobytes())
    q = d.rotations[:, [1, 2, 3, 0]].astype(np.float64)   # x,y,z,w
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-30)
    if version == 3:
        largest = np.argmax(np.abs(q), axis=1)
        rows = np.arange(n)
        negate = q[rows, largest] < 0
        comp = largest.astype(np.uint32)
        for i in range(4):
            sel = largest != i
            negbit = ((q[:, i] < 0) ^ negate).astype(np.uint32)
            mag = np.clip(np.floor(511.0 * (np.abs(q[:, i]) / _SQRT_HALF) + 0.5), 0, 511).astype(np.uint32)
            comp = np.where(sel, (comp << np.uint32(10)) | (negbit << np.uint32(9)) | mag, comp)
        parts.append(comp.astype('<u4').tobytes())
    else:
        q = np.where(q[:, 3:4] < 0, -q, q)
        parts.append(np.clip(np.round(q[:, :3] * 127.5 + 127.5), 0, 255).astype(np.uint8).tobytes())
    if m:
        sh = d.sh_rest[:, :m, :]
        qs = np.empty((n, m, 3), np.uint8)
        qs[:, :3] = _quantize_sh(sh[:, :3], 5)
        if m > 3:
            qs[:, 3:] = _quantize_sh(sh[:, 3:], 4)
        parts.append(qs.tobytes())
    with open(path, 'wb') as f:
        f.write(gzip.compress(b''.join(parts), compresslevel=6))
    return n
