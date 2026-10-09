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

def read_ply_elements():
    pass 

def _read_ascii():
    pass 

def _normalize_quats():
    pass

def _sh_rest_from_colums():
    pass 

def gaussian_from_vertex():
    pass

def _rgb_to_sh0():
    pass 

def _default_scales():
    pass 

def write_ply():
    pass 


def write_ply_ascii():
    pass



