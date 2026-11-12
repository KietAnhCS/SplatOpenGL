"""Toán 3D: ma trận chiếu / nhìn, góc Euler, quaternion."""

"""
proj = perspective(fov_y_deg=45, aspect=16 / 9, near=0.01, far=1000)
view = look_at(eye=[0, 1, 5], target=[0, 0, 0], up=[0, 1, 0])

R = euler_to_matrix([0, 90, 0])        # góc Euler (độ) quanh X, Y, Z -> ma trận 3x3
angles = matrix_to_euler(R)            # ngược lại
R2 = axis_angle_matrix([0, 1, 0], 30)  # xoay 30 độ quanh trục Y

q = matrix_to_quat(R)                  # quaternion (w, x, y, z)
q2 = quat_mul(q, q)                    # nhân hai quaternion (xoay liên tiếp)
R3 = quat_to_matrix(q2)
"""

import math

import numpy as np


# ----------------------------------------------------------------------------- ma trận camera

def perspective(fov_y_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_y_deg) / 2)
    m = np.zeros((4, 4), np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def orthographic(half_size, near, far):
    """Phép chiếu trực giao đối xứng (dùng cho bản đồ bóng của mặt trời): hộp [-h,h]^2 x [near,far]."""
    m = np.identity(4, np.float32)
    m[0, 0] = m[1, 1] = 1.0 / half_size
    m[2, 2] = -2.0 / (far - near)
    m[2, 3] = -(far + near) / (far - near)
    return m


def orthographic(half_size, near, far):
    """Phép chiếu trực giao đối xứng (bản đồ bóng của mặt trời): hộp [-h,h]^2 x [near,far]."""
    m = np.identity(4, np.float32)
    m[0, 0] = m[1, 1] = 1.0 / half_size
    m[2, 2] = -2.0 / (far - near)
    m[2, 3] = -(far + near) / (far - near)
    return m


def look_at(eye, target, up):
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    m = np.identity(4, np.float32)
    m[0, :3] = right
    m[1, :3] = true_up
    m[2, :3] = -forward
    m[:3, 3] = -m[:3, :3] @ eye
    return m


# ----------------------------------------------------------------------------- xoay

def euler_to_matrix(degrees):
    """Góc Euler (độ) quanh X, Y, Z -> ma trận xoay R = Rz * Ry * Rx."""
    x, y, z = np.radians(degrees)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def matrix_to_euler(m):
    """Ngược lại của euler_to_matrix: ma trận R = Rz * Ry * Rx -> góc (độ) quanh X, Y, Z."""
    y = math.asin(min(max(-m[2, 0], -1.0), 1.0))
    if abs(m[2, 0]) < 0.999999:
        x = math.atan2(m[2, 1], m[2, 2])
        z = math.atan2(m[1, 0], m[0, 0])
    else:                                   # khoá gimbal (Y = ±90°): gộp hết vào Z
        x = 0.0
        z = math.atan2(-m[0, 1], m[1, 1])
    return [math.degrees(x), math.degrees(y), math.degrees(z)]


def axis_angle_matrix(axis, degrees):
    """Ma trận xoay `degrees` độ quanh trục `axis` (công thức Rodrigues)."""
    x, y, z = np.asarray(axis, float) / np.linalg.norm(axis)
    a = math.radians(degrees)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def matrix_to_quat(m):
    """Ma trận xoay 3x3 -> quaternion (w, x, y, z)."""
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = 2 * math.sqrt(trace + 1)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2 * math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2 * math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = 2 * math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    return np.array(q)


def quat_mul(a, b):
    """Nhân quaternion a (4,) với từng quaternion trong b (N,4)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], axis=1)


def quat_to_matrix(q):
    """(N,4) quaternion (w,x,y,z) -> (N,3,3) ma trận xoay."""
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], axis=1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], axis=1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], axis=1),
    ], axis=1)
