#version 330 core
// Bản đồ bóng: vẽ tâm mỗi gaussian đã được chọn thành một điểm (vài pixel) vào bản đồ độ sâu nhìn từ mặt trời.
layout(location = 0) in uint aSplatIndex;

uniform usamplerBuffer uData;
uniform usamplerBuffer uState;
uniform samplerBuffer uLayers;
uniform mat4 uLightVP;
uniform float uPointSize;

float halfToFloat(uint h) {
    uint e = (h >> 10u) & 31u;
    uint m = h & 1023u;
    float v = (e == 0u) ? float(m) * exp2(-24.0) : float(m | 1024u) * exp2(float(e) - 25.0);
    return (h & 32768u) != 0u ? -v : v;
}

void main() {
    int splat = int(aSplatIndex);
    uvec4 t0 = texelFetch(uData, splat * 2 + 0);
    uvec4 t1 = texelFetch(uData, splat * 2 + 1);
    float alpha = halfToFloat(t1.x >> 16u);
    // đã xoá hoặc quá mờ: không đổ bóng
    if ((texelFetch(uState, splat).r & 2u) != 0u || alpha < 0.3) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        gl_PointSize = 1.0;
        return;
    }
    int layer = int(t1.z >> 16u) * 4;
    mat4 model = mat4(texelFetch(uLayers, layer), texelFetch(uLayers, layer + 1),
                      texelFetch(uLayers, layer + 2), texelFetch(uLayers, layer + 3));
    gl_Position = uLightVP * (model * vec4(uintBitsToFloat(t0.xyz), 1.0));
    gl_PointSize = uPointSize;
}
