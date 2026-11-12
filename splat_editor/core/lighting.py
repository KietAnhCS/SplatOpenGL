"""Ánh sáng và chu kỳ ngày đêm (T4 + T5).

- Ánh sáng môi trường (ambient) + một mặt trời (ánh sáng định hướng) + tối đa 8 "khối đèn" (đèn điểm).
- Phong shading: diffuse + specular, tính trong shader cho từng gaussian (xem splat_prep.vert).
- Bóng đổ của mặt trời bằng shadow mapping (bản đồ độ sâu nhìn từ mặt trời, vẽ ở SplatRenderer).
- Mặt trời chuyển động theo thời gian; chu kỳ ngày đêm là một máy trạng thái (NIGHT -> DAWN -> DAY -> DUSK)
  điều khiển màu bầu trời và tự bật / tắt các khối đèn.
- Khối đèn chịu trọng lực: thả xuống thì rơi, nảy nhẹ rồi nằm yên trên bề mặt của file ply.

Không có OpenGL ở đây: Lighting chỉ giữ trạng thái và đổi ra tham số (params) cho renderer.
"""

"""
lighting = Lighting()
lighting.set_bounds(center, radius)         # kích thước cảnh (để đặt tầm đèn, bản đồ bóng)
lighting.add_sun()                          # bật mặt trời (và bật hệ thống ánh sáng)
light = lighting.add_light(position)        # thêm một khối đèn, trả về None nếu đã đủ 8
lighting.update(dt, physics)                # mỗi khung hình: thời gian, máy trạng thái, khối đèn rơi
params = lighting.params()                  # dict cho SplatRenderer.set_lighting / LightRenderer
"""

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .math3d import look_at, orthographic

MAX_LIGHTS = 8


class DayPhase(Enum):
    NIGHT = "Night"
    DAWN = "Dawn"
    DAY = "Day"
    DUSK = "Dusk"


class DayCycle:
    """Máy trạng thái ngày đêm. Mỗi trạng thái bắt đầu ở một giờ cố định; chuyển trạng thái khi giờ
    chạm mốc của trạng thái kế tiếp (hoặc nhảy thẳng tới trạng thái đúng nếu kéo thanh trượt giờ)."""

    START = {DayPhase.DAWN: 5.0, DayPhase.DAY: 7.0, DayPhase.DUSK: 17.0, DayPhase.NIGHT: 19.0}
    NEXT = {DayPhase.NIGHT: DayPhase.DAWN, DayPhase.DAWN: DayPhase.DAY,
            DayPhase.DAY: DayPhase.DUSK, DayPhase.DUSK: DayPhase.NIGHT}

    def __init__(self, hour=10.0):
        self.state = self.phase_for(hour)

    @classmethod
    def phase_for(cls, hour):
        for phase, start in cls.START.items():
            end = cls.START[cls.NEXT[phase]]
            if (start <= hour < end) if start < end else (hour >= start or hour < end):
                return phase
        return DayPhase.DAY

    def update(self, hour):
        """Trả về trạng thái mới nếu vừa chuyển, ngược lại None (sự kiện on_enter)."""
        phase = self.phase_for(hour)
        if phase is self.state:
            return None
        self.state = phase
        return phase


@dataclass
class PointLight:
    position: np.ndarray
    range: float
    color: tuple = (1.0, 0.82, 0.55)
    intensity: float = 3.0
    on: bool = True
    auto_night: bool = False     # tự bật lúc hoàng hôn, tắt lúc bình minh (máy trạng thái ngày đêm)
    falls: bool = False          # đèn đứng yên tại chỗ đặt, không chịu trọng lực
    vel_y: float = 0.0
    resting: bool = False
    name: str = "Light"


def _smooth(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class Lighting:
    SHADOW_SIZE = 2048

    def __init__(self):
        self.enabled = False
        self.ambient = 0.3
        self.specular = 0.25
        self.shininess = 24.0
        self.shadows = True

        self.sun_on = False
        self.sun_intensity = 0.9
        self.sun_azimuth = 35.0          # độ
        self.hour = 10.0                 # giờ trong ngày, 0..24
        self.animate = True              # mặt trời tự di chuyển theo mặc định
        self.day_length = 36.0           # giây thật cho một ngày: 1.5 giây = 1 giờ
        self.sky_follows = True
        self.cycle = DayCycle(self.hour)

        self.lights = []
        self.selected = -1
        self.picked = -1                 # đèn vừa click chọn trong cảnh 3D: phím Delete xoá đèn này
        self.fireflies = True
        self.center = np.zeros(3)
        self.radius = 1.0
        self.events = []                 # thông báo ngắn cho thanh trạng thái

    # ------------------------------------------------------------------ cấu hình
    def set_bounds(self, center, radius):
        self.center = np.asarray(center, float)
        self.radius = max(float(radius), 1e-6)

    def add_sun(self):
        self.enabled = self.sun_on = True

    def remove_sun(self):
        self.sun_on = False

    def add_light(self, position, light_range=None):
        if len(self.lights) >= MAX_LIGHTS:
            return None
        light = PointLight(np.array(position, float), light_range or self.radius * 0.5,
                           name=f"Light {len(self.lights) + 1}")
        self.lights.append(light)
        self.selected = len(self.lights) - 1
        self.enabled = True
        return light

    def remove_light(self, index):
        if 0 <= index < len(self.lights):
            del self.lights[index]
            self.selected = min(self.selected, len(self.lights) - 1)
            self.picked = -1

    @property
    def active_light(self):
        return self.lights[self.selected] if 0 <= self.selected < len(self.lights) else None

    # ------------------------------------------------------------------ mặt trời / bầu trời
    def sun_direction(self):
        """Vector đơn vị từ cảnh hướng về mặt trời. Giờ 6: mọc, 12: trên cao nhất, 18: lặn."""
        angle = (self.hour - 6.0) / 12.0 * math.pi
        elevation = math.sin(angle) * math.radians(65.0)        # âm vào ban đêm
        azimuth = math.radians(self.sun_azimuth) + (angle - math.pi / 2)
        return np.array([math.cos(elevation) * math.cos(azimuth), math.sin(elevation),
                         math.cos(elevation) * math.sin(azimuth)])

    def daylight(self):
        """0 (đêm) .. 1 (ban ngày), mượt quanh lúc mặt trời qua đường chân trời."""
        return _smooth(-0.08, 0.3, self.sun_direction()[1])

    def sun_color(self):
        s = self.sun_direction()[1]
        warm = _mix((1.0, 0.5, 0.25), (1.0, 0.96, 0.88), _smooth(0.0, 0.35, s))
        strength = self.sun_intensity * _smooth(-0.02, 0.2, s)
        return tuple(c * strength for c in warm)

    def sun_color_for_gizmo(self):
        """Màu quả cầu mặt trời (luôn sáng rõ, đỏ cam khi gần đường chân trời)."""
        return _mix((1.0, 0.45, 0.2), (1.0, 0.95, 0.75), _smooth(0.0, 0.35, self.sun_direction()[1]))

    def ambient_color(self):
        base = self.ambient
        if not self.sun_on:
            return (base, base, base)
        tint = _mix((0.12, 0.16, 0.32), (1.0, 1.0, 1.0), self.daylight())
        return tuple(base * c for c in tint)

    def sky_color(self):
        s = self.sun_direction()[1]
        sky = _mix((0.012, 0.018, 0.05), (0.42, 0.62, 0.92), self.daylight())
        twilight = math.exp(-(s / 0.18) ** 2)
        return _mix(sky, (0.85, 0.45, 0.32), 0.55 * twilight)

    # ------------------------------------------------------------------ cập nhật theo thời gian
    def update(self, dt, physics=None):
        """Tiến thời gian, chạy máy trạng thái ngày đêm và vật lý của khối đèn."""
        if self.animate and self.sun_on:
            self.hour = (self.hour + dt * 24.0 / max(self.day_length, 1.0)) % 24.0
        phase = self.cycle.update(self.hour)
        if phase is not None and self.sun_on:
            self._on_enter(phase)
        if physics is not None:
            self._update_lights(dt, physics)

    def _on_enter(self, phase):
        if phase in (DayPhase.DUSK, DayPhase.NIGHT):
            changed = [l for l in self.lights if l.auto_night and not l.on]
            for light in changed:
                light.on = True
        elif phase in (DayPhase.DAWN, DayPhase.DAY):
            changed = [l for l in self.lights if l.auto_night and l.on]
            for light in changed:
                light.on = False
        else:
            changed = []
        self.events.append(f"{phase.value}" + (f": {len(changed)} auto light(s) switched" if changed else ""))

    def _update_lights(self, dt, physics):
        dt = min(dt, 0.05)
        g = physics.gravity
        rest = physics.height * 0.12                # khối đèn nằm cách mặt đất một chút
        for light in self.lights:
            if not light.falls or light.resting:
                continue
            x, y, z = light.position
            light.vel_y -= g * dt
            new_y = y + light.vel_y * dt
            ground = physics.drop_height(x, z, y, radius=physics.height * 0.05) if physics.ready else None
            floor = ground if ground is not None else (physics.world.min_y if physics.ready else None)
            if floor is None:
                light.vel_y = 0.0                   # chưa có bản đồ va chạm: đứng yên chờ
                continue
            if new_y <= floor + rest:
                new_y = floor + rest
                if ground is not None and abs(light.vel_y) > 0.6 * physics.height:
                    light.vel_y = -light.vel_y * 0.35   # nảy lên
                else:
                    light.vel_y, light.resting = 0.0, True
            light.position[1] = new_y

    # ------------------------------------------------------------------ bản đồ bóng
    def shadow_setup(self):
        """(ma trận ánh sáng, kích thước texel theo thế giới, độ lệch độ sâu) cho bản đồ bóng trực giao."""
        d = self.sun_direction()
        r = self.radius * 1.1
        eye = self.center + d * 2.0 * r
        up = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
        view = look_at(eye, self.center, up).astype(np.float64)
        proj = orthographic(r, 0.01 * r, 4.0 * r).astype(np.float64)
        texel = 2.0 * r / self.SHADOW_SIZE
        return (proj @ view).astype(np.float32), texel, 3.0 * texel / (3.99 * r)

    # ------------------------------------------------------------------ tham số cho renderer
    def point_lights(self):
        return [l for l in self.lights if l.on]

    def params(self):
        """Trạng thái ánh sáng dạng dict cho renderer; `signature` đổi khi cần tính lại màu gaussian."""
        if not self.enabled:
            return {'enabled': False, 'signature': (False,)}
        points = self.point_lights()
        sun = self.sun_on and self.sun_direction()[1] > -0.1
        sun_dir = self.sun_direction() if self.sun_on else np.array([0.0, 1.0, 0.0])
        shadows = bool(self.shadows and sun and self.sun_color()[0] > 1e-3)
        params = {
            'enabled': True,
            'ambient': self.ambient_color(),
            'sun_on': bool(sun),
            'sun_dir': sun_dir,
            'sun_color': self.sun_color() if sun else (0.0, 0.0, 0.0),
            'specular': self.specular,
            'shininess': self.shininess,
            'point_pos': np.array([l.position for l in points], np.float32).reshape(-1, 3),
            'point_color': np.array([np.array(l.color) * l.intensity for l in points], np.float32).reshape(-1, 3),
            'point_range': np.array([l.range for l in points], np.float32),
            'shadows': shadows,
        }
        if shadows:
            params['shadow_vp'], params['shadow_texel'], params['shadow_bias'] = self.shadow_setup()
        key = lambda a: tuple(np.round(np.asarray(a, np.float64).ravel(), 4))  # noqa: E731
        params['signature'] = (True, key(params['ambient']), params['sun_on'], key(sun_dir),
                               key(params['sun_color']), round(self.specular, 3), round(self.shininess, 1),
                               shadows, key(params['point_pos']), key(params['point_color']),
                               key(params['point_range']), round(self.radius, 4))
        return params
