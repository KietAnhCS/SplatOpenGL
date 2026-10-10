"""Chương trình shader OpenGL (vertex + fragment), nạp từ thư mục shaders/."""

from pathlib import Path 

import numpy as np
from OpenGL import GL 

SHADER_DIR = Path(__file__).parent / "shaders"

class ShaderError(RuntimeError):
    pass 

class ShaderProgram:
    def __init__():
        pass 

    @classmethod 
    def load(cls, name):
        pass

    @staticmethod
    def _compile(src, kind):
        pass 

    def use(self):
        pass 

    def location(self, name):
        pass 

    def set_int(self, name, value):
        pass

    def set_float(self, name, value):
        pass

    def set_vec2(self, name, x,y):
        pass 

    def set_vec3():
        pass 

    def set_mat3():
        pass 

    def set_mat4():
        pass