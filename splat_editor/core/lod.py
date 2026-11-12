"""Mức chi tiết (LOD): chỉ vẽ tối đa `budget` gaussian mỗi khung hình, dù cảnh có hàng chục triệu.

Ý tưởng:
1. Chia gaussian thành các khối (chunk) nhỏ gần nhau trong không gian: sắp xếp theo mã Morton
   (đường cong Z) rồi cắt thành từng đoạn CHUNK_SIZE gaussian. Mỗi khối có hình cầu bao.
2. Trong mỗi khối, xếp gaussian theo độ "quan trọng" giảm dần (độ đục x diện tích), nên lấy
   k gaussian đầu của khối = k gaussian quan trọng nhất (cái to, đục giữ lại; cái nhỏ, mờ bỏ đi).
3. Mỗi lần camera đổi:
   - bỏ khối nằm ngoài khung nhìn (frustum culling theo hình cầu bao);
   - khối gần camera lấy nhiều gaussian, khối xa lấy ít: khối c lấy min(n_c, lambda * n_c / d_c),
     với d_c là khoảng cách tới camera và lambda tìm bằng chia đôi sao cho tổng = budget.
4. Renderer lưu gaussian trên GPU theo đúng thứ tự `order` ("vị trí"), nên gaussian gần nhau
   trong không gian cũng gần nhau trong bộ nhớ -> GPU đọc liền mạch, ít trượt cache.
5. Cọ chọn (editor/brush.py) dùng hộp bao các khối để chỉ kiểm tra gaussian gần nét cọ.
"""

"""
# positions (N,3), scales (N,3), alphas (N,) lấy từ Splats; ranges: mỗi lớp một đoạn (đầu, cuối)
lod = LodIndex(positions, scales, alphas, ranges=[(0, n1), (n1, n1 + n2)])

# Mỗi khi camera đổi: chọn tối đa 2 triệu gaussian cần vẽ
slots = lod.select(model_view, projection, budget=2_000_000, transforms=layer_matrices)
indices = lod.order[slots]              # chỉ số gaussian gốc của các vị trí được chọn

# Hàm tiện ích (đa luồng)
codes = morton_codes(positions)        # mã Morton: gaussian gần nhau -> mã gần nhau
perm = radix_argsort(codes)            # sắp xếp nhanh hơn np.argsort cho khoá số nguyên
"""

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

CHUNK_SIZE = 1024


_WORKERS = min(max((os.cpu_count() or 2) - 1, 1), 6)


def _parallel(fn, n, chunk=1 << 20):
    """Chạy fn(start, end) trên các đoạn [0, n) ở nhiều luồng (numpy nhả GIL)."""
    with ThreadPoolExecutor(_WORKERS) as pool:
        list(pool.map(lambda a: fn(a, min(a + chunk, n)), range(0, n, chunk)))


def gather(array, index):
    """array[index] theo trục 0, chia nhiều luồng: truy cập ngẫu nhiên bị nghẽn bởi độ trễ bộ
    nhớ nên nhiều luồng cùng đọc nhanh hơn ~3 lần."""
    out = np.empty((len(index),) + array.shape[1:], array.dtype)

    def part(a, b):
        out[a:b] = array[index[a:b]]
    _parallel(part, len(index))
    return out


def _spread_table():
    """Bảng tra: số 10 bit -> các bit đó cách nhau 2 bit 0 (để xen kẽ thành mã Morton 3D)."""
    v = np.arange(1024, dtype=np.uint32)
    out = np.zeros(1024, np.uint32)
    for bit in range(10):
        out |= ((v >> bit) & 1) << (3 * bit)
    return out


_SPREAD = _spread_table()


def morton_codes(positions):
    """(N,3) -> (N,) mã Morton 30 bit (10 bit / trục, đủ để chia khối). Dùng phân vị
    0.1%..99.9% làm hộp bao để điểm nhiễu ở xa không làm cả cảnh dồn vào vài ô."""
    sample = positions[::max(len(positions) // 200_000, 1)]
    lo = np.percentile(sample, 0.1, axis=0).astype(np.float32)
    hi = np.percentile(sample, 99.9, axis=0).astype(np.float32)
    scale = 1023.0 / np.maximum(hi - lo, 1e-9).astype(np.float32)
    code = np.zeros(len(positions), np.uint32)

    def part(a, b):
        for axis in range(3):
            q = np.clip((positions[a:b, axis] - lo[axis]) * scale[axis], 0, 1023).astype(np.uint16)
            code[a:b] |= _SPREAD[q] << np.uint32(axis)
    _parallel(part, len(positions))
    return code


def radix_argsort(key):
    """argsort ổn định cho khoá uint32: 2 lượt sắp theo 16 bit (numpy dùng radix sort cho
    số 16 bit, O(N), nhanh hơn nhiều so với argsort số 32 bit)."""
    order = np.argsort((key & 0xFFFF).astype(np.uint16), kind='stable')
    return order[np.argsort((key[order] >> 16).astype(np.uint16), kind='stable')]


def _build_group(positions, scales, alphas, chunk_size):
    """Chỉ mục cho một nhóm gaussian (một lớp): (order, positions, sizes, box_lo, box_hi, radii)."""
    n = len(positions)
    order = radix_argsort(morton_codes(positions)).astype(np.uint32)

    # trong mỗi khối (chunk_size gaussian liên tiếp theo Morton) xếp theo độ quan trọng giảm dần:
    # sắp ổn định theo độ quan trọng rồi theo số thứ tự khối (2 lượt radix sort 16 bit).
    # Khoá độ quan trọng = 16 bit cao của số float32 dương (giữ nguyên thứ tự, khỏi tính log);
    # tính theo thứ tự gốc (đọc tuần tự) rồi mới gather khoá 2 byte theo thứ tự Morton.
    chunks = -(-n // chunk_size)
    key = np.empty(n, np.uint16)
    max_scale = np.empty(n, np.float32)

    def part(a, b):
        s = scales[a:b]
        importance = alphas[a:b] * (s[:, 0] * s[:, 1] + s[:, 1] * s[:, 2] + s[:, 0] * s[:, 2])
        key[a:b] = np.uint16(65535) - (np.maximum(importance, 0).astype(np.float32).view(np.uint32) >> 16)
        max_scale[a:b] = s.max(axis=1)
    _parallel(part, n)
    within = np.argsort(gather(key, order), kind='stable')
    chunk_id = (within // chunk_size).astype(np.uint32)
    within = within[radix_argsort(chunk_id) if chunks > 65536 else
                    np.argsort(chunk_id.astype(np.uint16), kind='stable')]
    order = gather(order, within)            # theo khối, trong khối theo độ quan trọng
    sorted_positions = gather(positions, order)
    sizes = np.minimum(chunk_size, n - np.arange(chunks, dtype=np.int64) * chunk_size)

    # hộp bao các tâm của mỗi khối; đệm cho đủ số khối tròn bằng phần tử đầu khối cuối
    # (min / max không đổi), tính từng trục trên mảng liền mạch cho nhanh
    pad = chunks * chunk_size - n
    lo, hi = np.empty((chunks, 3)), np.empty((chunks, 3))
    for axis in range(3):
        v = sorted_positions[:, axis]
        v = np.concatenate([v, np.full(pad, v[n - sizes[-1]], v.dtype)]).reshape(chunks, chunk_size)
        lo[:, axis], hi[:, axis] = v.min(axis=1), v.max(axis=1)
    # hình cầu bao: cộng thêm bán kính gaussian lớn nhất trong khối (3 sigma) để không cắt nhầm
    max_scale = np.concatenate([gather(max_scale, order), np.zeros(pad, np.float32)])
    radii = 0.5 * np.linalg.norm(hi - lo, axis=1) + 3.0 * max_scale.reshape(chunks, chunk_size).max(axis=1)
    return order, sorted_positions, sizes, lo, hi, radii


class LodIndex:
    """Chỉ mục khối của N gaussian, chia theo nhóm `ranges` (mỗi lớp một nhóm, khối không bao giờ
    trộn hai lớp). Toạ độ là toạ độ riêng của từng nhóm (toạ độ file của lớp); phép biến đổi của
    nhóm (ma trận 4x4, đổi được bất cứ lúc nào) được áp khi chọn / chiếu, nên kéo, xoay, phóng to
    một lớp không phải dựng lại chỉ mục."""

    def __init__(self, positions, scales, alphas, chunk_size=CHUNK_SIZE, ranges=None):
        n = len(positions)
        self.count = n
        ranges = [(0, n)] if ranges is None else [(a, b) for a, b in ranges if b > a]
        parts = [_build_group(positions[a:b], scales[a:b], alphas[a:b], chunk_size) for a, b in ranges]
        self.group_count = len(ranges)
        self.order = np.concatenate([p[0] + np.uint32(a) for p, (a, _) in zip(parts, ranges)]) if parts             else np.zeros(0, np.uint32)
        self.positions = np.concatenate([p[1] for p in parts]) if parts else np.zeros((0, 3), np.float32)
        self.sizes = np.concatenate([p[2] for p in parts]) if parts else np.zeros(0, np.int64)
        self.starts = np.cumsum(self.sizes) - self.sizes
        self.box_lo = np.concatenate([p[3] for p in parts]) if parts else np.zeros((0, 3))
        self.box_hi = np.concatenate([p[4] for p in parts]) if parts else np.zeros((0, 3))
        self.centers = (self.box_lo + self.box_hi) * 0.5
        self.radii = np.concatenate([p[5] for p in parts]) if parts else np.zeros(0)
        self.chunk_group = np.repeat(np.arange(len(parts)), [len(p[2]) for p in parts])
        # vị trí (trong order) đầu / cuối của mỗi nhóm: nhóm g chiếm [group_slots[g], group_slots[g+1])
        self.group_slots = np.concatenate([[0], np.cumsum([b - a for a, b in ranges])]).astype(np.int64)

    def world_bounds(self, transforms=None):
        """(tâm, bán kính) hình cầu bao của các khối trong toạ độ thế giới.
        transforms: ma trận 4x4 (s * R | t) của từng nhóm; None: đơn vị."""
        if transforms is None:
            return self.centers, self.radii
        m = np.asarray(transforms, np.float64)[self.chunk_group]           # (C,4,4)
        centers = np.einsum('cij,cj->ci', m[:, :3, :3], self.centers) + m[:, :3, 3]
        return centers, self.radii * np.linalg.norm(m[:, :3, 0], axis=1)

    @staticmethod
    def _frustum_planes(view_proj):
        """6 mặt phẳng (a,b,c,d) của khung nhìn, pháp tuyến hướng vào trong, đã chuẩn hoá."""
        m = np.asarray(view_proj, np.float64)
        planes = np.array([m[3] + m[0], m[3] - m[0], m[3] + m[1], m[3] - m[1], m[3] + m[2], m[3] - m[2]])
        return planes / np.linalg.norm(planes[:, :3], axis=1, keepdims=True)

    def select(self, model_view, projection, budget, transforms=None):
        """Vị trí trong `self.order` (tăng dần) của các gaussian cần vẽ, chưa sắp theo độ sâu.
        Chỉ số gaussian gốc = self.order[kết quả]."""
        centers, radii = self.world_bounds(transforms)
        planes = self._frustum_planes(projection @ model_view)
        dist = centers @ planes[:, :3].T + planes[:, 3]               # (chunks, 6)
        visible = np.flatnonzero((dist[:, :5] > -radii[:, None]).all(axis=1))   # bỏ qua mặt xa
        if len(visible) == 0:
            return np.zeros(0, np.int64)
        sizes = self.sizes[visible]
        if budget is None or sizes.sum() <= budget:
            take = sizes
        else:
            mv = np.asarray(model_view, np.float64)
            depth = -(centers[visible] @ mv[2, :3] + mv[2, 3])
            # khối chứa camera (hoặc rất gần) luôn đủ chi tiết
            d = np.maximum(depth - radii[visible], 1e-3 * max(float(radii.max()), 1e-9))
            weight = sizes / d
            lo, hi = 0.0, float(d.max())
            for _ in range(40):                 # tìm lambda: sum(min(n_c, lambda * w_c)) = budget
                lam = 0.5 * (lo + hi)
                if np.minimum(sizes, np.ceil(lam * weight)).sum() > budget:
                    hi = lam
                else:
                    lo = lam
            take = np.minimum(sizes, np.ceil(lo * weight)).astype(np.int64)
            keep = take > 0
            visible, take = visible[keep], take[keep]

        # gom các đoạn [start_c, start_c + take_c) thành một mảng
        total = int(take.sum())
        ends = np.cumsum(take)
        offsets = np.repeat(self.starts[visible] - (ends - take), take)
        return np.arange(total, dtype=np.int64) + offsets
