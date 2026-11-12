#version 330 core
in float vTwinkle;
out vec4 fragColor;
uniform vec3 uColor;

void main() {
    float d = length(gl_PointCoord - 0.5) * 2.0;
    float a = clamp(1.0 - d, 0.0, 1.0);
    a = a * a * vTwinkle;
    if (a < 0.01) discard;
    fragColor = vec4(uColor * a, 0.0);               // cộng thêm (premultiplied, alpha 0)
}
