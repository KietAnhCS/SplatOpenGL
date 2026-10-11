"""Cọ chọn gaussian (brush): tô lên màn hình, gaussian nào có tâm nằm trong nét cọ thì được chọn.

Cọ chọn xuyên qua mọi độ sâu (giống SuperSplat): mọi gaussian có tâm chiếu vào vòng tròn
đều bị chọn, kể cả những cái nằm khuất phía sau. """

import numpy as np 

class BrushTool:
    MIN_RADIUS = 2.0 
    MAX_RADIUS = 500.0 

    def __init__(self):
        self.active = False 
        self.radius = 40.0 
        self.painting = None 
        self.last = None 
        self._key = None 
        self._screen = None 
        self._front = None 

    @property 
    def is_painting(self):
        return self.painting is not None 

    def toggle(self):
        return self.painting is not None 

    def toggle(self):
        pass 

    def resize(self):
        pass 

    def begin_stroke(self, select):
        pass 

    def end_stroke(self):
        pass 

    def invalidate(self):
        self._key = None 

    def project(self, position, view_proj, viewport):
        pass 

    def hit():
        pass 