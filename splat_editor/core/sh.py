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

import math

import numpy as np

COEFFS_FOR_DEGREE = {0: 0, 1: 3, 2: 8, 3: 15}   # số hệ số bậc cao (không tính f_dc)

C1 = 0.4886025119029199
C2 = (1.0925484305920792, -1.0925484305920792, 0.31539156525252005, -1.0925484305920792,
      0.5462742152960396)
C3 = (-0.5900435899266435, 2.890611442640554, -0.4570457994644658, 0.3731763325901154,
      -0.4570457994644658, 1.445305721320277, -0.5900435899266435)


def degree_for_coeffs(k):
    """Số hệ số bậc cao -> bậc SH (None nếu không hợp lệ)."""
    for degree, count in COEFFS_FOR_DEGREE.items():
        if count == k:
            return degree
    return None


def basis(dirs, k=15):
    """(M,3) hướng đơn vị -> (M,k) giá trị K hàm cơ sở SH bậc cao đầu tiên."""
    x, y, z = dirs[:, 0], dirs[:, 1], dirs[:, 2]
    xx, yy, zz = x * x, y * y, z * z
    columns = [
        -C1 * y, C1 * z, -C1 * x,
        C2[0] * x * y, C2[1] * y * z, C2[2] * (2 * zz - xx - yy), C2[3] * x * z, C2[4] * (xx - yy),
        C3[0] * y * (3 * xx - yy), C3[1] * x * y * z, C3[2] * y * (4 * zz - xx - yy),
        C3[3] * z * (2 * zz - 3 * xx - 3 * yy), C3[4] * x * (4 * zz - xx - yy),
        C3[5] * z * (xx - yy), C3[6] * x * (xx - 3 * yy),
    ]
    return np.stack(columns[:k], axis=1)


def evaluate(sh_rest, dirs):
    """Phần màu do SH bậc cao đóng góp: (N,K,3) hệ số, (N,3) hướng -> (N,3)."""
    return np.einsum('nk,nkc->nc', basis(dirs, sh_rest.shape[1]), sh_rest)


def _sample_dirs(n=64):
    """n hướng phân bố đều trên mặt cầu (xoắn ốc Fibonacci)."""
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    r = np.sqrt(1 - z * z)
    phi = i * math.pi * (3 - math.sqrt(5))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


_DIRS = _sample_dirs()


def rotation_matrix(rot, k):
    """Ma trận D (k,k) để xoay hệ số SH theo phép xoay 3x3 `rot`: sh' = D @ sh."""
    rot = np.asarray(rot, float)
    # cần: basis(d) @ sh' = basis(rot^T d) @ sh với mọi d
    return np.linalg.lstsq(basis(_DIRS, k), basis(_DIRS @ rot, k), rcond=None)[0]


CHUNK = 1 << 20   # xử lý từng đoạn 1 triệu gaussian để mảng tạm nhỏ


def rotate(sh_rest, rot):
    """Xoay hệ số SH (N,K,3) theo phép xoay 3x3 `rot`. Trả về mảng mới cùng kiểu dữ liệu."""
    k = sh_rest.shape[1]
    if k == 0 or np.allclose(rot, np.identity(3), atol=1e-9):
        return sh_rest.copy()
    work = np.float64 if sh_rest.dtype == np.float64 else np.float32
    D = rotation_matrix(rot, k).astype(work)
    out = np.empty_like(sh_rest)
    for a in range(0, len(sh_rest), CHUNK):
        part = sh_rest[a:a + CHUNK].astype(work, copy=False)
        # nhân ma trận 2D (BLAS) nhanh hơn einsum nhiều lần với hàng triệu gaussian
        flat = part.transpose(0, 2, 1).reshape(-1, k) @ D.T          # (n*3, K)
        out[a:a + CHUNK] = flat.reshape(-1, 3, k).transpose(0, 2, 1)
    return out


def column_count(names):
    """Số hệ số SH bậc cao K đọc được từ các cột f_rest_* (0 nếu không có / không hợp lệ)."""
    count = sum(1 for n in names if n.startswith('f_rest_'))
    k = count // 3
    if k == 0 or count % 3 or degree_for_coeffs(k) is None or any(f'f_rest_{i}' not in names for i in range(count)):
        return 0
    return k


def from_columns(data, names, dtype=np.float32):
    """Lấy hệ số SH bậc cao (N,K,3) từ các cột f_rest_* của PLY (K = 0 nếu không có / không hợp lệ).
    Đọc từng đoạn hàng (dữ liệu có thể là memmap trên đĩa) để không tạo mảng tạm khổng lồ."""
    from ..io.ply import read_block
    k = column_count(names)
    out = np.empty((len(data), k, 3), dtype)
    if k:
        for a in range(0, len(data), CHUNK):
            block, matrix = read_block(data, a, a + CHUNK)
            out[a:a + len(block)] = block_coeffs(block, matrix, k)
    return out


def block_coeffs(block, matrix, k):
    """(n,K,3) hệ số SH của một khối hàng PLY (matrix: khối dạng ma trận float32, hoặc None)."""
    if matrix is not None:
        columns = [block.dtype.names.index(f'f_rest_{i}') for i in range(3 * k)]
        first = columns[0]
        # file 3DGS chuẩn: f_rest_* là các cột liền nhau -> cắt slice (view), không gather
        flat = (matrix[:, first:first + 3 * k] if columns == list(range(first, first + 3 * k))
                else np.ascontiguousarray(matrix[:, columns]))
    else:
        flat = np.stack([block[f'f_rest_{i}'] for i in range(3 * k)], axis=1)
    return flat.reshape(len(block), 3, k).transpose(0, 2, 1)


def to_columns(sh_rest, out):
    """Ghi hệ số SH (N,K,3) vào các cột f_rest_* của mảng PLY `out`."""
    k = sh_rest.shape[1]
    for c in range(3):
        for i in range(k):
            out[f'f_rest_{c * k + i}'] = sh_rest[:, i, c]
