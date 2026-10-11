"""Phép biến đổi của một lớp: vị trí, góc xoay (độ), tỉ lệ đều."""

from dataclasses import dataclass, field 

import numpy as np 

from .math3d import euler_to_matrix, matrix_to_euler 

@dataclass 
class Transform:
    pass 

