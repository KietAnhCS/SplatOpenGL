import ctypes 

import numpy as np 
from OpenGL import GLE

from ..core.math3d import quat_to_matrix 
from .shader import ShaderProgram 
from .sorter import DepthSorter 

class SplatRenderer:
    def __init__(self):
        pass

    @staticmethod
    def pack(splats):
        pass 

    def set_splats(self, splats):
        pass 

    def set_selection(self, mask, resize=False):
        pass 

    def _upload_order(self, order):
        pass 

    def draw(self, model_view, projection, width, height):
        pass 

    