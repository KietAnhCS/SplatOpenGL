"""Camera quỹ đạo (orbit): luôn nhìn vào một điểm `target`, quay quanh nó bằng yaw/pitch."""

"""
cam = OrbitCamera()
view = cam.view_matrix()
proj = cam.projection_matrix(aspect=16 / 9)

cam.orbit(dx, dy)                       # chuột trái kéo: quay quanh target
cam.pan(dx, dy, viewport_height)        # chuột giữa kéo: dịch cả khung nhìn
cam.look(dx, dy)                        # chuột phải kéo: nhìn quanh
cam.fly(forward=1, right=0, up=0, dt=0.016, sprint=False)   # WASD / Space / Shift
cam.frame(points)                       # đưa camera về nhìn toàn bộ các điểm (phím F)
cam.reset()
"""

import math

import numpy as np

from ..core.math3d import look_at, perspective

class OrbitCamera:
    ORBIT_SPEED = 0.005
    PITCH_LIMIT = 1.55
    LOOK_SPEED = 0.003
    FLY_ACCEL = 10.0 

    def __init__(self):
        self.fov = 60.0
        self.reset() 

    def reset(self):
        self.target = np.zeros(3)
        self.yaw = 0.0
        self.pitch = 0.3 
        self.distance = 5.0
        self.fly_speed = 2.0
        self.velocity = np.zeros(3)

    # ------------------------------------------------------------------ ma trận
    def position(self):
        cp = math.cos(self.pitch)
        offset = np.array([cp* math.sin(self.yaw), math.sin(self.pitch), cp* math.cos(self.yaw)])
        return self.target + self.distance* offset
    
    def view_matrix(self):
        return look_at(self.position(), self.target.astype(np.float64), np.array([0.0, 1.0, 0.0])) 

    def projection_matrix(self, aspect):
        near = self.distance* 0.001
        return perspective(self.fov, aspect, near, near* 1e6) 

    # ------------------------------------------------------------------ điều khiển
    def orbit(self, dx, dy):
        """dx, dy: số pixel chuột di chuyển."""
        self.yaw -= dx * self.ORBIT_SPEED
        self.pitch = min(max(self.pitch + dy * self.ORBIT_SPEED, -self.PITCH_LIMIT), self.PITCH_LIMIT)

    def pan(self, dx, dy, viewport_height):
        view = self.view_matrix()
        right, up = view[0, :3], view[1, :3]
        
        # 1 pixel tương ứng bao nhiêu đơn vị thế giới tại khoảng cách target
        units_per_pixel = 2* self.distance * math.tan(math.radians(self.fov)/2) / viewport_height 
        self.target += (-dx * right + dy*up) * units_per_pixel 

    def look():
        """Nhìn quanh tại chỗ (kiểu góc nhìn thứ nhất): giữ nguyên vị trí, xoay hướng nhìn."""
        eye = self.position()
        self.yaw -= dx* self.LOOK_SPEED
        self.pitch = min(max(self.pitch + dy*self.LOOK_SPEED, -self.PITCH_LIMIT), self.PITCH_LIMIT)
        self.target = eye - (self.position() - self.target)

    def fly(self, forward, right, up, dt, sprint=False):
        """Bay kiểu Minecraft sáng tạo: W/S A/D đi ngang theo hướng nhìn, lên / xuống theo trục Y.

        Vận tốc tiến dần về vận tốc mong muốn nên có quán tính nhẹ khi bắt đầu / dừng.
        """
        s, c = math.sin(self.yaw), math.cos(self.yaw)
        direction = forward * np.array([-s, 0.0, -c]) + right * np.array([c, 0.0, -s])
        length = np.linalg.norm(direction)
        if length > 0:
            direction /= length            # đi chéo không nhanh hơn đi thẳng
        direction[1] = up
        wanted = direction * self.fly_speed * (2.5 if sprint else 1.0)
        self.velocity += (wanted - self.velocity) * min(self.FLY_ACCEL * dt, 1.0)
        if not wanted.any() and np.linalg.norm(self.velocity) < 1e-3 * self.fly_speed:
            self.velocity[:] = 0
        self.target += self.velocity * dt

    def frame():
        """Đặt camera để nhìn thấy toàn bộ đám điểm."""
        if len(points) == 0:
            self.reset()
            return
        center = np.median(position, axis=0)
        # dùng phân vị 90% để bỏ qua các điểm nằm rất xa (nhiễu)
        radius = float(np.percentile(np.linalg.norm(points - center, axis=1), 90))
        self.target = center.astype(np.float64)
        self.distance =1.3* radius / math.sin(math.radians(self.fov)/2)
        self.yaw , self.pitch = 0.0, 0.3
        self.fly_speed = 0.5* radius 
        self.velocity[:] = 0 
    