#version 330 core
// Pass 2: kéo hình vuông theo kết quả đã tính sẵn ở pass 1 (splat_prep.vert).
layout(location = 0) in vec2 aCorner;   // góc hình vuông: (-1,-1) .. (1,1)
layout(location = 1) in uint aRank;     // chỉ số vào kết quả pass 1 (instance xếp xa -> gần)

uniform usamplerBuffer uPrep;           // 2 texel / gaussian: kết quả pass 1 (đọc dạng uint vì màu là uint)

out vec4 vColor;
out vec2 vCorner;

void main() {
    int base = int(aRank) * 2;
    vec4 centerMajor = uintBitsToFloat(texelFetch(uPrep, base));   // tâm (NDC) xy, trục lớn (NDC) xy
    uvec4 t1 = texelFetch(uPrep, base + 1);                         // trục nhỏ xy, bán kính (sigma), màu RGBA8
    vec3 minorExtent = uintBitsToFloat(t1.xyz);
    vec2 offset = aCorner.x * centerMajor.zw + aCorner.y * minorExtent.xy;
    gl_Position = vec4(centerMajor.xy + offset, 0.0, 1.0);
    vColor = vec4(uvec4(t1.w, t1.w >> 8u, t1.w >> 16u, t1.w >> 24u) & 255u) / 255.0;
    vCorner = aCorner * minorExtent.z;   // toạ độ tính theo đơn vị sigma
}
