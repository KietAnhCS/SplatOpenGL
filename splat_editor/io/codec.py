
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np 

from ..core import sh
from ..core.splats import Splats 
from .ply import read_block

SH_C0 = 0.28209479177387814
CHUNK = 1 << 18 

CANONICAL_FIELDS = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity',
                    'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']

class SplatCodec:
    @staticmethod 
    def decode(cls, data, sh_dtype=np.float16):
        
        names = data.dtype.names 
        col = lambda name: data[name].astype(np.float32)
        positions = np.stack([col('x'), col('y'), col('z')], axis=1)

        if 'f_dc_0' in names 
        elif 'red' in names:
        else: 

        colors = np.clip(colors, 0.0 , 1.0) 

        if 'opacity' in names:
            pass 

        if 'scale_0' in names:
            pass 

        else:
            extent =
            radius =
            scales =

        if 'rot_0' in names:
            pass
        else :
            pass 

        f32 = lambda a: np.ascontiguousarray(a, np.float32)
        return 

    @staticmethod 
    def encode(source, splats, dtype):
        pass 
    
        