"""Khung nhìn 3D: camera + lưới sàn + gaussian, vẽ vào một vùng chữ nhật của cửa sổ."""

import numpy as np
from OpenGL import GL 

from .camera import OrbitCamera
from .grid_renderer import GridRenderer 
from .splat_renderer import SplatRenderer 

class Viewport:
    def __init__(self):
        self.camera = OrbitCamera()
        self.splat_renderer = SplatRenderer()
        self.grid = GridRenderer()
        self.show_grid = True 
        self.background = [0.13, 0.13, 0.15]
        self._geometry_version = None 
        self._selection_version = None 

    def sync(self, editor):
        if self._geometry_version != editor.geometry_version:
            self.splat_renderer.set_splats(editor.splats)
            self._geometry_version = editor.geometry_version 
            self._selection_version = None 
        if self._selection_version != editor.selection_version:
            self.splat_renderer.set_selection(editor.scene.selection_mask())
            self._selection_version = editor.selection_version 

    def view_projection(self, rect):
        return self.camera.projection_matrix(rect.aspect) @ self.camera.view_matrix()

    def frame(self, splats):
        if splats is None:
            self.camera.reset()
        else: 
            self.camra.frame(splats.positions)

    def render(self, rect, window_size, framebuffer_size):
        fb_w, fb_h = framebuffer_size 
        GL.glViewport()
        GL.glClearColor()
        GL.glClear()
        if rect.is_empty or window_size[0] <= 0 or window_size[1] <= 0:
            return  

        sx, sy = fb_w / window_size[0], fb_h / window_size[1]
        x, w = int(rect.left * sx), int(rect.width * sx)
        h = int(rect.height * sy)
        y = fb_h - int((rect.top + rect.height)* sy)
        if w <= 0 or h <=0 :
            return 
        GL.glViewport(x,y,w,h)

        view = self.camera.view_matrix().astype(np.float32)
        projection = self.camera.projection_matrix(w/h) 
        if self.show_grid: 
            self.grid.draw(view.astype(np.float64), projection, self.camera.distance)
        self.splat_renderer.draw(view, projection, w, h)
        GL.glViewport(0,0, fb_w, fb_h)

    