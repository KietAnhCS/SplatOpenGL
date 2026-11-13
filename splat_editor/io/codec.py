"""Chuyển đổi giữa các cột của file 3DGS PLY và Splats (đã giải mã để render)."""

"""
data = PlyFile.read("scene.ply")        # mảng numpy có cấu trúc (62 cột / gaussian)
splats = SplatCodec.decode(data)       # màu = 0.5 + C0*f_dc, alpha = sigmoid(opacity), scale = exp(scale)

# Ghi ngược: áp lại các thay đổi lên bản ghi gốc rồi lưu
out = SplatCodec.encode(data, splats, data.dtype)
PlyFile.write("out.ply", out)
"""

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..core import sh
from ..core.splats import Splats
from .ply import read_block

SH_C0 = 0.28209479177387814   # hệ số spherical harmonic bậc 0
CHUNK = 1 << 18               # số hàng giải mã mỗi lần (mỗi luồng)

CANONICAL_FIELDS = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity',
                    'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']


class SplatCodec:
    @classmethod
    def decode(cls, data, sh_dtype=np.float16):
        """Chuyển các cột của file 3DGS PLY thành Splats.

        File 3DGS chuẩn có: x y z, f_dc_0..2 (màu), f_rest_* (màu theo hướng nhìn, tuỳ chọn),
        opacity (logit), scale_0..2 (log), rot_0..3.
        Nếu chỉ là point cloud (x y z red green blue) thì tự tạo gaussian nhỏ hình cầu.

        Giải mã từng đoạn CHUNK hàng (dữ liệu có thể là memmap trên đĩa) để không tạo mảng tạm
        bằng cả file. Hệ số SH chỉ dùng để hiển thị nên lưu float16 (đỡ một nửa RAM); khi lưu file
        vẫn đọc lại từ dữ liệu gốc nên không mất độ chính xác.
        """
        names = data.dtype.names
        n = len(data)
        k = sh.column_count(names)
        out = Splats(np.empty((n, 3), np.float32), np.empty((n, 3), np.float32), np.empty(n, np.float32),
                     np.empty((n, 3), np.float32), np.empty((n, 4), np.float32), np.empty((n, k, 3), sh_dtype))

        def decode_rows(a):
            block, matrix = read_block(data, a, a + CHUNK)
            rows = slice(a, a + len(block))
            if k:
                out.sh_rest[rows] = sh.block_coeffs(block, matrix, k)
            columns = {name: matrix[:, i] for i, name in enumerate(names)} if matrix is not None else block
            for name, values in zip(Splats.ARRAYS[:5], cls._decode_block(columns, names, data.dtype)):
                getattr(out, name)[rows] = values

        # các đoạn ghi vào vùng riêng của mảng kết quả; numpy nhả GIL nên chạy song song được
        with ThreadPoolExecutor(min(max((os.cpu_count() or 2) - 1, 1), 6)) as pool:
            list(pool.map(decode_rows, range(0, n, CHUNK)))
        if 'scale_0' not in names:
            # point cloud: lấy khoảng cách trung bình giữa các điểm làm bán kính
            extent = np.maximum(out.positions.max(axis=0) - out.positions.min(axis=0), 1e-6) if n else np.ones(3)
            out.scales[:] = 0.5 * (np.prod(extent) / max(n, 1)) ** (1 / 3)
        return out

    @staticmethod
    def _decode_block(data, names, dtype):
        """(tâm, màu, alpha, scale, quaternion) của một đoạn hàng (scale = 1 nếu là point cloud)."""
        def col(name):
            """Lấy một cột của file PLY dưới dạng float32."""
            return data[name].astype(np.float32)

        n = len(data['x'])
        positions = np.stack([col('x'), col('y'), col('z')], axis=1)

        # --- màu (bậc 0) ---
        # Chưa cắt về 0..1 vì còn cộng phần SH bậc cao (shader sẽ cắt sau).
        if 'f_dc_0' in names:
            colors = 0.5 + SH_C0 * np.stack([col('f_dc_0'), col('f_dc_1'), col('f_dc_2')], axis=1)
        elif 'red' in names:
            colors = np.stack([col('red'), col('green'), col('blue')], axis=1)
            if dtype['red'].kind in 'ui':   # kiểu số nguyên (uchar 0..255) -> đổi về 0..1
                colors /= 255.0
        else:
            colors = np.full((n, 3), 0.7, np.float32)   # không có màu: tô xám nhạt

        # --- độ đục: file lưu dạng logit nên phải qua sigmoid để về 0..1 ---
        alphas = 1.0 / (1.0 + np.exp(-col('opacity'))) if 'opacity' in names else np.ones(n, np.float32)

        # --- kích thước: file lưu dạng log nên phải qua exp ---
        if 'scale_0' in names:
            scales = np.exp(np.stack([col('scale_0'), col('scale_1'), col('scale_2')], axis=1))
        else:
            scales = np.ones((n, 3), np.float32)

        # --- xoay (quaternion w, x, y, z): chuẩn hoá về độ dài 1 ---
        identity_quat = np.float32([1, 0, 0, 0])        # "không xoay"
        if 'rot_0' in names:
            q = np.stack([col('rot_0'), col('rot_1'), col('rot_2'), col('rot_3')], axis=1)
            length = np.linalg.norm(q, axis=1, keepdims=True)
            q = np.where(length > 0, q / np.maximum(length, 1e-12), identity_quat)
        else:
            q = np.tile(identity_quat, (n, 1))
        return positions, colors, alphas, scales, q

    @staticmethod
    def encode(source, splats, dtype):
        """Đổi dữ liệu PLY `source` sang kiểu 3DGS chuẩn `dtype`.

        Cột nào có sẵn trong file thì chép nguyên, cột thiếu thì tính từ `splats`
        (ví dụ point cloud chỉ có red/green/blue -> tính f_dc, opacity, scale, rot).
        """
        derived = {'x': splats.positions[:, 0], 'y': splats.positions[:, 1], 'z': splats.positions[:, 2]}
        for i in range(3):
            derived[f'f_dc_{i}'] = (splats.colors[:, i] - 0.5) / SH_C0
            derived[f'scale_{i}'] = np.log(np.maximum(splats.scales[:, i], 1e-12))
        a = np.clip(splats.alphas, 1e-6, 1 - 1e-6)
        derived['opacity'] = np.log(a / (1 - a))
        for i in range(4):
            derived[f'rot_{i}'] = splats.rotations[:, i]

        out = np.zeros(splats.count, dtype)
        for name in dtype.names:
            if name in source.dtype.names:
                out[name] = source[name]
            elif name in derived:
                out[name] = derived[name]
        return out
