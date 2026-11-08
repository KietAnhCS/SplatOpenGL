"""Splat Editor - xem / chỉnh sửa file Gaussian Splat (.ply) bằng Python + OpenGL.

Cách chạy:
    python main.py              # mở cửa sổ trống, bấm Ctrl+O để chọn file
    python main.py scene.ply    # mở luôn file (thêm nhiều file: python main.py a.ply b.ply)
"""

from splat_editor.app import main

if __name__ == '__main__':
    main()