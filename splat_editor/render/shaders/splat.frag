#version 330 core
in vec4 vColor;
in vec2 vCorner;
out vec4 fragColor;

void main() {
    float r2 = dot(vCorner, vCorner);
    if (r2 > 9.0) discard;
    float alpha = vColor.a * exp(-0.5 * r2);
    if (alpha < 1.0 / 255.0) discard;
    fragColor = vec4(vColor.rgb * alpha, alpha);   // premultiplied alpha
}
