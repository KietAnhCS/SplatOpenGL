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

def perspective(fov_y_deg, aspect, near, far):
    pass 

def look_at(eye, target, up):
    pass 

def euler_to_matrix(degrees):
    pass 

def matrix_to_euler(m):
    pass  

def axis_angle_matrix():
    pass 

def matrix_to_quat(m):
    pass 

def quat_mul(a,b):
    pass 

def quat_to_matrix(q):
    pass 