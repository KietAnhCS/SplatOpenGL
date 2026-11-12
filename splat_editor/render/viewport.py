"""Khung nhìn 3D: camera + lưới sàn + gaussian, vẽ vào một vùng chữ nhật của cửa sổ.

Để chạy mượt trên máy yếu, cảnh có thể được vẽ ở độ phân giải thấp hơn (render_scale) vào một
framebuffer riêng rồi phóng lên khung nhìn. Khi camera đang di chuyển có thể hạ thêm
(motion_scale): lúc chuyển động mắt khó thấy mờ, dừng lại thì vẽ lại nét ngay.
"""

"""
viewport = Viewport()
viewport.set_quality("Auto")            # Auto / Low / Medium / High / Ultra
viewport.frame(positions)               # đưa camera về nhìn toàn cảnh

# Mỗi khung hình
viewport.sync(editor)                   # nếu Editor đổi thì gửi lại GPU
viewport.render(rect, window.size, window.framebuffer_size)

vp = viewport.view_projection(rect)    # dùng cho cọ chọn
"""

from typing import NamedTuple

import numpy as np
from OpenGL import GL

from .avatar_renderer import AvatarRenderer
from .camera import OrbitCamera
from .grid_renderer import GridRenderer
from .light_renderer import LightRenderer
from .splat_renderer import SplatRenderer


class QualityPreset(NamedTuple):
    budget: int | None       # số gaussian tối đa mỗi khung hình (None: không giới hạn)
    render_scale: float      # tỉ lệ độ phân giải khi đứng yên
    motion_scale: float      # tỉ lệ độ phân giải khi camera đang di chuyển
    auto: bool = False       # tự chỉnh budget theo thời gian GPU đo được để đạt target_fps


QUALITY_PRESETS = {
    "Auto": QualityPreset(1_500_000, 1.0, 0.6, auto=True),
    "Low": QualityPreset(1_000_000, 0.75, 0.5),
    "Medium": QualityPreset(2_000_000, 1.0, 0.6),
    "High": QualityPreset(4_000_000, 1.0, 0.75),
    "Ultra": QualityPreset(None, 1.0, 1.0),
}
DEFAULT_QUALITY = "Auto"
GPU_SHARE = 0.7    # phần thời gian mỗi khung hình dành cho gaussian (còn lại: giao diện, CPU, ...)


class Viewport:
    MOTION_HOLD_FRAMES = 6

    def __init__(self):
        self.camera = OrbitCamera()
        self.splat_renderer = SplatRenderer()
        self.grid = GridRenderer()
        self.light_renderer = LightRenderer()
        self.avatar_renderer = AvatarRenderer()
        self.avatar = None            # (6 ma trận model, độ sáng RGB) của nhân vật người chơi, None: không vẽ
        self.occluder = None          # Physics: dùng bản đồ va chạm để cảnh che mặt trời
        self.lighting = None         # core.lighting.Lighting (gắn bởi Application)
        self.unit = 1.0              # chiều cao người chơi: thước đo kích thước vật thể
        self.clock = 0.0             # giây, cho hạt chuyển động
        self.show_grid = True
        self.background = [0.13, 0.13, 0.15]
        self.render_scale = 1.0
        self.motion_scale = 1.0
        self.quality = None
        self.auto_budget = False
        self.target_fps = 60
        self.set_quality(DEFAULT_QUALITY)
        self._fbo = GL.glGenFramebuffers(1)
        self._fbo_texture = GL.glGenTextures(1)
        self._fbo_depth = GL.glGenRenderbuffers(1)     # độ sâu riêng cho nhân vật (gaussian không ghi độ sâu)
        self._fbo_size = None
        self._last_view = None
        self._still_frames = self.MOTION_HOLD_FRAMES
        self.moving = False
        # phiên bản dữ liệu đã gửi lên GPU (so với Editor để biết khi nào cần gửi lại)
        self._geometry_version = None
        self._deleted_version = None
        self._selection_version = None
        self._transform_version = None

    def sync(self, editor):
        """Gửi lại gaussian / vùng chọn lên GPU nếu Editor đã thay đổi."""
        if self._geometry_version != editor.geometry_version:
            self.splat_renderer.set_splats(editor.splats, editor.lod)
            self._geometry_version = editor.geometry_version
            self._deleted_version = None
            self._selection_version = None
            self._transform_version = None
        if self._deleted_version != editor.deleted_version:
            # xoá / hoàn tác (xoá mềm): chỉ gửi lại cờ đã xoá, không gửi lại dữ liệu gaussian
            self.splat_renderer.set_deleted(editor.scene.deleted_mask())
            self._deleted_version = editor.deleted_version
        if self._transform_version != editor.transform_version:
            # kéo / xoay / phóng to lớp hoặc lật trục: chỉ gửi ma trận, không gửi lại dữ liệu
            self.splat_renderer.set_transforms(editor.layer_matrices())
            self._transform_version = editor.transform_version
        if self._selection_version != editor.selection_version:
            changes = editor.selection_changes_since(self._selection_version)
            if changes is None:
                self.splat_renderer.set_selection(editor.scene.selection_mask())
            else:
                for indices, value in changes:      # chỉ các nét cọ mới: gửi phần bị đổi
                    self.splat_renderer.update_selection(indices, value)
            self._selection_version = editor.selection_version

    def set_quality(self, name):
        preset = QUALITY_PRESETS[name]
        self.quality = name
        self.splat_renderer.budget = preset.budget
        self.render_scale = preset.render_scale
        self.motion_scale = preset.motion_scale
        self.auto_budget = preset.auto

    def view_projection(self, rect):
        return self.camera.projection_matrix(rect.aspect) @ self.camera.view_matrix()

    def frame(self, positions):
        """Đưa camera về nhìn toàn bộ các điểm `positions` (toạ độ thế giới; None: đặt lại camera)."""
        if positions is None:
            self.camera.reset()
        else:
            self.camera.frame(positions)

    def render(self, rect, window_size, framebuffer_size):
        """rect: vùng 3D theo toạ độ cửa sổ (gốc trên-trái), được đổi sang pixel framebuffer."""
        fb_w, fb_h = framebuffer_size
        GL.glViewport(0, 0, fb_w, fb_h)
        GL.glClearColor(*self.sky(), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if rect.is_empty or window_size[0] <= 0 or window_size[1] <= 0:
            return

        # màn hình HiDPI: framebuffer có thể lớn hơn kích thước cửa sổ
        sx, sy = fb_w / window_size[0], fb_h / window_size[1]
        x, w = int(rect.left * sx), int(rect.width * sx)
        h = int(rect.height * sy)
        y = fb_h - int((rect.top + rect.height) * sy)        # OpenGL tính y từ dưới lên
        if w <= 0 or h <= 0:
            return

        view = self.camera.view_matrix().astype(np.float32)
        projection = self.camera.projection_matrix(w / h)
        # coi là đang di chuyển thêm vài khung hình sau lần đổi cuối (chuột không gửi sự kiện
        # đều mỗi khung hình), tránh độ phân giải nhảy qua lại liên tục
        changed = self._last_view is None or not np.array_equal(view, self._last_view)
        self._still_frames = 0 if changed else self._still_frames + 1
        self.moving = self._still_frames < self.MOTION_HOLD_FRAMES
        self._last_view = view
        scale = min(self.render_scale, self.motion_scale) if self.moving else self.render_scale

        if scale >= 0.999:
            GL.glViewport(x, y, w, h)
            self._draw_scene(view, projection, w, h)
        else:
            # vẽ vào framebuffer nhỏ hơn rồi phóng lên khung nhìn (lọc tuyến tính)
            sw, sh = max(int(w * scale), 1), max(int(h * scale), 1)
            self._bind_offscreen(sw, sh)
            GL.glViewport(0, 0, sw, sh)
            GL.glClearColor(*self.sky(), 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            self._draw_scene(view, projection, sw, sh)
            GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self._fbo)
            GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
            GL.glBlitFramebuffer(0, 0, sw, sh, x, y, x + w, y + h, GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        GL.glViewport(0, 0, fb_w, fb_h)

    def sky(self):
        """Màu nền: đổi theo giờ trong ngày khi có mặt trời, ngược lại là màu người dùng chọn."""
        light = self.lighting
        if light is not None and light.enabled and light.sun_on and light.sky_follows:
            return light.sky_color()
        return self.background

    def _draw_scene(self, view, projection, w, h):
        if self.show_grid:
            self.grid.draw(view.astype(np.float64), projection, self.camera.distance)
        if self.lighting is not None:
            self.splat_renderer.set_lighting(self.lighting.params())
        self.splat_renderer.draw(view, projection, w, h)
        if self.lighting is not None:
            self.light_renderer.draw(view, projection, self.lighting, self.clock, self.unit,
                                     self.occluder)
        if self.avatar is not None and self.camera.view_mode:
            matrices, brightness = self.avatar
            self.avatar_renderer.draw(view, projection, matrices, brightness)
        if self.auto_budget:
            self.splat_renderer.adapt_budget(GPU_SHARE * 1000.0 / self.target_fps)

    def _bind_offscreen(self, w, h):
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._fbo)
        if self._fbo_size == (w, h):
            return
        # cấp lại texture khi kích thước đổi (thường chỉ vài cỡ: lúc đứng yên / lúc di chuyển)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._fbo_texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_TEXTURE_2D,
                                  self._fbo_texture, 0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self._fbo_depth)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT24, w, h)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_RENDERBUFFER,
                                     self._fbo_depth)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, 0)
        self._fbo_size = (w, h)
