"""Chọn gaussian cần vẽ (LOD) và sắp xếp theo độ sâu ở luồng nền, để vòng lặp vẽ không bị chặn.

- Luồng chính gửi yêu cầu (ma trận model-view / projection mới nhất + ngân sách số gaussian),
  luồng nền chọn gaussian theo LOD (xem lod.py) rồi sắp xếp. Trong lúc chờ, renderer vẫn vẽ
  bằng thứ tự cũ (sai lệch nhỏ, mắt gần như không thấy).
- Mọi chỉ số ở đây là "vị trí" trên GPU (thứ tự LodIndex.order), không phải chỉ số trong file.
- Tâm gaussian ở toạ độ file của từng lớp; ma trận thế giới của mỗi lớp đi kèm yêu cầu.
- Kết quả gồm 2 mảng:
    slots: vị trí các gaussian được chọn, tăng dần -> pass 1 đọc bộ nhớ liền mạch;
    ranks: thứ tự vẽ xa -> gần, là chỉ số vào `slots` (bỏ gaussian sau camera).
- Gaussian đã xoá (bit STATE_DELETED trong mảng trạng thái của renderer) bị bỏ khỏi kết quả.
- Độ sâu được lượng tử hoá về uint16 để numpy dùng radix sort (O(N), nhanh hơn argsort
  float ~3 lần). numpy nhả GIL khi nhân ma trận / sắp xếp nên luồng nền chạy song song thật.
"""

"""
sorter = DepthSorter()                  # tạo luồng nền "depth-sorter"
sorter.set_splats(lod, state)          # khi đổi tập gaussian

# Mỗi khung hình
sorter.request(model_view, projection, budget, transforms)   # gửi yêu cầu, không chờ
result = sorter.take_result()          # (slots, ranks) nếu luồng nền đã xong, ngược lại None
if result is not None:
    slots, ranks = result              # cập nhật thứ tự vẽ lên GPU

sorter.close()                          # tắt luồng khi thoát
"""

import threading

import numpy as np

STATE_DELETED = 2       # = splat_renderer.STATE_DELETED


class DepthSorter:
    def __init__(self):
        self._cond = threading.Condition()
        self._positions = None     # tâm gaussian theo thứ tự vị trí
        self._lod = None
        self._state = None         # trạng thái theo vị trí (uint8), dùng chung với renderer
        self._version = 0          # tăng mỗi khi đổi tập gaussian, để bỏ kết quả cũ
        self._request = None       # (version, model_view, projection, budget, transforms) đang chờ
        self._result = None        # (version, slots, ranks) đã sắp xếp xong, chưa lấy
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="depth-sorter", daemon=True)
        self._thread.start()

    def set_splats(self, lod, state=None):
        """lod: LodIndex (tâm gaussian theo thứ tự vị trí: lod.positions).
        state: mảng trạng thái (uint8) theo vị trí, renderer sửa tại chỗ; None: không bỏ gì."""
        with self._cond:
            self._lod = lod
            self._state = state
            self._positions = lod.positions
            self._version += 1
            self._request = None
            self._result = None

    def request(self, model_view, projection, budget, transforms=None):
        """Yêu cầu chọn + sắp xếp. Yêu cầu chưa xử lý bị thay bằng yêu cầu mới nhất.
        budget: số gaussian tối đa (None: không giới hạn); transforms: ma trận thế giới mỗi lớp."""
        with self._cond:
            self._request = (self._version, model_view.copy(), projection.copy(), budget,
                             None if transforms is None else np.array(transforms, np.float64))
            self._cond.notify()

    def take_result(self):
        """(slots, ranks) nếu có kết quả mới, ngược lại None."""
        with self._cond:
            result, self._result = self._result, None
        if result is None or result[0] != self._version:
            return None
        return result[1:]

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify()

    def _run(self):
        while True:
            with self._cond:
                while self._request is None and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                (version, model_view, projection, budget, transforms), self._request = self._request, None
                positions, lod, state = self._positions, self._lod, self._state
            slots = self._select(lod, state, model_view, projection, budget, transforms)
            ranks = self.sort(positions[slots], self._depth_rows(model_view, transforms, lod, slots))
            with self._cond:
                if version == self._version:
                    self._result = (version, slots.astype(np.uint32), ranks)

    @staticmethod
    def _select(lod, state, model_view, projection, budget, transforms):
        """lod.select rồi bỏ gaussian đã xoá. Nếu bị giới hạn bởi budget mà bỏ đi nhiều, chọn lại
        với budget nới theo tỉ lệ còn lại để vẫn vẽ gần đủ budget gaussian."""
        slots = lod.select(model_view, projection, budget, transforms)
        if state is None:
            return slots
        kept = slots[(state[slots] & STATE_DELETED) == 0]
        if budget is not None and len(slots) >= budget and len(kept) < 0.9 * budget:
            wider = int(budget * len(slots) / max(len(kept), 1))
            slots = lod.select(model_view, projection, wider, transforms)
            kept = slots[(state[slots] & STATE_DELETED) == 0]
        return kept

    @staticmethod
    def _depth_rows(model_view, transforms, lod, slots):
        """Hàng z của ma trận model-view * thế giới cho từng đoạn `slots` (tăng dần) theo lớp:
        [(số phần tử, hàng (4,))]."""
        mv = np.asarray(model_view, np.float64)
        if transforms is None:
            return [(len(slots), mv[2])]
        bounds = np.searchsorted(slots, lod.group_slots)
        return [(int(bounds[g + 1] - bounds[g]), (mv @ transforms[g])[2]) for g in range(len(transforms))]

    @staticmethod
    def sort(positions, depth_rows):
        """Chỉ số các tâm nằm trước camera, xếp xa -> gần.
        depth_rows: ma trận model-view 4x4, hoặc [(số phần tử, hàng z)] cho từng đoạn liên tiếp."""
        if not isinstance(depth_rows, list):
            depth_rows = [(len(positions), np.asarray(depth_rows, np.float64)[2])]
        # trong không gian camera, camera nhìn theo -z nên z càng âm càng xa
        depth = np.empty(len(positions), np.float32)
        start = 0
        for count, row in depth_rows:
            row = row.astype(np.float32)
            depth[start:start + count] = positions[start:start + count] @ row[:3] + row[3]
            start += count
        visible = np.flatnonzero(depth < 0)
        depth = depth[visible]
        if len(depth) == 0:
            return np.zeros(0, np.uint32)
        lo, hi = float(depth.min()), float(depth.max())
        scale = 65535.0 / (hi - lo) if hi > lo else 0.0
        key = ((depth - lo) * scale).astype(np.uint16)
        return visible[np.argsort(key, kind='stable')].astype(np.uint32)
