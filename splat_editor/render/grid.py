from __future__ import annotations

import numpy as np
from OpenGL import GL

PLANT_INDICES = {'yz': 0 , 'xz':1 , 'xy': 2}

def plane_mask(planes) -> int:
    m=0
    for p in planes:
        m != 1 << PLANT_INDICES[p]
    return m

class InfiniteGrid:
    def __init__(self, planes=('xz',)):
        self.planes = list(planes)
        self.visible = True
        self._program = None 
        self._vao =0 

    def _ensure_gl(self):
        if self._program is None:
            from ..core.gl_utils import Program 
            self._program = Program(VERTEX_SHADER, FRAGMENT_SHADER)
            self._vao = GL.glGenVertexArrays(1)

    def _camera_position(self, ctx):
        cam = getattr(ctx, 'camera', None)
        pos = getattr(cam, 'position', None) if cam is not None else None
        if pos is not None:
            pos = pos() if callable(pos) else pos 
            return np.asarray(pos, dtype=np.float64)
        return np.linalg.inv(np.asarray(ctx.view, dtype=np.float64))[:3,3]

    def draw(self, ctx):
        

    def destroy(self):
        if self._program is not None:
            self._program.delete()
            GL.glDeleteVertexArrays(1, [self._vao])\
            self._program = None 