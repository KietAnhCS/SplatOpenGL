"""PlayCanvas SOG (version 2) reader: meta.json + lossless WebP textures, either loose
files next to meta.json or bundled in a .sog zip archive.

meta.json:
  means : {mins[3], maxs[3], files: [means_l.webp, means_u.webp]}  16-bit (lo/hi bytes) per axis,
          v = lerp(mins, maxs, q/65535); position = sign(v) * (exp(|v|) - 1)
  scales: {codebook[256], files: [scales.webp]}           rgb -> codebook index -> log scale
  quats : {files: [quats.webp]}                           rgb = 3 smallest comps, a = 252 + largest idx (w,x,y,z)
  sh0   : {codebook[256], files: [sh0.webp]}              rgb -> codebook -> f_dc, a = sigmoid(opacity)*255
  shN   : {count, bands, codebook[256], files: [shN_centroids.webp, shN_labels.webp]}
"""

from __future__ import annotations

import io
import json
import os
import zipfile

import numpy as np

from ..core.splat import SH_COEFFS_FOR_BANDS, SplatData, logit


def _image(get, name, n) -> np.ndarray:
    from PIL import Image
    with Image.open(io.BytesIO(get(name))) as im:
        a = np.asarray(im.convert('RGBA'))
    return a.reshape(-1, 4)[:n] if n is not None else a


def read_sog(path: str) -> SplatData:
    if path.lower().endswith('.sog') or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = {os.path.basename(i.filename): i.filename for i in z.infolist()}
            if 'meta.json' not in names:
                raise ValueError("sog: archive has no meta.json")

            def get(name):
                return z.read(names.get(os.path.basename(name), name))
            return _decode(json.loads(get('meta.json')), get)
    base = os.path.dirname(os.path.abspath(path))

    def get(name):
        with open(os.path.join(base, name), 'rb') as f:
            return f.read()
    with open(path, 'rb') as f:
        meta = json.loads(f.read())
    return _decode(meta, get)


def is_sog_meta(path: str) -> bool:
    try:
        with open(path, 'rb') as f:
            meta = json.loads(f.read(1 << 22))
        return isinstance(meta, dict) and 'means' in meta and 'quats' in meta
    except Exception:
        return False


def _decode(meta: dict, get) -> SplatData:
    try:
        version = int(meta.get('version', 1))
        if version < 2:
            raise ValueError("sog: only version 2 meta.json is supported")
        n = int(meta['count'])
        means = meta['means']
        lo = _image(get, means['files'][0], n)[:, :3].astype(np.uint32)
        hi = _image(get, means['files'][1], n)[:, :3].astype(np.uint32)
        q = ((hi << 8) | lo).astype(np.float64) / 65535.0
        mins, maxs = np.asarray(means['mins'], np.float64), np.asarray(means['maxs'], np.float64)
        v = mins + (maxs - mins) * q
        pos = np.sign(v) * (np.exp(np.abs(v)) - 1.0)

        scb = np.asarray(meta['scales']['codebook'], np.float32)
        scales = scb[_image(get, meta['scales']['files'][0], n)[:, :3]]

        qi = _image(get, meta['quats']['files'][0], n)
        comps = (qi[:, :3].astype(np.float64) / 255.0 - 0.5) * np.sqrt(2.0)
        largest = qi[:, 3].astype(np.int64) - 252
        if np.any((largest < 0) | (largest > 3)):
            raise ValueError("sog: bad quaternion mode")
        rows = np.arange(n)
        rot = np.empty((n, 4))
        rot[rows, largest] = np.sqrt(np.maximum(0.0, 1.0 - np.sum(comps * comps, axis=1)))
        slots = np.array([[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]])
        rot[rows[:, None], slots[largest]] = comps

        cb0 = np.asarray(meta['sh0']['codebook'], np.float32)
        s0 = _image(get, meta['sh0']['files'][0], n)
        sh0 = cb0[s0[:, :3]]
        opac = logit(s0[:, 3].astype(np.float32) / 255.0)

        sh_rest = None
        shn = meta.get('shN')
        if shn:
            bands = int(shn.get('bands', 3))
            m = SH_COEFFS_FOR_BANDS[bands]
            cbn = np.asarray(shn['codebook'], np.float32)
            cent = _image(get, shn['files'][0], None)       # (H, 64*m, 4)
            lab = _image(get, shn['files'][1], n)
            labels = lab[:, 0].astype(np.int64) | (lab[:, 1].astype(np.int64) << 8)
            h, w = cent.shape[:2]
            per_row = w // m
            palette = cent[:, :per_row * m, :3].reshape(h, per_row, m, 3).reshape(h * per_row, m, 3)
            labels = np.clip(labels, 0, len(palette) - 1)
            sh_rest = cbn[palette[labels]]
        return SplatData(pos, scales, rot, opac, sh0, sh_rest)
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"sog: malformed data ({e})") from None
