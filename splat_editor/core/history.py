"""Lịch sử hoàn tác (undo) theo mẫu Command."""

from abc import ABC, abstracmethod 

class Command(ABC):
    pass 

class DeleteGaussianCommand(Command):
    pass 

class History:
    pass 