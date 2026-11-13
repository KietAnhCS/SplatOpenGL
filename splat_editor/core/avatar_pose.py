"""Tư thế của nhân vật người chơi (nhìn thấy khi bấm F5): nhịp đi bộ, cúi người, ngồi và các cử chỉ.

Port từ voxel-engine (WalkCycle.java + HumanoidFigure.java). Lớp này chỉ tính GÓC các khớp (độ),
không đụng tới OpenGL nên kiểm thử được; việc dựng ma trận và vẽ nằm ở render/avatar_renderer.py.

Quy ước (giống Java): nhân vật quay mặt về +Z, quay quanh trục X dương là "đưa chi về phía trước"
khi góc ÂM (chân đá ra trước = góc âm); quay quanh Z dương đưa tay ra ngoài về phía +X.
Đơn vị dài là điểm ảnh của skin 64x64 (người cao 32).
"""

"""
pose = AvatarPose()
pose.update(dt, distance, crouching)    # mỗi khung hình; distance = quãng đường ngang vừa đi
pose.toggle_sit()                       # phím C
pose.toggle_gesture("wave")             # phím V; GESTURES = wave, zombie, cheer
joints = pose.joints()                  # dict góc các khớp + độ hạ thân, đưa cho AvatarRenderer
"""

import math

import numpy as np

GESTURES = ("wave", "zombie", "cheer")

SWING_ANGLE = 60.0      # góc vung tối đa của tay / chân khi chạy
STRIDE = 2.0            # radian pha của nhịp bước cho mỗi "chiều cao người" đi được (xem update)
GAIT_SCALE = 1.75       # hệ số chỉnh nhịp bước cho khớp với bản Java gốc
FULL_SPEED = 4.3        # chiều cao người mỗi giây tương ứng bước tối đa (khối/giây trong Java)
BLEND = 8.0             # độ nhạy khi bật / tắt biên độ vung
POSE_BLEND = 7.0        # độ nhạy chuyển giữa các tư thế (ngồi, cúi, cử chỉ)
SIT_DROP = 10.0         # ngồi: hạ cả người xuống (điểm ảnh skin) để đùi chạm đất
CROUCH_LEAN = 28.0      # cúi người về phía trước (độ)


def _approach(value, target, rate, dt):
    """Đưa `value` tiến dần về `target` (làm mượt): mỗi khung hình đi một phần của khoảng còn lại."""
    return value + (target - value) * min(1.0, dt * rate)


class AvatarPose:
    def __init__(self):
        self.phase = 0.0
        self.amount = 0.0                     # biên độ vung tay chân hiện tại, 0..1
        self.time = 0.0
        self.sit = 0.0                        # 0 = đứng, 1 = ngồi hẳn (đã làm mượt)
        self.crouch = 0.0
        self.sitting = False
        self.gesture = None                   # tên cử chỉ đang bật hoặc None
        self.gesture_amount = {name: 0.0 for name in GESTURES}

    # ------------------------------------------------------------------ điều khiển
    def toggle_sit(self):
        self.sitting = not self.sitting
        if self.sitting:
            self.gesture = None

    def stand(self):
        self.sitting = False

    def toggle_gesture(self, name):
        self.gesture = None if self.gesture == name else name
        if self.gesture is not None:
            self.sitting = False if name != "wave" else self.sitting     # vẫy tay được cả khi ngồi

    # ------------------------------------------------------------------ mỗi khung hình
    def update(self, dt, distance, crouching, height=1.0):
        """distance: quãng đường ngang đã đi (đơn vị cảnh); height: chiều cao người (cùng đơn vị) để
        nhịp bước và biên độ không phụ thuộc kích thước cảnh."""
        if dt <= 0.0:
            return
        walked = distance / max(height, 1e-9)                 # đơn vị: chiều cao người
        speed = walked / dt
        target = min(1.0, speed / (FULL_SPEED / GAIT_SCALE))     # biên độ vung muốn đạt (0..1)
        self.amount = _approach(self.amount, target, BLEND, dt)
        self.phase += walked * STRIDE * GAIT_SCALE               # đi càng xa, pha càng tăng
        self.time += dt
        self.sit = _approach(self.sit, 1.0 if self.sitting else 0.0, POSE_BLEND, dt)
        self.crouch = _approach(self.crouch, 1.0 if crouching and not self.sitting else 0.0, POSE_BLEND, dt)
        for name in GESTURES:
            self.gesture_amount[name] = _approach(self.gesture_amount[name],
                                                  1.0 if self.gesture == name else 0.0, POSE_BLEND, dt)

    @property
    def stance(self):
        """Hệ số chiều cao mắt so với lúc đứng (ngồi / cúi thì thấp hơn)."""
        return 1.0 - 0.48 * self.sit - 0.12 * self.crouch

    # ------------------------------------------------------------------ góc các khớp
    def joints(self):
        """Góc (độ) của từng khớp. Tay: (quay quanh X, quay quanh Z)."""
        t = self.time
        walk = self.amount * (1.0 - self.sit)
        swing = math.sin(self.phase) * SWING_ANGLE * walk
        idle = math.sin(t * 1.13) * 2.2 + math.sin(t * 1.91) * 0.8     # thở nhẹ khi đứng yên

        leg_l, leg_r = swing, -swing
        arm_l = [-swing + idle, 0.0]
        arm_r = [swing - idle, 0.0]

        g = self.gesture_amount
        if g["zombie"] > 0.001:                       # hai tay đưa thẳng ra trước, hơi rung theo nhịp bước
            raise_x = -85.0 + 3.0 * math.sin(t * 2.4) + 0.15 * swing
            arm_l = _mix_pair(arm_l, [raise_x, 0.0], g["zombie"])
            arm_r = _mix_pair(arm_r, [raise_x, 0.0], g["zombie"])
        if g["cheer"] > 0.001:                        # hai tay giơ cao qua đầu
            bob = 6.0 * math.sin(t * 7.0)
            arm_l = _mix_pair(arm_l, [0.0, -(158.0 + bob)], g["cheer"])
            arm_r = _mix_pair(arm_r, [0.0, 158.0 + bob], g["cheer"])
        if g["wave"] > 0.001:                         # tay phải giơ lên và vẫy
            wave = 142.0 + 20.0 * math.sin(t * 9.0)
            arm_r = _mix_pair(arm_r, [0.0, wave], g["wave"])

        if self.sit > 0.001:                          # ngồi bệt: đùi ngang, tay đặt lên đùi
            leg_l = leg_l * (1 - self.sit) - 90.0 * self.sit
            leg_r = leg_r * (1 - self.sit) - 90.0 * self.sit
            rest = [-35.0 + idle, 0.0]
            keep = 1.0 - 0.8 * max(g["wave"], g["zombie"], g["cheer"])    # cử chỉ vẫn thắng tư thế nghỉ
            arm_l = _mix_pair(arm_l, rest, self.sit * keep)
            arm_r = _mix_pair(arm_r, [-35.0 - idle, 0.0], self.sit * keep * (1.0 - g["wave"]))

        return {
            "leg_l": leg_l, "leg_r": leg_r,
            "arm_l": tuple(arm_l), "arm_r": tuple(arm_r),
            "lean": CROUCH_LEAN * self.crouch,        # thân + tay + đầu nghiêng quanh hông
            "drop": SIT_DROP * self.sit,              # hạ cả người xuống
        }


def _mix_pair(a, b, k):
    """Trộn hai cặp góc: k = 0 giữ a, k = 1 thành b."""
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]


# ---------------------------------------------------------------------- ma trận các khớp
LIMBS = ("legLeft", "legRight", "body", "armLeft", "armRight", "head")
HIP_Y = 12.0
SHOULDER_Y = 24.0
ARM_X = 6.0


def _translate(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _rot(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    m = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    m[i, i], m[i, j], m[j, i], m[j, j] = c, -s, s, c
    return m


def limb_matrices(feet, facing, head_yaw, head_pitch, joints, scale):
    """Ma trận model (4x4) của 6 khối theo thứ tự LIMBS.

    feet: vị trí bàn chân; facing: yaw camera (rad) của thân; head_yaw: lệch của đầu so với thân (rad);
    head_pitch: pitch camera (rad, dương = nhìn xuống); scale: kích thước một điểm ảnh skin (= chiều cao / 32).
    """
    root = (_translate(*feet) @ _rot("y", math.degrees(facing) + 180.0) @ np.diag([scale, scale, scale, 1.0])
            @ _translate(0.0, -joints["drop"], 0.0))
    upper = root @ _translate(0, HIP_Y, 0) @ _rot("x", joints["lean"]) @ _translate(0, -HIP_Y, 0)

    def leg(angle):
        return root @ _translate(0, HIP_Y, 0) @ _rot("x", angle) @ _translate(0, -HIP_Y, 0)

    def arm(px, angles):
        return (upper @ _translate(px, SHOULDER_Y, 0) @ _rot("z", angles[1]) @ _rot("x", angles[0])
                @ _translate(-px, -SHOULDER_Y, 0))

    head = (upper @ _translate(0, SHOULDER_Y, 0) @ _rot("y", math.degrees(head_yaw))
            @ _rot("x", math.degrees(head_pitch)) @ _translate(0, -SHOULDER_Y, 0))
    return [leg(joints["leg_l"]), leg(joints["leg_r"]), upper,
            arm(-ARM_X, joints["arm_l"]), arm(ARM_X, joints["arm_r"]), head]
