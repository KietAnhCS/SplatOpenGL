import numpy as np 

from ..io.codec import CANONICAL_FIELDS 
from .splats import Splats

class Scene:
    def __init__(self):
        pass 



    def world_splats(self):
        parts = [layer.world_splats(self.flip) for layer in self.visible_layers()]
        return Splats.concat(parts) if parts else None 