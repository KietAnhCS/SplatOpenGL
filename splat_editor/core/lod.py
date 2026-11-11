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