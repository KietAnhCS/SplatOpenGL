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

STATE_DELETED = 2 

class DepthSorter:
    def __init__(self):
        self._cond = threading.Condition()
        self._positions = None 
        self._lod = None 
        self._state = None 
        self._version = 0 
        self._request = None 
        self._result = None 
        self._closed = False
        self._thread = thread.Thread(target=self._run, name="depth-sorter", daemon=True)
        self._thread.start()

    def set_splat(self, lod, state=None):
        pass 

    def request():
        pass 


    def take_result():
        pass 

    def close(self):
        pass

    def _run(self):
        pass 

    @staticmethod
    def _select():
        pass

    @staticmethod
    def _depth_rows():
        pass

    @staticmethod
    def sort():
        pass