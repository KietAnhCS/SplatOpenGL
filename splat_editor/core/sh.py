"""Spherical harmonic (SH) bậc 1..3: màu thay đổi theo hướng nhìn.

Màu của một gaussian khi nhìn theo hướng d (vector đơn vị từ camera tới tâm gaussian):
    màu(d) = 0.5 + C0 * f_dc + sum_k Y_k(d) * sh_k
với Y_k là các hàm cơ sở SH thực bậc 1..3 (3 + 5 + 7 = 15 hàm), theo đúng quy ước dấu của
3DGS gốc (giống shader splat.vert). Hệ số bậc cao lưu ở mảng (N, K, 3): K hệ số, mỗi hệ số
một vector RGB. Trong file PLY chúng nằm ở f_rest_0..f_rest_{3K-1}, xếp theo kênh màu:
f_rest_{c*K + k} = hệ số k của kênh c.

Khi xoay gaussian bằng ma trận R thì hàm màu cũng phải xoay theo: màu'(d) = màu(R^T d).
Mỗi bậc SH là một không gian đóng với phép xoay, nên hệ số mới là sh' = D(R) sh với D là
ma trận K x K (khối chéo theo từng bậc). Ta tìm D bằng bình phương tối thiểu trên một tập
hướng cố định — chính xác (sai số làm tròn) và luôn khớp với hàm cơ sở ở dưới.
"""

"""
# sh_rest: (N, K, 3) hệ số SH bậc 1..3, K = 0, 3, 8 hoặc 15
rgb_offset = evaluate(sh_rest, dirs)    # dirs (N,3) hướng đơn vị camera -> gaussian; ra (N,3) phần cộng thêm vào màu

R = euler_to_matrix([0, 90, 0])         # (từ core.math3d)
sh_rotated = rotate(sh_rest, R)         # xoay hệ số khi xoay gaussian, màu theo hướng nhìn vẫn đúng

# Đọc / ghi cột f_rest_* của PLY
k = column_count(data.dtype.names)      # số hệ số bậc cao có trong file
sh_rest = from_columns(data, data.dtype.names)
to_columns(sh_rest, out)                # ghi ngược vào bản ghi PLY
"""