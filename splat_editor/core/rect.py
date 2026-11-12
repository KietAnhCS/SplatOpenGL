"""Hình chữ nhật trên màn hình (toạ độ cửa sổ, gốc ở góc trên bên trái)."""

"""
rect = Rect(left=330, top=20, width=1170, height=860)   # toạ độ cửa sổ, gốc trên-trái
rect.aspect                             # width / height (dùng cho ma trận chiếu)
rect.center                             # (x, y) tâm hình chữ nhật
rect.contains(400, 300)                 # True nếu điểm nằm trong
rect.is_empty                           # True nếu rộng hoặc cao <= 0
"""

from typing import NamedTuple


class Rect(NamedTuple):
    left: float
    top: float
    width: float
    height: float

    @property
    def is_empty(self):
        return self.width <= 0 or self.height <= 0

    @property
    def aspect(self):
        return self.width / self.height if self.height > 0 else 1.0

    @property
    def center(self):
        return self.left + self.width / 2, self.top + self.height / 2

    def contains(self, x, y):
        return self.left <= x < self.left + self.width and self.top <= y < self.top + self.height
