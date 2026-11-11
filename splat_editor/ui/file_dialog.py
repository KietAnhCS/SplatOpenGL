"""Hộp thoại chọn file của hệ điều hành (tkinter có sẵn trong Python)."""

"""
path = FileDialog.open_file()           # một file .ply, hoặc None nếu bấm Cancel
paths = FileDialog.open_files()         # nhiều file (danh sách rỗng nếu Cancel)
out = FileDialog.save_file("scene.ply")  # tên gợi ý; None nếu Cancel
"""

import tkinter
from tkinter import filedialog


class FileDialog:
    FILE_TYPES = [("PLY files", "*.ply"), ("All files", "*.*")]

    @classmethod
    def _run(cls, ask, **options):
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            return ask(filetypes=cls.FILE_TYPES, **options)
        finally:
            root.destroy()

    @classmethod
    def open_file(cls):
        return cls._run(filedialog.askopenfilename, title="Open PLY") or None

    @classmethod
    def open_files(cls):
        return list(cls._run(filedialog.askopenfilenames, title="Add PLY Files") or [])

    @classmethod
    def save_file(cls, initial="scene.ply"):
        return cls._run(filedialog.asksaveasfilename, title="Save PLY",
                        defaultextension=".ply", initialfile=initial) or None
