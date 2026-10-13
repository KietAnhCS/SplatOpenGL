#version 330 core
out vec2 vNdc;
void main() {
    // tam giác lớn phủ kín màn hình, không cần vertex buffer
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2) * 2.0 - 1.0;
    vNdc = p;
    gl_Position = vec4(p, 0.0, 1.0);
}
