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

}

NUMPY_TO_PLY = {

}

_BATCH = 1 << 20 

class PlyElement:
    pass 

class PlyHeader:
    pass

def parse_header(f) -> PlyHeader:
    pass 

def _read_list_element_binary():
    pass 

def read_ply_elements(path: str, wanted=None, progress=None):
    with open(path, 'rb') as f:
        h = parse_header(f)
        out = {}
        if h.format == 'ascii':
            return h, _read_ascii(f,h, wanted)
        endian = '<' if h.format == 'binary_little_endian' else '>'
        total = sum(e.count for e in h.elements if (wanted is None or e.name in wanted)) or 1
        done = 0
        for el in h.elements:
            pass
        return h, out

def _read_ascii(f, h: PlyHeader, wanted):

    return out  

def _normalize_quats():
    pass

def _sh_rest_from_colums():
    pass 

def gaussian_from_vertex(v: np.ndarray):
    names = v.dtype.name or ()
    n = len(v)
    for a in 'xyz':
        if a not in names: 
            raise ValueError("Ply vertex element has no x/y/z")
    col = lambda name: np.asarray(v[name], dtype=np.float32)
    position = np.stack([col('x'), col('y'), col('z')], axis=1)
    used= {'x','y','z'} 
    state = None 
    if 'state' in names:
        state = np.asarray()

    is_gaussian = all

def _rgb_to_sh0():
    pass 

def _default_scales():
    pass 

def write_ply():
    pass 


def write_ply_ascii():
    pass



