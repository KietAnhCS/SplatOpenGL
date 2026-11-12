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
    position: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list = field(default_factory=lambda: [0.0, 0.0, 0.0])   # độ, quanh X Y Z
    scale: float = 1.0

    def reset(self):
        self.position = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0, 0.0]
        self.scale = 1.0

    def rotation_matrix(self):
        return euler_to_matrix(self.rotation)

    def translation(self):
        return np.array(self.position, float)

    def rotate_about(self, delta, pivot):
        """Xoay thêm `delta` (ma trận 3x3, trong toạ độ thế giới) quanh điểm `pivot`."""
        pivot = np.asarray(pivot, float)
        self.rotation = matrix_to_euler(delta @ self.rotation_matrix())
        self.position = list(delta @ (self.translation() - pivot) + pivot)
