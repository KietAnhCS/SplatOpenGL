from __future__ import annotations

import numpy as np

from ..core.splat import SH_C0, ColorAdjust, SplatData

LUMA = (0.299, 0.587, 0.114)

GLSL_COLOR_GRADE = """
// ---- colour grade (splatpy.data.color_grade) ----
uniform vec4 uGradeRow0;   // (m[0][0..2], offset.r)
uniform vec4 uGradeRow1;   // (m[1][0..2], offset.g)
uniform vec4 uGradeRow2;   // (m[2][0..2], offset.b)
uniform float uGradeAlpha; // transparency multiplier

vec4 applyColorGrade(vec4 rgba) {
    vec3 c = rgba.rgb;
    vec3 g = vec3(dot(uGradeRow0.xyz, c), dot(uGradeRow1.xyz, c), dot(uGradeRow2.xyz, c))
           + vec3(uGradeRow0.w, uGradeRow1.w, uGradeRow2.w);
    return vec4(g, clamp(rgba.a * uGradeAlpha, 0.0, 1.0));
}
"""


def grade_terms(adj: ColorAdjust) -> tuple[np.ndarray, np.ndarray, float]:


def grade_uniforms(adj: ColorAdjust) -> dict:


def apply_grade(rgb: np.ndarray, alpha: np.ndarray, adj: ColorAdjust):


def apply_grade_to_data(data: SplatData, adj: ColorAdjust) -> SplatData:
