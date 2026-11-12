#version 330 core
in vec3 vNormal;
in vec2 vUV;
uniform sampler2D skin;
uniform vec3 uLight;
uniform vec3 uBright;
out vec4 fragColor;
void main() {
    vec4 texel = texture(uSkin, vUV);
    if (texel.a < 0.5) discard;
    float diffuse = max(dot(normalize(vNormal), normalize(uLight)), 0.0);
    vec3 shade = uBright * (0.62 + 0.38 * diffuse);
    fragColor = vec4(texel.rgb * shade, 1.0);
}