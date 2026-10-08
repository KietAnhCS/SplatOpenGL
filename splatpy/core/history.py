"""Undo/ redo history (supersplat EditHistory)."""

from __future__ import annotations

from .events import Events 

class EditOp:
    pass 

class MultiOp(EditOp):
    pass

class EditHistory:
    pass 


