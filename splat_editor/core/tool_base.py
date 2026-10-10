from __future__ import annotations 

from dataclasses import dataclass , field 

from .events import Events 

MOUSE_LEFT = 0 
MOUSE_RIGHT = 1
MOUSE_MIDDLE = 2 

@dataclass 
class Mods:
    shift: bool = False 
    ctrl: bool = False 
    alt: bool = False 

@dataclass 
class InputEvent:
    pass 

@dataclass 
class RenderContex:
    pass 

class Tool:
    name = "tool"

    def __init__(self, events: Events):
        pass 

    def activation(self):
        pass 

    def deactive(self):
        pass 

    def on_mouse_down() -> bool:
        pass 

    def on_mouse_move() -> bool:
        pass 

    def on_mouse_up() -> bool:
        pass 

    def on_scroll(self, ev: InputEvent) -> bool:
        pass 

    def on_key(self, ev: InputEvent) -> bool:
        pass
    
    def draw_3d(self, ctx: RenderContext):
        pass 

    
    def draw_2d(self, ctx: RenderContext):
        pass 

    
    def draw_ui(self, ui) -> None:
        pass 

class ToolManager:
    def __init__(self, events: Events):
        pass 

    def register(self, name: str, tool: Tool):
        pass

    def activate():
        pass 

    