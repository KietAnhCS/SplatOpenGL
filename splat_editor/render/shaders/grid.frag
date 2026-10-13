#version 330 core
in vec2 vNdc;
out vec4 fragColor;

uniform mat3 uCamRot;      // cột = trục right / up / back của camera trong toạ độ thế giới
uniform vec3 uCamPos;
uniform vec2 uProjScale;   // projection[0][0], projection[1][1]
uniform float uHeight;     // độ cao mặt sàn (y)
uniform float uCell;       // kích thước ô nhỏ
uniform float uBlend;      // 0..1: mức chuyển sang ô lớn hơn
uniform float uFade;       // khoảng cách bắt đầu mờ dần

float gridLine(vec2 p, float cell) {
    vec2 c = p / cell;
    vec2 w = fwidth(c);
    vec2 g = abs(fract(c - 0.5) - 0.5) / w;
    return 1.0 - min(min(g.x, g.y), 1.0);
}

void main() {
    vec3 dir = uCamRot * vec3(vNdc.x / uProjScale.x, vNdc.y / uProjScale.y, -1.0);
    if (abs(dir.y) < 1e-6) discard;
    float t = (uHeight - uCamPos.y) / dir.y;
    if (t <= 0.0) discard;                       // mặt sàn ở sau camera
    vec3 p = uCamPos + t * dir;

    float minor = gridLine(p.xz, uCell) * (1.0 - uBlend);
    float major = gridLine(p.xz, uCell * 10.0);
    float alpha = max(minor * 0.35, major * 0.7);
    vec3 color = vec3(0.55);

    // trục toạ độ
    float ax = 1.0 - min(abs(p.z) / fwidth(p.z), 1.0);   // trục X (z = 0)
    float az = 1.0 - min(abs(p.x) / fwidth(p.x), 1.0);   // trục Z (x = 0)
    if (ax > 0.0) { color = mix(color, vec3(0.9, 0.25, 0.25), ax); alpha = max(alpha, ax); }
    if (az > 0.0) { color = mix(color, vec3(0.25, 0.45, 0.95), az); alpha = max(alpha, az); }

    // mờ dần theo khoảng cách và khi nhìn gần song song mặt sàn
    float dist = length(p.xz - uCamPos.xz);
    alpha *= 1.0 - smoothstep(uFade, uFade * 3.0, dist);
    alpha *= smoothstep(0.0, 0.15, abs(normalize(dir).y));
    if (alpha < 0.004) discard;
    fragColor = vec4(color * alpha, alpha);      // premultiplied alpha
}
