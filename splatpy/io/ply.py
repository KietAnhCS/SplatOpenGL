"""PLY reading / writing (binary little/big endian and ascii).

read_ply_elements(path) parses any PLY into {element name: numpy structured array}.
gaussians_from_vertex(v) converts a 'vertex' element into SplatData (+ optional state),
handling standard 3DGS columns, plain point clouds (x,y,z + red,green,blue) and
keeping unknown properties in SplatData.extra.
write_ply(path, data, state=None, sh_bands=3) writes a standard binary little endian 3DGS PLY.
"""

from __future__ import annotations

import re

import numpy as np

from ..core.splat import SH_BANDS_FOR_COEFFS, SH_C0, SH_COEFFS_FOR_BANDS, SplatData, logit

PLY_TYPES = {
    'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
    'short': 'i2', 'int16': 'i2', 'ushort': 'u2', 'uint16': 'u2',
    'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'uint32': 'u4',
    'float': 'f4', 'float32': 'f4', 'double': 'f8', 'float64': 'f8',
}
NUMPY_TO_PLY = {'i1': 'char', 'u1': 'uchar', 'i2': 'short', 'u2': 'ushort', 'i4': 'int', 'u4': 'uint',
                'f4': 'float', 'f8': 'double'}

_BATCH = 1 << 20   # rows per read batch (progress granularity)


class PlyElement:
    def __init__(self, name: str, count: int):
        self.name = name
        self.count = count
        self.props: list[tuple] = []   # (name, dtype) or (name, 'list', count_dtype, item_dtype)

    @property
    def has_list(self) -> bool:
        return any(len(p) == 4 for p in self.props)

    def dtype(self, endian: str) -> np.dtype:
        return np.dtype([(p[0], endian + p[1]) for p in self.props])


class PlyHeader:
    def __init__(self):
        self.format = 'binary_little_endian'
        self.comments: list[str] = []
        self.elements: list[PlyElement] = []
        self.size = 0   # bytes of header incl. end_header newline

    def element(self, name):
        for e in self.elements:
            if e.name == name:
                return e
        return None


def parse_header(f) -> PlyHeader:
    first = f.readline()
    if first.strip() != b'ply':
        raise ValueError("not a PLY file (missing 'ply' magic)")
    h = PlyHeader()
    size = len(first)
    while True:
        line = f.readline()
        if not line:
            raise ValueError("PLY header not terminated")
        size += len(line)
        if size > 1 << 24:
            raise ValueError("PLY header too large")
        parts = line.decode('ascii', errors='replace').strip().split()
        if not parts:
            continue
        kw = parts[0]
        if kw == 'end_header':
            break
        if kw == 'format':
            if len(parts) < 2 or parts[1] not in ('ascii', 'binary_little_endian', 'binary_big_endian'):
                raise ValueError(f"unsupported PLY format: {' '.join(parts[1:])}")
            h.format = parts[1]
        elif kw in ('comment', 'obj_info'):
            h.comments.append(' '.join(parts[1:]))
        elif kw == 'element':
            if len(parts) != 3:
                raise ValueError(f"bad element line: {line!r}")
            h.elements.append(PlyElement(parts[1], int(parts[2])))
        elif kw == 'property':
            if not h.elements:
                raise ValueError("property before element")
            el = h.elements[-1]
            try:
                if parts[1] == 'list':
                    el.props.append((parts[4], 'list', PLY_TYPES[parts[2]], PLY_TYPES[parts[3]]))
                else:
                    el.props.append((parts[2], PLY_TYPES[parts[1]]))
            except (KeyError, IndexError):
                raise ValueError(f"bad property line: {line!r}") from None
        else:
            raise ValueError(f"unknown PLY header keyword {kw!r}")
    h.size = size
    return h


def _read_list_element_binary(f, el: PlyElement, endian: str):
    """Slow fallback for elements with list properties: returns None (data skipped) but advances f."""
    for _ in range(el.count):
        for p in el.props:
            if len(p) == 4:
                cdt = np.dtype(endian + p[2])
                n = int(np.frombuffer(f.read(cdt.itemsize), cdt)[0])
                f.read(n * np.dtype(p[3]).itemsize)
            else:
                f.read(np.dtype(p[1]).itemsize)
    return None


def read_ply_elements(path: str, wanted=None, progress=None):
    """-> (header, {name: structured array}). Elements with list properties are skipped (None).
    `wanted`: optional set of element names; reading stops once all were read."""
    with open(path, 'rb') as f:
        h = parse_header(f)
        out = {}
        if h.format == 'ascii':
            return h, _read_ascii(f, h, wanted)
        endian = '<' if h.format == 'binary_little_endian' else '>'
        total = sum(e.count for e in h.elements if (wanted is None or e.name in wanted)) or 1
        done = 0
        for el in h.elements:
            if wanted is not None and all(n in out for n in wanted if h.element(n) is not None):
                break
            if el.has_list:
                out[el.name] = _read_list_element_binary(f, el, endian)
                continue
            dt = el.dtype(endian)
            if wanted is not None and el.name not in wanted:
                f.seek(dt.itemsize * el.count, 1)
                continue
            arr = np.empty(el.count, dt)
            pos = 0
            while pos < el.count:
                n = min(_BATCH, el.count - pos)
                chunk = np.fromfile(f, dtype=dt, count=n)
                if len(chunk) != n:
                    raise ValueError(f"PLY file truncated in element '{el.name}'")
                arr[pos:pos + n] = chunk
                pos += n
                done += n
                if progress:
                    progress(min(1.0, done / total))
            if endian == '>':
                arr = arr.astype(el.dtype('<'))
            out[el.name] = arr
        return h, out


def _read_ascii(f, h: PlyHeader, wanted):
    text = f.read().decode('ascii', errors='replace')
    out = {}
    lines = text.splitlines()
    li = 0
    for el in h.elements:
        if el.has_list:
            # per-line parse, keep only scalar props
            li += el.count
            out[el.name] = None
            continue
        block = lines[li:li + el.count]
        li += el.count
        if len(block) != el.count:
            raise ValueError(f"ascii PLY truncated in element '{el.name}'")
        if wanted is not None and el.name not in wanted:
            continue
        nprop = len(el.props)
        vals = np.array(' '.join(block).split(), dtype=np.float64) if el.count else np.zeros(0)
        if vals.size != el.count * nprop:
            raise ValueError(f"ascii PLY element '{el.name}' has wrong number of values")
        vals = vals.reshape(el.count, nprop)
        arr = np.empty(el.count, el.dtype('<'))
        for i, p in enumerate(el.props):
            arr[p[0]] = vals[:, i]
        out[el.name] = arr
    return out


# ----------------------------------------------------------------------------- gaussians

_FREST = re.compile(r'^f_rest_(\d+)$')
KNOWN = {'x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity', 'scale_0', 'scale_1', 'scale_2',
         'rot_0', 'rot_1', 'rot_2', 'rot_3', 'state'}


def _normalize_quats(q: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(q, axis=1, keepdims=True)
    bad = (n[:, 0] == 0) | ~np.isfinite(n[:, 0])
    q = q / np.where(n == 0, 1.0, n)
    if bad.any():
        q[bad] = (1, 0, 0, 0)
    return q.astype(np.float32)


def _sh_rest_from_columns(cols: dict[int, np.ndarray], n: int):
    """cols: f_rest index -> (N,) column. Returns (sh_rest or None, used index set)."""
    if not cols:
        return None, set()
    total = len(cols)
    per = total // 3
    # largest valid coefficient count <= per channel
    m = max(c for c in SH_BANDS_FOR_COEFFS if c <= per)
    if m == 0 or any(i not in cols for i in range(per * 3)):
        return None, set()
    sh = np.empty((n, m, 3), np.float32)
    for c in range(3):
        for k in range(m):
            sh[:, k, c] = cols[c * per + k]
    used = set(range(per * 3)) if per == m else {c * per + k for c in range(3) for k in range(m)}
    return sh, used


def gaussians_from_vertex(v: np.ndarray):
    """vertex structured array -> (SplatData, state or None)."""
    names = v.dtype.names or ()
    n = len(v)
    for a in 'xyz':
        if a not in names:
            raise ValueError("PLY vertex element has no x/y/z")
    col = lambda name: np.asarray(v[name], dtype=np.float32)  # noqa: E731
    positions = np.stack([col('x'), col('y'), col('z')], axis=1)
    used = {'x', 'y', 'z'}
    state = None
    if 'state' in names:
        state = np.asarray(v['state']).astype(np.uint8)
        used.add('state')

    is_gaussian = all(f'f_dc_{i}' in names for i in range(3)) or (
        'opacity' in names and all(f'scale_{i}' in names for i in range(3)))

    if is_gaussian:
        if all(f'f_dc_{i}' in names for i in range(3)):
            sh0 = np.stack([col(f'f_dc_{i}') for i in range(3)], axis=1)
            used |= {'f_dc_0', 'f_dc_1', 'f_dc_2'}
        else:
            sh0 = _rgb_to_sh0(v, names, n)
            used |= {'red', 'green', 'blue'}
        if 'opacity' in names:
            opac = col('opacity')
            used.add('opacity')
        else:
            opac = np.full(n, logit(0.95)[()], np.float32)
        if all(f'scale_{i}' in names for i in range(3)):
            scales = np.stack([col(f'scale_{i}') for i in range(3)], axis=1)
            used |= {'scale_0', 'scale_1', 'scale_2'}
        else:
            scales = _default_scales(positions)
        if all(f'rot_{i}' in names for i in range(4)):
            rots = _normalize_quats(np.stack([col(f'rot_{i}') for i in range(4)], axis=1))
            used |= {'rot_0', 'rot_1', 'rot_2', 'rot_3'}
        else:
            rots = np.tile(np.array([1, 0, 0, 0], np.float32), (n, 1))
        frest = {}
        for name in names:
            mm = _FREST.match(name)
            if mm:
                frest[int(mm.group(1))] = col(name)
        sh_rest, used_idx = _sh_rest_from_columns(frest, n)
        used |= {f'f_rest_{i}' for i in used_idx}
    else:
        # point cloud: synthesize gaussians
        sh0 = _rgb_to_sh0(v, names, n)
        used |= {'red', 'green', 'blue', 'r', 'g', 'b', 'alpha'}
        opac = np.full(n, logit(0.95)[()], np.float32)
        if 'alpha' in names:
            a = np.asarray(v['alpha'], np.float32)
            if v.dtype['alpha'].kind in 'ui':
                a = a / 255.0
            opac = logit(a)
        scales = _default_scales(positions)
        rots = np.tile(np.array([1, 0, 0, 0], np.float32), (n, 1))
        sh_rest = None

    extra = {name: np.ascontiguousarray(v[name]) for name in names if name not in used}
    data = SplatData(positions, scales, rots, opac, sh0, sh_rest, extra)
    return data, state


def _rgb_to_sh0(v, names, n):
    for trip in (('red', 'green', 'blue'), ('r', 'g', 'b'), ('diffuse_red', 'diffuse_green', 'diffuse_blue')):
        if all(t in names for t in trip):
            rgb = np.stack([np.asarray(v[t], np.float32) for t in trip], axis=1)
            if v.dtype[trip[0]].kind in 'ui':
                rgb = rgb / float(np.iinfo(v.dtype[trip[0]]).max)
            elif rgb.size and rgb.max() > 1.0:
                rgb = rgb / 255.0
            return ((rgb - 0.5) / SH_C0).astype(np.float32)
    return np.zeros((n, 3), np.float32)   # grey


def _default_scales(positions: np.ndarray) -> np.ndarray:
    n = len(positions)
    if n == 0:
        return np.zeros((0, 3), np.float32)
    ext = positions.max(axis=0) - positions.min(axis=0)
    vol = float(np.prod(np.maximum(ext, 1e-6)))
    spacing = (vol / n) ** (1.0 / 3.0)
    s = max(spacing * 0.5, 1e-4)
    return np.full((n, 3), np.log(s), np.float32)


# ----------------------------------------------------------------------------- writing

def write_ply(path: str, data: SplatData, state: np.ndarray | None = None, sh_bands: int = 3,
              include_extra: bool = True, comment: str = 'Generated by splatpy') -> int:
    """Write standard 3DGS binary little endian PLY. Returns number of gaussians written."""
    n = data.count
    m = 0
    if data.sh_rest is not None:
        m = min(data.sh_rest.shape[1], SH_COEFFS_FOR_BANDS[max(0, min(3, sh_bands))])
    fields = [('x', 'f4'), ('y', 'f4'), ('z', 'f4'), ('f_dc_0', 'f4'), ('f_dc_1', 'f4'), ('f_dc_2', 'f4')]
    fields += [(f'f_rest_{i}', 'f4') for i in range(3 * m)]
    fields += [('opacity', 'f4'), ('scale_0', 'f4'), ('scale_1', 'f4'), ('scale_2', 'f4'),
               ('rot_0', 'f4'), ('rot_1', 'f4'), ('rot_2', 'f4'), ('rot_3', 'f4')]
    taken = {f[0] for f in fields} | {'state'}
    extras = []
    if include_extra:
        for k, a in data.extra.items():
            a = np.asarray(a)
            if k in taken or a.ndim != 1 or len(a) != n:
                continue
            code = a.dtype.str[1:]
            if code not in NUMPY_TO_PLY:
                a = a.astype(np.float32)
                code = 'f4'
            extras.append((k, code, a))
    fields += [(k, code) for k, code, _ in extras]
    if state is not None:
        fields.append(('state', 'u1'))
    dt = np.dtype([(k, '<' + c) for k, c in fields])
    arr = np.empty(n, dt)
    arr['x'], arr['y'], arr['z'] = data.positions.T
    for i in range(3):
        arr[f'f_dc_{i}'] = data.sh0[:, i]
    for c in range(3):
        for k in range(m):
            arr[f'f_rest_{c * m + k}'] = data.sh_rest[:, k, c]
    arr['opacity'] = data.opacities
    for i in range(3):
        arr[f'scale_{i}'] = data.scales[:, i]
    for i in range(4):
        arr[f'rot_{i}'] = data.rotations[:, i]
    for k, _, a in extras:
        arr[k] = a
    if state is not None:
        arr['state'] = np.asarray(state, np.uint8)

    lines = ['ply', 'format binary_little_endian 1.0']
    if comment:
        lines.append(f'comment {comment}')
    lines.append(f'element vertex {n}')
    for name in dt.names:
        lines.append(f'property {NUMPY_TO_PLY[dt[name].str[1:]]} {name}')
    lines.append('end_header')
    with open(path, 'wb') as f:
        f.write(('\n'.join(lines) + '\n').encode('ascii'))
        arr.tofile(f)
    return n


def write_ply_ascii(path: str, data: SplatData, state=None, sh_bands: int = 3) -> int:
    """Mostly for tests / debugging."""
    import io as _io
    tmp = _io.BytesIO()
    m = 0 if data.sh_rest is None else min(data.sh_rest.shape[1], SH_COEFFS_FOR_BANDS[sh_bands])
    cols = [data.positions, data.sh0]
    names = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2']
    if m:
        cols.append(data.sh_rest[:, :m, :].transpose(0, 2, 1).reshape(data.count, -1))
        names += [f'f_rest_{i}' for i in range(3 * m)]
    cols += [data.opacities[:, None], data.scales, data.rotations]
    names += ['opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    mat = np.concatenate([np.asarray(c, np.float64).reshape(data.count, -1) for c in cols], axis=1)
    hdr = ['ply', 'format ascii 1.0', f'element vertex {data.count}']
    hdr += [f'property float {k}' for k in names]
    if state is not None:
        hdr.append('property uchar state')
    hdr.append('end_header')
    tmp.write(('\n'.join(hdr) + '\n').encode())
    for i in range(data.count):
        row = ' '.join(repr(float(x)) for x in mat[i])
        if state is not None:
            row += f' {int(state[i])}'
        tmp.write((row + '\n').encode())
    with open(path, 'wb') as f:
        f.write(tmp.getvalue())
    return data.count
