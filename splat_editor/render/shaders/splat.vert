#version 330 core
layout(location = 0) in vec2 aCorner;       // góc hình vuông: (-1,-1) .. (1,1)
layout(location = 1) in uint aSplatIndex;   // chỉ số gaussian (đã sắp xếp xa -> gần)

uniform samplerBuffer uData;   // 4 texel / gaussian
uniform samplerBuffer uSelect; // 1 texel / gaussian: 1 = đang chọn
uniform mat4 uModelView;
uniform mat4 uProjection;
uniform vec2 uViewport;        // kích thước khung hình (pixel)
uniform float uFocal;          // tiêu cự (pixel)
uniform vec3 uSelectColor;     // màu pha cho gaussian đang chọn

out vec4 vColor;
out vec2 vCorner;

void main() {
    int base = int(aSplatIndex) * 4;
    vec4 t0 = texelFetch(uData, base + 0);   // tâm xyz, alpha
    vec4 t1 = texelFetch(uData, base + 1);   // màu rgb
    vec4 t2 = texelFetch(uData, base + 2);   // Sigma00 Sigma01 Sigma02
    vec4 t3 = texelFetch(uData, base + 3);   // Sigma11 Sigma12 Sigma22

    vec4 viewPos = uModelView * vec4(t0.xyz, 1.0);
    vec4 clipPos = uProjection * viewPos;
    vec3 ndc = clipPos.xyz / clipPos.w;
    // loại gaussian ở sau camera hoặc ngoài màn hình
    if (clipPos.w <= 0.0 || abs(ndc.x) > 1.3 || abs(ndc.y) > 1.3) {
        gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
        return;
    }

    // ma trận hiệp phương sai 3D (đối xứng)
    mat3 sigma = mat3(t2.x, t2.y, t2.z,
                      t2.y, t3.x, t3.y,
                      t2.z, t3.y, t3.z);

    // Jacobian của phép chiếu phối cảnh tại tâm gaussian (GLSL: mat3 theo cột)
    float x = viewPos.x, y = viewPos.y, z = viewPos.z;
    mat3 J = mat3(uFocal / -z, 0.0, 0.0,
                  0.0, uFocal / -z, 0.0,
                  uFocal * x / (z * z), uFocal * y / (z * z), 0.0);
    mat3 W = mat3(uModelView);
    mat3 T = J * W;
    mat3 cov = T * sigma * transpose(T);

    // ellipse 2D (pixel); cộng 0.3 để gaussian không nhỏ hơn 1 pixel
    float a = cov[0][0] + 0.3;
    float b = cov[0][1];
    float c = cov[1][1] + 0.3;

    // trị riêng / vector riêng của ma trận 2x2 [[a b] [b c]]
    float mid = 0.5 * (a + c);
    float radius = length(vec2(0.5 * (a - c), b));
    float lambda1 = mid + radius;
    float lambda2 = max(mid - radius, 0.1);
    vec2 axis1 = (abs(b) < 1e-6) ? (a >= c ? vec2(1.0, 0.0) : vec2(0.0, 1.0))
                                 : normalize(vec2(b, lambda1 - a));
    vec2 axis2 = vec2(-axis1.y, axis1.x);

    // hình vuông phủ 3 độ lệch chuẩn (3 sigma), tối đa 1024 pixel
    vec2 major = min(3.0 * sqrt(lambda1), 1024.0) * axis1;
    vec2 minor = min(3.0 * sqrt(lambda2), 1024.0) * axis2;
    vec2 offsetPixels = aCorner.x * major + aCorner.y * minor;

    gl_Position = vec4(ndc.xy + offsetPixels * 2.0 / uViewport, 0.0, 1.0);
    float selected = texelFetch(uSelect, int(aSplatIndex)).r;
    vColor = vec4(mix(t1.rgb, uSelectColor, 0.7 * selected), t0.w);
    vCorner = aCorner * 3.0;   // toạ độ tính theo đơn vị sigma
}
