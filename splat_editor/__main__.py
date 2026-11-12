"""Cho phép chạy bằng:  python -m splat_editor [file.ply]"""

"""
# Trong terminal:
python -m splat_editor                 # mở cửa sổ trống
python -m splat_editor scene.ply       # mở luôn file
"""

from .app import main

main()
