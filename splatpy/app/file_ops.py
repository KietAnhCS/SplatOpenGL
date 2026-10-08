from __future__ import annotations 

import os 
import time 
import traceback

import numpy as np

PROJECT_EXT = '.ssproj'
DEFAULT_LOAD_EXTS = ('.ply', '.splat', '.ksplat', '.spz', '.sog')

class Dialogs:
    def __init__():
        pass

    def _tk():
        pass 

    def _done():
        pass 

    def open_files():
        pass 

    def save_files():
        pass 

    def ask_yes_no_cancel():
        pass 

    def error():
        pass

    def destroy():
        pass 

class FileOps:
    def __init__(self, app):
        pass 

    def notify():
        pass 

    def report_error():
        pass 

    def load_exts(self) -> tuple:
        try:
            pass
        except Exception:
            pass

    def _open_filetypes():
        pass 

    def is_dirty() -> bool:
        pass 

    def confirm_discard() -> bool:
        pass 

    def _remember():
        pass 

    def new() -> bool:
        pass 

    def open_dialog(self):
        pass 

    def import_dialog(self):
        pass 

    def import_file() -> bool:
        pass 

    def add_splat():
        pass 

    def load_project():
        pass 

    def save() -> bool:
        pass

    def save_as(self) -> bool:
        pass 

    def save_ply() -> bool: 
        pass 

    def save_project() -> bool:
        pass 

    def save_formats(self) -> dict:
        pass 

    def export_dialog() -> bool:
        pass

    def export() -> bool:
        pass

    def reexport(self) -> bool:
        pass

    def export_image_dialog() -> bool:
        pass

    def export_image() -> bool:
        pass

    
    def destroy(self):
        pass 


def unpremultiply(rgba: np.ndarray) -> np.ndarray:
    pass