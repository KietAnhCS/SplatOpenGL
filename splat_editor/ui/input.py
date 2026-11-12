"""Chuột / bàn phím: chuyển cho ImGui trước, phần còn lại điều khiển camera, cọ chọn và phím tắt."""

"""
input = InputController(app)           # tự đăng ký callback chuột / phím / kéo thả với GLFW

# Mỗi khung hình
input.update(dt)                        # WASD bay camera khi giữ chuột phải

# Bên trong, mỗi sự kiện đi qua ImGui trước (nếu ImGui cần thì bỏ qua):
#   on_mouse_move  -> orbit / pan / look / tô cọ
#   on_mouse_button, on_scroll (zoom hoặc đổi cỡ cọ)
#   on_key -> actions.handle_key
#   on_drop -> app.add_files
input.reset()                           # xoá trạng thái nút / phím (sau khi hộp thoại file đóng)
"""

import glfw


class InputController:
    def __init__(self, app):
        self.app = app
        self.gui = app.gui.backend
        self.last_mouse = None
        self.drag_button = None      # nút chuột đang kéo trong vùng 3D (xoay / dịch / nhìn quanh)
        self._click_start = None     # vị trí nhấn chuột trái, để phân biệt click (chọn đèn) với kéo (xoay)

        handle = app.window.handle
        glfw.set_cursor_pos_callback(handle, self.on_mouse_move)
        glfw.set_mouse_button_callback(handle, self.on_mouse_button)
        glfw.set_scroll_callback(handle, self.on_scroll)
        glfw.set_key_callback(handle, self.on_key)
        glfw.set_char_callback(handle, self.gui.char_callback)
        glfw.set_drop_callback(handle, self.on_drop)

    @property
    def brush(self):
        return self.app.editor.brush

    @property
    def looking(self):
        """Đang giữ chuột phải: nhìn quanh + bay kiểu Minecraft."""
        return self.drag_button == glfw.MOUSE_BUTTON_RIGHT

    def _set_drag(self, button):
        # khi nhìn quanh thì ẩn và khoá con trỏ, để xoay mãi không bị chạm mép màn hình
        mode = glfw.CURSOR_DISABLED if button == glfw.MOUSE_BUTTON_RIGHT else glfw.CURSOR_NORMAL
        glfw.set_input_mode(self.app.window.handle, glfw.CURSOR, mode)
        self.drag_button = button
        self.last_mouse = None

    def reset(self):
        """Gọi sau khi mở hộp thoại hệ thống (cửa sổ mất focus, chuột có thể đã nhả)."""
        self._set_drag(None)
        self.brush.end_stroke()

    # ------------------------------------------------------------------ chuột
    def on_mouse_move(self, window, x, y):
        self.gui.mouse_callback(window, x, y)
        if self.brush.is_painting:
            self.app.paint(x, y)
        elif self.drag_button is not None and self.last_mouse is not None:
            dx, dy = x - self.last_mouse[0], y - self.last_mouse[1]
            # chế độ cọ: chuột trái dùng để tô nên xoay camera bằng chuột giữa
            orbit = self.drag_button == glfw.MOUSE_BUTTON_LEFT or (
                self.drag_button == glfw.MOUSE_BUTTON_MIDDLE and self.brush.active)
            camera = self.app.viewport.camera
            if self.looking:
                camera.look(dx, dy)
            elif orbit:
                camera.orbit(dx, dy)
            else:
                camera.pan(dx, dy, max(self.app.layout.viewport.height, 1))
        self.last_mouse = (x, y)

    def on_mouse_button(self, window, button, action, mods):
        self.gui.mouse_button_callback(window, button, action, mods)
        if action == glfw.PRESS:
            x, y = glfw.get_cursor_pos(window)
            if self.app.gui.wants_mouse or not self.app.layout.viewport.contains(x, y):
                return
            if button == glfw.MOUSE_BUTTON_LEFT and self.brush.active:
                self.app.lighting.picked = -1            # tô cọ -> Delete xoá gaussian, không phải đèn
                self.brush.begin_stroke(select=not (mods & glfw.MOD_CONTROL))   # giữ Ctrl: bỏ chọn
                self.app.paint(x, y)
            elif self.drag_button is None:
                if button == glfw.MOUSE_BUTTON_LEFT:
                    self._click_start = (x, y)           # có thể là click chọn đèn (nếu không kéo)
                self._set_drag(button)
        elif action == glfw.RELEASE:
            if button == glfw.MOUSE_BUTTON_LEFT:
                self.brush.end_stroke()
                start, self._click_start = self._click_start, None
                if start is not None and not self.brush.active and not self.app.gui.wants_mouse:
                    x, y = glfw.get_cursor_pos(window)
                    if abs(x - start[0]) < 4 and abs(y - start[1]) < 4:
                        self.app.pick_light(x, y)
            if button == self.drag_button:
                self._set_drag(None)

    def on_scroll(self, window, dx, dy):
        self.gui.scroll_callback(window, dx, dy)
        # lăn chuột không điều khiển camera: lên xuống bằng Space / Shift như Minecraft

    def on_drop(self, window, paths):
        self.app.add_files(paths)

    # ------------------------------------------------------------------ bàn phím
    def on_key(self, window, key, scancode, action, mods):
        self.gui.keyboard_callback(window, key, scancode, action, mods)
        # đang bay thì Ctrl là chạy nhanh, không kích hoạt phím tắt (Ctrl+S, Ctrl+D...)
        if action != glfw.PRESS or self.app.gui.wants_text or self.looking:
            return
        self.app.actions.handle_key(key, mods & glfw.MOD_CONTROL)

    def update(self, dt):
        """Bay kiểu Minecraft sáng tạo (giữ phím), gọi mỗi khung hình.

        W A S D: đi ngang, Space: lên, Shift: xuống, Ctrl: bay nhanh (khi giữ chuột phải).
        """
        camera = self.app.viewport.camera
        io = self.app.gui.io
        pressed = self.app.window.is_key_down
        ctrl = pressed(glfw.KEY_LEFT_CONTROL) or pressed(glfw.KEY_RIGHT_CONTROL)
        if io.want_text_input or (ctrl and not self.looking):
            forward = right = up = 0
        else:
            forward = pressed(glfw.KEY_W) - pressed(glfw.KEY_S)
            right = pressed(glfw.KEY_D) - pressed(glfw.KEY_A)
            shift = pressed(glfw.KEY_LEFT_SHIFT) or pressed(glfw.KEY_RIGHT_SHIFT)
            up = pressed(glfw.KEY_SPACE) - shift
        if self.app.mode == "survival":
            # sinh tồn: Space nhảy, Ctrl chạy nhanh, Shift đi chậm; camera là mắt người chơi
            self.app.walk(forward, right, up > 0, ctrl and (forward or right), up < 0, dt)
        else:
            camera.fly(forward, right, up, min(dt, 0.1), sprint=ctrl)
