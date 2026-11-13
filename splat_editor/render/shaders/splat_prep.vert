#version 330 core
// Pass 1 (transform feedback, không vẽ gì): mỗi gaussian chạy đúng MỘT lần, tính sẵn
// tâm + 2 trục ellipse trên màn hình và màu (kể cả SH). Pass 2 (splat.vert) chỉ còn kéo
// hình vuông theo kết quả này -> bớt 4 lần việc so với tính ở từng đỉnh của hình vuông.
layout(location = 0) in uint aSplatIndex;   // vị trí gaussian trên GPU (thứ tự Morton, tăng dần)

uniform usamplerBuffer uData;  // 2 texel RGBA32UI / gaussian (xem SplatRenderer.pack)
uniform usamplerBuffer uState; // 1 texel / gaussian: bit 1 = đang chọn, bit 2 = đã xoá (SplatRenderer.STATE_*)
uniform samplerBuffer uSh;     // uShCount texel RGBA8 / gaussian: hệ số SH bậc cao (rgb, lượng tử 8 bit)
uniform mat4 uModelView;
uniform mat4 uProjection;
uniform vec2 uViewport;        // kích thước khung hình (pixel)
uniform float uFocal;          // tiêu cự (pixel)
uniform vec3 uSelectColor;     // màu pha cho gaussian đang chọn
uniform int uShDegree;         // 0..3, 0 = màu không đổi theo hướng nhìn
uniform int uShCount;          // số hệ số SH bậc cao mỗi gaussian trên GPU (0, 3, 8, 15)
uniform float uShScale;        // hệ số giải lượng tử SH
uniform vec3 uCamPos;          // vị trí camera (toạ độ thế giới)
uniform samplerBuffer uLayers; // 4 texel (4 cột) / lớp: ma trận thế giới của lớp (s * R | t)

// ---- ánh sáng (T4): ambient + mặt trời + đèn điểm, Phong, bóng đổ bằng shadow map ----
uniform int uLightingOn;
uniform vec3 uAmbient;
uniform int uSunOn;
uniform vec3 uSunDir;          // từ cảnh hướng về mặt trời
uniform vec3 uSunColor;
uniform float uSpecular;
uniform float uShininess;
uniform int uPointCount;
uniform vec3 uPointPos[8];
uniform vec3 uPointColor[8];   // màu * cường độ
uniform float uPointRange[8];
uniform int uShadowOn;
uniform sampler2D uShadowMap;  // độ sâu nhìn từ mặt trời
uniform mat4 uLightVP;
uniform float uShadowTexel;    // cạnh một texel bản đồ bóng (đơn vị thế giới)
uniform float uShadowBias;     // độ lệch độ sâu (đơn vị NDC 0..1)
uniform float uShadowInv;      // 1 / kích thước bản đồ bóng

out vec4 vCenterMajor;        // tâm (NDC) xy, trục lớn (NDC) xy
out vec3 vMinorExtent;         // trục nhỏ (NDC) xy, bán kính hình vuông (đơn vị sigma)
flat out uint vColor;          // màu RGBA8 đóng gói

// half float (16 bit) -> float; GLSL 3.30 chưa có unpackHalf2x16
float halfToFloat(uint h) {
    uint e = (h >> 10u) & 31u;
    uint m = h & 1023u;
    float v = (e == 0u) ? float(m) * exp2(-24.0) : float(m | 1024u) * exp2(float(e) - 25.0);
    return (h & 32768u) != 0u ? -v : v;
}
vec2 unpackHalf(uint v) { return vec2(halfToFloat(v & 65535u), halfToFloat(v >> 16u)); }

uint packColor(vec4 c) {
    uvec4 u = uvec4(clamp(c, 0.0, 1.0) * 255.0 + 0.5);
    return u.r | (u.g << 8u) | (u.b << 16u) | (u.a << 24u);
}

vec3 shCoeff(int splat, int k) {
    return (texelFetch(uSh, splat * uShCount + k).rgb * 255.0 - 128.0) * uShScale;
}

// phần màu do SH bậc 1..3 đóng góp theo hướng nhìn d (cùng công thức với 3DGS gốc, xem core/sh.py)
vec3 shColor(int splat, vec3 d) {
    float x = d.x, y = d.y, z = d.z;
    vec3 c = -0.4886025119029199 * y * shCoeff(splat, 0)
           +  0.4886025119029199 * z * shCoeff(splat, 1)
           -  0.4886025119029199 * x * shCoeff(splat, 2);
    if (uShDegree < 2) return c;
    float xx = x * x, yy = y * y, zz = z * z;
    c +=  1.0925484305920792 * x * y * shCoeff(splat, 3)
       -  1.0925484305920792 * y * z * shCoeff(splat, 4)
       + 0.31539156525252005 * (2.0 * zz - xx - yy) * shCoeff(splat, 5)
       -  1.0925484305920792 * x * z * shCoeff(splat, 6)
       +  0.5462742152960396 * (xx - yy) * shCoeff(splat, 7);
    if (uShDegree < 3) return c;
    c += -0.5900435899266435 * y * (3.0 * xx - yy) * shCoeff(splat, 8)
       +   2.890611442640554 * x * y * z * shCoeff(splat, 9)
       -  0.4570457994644658 * y * (4.0 * zz - xx - yy) * shCoeff(splat, 10)
       +  0.3731763325901154 * z * (2.0 * zz - 3.0 * xx - 3.0 * yy) * shCoeff(splat, 11)
       -  0.4570457994644658 * x * (4.0 * zz - xx - yy) * shCoeff(splat, 12)
       +   1.445305721320277 * z * (xx - yy) * shCoeff(splat, 13)
       -  0.5900435899266435 * x * (xx - 3.0 * yy) * shCoeff(splat, 14);
    return c;
}

// 1 = sáng, 0 = trong bóng. Dịch điểm dọc pháp tuyến vài texel + bias để gaussian không tự đổ bóng lên mình.
float shadowFactor(vec3 worldPos, vec3 n) {
    vec4 lp = uLightVP * vec4(worldPos + n * uShadowTexel * 2.0, 1.0);
    vec3 s = lp.xyz / lp.w * 0.5 + 0.5;
    if (s.x < 0.0 || s.x > 1.0 || s.y < 0.0 || s.y > 1.0 || s.z > 1.0) return 1.0;
    float lit = 0.0;
    for (int i = -1; i <= 1; i++)
        for (int j = -1; j <= 1; j++) {
            float d = textureLod(uShadowMap, s.xy + vec2(i, j) * uShadowInv, 0.0).r;
            lit += (s.z - uShadowBias <= d) ? 1.0 : 0.0;
        }
    return lit / 9.0;
}

// Phong: màu * (ambient + sum diffuse) + specular. Pháp tuyến gaussian = trục ngắn nhất của ellipsoid (mặt phẳng
// mỏng ~ mảnh bề mặt), quay về phía camera. "Wrap" diffuse làm mềm vì pháp tuyến ước lượng khá nhiễu.
vec3 shade(vec3 albedo, vec3 worldPos, vec3 n, vec3 v) {
    vec3 diffuse = uAmbient;
    vec3 spec = vec3(0.0);
    if (uSunOn != 0) {
        float ndl = dot(n, uSunDir);
        float shadow = (uShadowOn != 0 && ndl > -0.4) ? shadowFactor(worldPos, n) : 1.0;
        diffuse += uSunColor * clamp((ndl + 0.35) / 1.35, 0.0, 1.0) * shadow;
        if (ndl > 0.0) spec += uSunColor * pow(max(dot(reflect(-uSunDir, n), v), 0.0), uShininess) * shadow;
    }
    for (int i = 0; i < uPointCount; i++) {
        vec3 d = uPointPos[i] - worldPos;
        float dist = length(d);
        vec3 l = d / max(dist, 1e-6);
        float att = clamp(1.0 - (dist * dist) / (uPointRange[i] * uPointRange[i]), 0.0, 1.0);
        att *= att;
        float ndl = dot(n, l);
        diffuse += uPointColor[i] * clamp((ndl + 0.35) / 1.35, 0.0, 1.0) * att;
        if (ndl > 0.0) spec += uPointColor[i] * pow(max(dot(reflect(-l, n), v), 0.0), uShininess) * att;
    }
    return albedo * diffuse + spec * uSpecular;
}

// Quaternion (w, x, y, z) -> ma trận xoay 3x3 R (GLSL điền mat3 theo từng cột)
mat3 quatToMat3(vec4 q) {
    float w = q.x, x = q.y, y = q.z, z = q.w;
    return mat3(1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + w * z), 2.0 * (x * z - w * y),
                2.0 * (x * y - w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + w * x),
                2.0 * (x * z + w * y), 2.0 * (y * z - w * x), 1.0 - 2.0 * (x * x + y * y));
}

// Hiệp phương sai 3D của gaussian: Sigma = R S S^T R^T (S = ma trận đường chéo chứa scale)
mat3 covariance3D(mat3 R, vec3 scale) {
    mat3 M = R * mat3(scale.x, 0.0, 0.0, 0.0, scale.y, 0.0, 0.0, 0.0, scale.z);
    return M * transpose(M);
}

// Chiếu Sigma 3D xuống màn hình thành ellipse 2D (cov 2x2 nằm ở góc trên trái của mat3 kết quả).
// viewPos: tâm gaussian trong không gian camera; linear: phần xoay/tỉ lệ của ma trận lớp.
mat3 projectCovariance(mat3 sigma, vec3 viewPos, mat3 linear) {
    // Jacobian J của phép chiếu phối cảnh tại tâm gaussian (xấp xỉ tuyến tính, GLSL: mat3 theo cột)
    float vx = viewPos.x, vy = viewPos.y, vz = viewPos.z;
    mat3 J = mat3(uFocal / -vz, 0.0, 0.0,
                  0.0, uFocal / -vz, 0.0,
                  uFocal * vx / (vz * vz), uFocal * vy / (vz * vz), 0.0);
    mat3 T = J * mat3(uModelView) * linear;        // Sigma (toạ độ file) -> thế giới -> camera -> màn hình
    return T * sigma * transpose(T);
}

void cull() {
    vCenterMajor = vec4(2.0, 2.0, 0.0, 0.0);   // hình vuông suy biến ngoài màn hình -> không tô pixel nào
    vMinorExtent = vec3(0.0);
    vColor = 0u;
}

void main() {
    int splat = int(aSplatIndex);
    uint state = texelFetch(uState, splat).r;
    // đã xoá: luồng sắp xếp đã bỏ, nhưng kết quả sắp xếp có thể đến trễ vài khung hình
    if ((state & 2u) != 0u) { cull(); return; }   // bit 2 = đã xoá
    uvec4 t0 = texelFetch(uData, splat * 2 + 0);   // tâm xyz (float), màu rg (half)
    uvec4 t1 = texelFetch(uData, splat * 2 + 1);   // màu b + alpha, scale xyz (half), quaternion (4 x snorm8)

    // dữ liệu ở toạ độ file của lớp; ma trận lớp đưa sang toạ độ thế giới (đổi được tức thì)
    int layer = int(t1.z >> 16u) * 4;
    mat4 model = mat4(texelFetch(uLayers, layer), texelFetch(uLayers, layer + 1),
                      texelFetch(uLayers, layer + 2), texelFetch(uLayers, layer + 3));
    mat3 linear = mat3(model);                     // s * R
    vec3 center = (model * vec4(uintBitsToFloat(t0.xyz), 1.0)).xyz;
    vec2 rg = unpackHalf(t0.w);
    vec2 ba = unpackHalf(t1.x);
    float alpha = ba.y;
    // hình vuông chỉ cần phủ tới chỗ alpha * exp(-r^2/2) = 1/255 (tối đa 3 sigma):
    // gaussian mờ -> hình vuông nhỏ hơn -> ít pixel phải tô
    if (alpha < 1.0 / 255.0) { cull(); return; }
    float extent = min(sqrt(2.0 * log(255.0 * alpha)), 3.0);

    vec4 viewPos = uModelView * vec4(center, 1.0);
    vec4 clipPos = uProjection * viewPos;
    vec3 ndc = clipPos.xyz / clipPos.w;
    // loại gaussian ở sau camera hoặc ngoài màn hình
    if (clipPos.w <= 0.0 || abs(ndc.x) > 1.3 || abs(ndc.y) > 1.3) { cull(); return; }

    // Giải nén scale (3 half float) và quaternion (4 byte, mỗi byte là snorm8) rồi dựng Sigma 3D
    vec3 scale = vec3(unpackHalf(t1.y), halfToFloat(t1.z & 65535u));
    vec4 q = normalize((vec4(uvec4(t1.w, t1.w >> 8u, t1.w >> 16u, t1.w >> 24u) & 255u) - 128.0) / 127.0);
    mat3 R = quatToMat3(q);
    mat3 sigma = covariance3D(R, scale);

    // Chiếu xuống màn hình -> ellipse 2D
    mat3 cov = projectCovariance(sigma, viewPos.xyz, linear);

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

    // nửa cạnh hình vuông = extent độ lệch chuẩn, tối đa 1024 pixel; đổi pixel -> NDC
    vec2 toNdc = 2.0 / uViewport;
    vec2 major = min(extent * sqrt(lambda1), 1024.0) * axis1 * toNdc;
    vec2 minor = min(extent * sqrt(lambda2), 1024.0) * axis2 * toNdc;

    vec3 color = vec3(rg, ba.x);
    // hệ số SH ở toạ độ file: xoay hướng nhìn ngược về toạ độ file (R^T d) thay vì xoay hệ số
    if (uShDegree > 0) color += shColor(splat, normalize(transpose(linear) * (center - uCamPos)));
    color = clamp(color, 0.0, 1.0);
    if (uLightingOn != 0) {
        vec3 sAbs = abs(scale);
        int axis = (sAbs.x <= sAbs.y && sAbs.x <= sAbs.z) ? 0 : ((sAbs.y <= sAbs.z) ? 1 : 2);
        vec3 n = normalize(linear * R[axis]);
        vec3 toCam = normalize(uCamPos - center);
        if (dot(n, toCam) < 0.0) n = -n;
        // gaussian tròn (không có mặt phẳng rõ ràng): pháp tuyến không xác định -> hướng lên
        float roundness = smoothstep(0.35, 0.9, min(sAbs.x, min(sAbs.y, sAbs.z)) / max(max(sAbs.x, max(sAbs.y, sAbs.z)), 1e-9));
        n = normalize(mix(n, vec3(0.0, 1.0, 0.0), roundness));
        color = clamp(shade(color, center, n, toCam), 0.0, 1.0);
    }
    float selected = float(state & 1u);

    vCenterMajor = vec4(ndc.xy, major);
    vMinorExtent = vec3(minor, extent);
    vColor = packColor(vec4(mix(color, uSelectColor, 0.7 * selected), alpha));
}
