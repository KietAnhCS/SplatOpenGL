#version 330 core
in vec2 vPos;
out vec4 fragColor;

uniform vec3 uColor;
uniform float uHalo;
uniform float uBrightness;              // 0..1: mờ dần (ví dụ đèn tắt, mặt trời lặn)

void main() {
    float r = length(vPos);
    if (r <= 1.0) {
        float z = sqrt(1.0 - r * r);
        vec3 col = uColor * (0.7 + 0.5 * z);          // sáng nhất ở giữa
        fragColor = vec4(mix(vec3(0.12), col, uBrightness), 1.0);
    } else {
        float h = clamp(1.0 - (r - 1.0) / max(uHalo - 1.0, 1e-3), 0.0, 1.0);
        h = h * h * 0.65 * uBrightness;
        if (h < 0.004) discard;
        fragColor = vec4(uColor * h, 0.0);            // cộng thêm (premultiplied, alpha 0)
    }
}
