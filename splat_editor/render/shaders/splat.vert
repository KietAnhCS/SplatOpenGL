#version 330 core 

//vertext attribute 
layout(location = 0) int vec2 aCorner;
layout(location = 1) in uint aSplatIndex;

uniform sampleBuffer uData;
uniform mat4 uModelView;
uniform vec2 uViewport;
uniform float uFocal;
uniform int uShDegree;
uniform vec3 uCamPos;

out vec4 vColor;
out vec2 vCorner; 

vec3 shCoeff(int splat, int k) {
    return texelFetch(uSh, splat * uShCount + k).rgb;
}

// phần màu do SH bậc 1..3 đóng góp theo hướng nhìn d (cùng công thức với 3DGS gốc, xem core/sh.py)
vec3 shColor(int splat, vec3 d) {
    float x = d.x, y = d.y, z = d.z;
    vec3 c = -0.4886025119029199 * y * shCoeff(splat, 0)
           +  0.4886025119029199 * z * shCoeff(splat, 1)
           -  0.4886025119029199 * x * shCoeff(splat, 2);
    if (uShDegree < 2) return c;
    float xx = x * x, yy = y * y, zz = z * z;
    c +=  1.0925484305920792 * x * y * shCoeff(splat, 3)
       -  1.0925484305920792 * y * z * shCoeff(splat, 4)
       + 0.31539156525252005 * (2.0 * zz - xx - yy) * shCoeff(splat, 5)
       -  1.0925484305920792 * x * z * shCoeff(splat, 6)
       +  0.5462742152960396 * (xx - yy) * shCoeff(splat, 7);
    if (uShDegree < 3) return c;
    c += -0.5900435899266435 * y * (3.0 * xx - yy) * shCoeff(splat, 8)
       +   2.890611442640554 * x * y * z * shCoeff(splat, 9)
       -  0.4570457994644658 * y * (4.0 * zz - xx - yy) * shCoeff(splat, 10)
       +  0.3731763325901154 * z * (2.0 * zz - 3.0 * xx - 3.0 * yy) * shCoeff(splat, 11)
       -  0.4570457994644658 * x * (4.0 * zz - xx - yy) * shCoeff(splat, 12)
       +   1.445305721320277 * z * (xx - yy) * shCoeff(splat, 13)
       -  0.5900435899266435 * x * (xx - 3.0 * yy) * shCoeff(splat, 14);
    return c;
}

void main() {
    
}