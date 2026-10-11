"""Các mục trong bảng bên trái. Mỗi mục là một lớp con của PanelSection."""

import math 
from abc import ABC, abstractmethod 

from imgui_bundle import imgui 

from ..core.math3d import axis_angle_matrix 
from . import widgets 

class PanelSection(ABC):
    title = ""

    def __init__(self, app):
        pass 

    