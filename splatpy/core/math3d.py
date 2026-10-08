from __future__ import annotations

import math

import numpy as np 

QUAT_IDENTITY = np.array([1.0 , 0.0, 0.0, 0.0])

def quat_normalize(q):
    pass 

def quat_mul(a, b):
    pass 

def quat_conj(q):
    pass 

def quat_inverse(q):
    pass 

def quat_from_axis_angle(axis, angle_rad):
    pass

def quat_from_euler():
    pass 

def quat_to_euler(q):
    pass

def quat_to_mat3(q):
    pass 

def mat3_to_quat(m):
    pass 

def quat_rotate(q, v):
    pass 

def quat_slerp(a, b, t):
    pass 

def mat4_identity():
    pass 

def mat4_translate(t):
    pass 

def mat4_scale(s):
    pass 

def mat4_from_quat(q):
    pass 

def mat4_trs(t, q, s):
    pass 

def mat4_decompose(m):
    pass 

def mat_inverse(m):
    pass 

def look_at(eye, target, up=(0.0, 1.0, 0.0)):
    pass 

def perspective():
    pass 

def ortho():
    pass 

def transform_points(m, p):
    pass 

def transform_dirs(m, d):
    pass 

def to_gl(m):
    pass 


class AABB: 
    def __init__(self, bmin=None, bmax=None):
        pass 

    @staticmethod 
    def from_points(p) -> "AABB":
        pass 

    @property 
    def empty(self) -> bool:
        pass 

    @property
    def center(self):
        pass 

    @property
    def half_extents(self):
        pass 

    @property
    def radius(self) -> float:
        pass 
 
    def union(self, other: "AABB") -> "AABB":
        pass 

    
    def transformed(self, m) -> "AABB":
        pass 

    
    def corners(self):
        pass 

    
    def copy(self) -> "AABB":
        pass 

    def __repr__(self):
        pass 