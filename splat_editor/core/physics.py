"""Vật lý cho file ply (T5): va chạm voxel dựng từ tâm gaussian, người chơi kiểu Minecraft sinh tồn
(trọng lực, nhảy, leo bậc, trượt dọc tường) và vật rơi (khối đèn).

Gaussian không có mặt phẳng / thể tích rõ ràng nên ta rời rạc hoá thành lưới voxel: ô nào có đủ
gaussian "rắn" (đủ đục, chưa xoá) thì là đặc. Mỗi ô đặc được mã hoá thành một số nguyên 64 bit
(ix, iz, iy) rồi xếp tăng dần; truy vấn "ô đặc cao nhất tại cột (ix, iz) không cao hơn iy" chỉ là một lần
np.searchsorted, nên vài chục truy vấn mỗi khung hình gần như không tốn gì.

Trục Y hướng lên (sau khi lật COLMAP), trọng lực kéo về -Y. Mọi kích thước tính theo
`Physics.height` (chiều cao người chơi, đơn vị cảnh) vì cảnh 3DGS không có đơn vị cố định.
"""

"""
physics = Physics()
physics.set_scale(radius)                   # đặt chiều cao người chơi theo kích thước cảnh
physics.ensure_world(scene, needed=True)    # mỗi khung hình: dựng bản đồ va chạm ở luồng nền khi cần
physics.player.place(eye, physics.eye_height)   # thả người chơi từ vị trí mắt
physics.walk(forward, right, yaw, jump, sprint, sneak, dt)   # đi bộ: cập nhật vị trí chân
eye = physics.player.eye(physics.eye_height, dt)
y = physics.drop_height(x, z, y_from)       # độ cao mặt đất dưới (x, z) hoặc None
"""

import math
import threading
import time

import numpy as np

_BITS = 21
_MASK = (1 << _BITS) - 1
_RING = np.array([(0.0, 0.0)] + [(math.cos(a * math.pi / 4), math.sin(a * math.pi / 4)) for a in range(8)])


class CollisionWorld:
    """Tập các voxel đặc, dựng một lần từ vị trí gaussian (toạ độ thế giới)."""

    def __init__(self):
        self.keys = np.zeros(0, np.int64)
        self.origin = np.zeros(3)
        self.voxel = 1.0
        self.min_y = 0.0
        self.max_y = 0.0
        self.solid_count = 0
        self.floor_y = 0.0         # sàn an toàn: không bao giờ rơi xuống dưới mức này

    @property
    def ready(self):
        return len(self.keys) > 0

    def build(self, positions, voxel, min_count=1):
        """positions (N,3) float; voxel: cạnh ô; min_count: số gaussian tối thiểu để ô là đặc."""
        self.voxel = float(voxel)
        if len(positions) == 0:
            return self
        lo = positions.min(axis=0).astype(np.float64)
        self.origin = lo - self.voxel
        self.min_y, self.max_y = float(lo[1]), float(positions[:, 1].max())
        self.floor_y = float(np.percentile(positions[:, 1], 1.0))   # bỏ qua gaussian lạc xa bên dưới
        cells = np.floor((positions - self.origin) / self.voxel).astype(np.int64)
        np.clip(cells, 0, _MASK, out=cells)
        keys = (cells[:, 0] << (2 * _BITS)) | (cells[:, 2] << _BITS) | cells[:, 1]
        if min_count > 1:
            keys, counts = np.unique(keys, return_counts=True)
            keys = keys[counts >= min_count]
        else:
            keys = np.unique(keys)
        self.keys = keys
        self.solid_count = len(keys)
        return self

    def _highest(self, x, z, y):
        """Chỉ số iy của ô đặc cao nhất tại cột (x, z) mà iy <= ô chứa độ cao y; -1 nếu không có."""
        x, z, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(z, float), np.asarray(y, float))
        cell = np.floor((np.stack([x, y, z], axis=-1) - self.origin) / self.voxel).astype(np.int64)
        ix, iy, iz = cell[..., 0], cell[..., 1], cell[..., 2]
        valid = (ix >= 0) & (ix <= _MASK) & (iz >= 0) & (iz <= _MASK) & (iy >= 0)
        iy = np.minimum(iy, _MASK)
        query = (np.clip(ix, 0, _MASK) << (2 * _BITS)) | (np.clip(iz, 0, _MASK) << _BITS) | iy
        idx = np.searchsorted(self.keys, query, side='right') - 1
        found = self.keys[np.maximum(idx, 0)]
        same = valid & (idx >= 0) & ((found >> _BITS) == (query >> _BITS))
        return np.where(same, found & _MASK, -1)

    def column_top(self, x, z, y_max):
        """Độ cao mặt trên của ô đặc cao nhất không vượt quá y_max tại mỗi cột (-inf: không có)."""
        top = self._highest(x, z, y_max)
        return np.where(top >= 0, self.origin[1] + (top + 1) * self.voxel, -np.inf)

    def segment_blocked(self, start, end, skip=1.0, skip_end=0.0):
        """Đoạn thẳng start→end có đi xuyên qua ô đặc nào không (bỏ qua `skip` ô đầu và `skip_end` ô cuối:
        đầu = ngay tại mắt, cuối = vật nằm sát / trong mặt đất như khối đèn đang nằm trên sàn)."""
        start, end = np.asarray(start, float), np.asarray(end, float)
        length = float(np.linalg.norm(end - start))
        if length < 1e-9 or not self.ready:
            return False
        n = int(length / (self.voxel * 0.5)) + 1
        t = np.linspace(0.0, 1.0, n)[int(skip * 2):max(n - int(skip_end * 2), 0)]
        if len(t) == 0:
            return False
        points = start + (end - start) * t[:, None]
        cell = np.floor((points - self.origin) / self.voxel).astype(np.int64)
        valid = np.all((cell >= 0) & (cell <= _MASK), axis=1)
        cell = np.clip(cell, 0, _MASK)
        query = (cell[:, 0] << (2 * _BITS)) | (cell[:, 2] << _BITS) | cell[:, 1]
        idx = np.minimum(np.searchsorted(self.keys, query), len(self.keys) - 1)
        return bool(np.any(valid & (self.keys[idx] == query)))

    def blocked(self, x, z, y0, y1):
        """Có ô đặc nào nằm trong khoảng độ cao [y0, y1] tại mỗi cột không."""
        top = self._highest(x, z, y1)
        low = np.floor((y0 - self.origin[1]) / self.voxel)
        return (top >= 0) & (top >= low)


class Player:
    """Người chơi: một cột đứng có bán kính, chân ở `feet`. Mắt ở trên chân."""

    def __init__(self):
        self.feet = np.zeros(3)
        self.vel_y = 0.0
        self.on_ground = False
        self.spawn = np.zeros(3)
        self.eye_y = 0.0           # độ cao mắt đã làm mượt (che bậc thang lởm chởm của bề mặt gaussian)
        self.respawns = 0

    def place(self, eye, eye_height):
        self.feet = np.array(eye, float) - np.array([0.0, eye_height, 0.0])
        self.spawn = self.feet.copy()
        self.vel_y = 0.0
        self.on_ground = False
        self.eye_y = float(eye[1])
        self.respawns = 0

    def eye(self, eye_height, dt=None):
        """Vị trí mắt; dt != None: làm mượt độ cao khi đang đứng trên mặt đất."""
        target = self.feet[1] + eye_height
        if dt is None or not self.on_ground or abs(target - self.eye_y) > eye_height * 0.6:
            self.eye_y = target
        else:
            self.eye_y += (target - self.eye_y) * min(dt * 18.0, 1.0)
        return np.array([self.feet[0], self.eye_y, self.feet[2]])


class Physics:
    EYE_RATIO = 0.92       # mắt cao bằng 92% chiều cao người
    VOXELS_PER_HEIGHT = 8  # cạnh voxel = chiều cao / 8
    DEFAULT_HEIGHT = 2.74  # chiều cao người chơi mặc định (đơn vị cảnh)

    def __init__(self):
        self.world = None
        self.player = Player()
        self.height = self.DEFAULT_HEIGHT
        self.radius_ratio = 0.14
        self.step_ratio = 0.35
        self.jump_ratio = 0.75
        self.gravity_scale = 1.0
        self.flat_ground = False  # mặc định: va chạm thật với cảnh (đứng được trên thùng xe...), có sàn an toàn nên không rơi mãi
        self.status = "Collision map not built"
        self._dirty = True
        self._dirty_since = 0.0
        self._building = False
        self._token = 0

    # ------------------------------------------------------------------ thông số (tỉ lệ theo chiều cao)
    @property
    def eye_height(self):
        return self.height * self.EYE_RATIO

    @property
    def gravity(self):
        return 12.0 * self.height * self.gravity_scale

    @property
    def walk_speed(self):
        return 2.5 * self.height

    def set_scale(self, radius):
        """Giữ chiều cao mặc định cố định (2.74); chỉnh lại được trong giao diện."""
        self.set_height(self.DEFAULT_HEIGHT)

    def set_height(self, height):
        if abs(height - self.height) > 1e-9:
            self.height = float(height)
            self.invalidate()

    # ------------------------------------------------------------------ bản đồ va chạm
    def invalidate(self):
        """Cảnh đổi (mở / xoá / kéo lớp): dựng lại bản đồ va chạm khi cần (chờ yên 0.4 giây)."""
        self._dirty = True
        self._dirty_since = time.perf_counter()

    @property
    def building(self):
        return self._building

    @property
    def ready(self):
        return self.flat_ground or self.has_world

    @property
    def has_world(self):
        return self.world is not None and self.world.ready

    def ensure_world(self, scene, needed):
        """Gọi mỗi khung hình. Dựng bản đồ ở luồng nền nếu cần mà đang cũ."""
        if not needed or not self._dirty or self._building or scene.is_empty:
            return
        if time.perf_counter() - self._dirty_since < 0.4:
            return
        positions, step = scene.solid_positions()
        voxel = self.height / self.VOXELS_PER_HEIGHT
        min_count = 3 if step == 1 else 2 if step == 2 else 1
        self._dirty = False
        self._building = True
        self._token += 1
        token = self._token
        self.status = "Building collision map..."

        def work():
            try:
                world = CollisionWorld().build(positions, voxel, min_count)
                if token == self._token:
                    self.world = world
                    self.status = f"Collision map: {world.solid_count:,} solid voxels"
            finally:
                self._building = False

        threading.Thread(target=work, name="collision-builder", daemon=True).start()

    # ------------------------------------------------------------------ truy vấn
    def drop_height(self, x, z, y_from, radius=0.0):
        """Độ cao mặt đất dưới (x, z) tính từ y_from trở xuống; None nếu không có."""
        if self.flat_ground:
            return 0.0
        if not self.has_world:
            return None
        if radius:
            xs, zs = x + radius * _RING[:, 0], z + radius * _RING[:, 1]
        else:
            xs, zs = np.array([x]), np.array([z])
        top = float(self.world.column_top(xs, zs, y_from).max())
        return top if top > -np.inf else None

    def visibility(self, eye, targets, skip_end=0.0):
        """Tỉ lệ các điểm `targets` nhìn thấy được từ `eye` (không bị cảnh che); 1.0 nếu chưa có bản đồ."""
        if not self.has_world or len(targets) == 0:
            return 1.0
        seen = sum(not self.world.segment_blocked(eye, t, skip_end=skip_end) for t in targets)
        return seen / len(targets)

    # ------------------------------------------------------------------ người chơi
    def walk(self, forward, right, yaw, jump, sprint, sneak, dt):
        """Đi bộ: W/S/A/D theo hướng nhìn `yaw`, nhảy, chạy nhanh, đi chậm.
        Trả về False nếu chưa có bản đồ va chạm (người chơi đứng yên)"""
        if not self.ready:
            return False
        player, world, h = self.player, self.world, self.height
        flat = self.flat_ground
        dt = min(dt, 0.05)
        radius, step = self.radius_ratio * h, self.step_ratio * h
        feet = player.feet

        s, c = math.sin(yaw), math.cos(yaw)
        move = forward * np.array([-s, -c]) + right * np.array([c, -s])
        length = np.linalg.norm(move)
        if length > 0:
            move = move / length * self.walk_speed * (1.7 if sprint else 0.4 if sneak else 1.0) * dt

        def ring(x, z):
            return x + radius * _RING[:, 0], z + radius * _RING[:, 1]

        def body_blocked(x, z):
            if flat:
                return False
            xs, zs = ring(x, z)
            return bool(world.blocked(xs, zs, feet[1] + step, feet[1] + 0.9 * h).any())

        def ground_at(x, z, y_max):
            if flat:
                return 0.0
            xs, zs = ring(x, z)
            top = float(world.column_top(xs, zs, y_max).max())
            return max(top, world.floor_y)               # có sàn an toàn: đi ra khỏi cảnh cũng không rơi mãi

        x, z = feet[0], feet[2]
        if length > 0:
            if not body_blocked(x + move[0], z + move[1]):
                x, z = x + move[0], z + move[1]
            elif not body_blocked(x + move[0], z):       # trượt dọc tường
                x += move[0]
            elif not body_blocked(x, z + move[1]):
                z += move[1]

        y = feet[1]
        ground = ground_at(x, z, y + step)
        if player.on_ground and jump:
            player.vel_y = math.sqrt(2.0 * self.gravity * self.jump_ratio * h)
            player.on_ground = False
        if player.on_ground:
            if ground is not None and y - ground <= step:
                y = ground                               # bám mặt đất khi đi xuống dốc / bậc nhỏ
            else:
                player.on_ground = False
        if not player.on_ground:
            player.vel_y -= self.gravity * dt
            new_y = y + player.vel_y * dt
            if player.vel_y <= 0 and ground is not None and new_y <= ground:
                y, player.vel_y, player.on_ground = ground, 0.0, True
            else:
                if player.vel_y > 0 and not flat:        # đụng trần
                    xs, zs = ring(x, z)
                    if world.blocked(xs, zs, y + 0.9 * h, new_y + h).any():
                        player.vel_y, new_y = 0.0, y
                y = new_y
        feet[:] = (x, y, z)

        if flat:
            y = max(y, 0.0)
            feet[1] = y
        return True
