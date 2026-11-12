#version 330 core
// Quả cầu phát sáng (mặt trời / khối đèn): hình vuông luôn quay về camera, fragment shader tô thành hình cầu + quầng sáng.
layout(location = 0) in vec2 aCorner;   // (-1,-1) .. (1,1)

uniform mat4 uView;
uniform mat4 uProj;
uniform vec3 uCenter;
uniform float uRadius;
uniform float uHalo;                    // hình vuông rộng gấp mấy lần bán kính cầu (quầng sáng)

out vec2 vPos;                          // đơn vị bán kính cầu

void main() {
    vec4 viewPos = uView * vec4(uCenter, 1.0);
    viewPos.xy += aCorner * uRadius * uHalo;
    vPos = aCorner * uHalo;
    gl_Position = uProj * viewPos;
}
