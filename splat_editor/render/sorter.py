"""Sắp xếp gaussian theo độ sâu ở luồng nền, để vòng lặp vẽ không bị chặn khi xoay camera.

- Luồng chính gửi yêu cầu (ma trận model-view mới nhất), luồng nền tính độ sâu rồi sắp xếp.
  Trong lúc chờ, renderer vẫn vẽ bằng thứ tự cũ (sai lệch nhỏ, mắt gần như không thấy).
- Độ sâu được lượng tử hoá về uint16 để numpy dùng radix sort (O(N), nhanh hơn argsort
  float ~3 lần). numpy nhả GIL khi nhân ma trận / sắp xếp nên luồng nền chạy song song thật.
- Gaussian nằm sau camera bị bỏ khỏi danh sách -> GPU vẽ ít instance hơn.
"""

import threacing 

import numpy as np 

class DepthSorter:
    def __init__(self):
        pass

    def set_positions(self, positions):
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
    def sort():
        pass