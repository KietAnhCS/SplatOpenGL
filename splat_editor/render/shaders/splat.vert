#version 330 core 
// Pass 2: kéo hình vuông theo kết quả đã tính sẵn ở pass 1 (splat_prep.vert).

layout(location = 0) in vec2 aCorner;
layout(location = 1) in uint aRank;

out vec4 vColor;
out vec2 vCorner;

void main() {
    int base = int (aRank)*2;
    vec4 centerMajor = uintBitsToFloat(texelFetch(uPrep, base));
    uvec4 t1 = texelFetch(uPrep, base + 1);
    vec3 minorExtent = uintBitsToFloat(t1.xyz);
    vec2 offset = aCorner.x * centerMajor.zw + aCorner.y * minorExtent.xy;
    gl_Position = vec4(centerMajor.xy + offset, 0.0, 1.0);
    vColor = vec4(uvec4(t1.w, t1.w >> 8u, t1.w >> 16u, t1.w >> 24u) & 255u) / 255.0;
    vCorner = aCorner * minorExtent.z; 
}