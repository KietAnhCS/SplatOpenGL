#version 330 core
// Hạt (T5): đom đóm bay quanh khối đèn. Vị trí là hàm của thời gian và gl_VertexID, tính hoàn toàn trên GPU.
uniform mat4 uView;
uniform mat4 uProj;
uniform vec3 uCenter;
uniform float uRadius;
uniform float uTime;
uniform float uPixel;

out float vTwinkle;

void main() {
    float i = float(gl_VertexID);
    float phase = i * 2.399963;                       // góc vàng: các hạt phân bố đều
    vec3 offset = vec3(sin(uTime * (0.4 + 0.13 * sin(i * 1.7)) + phase),
                       sin(uTime * 0.7 + phase * 1.3) * 0.6 + 0.2,
                       cos(uTime * (0.35 + 0.11 * cos(i * 2.3)) + phase * 0.7));
    offset *= uRadius * (0.35 + 0.65 * fract(i * 0.618));
    gl_Position = uProj * uView * vec4(uCenter + offset, 1.0);
    gl_PointSize = uPixel;
    vTwinkle = 0.5 + 0.5 * sin(uTime * 2.0 + phase * 3.0);
}
