"""mkkellogg GaussianSplats3D .ksplat reader (compression levels 0, 1, 2).

Main header (4096 bytes): u8 versionMajor, u8 versionMinor, (pad), u32 maxSectionCount @4,
u32 sectionCount @8, u32 maxSplatCount @12, u32 splatCount @16, u16 compressionLevel @20,
f32 sceneCenter[3] @24, f32 minSH @36, f32 maxSH @40.
Section headers (1024 bytes each, maxSectionCount of them): u32 splatCount @0, u32 maxSplatCount @4,
u32 bucketSize @8, u32 bucketCount @12, f32 bucketBlockSize @16, u16 bucketStorageSizeBytes @20,
u32 compressionScaleRange @24, u32 storageSizeBytes @28, u32 fullBucketCount @32,
u32 partiallyFilledBucketCount @36, u16 shDegree @40.
Section data: partially-filled bucket lengths (u32 each), bucket centres (3 x f32), then splats.
Per splat: centre (3 f32 | 3 u16), scale (3 f32 | 3 f16, linear), rotation (4 f32 | 4 f16, w x y z),
colour rgba u8, SH (f32 | f16 | u8) interleaved [coeff][rgb].
"""

from __future__ import annotations

import struct

import numpy as np

from ..core.splat import SH_C0, SH_COEFFS_FOR_BANDS, SplatData, logit

HEADER_SIZE = 4096
SECTION_HEADER_SIZE = 1024


def read_ksplat(path: str) -> SplatData:
    with open(path, 'rb') as f:
        buf = f.read()
    if len(buf) < HEADER_SIZE:
        raise ValueError("ksplat: file too small")
    vmaj, vmin = buf[0], buf[1]
    if vmaj != 0 or vmin < 1:
        raise ValueError(f"ksplat: unsupported version {vmaj}.{vmin}")
    max_sections, section_count, _max_splats, _splat_count = struct.unpack_from('<IIII', buf, 4)
    level = struct.unpack_from('<H', buf, 20)[0]
    min_sh, max_sh = struct.unpack_from('<ff', buf, 36)
    if min_sh == 0 and max_sh == 0:
        min_sh, max_sh = -1.5, 1.5
    if level not in (0, 1, 2):
        raise ValueError(f"ksplat: unsupported compression level {level}")
    if HEADER_SIZE + max_sections * SECTION_HEADER_SIZE > len(buf):
        raise ValueError("ksplat: truncated section headers")

    pos_b, scl_b, rot_b = (12, 12, 16) if level == 0 else (6, 6, 8)
    sh_b = {0: 4, 1: 2, 2: 1}[level]

    out = []
    data_off = HEADER_SIZE + max_sections * SECTION_HEADER_SIZE
    for s in range(section_count):
        h = HEADER_SIZE + s * SECTION_HEADER_SIZE
        (count, max_count, bucket_size, bucket_count, block_size, bucket_storage, scale_range,
         storage, full_buckets, partial_buckets) = struct.unpack_from('<IIIIfHxxIIII', buf, h)
        sh_deg = struct.unpack_from('<H', buf, h + 40)[0]
        if sh_deg > 3:
            raise ValueError("ksplat: bad sh degree")
        if scale_range == 0:
            scale_range = 32767
        m = SH_COEFFS_FOR_BANDS[sh_deg]
        nsh = m * 3
        per = pos_b + scl_b + rot_b + 4 + nsh * sh_b
        meta_bytes = partial_buckets * 4
        buckets_bytes = bucket_storage * bucket_count + meta_bytes
        base = data_off + buckets_bytes
        if base + per * count > len(buf):
            raise ValueError("ksplat: truncated section data")
        raw = np.frombuffer(buf, np.uint8, per * count, base).reshape(count, per)
        o = 0

        def field(nbytes, dt):
            nonlocal o
            a = np.ascontiguousarray(raw[:, o:o + nbytes]).view(dt)
            o += nbytes
            return a

        if level == 0:
            pos = field(12, '<f4').astype(np.float32)
            scl = field(12, '<f4').astype(np.float32)
            rot = field(16, '<f4').astype(np.float32)
        else:
            qpos = field(6, '<u2').astype(np.float64)
            scl = field(6, '<f2').astype(np.float32)
            rot = field(8, '<f2').astype(np.float32)
            # bucket per splat
            partial_lens = np.frombuffer(buf, '<u4', partial_buckets, data_off).astype(np.int64)
            centers = np.frombuffer(buf, '<f4', bucket_count * 3, data_off + meta_bytes).reshape(-1, 3)
            lens = np.concatenate([np.full(full_buckets, bucket_size, np.int64), partial_lens])
            bidx = np.repeat(np.arange(len(lens)), lens)[:count]
            if len(bidx) < count:
                bidx = np.concatenate([bidx, np.full(count - len(bidx), max(len(lens) - 1, 0))])
            factor = (block_size / 2.0) / scale_range
            pos = ((qpos - scale_range) * factor + centers[bidx]).astype(np.float32)
        rgba = field(4, 'u1').astype(np.float32) / 255.0
        sh_rest = None
        if nsh:
            if sh_b == 4:
                sh = field(nsh * 4, '<f4').astype(np.float32)
            elif sh_b == 2:
                sh = field(nsh * 2, '<f2').astype(np.float32)
            else:
                sh = (min_sh + field(nsh, 'u1').astype(np.float32) / 255.0 * (max_sh - min_sh)).astype(np.float32)
            sh_rest = sh.reshape(count, m, 3)
        nrm = np.linalg.norm(rot, axis=1, keepdims=True)
        rot = np.where(nrm > 0, rot / np.where(nrm > 0, nrm, 1), np.array([1, 0, 0, 0], np.float32))
        out.append(SplatData(pos, np.log(np.maximum(scl, 1e-30)), rot, logit(rgba[:, 3]),
                             (rgba[:, :3] - 0.5) / SH_C0, sh_rest))
        data_off += storage
        del max_count
    if not out:
        return SplatData.empty()
    return out[0] if len(out) == 1 else SplatData.concat(out)
