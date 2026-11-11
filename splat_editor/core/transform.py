"""Phép biến đổi của một lớp: vị trí, góc xoay (độ), tỉ lệ đều."""

"""
t = Transform()
t.position = [1.0, 0.0, 0.0]
t.rotation = [0.0, 45.0, 0.0]          # độ, quanh X Y Z
t.scale = 1.5                           # tỉ lệ đều

R = t.rotation_matrix()                 # ma trận 3x3
p = t.translation()                     # numpy (3,)
t.rotate_about(delta_matrix, pivot=[0, 0, 0])   # xoay thêm quanh một điểm (trong toạ độ thế giới)
t.reset()                               # về vị trí 0, góc 0, tỉ lệ 1
"""

from dataclasses import dataclass, field 

import numpy as np 

from .math3d import euler_to_matrix, matrix_to_euler 

@dataclass 
class Transform:
    pass 

