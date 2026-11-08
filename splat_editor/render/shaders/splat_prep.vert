#version 330 core
// Pass 1 (transform feedback, không vẽ gì): mỗi gaussian chạy đúng MỘT lần, tính sẵn
// tâm + 2 trục ellipse trên màn hình và màu (kể cả SH). Pass 2 (splat.vert) chỉ còn kéo
// hình vuông theo kết quả này -> bớt 4 lần việc so với tính ở từng đỉnh của hình vuông.
layout(location = 0) in uint aSplatIndex;   // vị trí gaussian trên GPU (thứ tự Morton, tăng dần)

uniform usamplerBuffer uData;
uniform usamplerBuffer uState;
uniform samplerBuffer uSh;
uniform mat4 uModelView;
uniform vec2 uViewport;
uniform float uFocal;
uniform vec3 uSelectColor;
uniform int uShDegree;
uniform int uShCount;
uniform float uShScale;
uniform vec3 uCamPos;
uniform sampleBuffer uLayers;

out vec4 vCenterMajor;
out vec3 vMinorExtent;
flat out uint vColor;

float halfToFloat(uint h) {

}

void main() {
    int splat = int(aSplatIndex);
    uint state = texelFetch(uState, splat).r;

    // Sigma = R S S^T R^T từ scale + quaternion (w, x, y, z)

    // Jacobian của phép chiếu phối cảnh tại tâm gaussian (GLSL: mat3 theo cột)

    // trị riêng / vector riêng của ma trận 2x2 [[a b] [b c]]

    // hệ số SH ở toạ độ file: xoay hướng nhìn ngược về toạ độ file (R^T d) thay vì xoay hệ số
}