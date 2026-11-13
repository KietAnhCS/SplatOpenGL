"""Application: ghép cửa sổ, giao diện, Editor và khung nhìn 3D lại với nhau, chạy vòng lặp chính."""

"""
# Cách dùng thông thường (main.py làm đúng như vậy)
from splat_editor.app import main
main()                                  # đọc đường dẫn file từ sys.argv rồi chạy vòng lặp chính

# Hoặc dùng trực tiếp
app = Application(1500, 900)
app.open_file("scene.ply")             # mở file (thay cảnh hiện tại) và đưa camera về nhìn toàn cảnh
app.add_files(["a.ply", "b.ply"])      # thêm mỗi file thành một lớp
app.actions.trigger("save")            # chạy một hành động theo tên (giống bấm menu / phím tắt)
app.run()                              # vòng lặp: poll_events -> input.update -> vẽ GUI -> viewport -> swap_buffers

# Mỗi khung hình:
#   input.update(dt)           điều khiển camera / cọ
#   gui.begin_frame() ... gui.end_frame()   dựng giao diện ImGui
#   viewport.sync(editor)      gửi dữ liệu mới lên GPU nếu Editor đã đổi
#   viewport.render(...)       vẽ cảnh 3D vào vùng giữa
#   gui.draw()                 vẽ ImGui đè lên
"""

import math
import sys
import time

import glfw
import numpy as np

from .core.avatar_pose import AvatarPose, limb_matrices
from .core.lighting import MAX_LIGHTS, Lighting
from .core.physics import Physics
from .editor.editor import Editor
from .render.viewport import Viewport
from .ui.actions import Action, ActionRegistry
from .ui.file_dialog import FileDialog
from .ui.gui import Gui
from .ui.input import InputController
from .ui.layout import Layout
from .ui.menu_bar import MainMenuBar
from .ui.shortcuts_window import ShortcutsWindow
from .ui.side_panel import SidePanel
from .ui.status_bar import StatusBar
from .ui.viewport_overlay import ViewportOverlay
from .ui.window import Window


class FpsCounter:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.value = 0.0
        self._frames = 0
        self._start = time.perf_counter()

    def tick(self, now):
        self._frames += 1
        if now - self._start >= self.interval:
            self.value = self._frames / (now - self._start)
            self._frames, self._start = 0, now


class Application:
    TITLE = "Splat Editor"

    def __init__(self, width=1500, height=900):
        self.window = Window(self.TITLE, width, height)
        self.gui = Gui(self.window)
        self.editor = Editor()
        self.viewport = Viewport()
        self.layout = Layout()
        self.fps = FpsCounter()
        self.physics = Physics()
        self.lighting = Lighting()
        self.viewport.lighting = self.lighting
        self.mode = "creative"       # "creative": bay tự do; "survival": đi bộ có trọng lực + va chạm
        self.pose = AvatarPose()     # tư thế nhân vật người chơi (đi, cúi, ngồi, cử chỉ) — thấy khi bấm F5
        self.body_yaw = 0.0          # hướng thân nhân vật (rad), đầu quay theo camera trong giới hạn
        self._last_feet = None
        self._world_versions = None
        self._spawn_pending = False
        self.actions = self._create_actions()

        self.menu_bar = MainMenuBar(self.actions)
        self.side_panel = SidePanel(self)
        self.status_bar = StatusBar(self)
        self.shortcuts_window = ShortcutsWindow(self.actions)
        self.overlay = ViewportOverlay(self)
        self.input = InputController(self)

    # ------------------------------------------------------------------ hành động
    def _create_actions(self):
        editor, viewport = self.editor, self.viewport
        has_layer = lambda: editor.scene.active_layer is not None  # noqa: E731
        has_selection = lambda: editor.scene.selected_count() > 0  # noqa: E731
        brush = editor.brush
        actions = ActionRegistry()
        add = actions.add

        # File
        add("open", Action("Open...", self.open_dialog, "File", "Ctrl+O", glfw.KEY_O, ctrl=True,
                           description="Open a file (replaces the scene)", deferred=True))
        add("add", Action("Add to Scene...", self.add_dialog, "File", "Ctrl+I", glfw.KEY_I, ctrl=True,
                          description="Add files to the scene as new layers", deferred=True))
        add("save", Action("Save As...", self.save_dialog, "File", "Ctrl+S", glfw.KEY_S, ctrl=True,
                           description="Save visible layers merged into one .ply", deferred=True,
                           enabled=editor.can_save))
        add("quit", Action("Exit", self.window.close, "File", "Ctrl+Q", glfw.KEY_Q, ctrl=True))

        # Edit
        add("undo", Action("Undo", editor.undo, "Edit", "Ctrl+Z", glfw.KEY_Z, ctrl=True,
                           description="Undo the last delete", enabled=lambda: editor.history.can_undo))
        add("select_all", Action("Select All", editor.select_all, "Edit", "Ctrl+A", glfw.KEY_A, ctrl=True))
        add("select_none", Action("Select None", editor.select_none, "Edit", "Ctrl+D", glfw.KEY_D, ctrl=True))
        add("invert_selection", Action("Invert Selection", editor.invert_selection, "Edit"))
        add("delete_selected", Action("Delete Selected", editor.delete_selected, "Edit", "Delete",
                                      enabled=has_selection))
        add("delete", Action("Delete", self.delete_key, "Edit", "Delete", glfw.KEY_DELETE,
                             description="Delete the picked light, else selected gaussians "
                                         "(or the active layer if none)"))
        add("remove_layer", Action("Remove Layer", editor.remove_layer, "Edit", deferred=True,
                                   enabled=has_layer))

        # View
        add("frame_scene", Action("Frame Scene", self.frame_scene, "View", "F", glfw.KEY_F,
                                  description="Frame the whole scene"))
        add("frame_layer", Action("Frame Active Layer", lambda: self.frame_scene(editor.scene.active_layer),
                                  "View", enabled=has_layer))
        add("show_grid", Action("Show Grid", self.toggle_grid, "View", "G", glfw.KEY_G,
                                description="Show / hide the floor grid", checked=lambda: viewport.show_grid))
        add("view_sh", Action("View-Dependent Color", self.toggle_sh, "View",
                              description="Use spherical harmonics (f_rest_*) so color changes with view angle",
                              checked=lambda: viewport.splat_renderer.use_sh))
        add("flip_y", Action("Flip Y Axis (COLMAP)", lambda: self.set_flip(not editor.scene.flip), "View",
                             checked=lambda: editor.scene.flip))
        # World: ánh sáng + vật lý
        add("toggle_mode", Action("Walk Mode", self.toggle_mode, "World", "M", glfw.KEY_M,
                                  description="Switch Fly <-> Walk (gravity, collision)",
                                  checked=lambda: self.mode == "survival"))
        survival = lambda: self.mode == "survival"  # noqa: E731
        add("third_person", Action("Third Person (F5)", self.cycle_view, "World", "F5", glfw.KEY_F5,
                                   description="See yourself: first person -> behind -> in front (Walk mode)",
                                   enabled=survival, checked=lambda: self.viewport.camera.view_mode != 0))
        add("sit", Action("Sit Down", self.pose.toggle_sit, "World", "C", glfw.KEY_C,
                          description="Sit on the ground / stand up (moving also stands up)", enabled=survival,
                          checked=lambda: self.pose.sitting))
        for name, label, key, letter in (("wave", "Wave", glfw.KEY_V, "V"),
                                         ("zombie", "Zombie Arms", glfw.KEY_X, "X"),
                                         ("cheer", "Cheer", glfw.KEY_Y, "Y")):
            add(name, Action(label, lambda n=name: self.pose.toggle_gesture(n), "World", letter, key,
                             description=f"Gesture: {label.lower()} (press again to stop)", enabled=survival,
                             checked=lambda n=name: self.pose.gesture == n))
        add("lighting", Action("Lighting", self.toggle_lighting, "World",
                               description="Ambient + sun + light blocks with Phong shading",
                               checked=lambda: self.lighting.enabled))
        add("shadows", Action("Sun Shadows", self.toggle_shadows, "World",
                              description="Shadow mapping for the sun", checked=lambda: self.lighting.shadows))
        add("add_sun", Action("Add Sun", self.add_sun, "World", description="Add a sun sphere (day-night cycle)"))
        add("add_light", Action("Add Light Block", self.add_light, "World", "L", glfw.KEY_L,
                                description="Drop a light block in front of the camera"))
        add("shortcuts", Action("Keyboard Shortcuts", self.shortcuts_window_toggle, "Help", "F1", glfw.KEY_F1,
                                description="Show this window"))

        # Brush
        add("brush", Action("Brush Tool", brush.toggle, "Brush", "B", glfw.KEY_B,
                            description="Toggle the selection brush", checked=lambda: brush.active))
        add("brush_smaller", Action("Smaller Brush", lambda: brush.resize(1 / 1.2), "Brush", "[",
                                    glfw.KEY_LEFT_BRACKET, description="Smaller brush"))
        add("brush_larger", Action("Larger Brush", lambda: brush.resize(1.2), "Brush", "]",
                                   glfw.KEY_RIGHT_BRACKET, description="Larger brush"))
        add("brush_off", Action("Exit Brush", self.exit_brush, "Brush", "Esc", glfw.KEY_ESCAPE,
                                description="Turn the brush off"))
        return actions

    # ------------------------------------------------------------------ lệnh
    def open_file(self, path):
        if self.editor.open_file(path):
            self.frame_scene()

    def add_files(self, paths):
        for path in paths:
            first = self.editor.scene.is_empty
            if self.editor.add_file(path) is not None and first:
                self.frame_scene()

    def open_dialog(self):
        path = FileDialog.open_file()
        self.input.reset()
        if path:
            self.open_file(path)

    def add_dialog(self):
        paths = FileDialog.open_files()
        self.input.reset()
        self.add_files(paths)

    def save_dialog(self):
        path = FileDialog.save_file(self.editor.suggested_save_name())
        self.input.reset()
        if path:
            self.editor.save_file(path)

    def frame_scene(self, layer=None):
        """Đưa camera về nhìn toàn cảnh (hoặc chỉ một lớp)."""
        scene = self.editor.scene
        positions = None if scene.is_empty else scene.world_positions(layer)
        self.viewport.frame(positions)
        if layer is None and positions is not None:
            self._update_bounds(positions, reset_scale=True)

    # ------------------------------------------------------------------ thế giới: ánh sáng + vật lý
    def _update_bounds(self, positions=None, reset_scale=False):
        """Kích thước cảnh -> tầm đèn, bản đồ bóng và chiều cao người chơi mặc định."""
        scene = self.editor.scene
        if positions is None:
            if scene.is_empty:
                return
            positions = scene.world_positions(limit=200_000)
        if len(positions) == 0:
            return
        center = np.median(positions, axis=0)
        radius = float(np.percentile(np.linalg.norm(positions - center, axis=1), 95)) or 1.0
        self.lighting.set_bounds(center, radius)
        if reset_scale:
            self.physics.set_scale(radius)

    def toggle_lighting(self):
        self.lighting.enabled = not self.lighting.enabled

    def toggle_shadows(self):
        self.lighting.shadows = not self.lighting.shadows

    def add_sun(self):
        if self.editor.scene.is_empty:
            return
        self.lighting.add_sun()
        self.editor.set_status("Sun added: drag the time of day or animate it in the Lighting panel")

    def add_light(self):
        if self.editor.scene.is_empty:
            return
        camera = self.viewport.camera
        if self.mode == "survival":
            position = camera.position() + camera.forward() * self.physics.height * 2.0
        else:
            position = camera.target.copy()
        light = self.lighting.add_light(position, self.physics.height * 4.0)
        if light is None:
            self.editor.set_status(f"At most {MAX_LIGHTS} light blocks")
        else:
            self.editor.set_status(f"{light.name} added")

    def pick_light(self, x, y):
        """Click trong cảnh 3D: chọn khối đèn gần con trỏ nhất (và không bị cảnh che); click ra ngoài: bỏ chọn."""
        lighting, rect = self.lighting, self.layout.viewport
        lighting.picked = -1
        if not lighting.lights or rect.is_empty:
            return False
        view = self.viewport.camera.view_matrix()
        projection = self.viewport.camera.projection_matrix(rect.aspect)
        cam_pos = -view[:3, :3].T @ view[:3, 3]
        half_tan = math.tan(math.radians(self.viewport.camera.fov) / 2)
        best, best_dist = -1, 1e9
        for i, light in enumerate(lighting.lights):
            clip = projection @ (view @ np.append(light.position, 1.0))
            if clip[3] <= 1e-9:
                continue                                          # sau lưng camera
            sx = rect.left + (clip[0] / clip[3] * 0.5 + 0.5) * rect.width
            sy = rect.top + (1.0 - (clip[1] / clip[3] * 0.5 + 0.5)) * rect.height
            distance = float(np.linalg.norm(light.position - cam_pos))
            radius = max(self.physics.height * 0.12, distance * 0.012)
            radius_px = radius / (distance * half_tan) * rect.height * 0.5
            pixels = math.hypot(sx - x, sy - y)
            if pixels <= max(radius_px * 1.6, 14.0) and pixels < best_dist:
                if self.physics.visibility(cam_pos, [light.position], skip_end=1.5) > 0:
                    best, best_dist = i, pixels
        lighting.picked = best                    # -1 khi click ra ngoài: Delete quay lại xoá gaussian
        if best >= 0:
            lighting.selected = best
            self.editor.set_status(f"{lighting.lights[best].name} selected: press Delete to remove it")
        return best >= 0

    def delete_key(self):
        """Delete: xoá khối đèn đang chọn trong cảnh; không có thì xoá gaussian như trước."""
        lighting = self.lighting
        if 0 <= lighting.picked < len(lighting.lights):
            name = lighting.lights[lighting.picked].name
            lighting.remove_light(lighting.picked)
            self.editor.set_status(f"{name} deleted")
        else:
            self.editor.delete()

    def set_mode(self, mode):
        if mode == self.mode:
            return
        if mode == "survival":
            if self.editor.scene.is_empty:
                return
            self.viewport.camera.velocity[:] = 0
            self._spawn_pending = True       # đặt người chơi khi bản đồ va chạm dựng xong
            self.editor.set_status("Walk: WASD walk, Space jump, Ctrl sprint, Shift sneak, drag to look, "
                                   "F5 see yourself, C sit, V/X/Y gestures")
            self._last_feet = None
        else:
            self.editor.set_status("Fly: WASD fly, Space up, Shift down")
            self._leave_third_person()
        self.mode = mode

    def _spawn_player(self):
        """Đặt người chơi ở nơi có mặt đất bên dưới: chỗ camera đang đứng, rồi tới điểm camera đang nhìn,
        cuối cùng là giữa cảnh (camera bay ở xa trong khoảng trống thì rơi ra ngoài thế giới)."""
        camera, physics = self.viewport.camera, self.physics
        eye = None
        if physics.flat_ground:
            pos = camera.position()
            eye = np.array([pos[0], physics.eye_height, pos[2]])
        for point in (() if eye is not None else (camera.position(), camera.target)):
            ground = physics.drop_height(point[0], point[2], point[1], physics.height * 0.3)
            if ground is not None:     # bắt đầu cao hơn mặt đất một chút, kẻo chân nằm dưới bề mặt
                eye = np.array([point[0], max(point[1], ground + physics.eye_height * 1.1), point[2]])
                break
        if eye is None and not physics.flat_ground:
            center = self.lighting.center
            top = physics.world.max_y + physics.height
            ground = physics.drop_height(center[0], center[2], top, physics.height * 0.3)
            eye = np.array([center[0], (top if ground is None else ground) + physics.eye_height * 1.5, center[2]])
        physics.player.place(eye, physics.eye_height)
        camera.set_eye(eye)
        self._spawn_pending = False

    def toggle_mode(self):
        self.set_mode("creative" if self.mode == "survival" else "survival")

    def walk(self, forward, right, jump, sprint, sneak, dt):
        """Một bước đi bộ của chế độ sinh tồn; camera đi theo mắt người chơi."""
        if self._spawn_pending:
            if not self.physics.ready:
                return
            self._spawn_player()
        camera, pose = self.viewport.camera, self.pose
        if forward or right or jump:
            pose.stand()                       # đi / nhảy thì đứng dậy
        if pose.sitting:
            forward = right = 0
            jump = False
        self.physics.walk(forward, right, camera.yaw, jump, sprint, sneak, dt)
        if self.physics.ready:
            player, height = self.physics.player, self.physics.height
            feet = player.feet.copy()
            walked = 0.0
            if self._last_feet is not None:
                walked = float(np.hypot(feet[0] - self._last_feet[0], feet[2] - self._last_feet[2]))
                if walked > height * 2.0:      # dịch chuyển (hồi sinh), không phải bước đi
                    walked = 0.0
            self._last_feet = feet
            pose.update(dt, walked, sneak, height)
            camera.set_eye(player.eye(self.physics.eye_height * pose.stance, dt))
            self._update_avatar(feet, walked, dt)

    # ------------------------------------------------------------------ nhân vật + góc nhìn thứ ba (F5)
    def cycle_view(self):
        """F5: góc nhìn thứ nhất -> thứ ba (sau lưng) -> thứ ba (trước mặt) -> thứ nhất."""
        camera = self.viewport.camera
        if self.mode != "survival":
            self.editor.set_status("F5 (see yourself) works in Walk mode: press M")
            return
        camera.view_mode = (camera.view_mode + 1) % 3
        if camera.view_mode == 0:
            self._leave_third_person()
        else:
            camera.third_distance = 0.0        # tính lại ở khung hình kế tiếp
            self._last_feet = None
            if self.body_yaw is None or camera.view_mode == 1:
                self.body_yaw = camera.yaw
        self.editor.set_status(("First person", "Third person (behind)", "Third person (front)")[camera.view_mode])

    def _leave_third_person(self):
        camera = self.viewport.camera
        camera.view_mode = 0
        camera.third_distance = 0.0
        self.viewport.avatar = None

    def _update_avatar(self, feet, walked, dt):
        """Hướng thân, ma trận các khớp và khoảng lùi camera (rút ngắn khi sau lưng có tường)."""
        camera, physics, pose = self.viewport.camera, self.physics, self.pose
        if not camera.view_mode:
            self.viewport.avatar = None
            return
        # thân quay theo hướng nhìn khi đi; đứng yên thì chỉ quay khi đầu lệch quá 50 độ (như Minecraft)
        diff = (camera.yaw - self.body_yaw + math.pi) % (2 * math.pi) - math.pi
        limit = math.radians(50.0)
        if walked > 1e-6 or pose.gesture == "zombie":
            self.body_yaw += diff * min(dt * 12.0, 1.0)
        elif abs(diff) > limit:
            self.body_yaw += diff - math.copysign(limit, diff)
        head_yaw = (camera.yaw - self.body_yaw + math.pi) % (2 * math.pi) - math.pi
        head_pitch = float(np.clip(camera.pitch, -1.2, 1.2))
        matrices = limb_matrices(feet, self.body_yaw, head_yaw, head_pitch, pose.joints(), physics.height / 32.0)
        brightness = (1.0, 1.0, 1.0)
        if self.lighting.enabled:
            brightness = tuple(float(np.clip(0.55 + 0.6 * c, 0.35, 1.0)) for c in self.lighting.ambient_color())
        self.viewport.avatar = (matrices, brightness)

        wanted = physics.height * (2.4 if camera.view_mode == 1 else 2.0)
        eye, forward = camera.position(), camera.forward()
        direction = -forward if camera.view_mode == 1 else forward
        distance = wanted
        if physics.has_world and physics.world.segment_blocked(eye, eye + direction * wanted, skip=0.0):
            low, high = 0.0, 1.0                  # tìm đoạn dài nhất chưa chạm tường
            for _ in range(7):
                mid = (low + high) / 2
                if physics.world.segment_blocked(eye, eye + direction * wanted * mid, skip=0.0):
                    high = mid
                else:
                    low = mid
            distance = max(low * wanted - physics.height * 0.1, physics.height * 0.15)
        current = camera.third_distance
        camera.third_distance = distance if current <= 0.0 or distance < current else \
            current + (distance - current) * min(dt * 6.0, 1.0)

    def update_world(self, dt):
        """Mỗi khung hình: bản đồ va chạm (luồng nền), thời gian trong ngày."""
        editor = self.editor
        versions = (editor.geometry_version, editor.transform_version, editor.deleted_version)
        if versions != self._world_versions:
            self._world_versions = versions
            self._update_bounds()
            self.physics.invalidate()
        # cần bản đồ để cảnh che mặt trời và các khối đèn
        sun_visible = self.lighting.enabled and (self.lighting.sun_on or bool(self.lighting.lights))
        self.physics.ensure_world(editor.scene, self.mode == "survival" or sun_visible)
        self.viewport.occluder = self.physics
        self.lighting.update(dt)
        while self.lighting.events:
            editor.set_status(self.lighting.events.pop(0))
        self.viewport.clock += dt
        self.viewport.unit = self.physics.height

    def toggle_grid(self):
        self.viewport.show_grid = not self.viewport.show_grid

    def toggle_sh(self):
        self.viewport.splat_renderer.use_sh = not self.viewport.splat_renderer.use_sh

    def set_flip(self, flip):
        self.editor.scene.flip = flip
        self.editor.notify_transform_changed()
        self.frame_scene()

    def exit_brush(self):
        self.editor.brush.active = False
        self.editor.brush.end_stroke()

    def shortcuts_window_toggle(self):
        self.shortcuts_window.toggle()

    def paint(self, x, y):
        rect = self.layout.viewport
        if not rect.is_empty:
            self.editor.paint(x, y, self.viewport.view_projection(rect), rect)

    def drag_speed(self):
        """Tốc độ kéo thanh trượt vị trí, tỉ lệ theo khoảng cách camera."""
        return max(self.viewport.camera.distance * 0.005, 1e-4)

    # ------------------------------------------------------------------ vòng lặp chính
    def _draw_gui(self):
        menu_height = self.menu_bar.draw()
        width, height = self.window.size
        self.layout.update(width, height, menu_height, self.status_bar.height())
        self.side_panel.draw(self.layout.side_panel)
        self.status_bar.draw(self.layout.status_bar)
        self.shortcuts_window.draw()
        self.overlay.draw(self.layout.viewport)

    def run(self):
        last_time = time.perf_counter()
        while not self.window.should_close:
            Window.poll_events()
            now = time.perf_counter()
            dt = now - last_time
            self.input.update(dt)
            self.update_world(dt)
            last_time = now

            self.gui.begin_frame()
            self._draw_gui()
            self.gui.end_frame()

            self.viewport.sync(self.editor)
            self.viewport.render(self.layout.viewport, self.window.size, self.window.framebuffer_size)
            self.gui.draw()
            self.window.swap_buffers()

            self.actions.run_pending()
            self.fps.tick(now)
        self.gui.shutdown()
        self.window.destroy()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    app = Application()
    if argv:
        app.open_file(argv[0])
        app.add_files(argv[1:])
    app.run()
