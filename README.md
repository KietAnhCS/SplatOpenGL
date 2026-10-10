# Splat Editor

Chương trình xem / chỉnh sửa file **3D Gaussian Splatting (.ply)** viết bằng Python + OpenGL 3.3.

Chức năng:
- Mở file `.ply` (3DGS hoặc point cloud thường; định dạng ascii / binary)
- Hiển thị các gaussian lên màn hình, có lưới sàn (grid) và trục X (đỏ) / Z (xanh)
- **Nhiều file trong cùng một cảnh** (mỗi file là một lớp): ẩn / hiện / xoá lớp,
  chỉnh vị trí / góc xoay / tỉ lệ từng lớp
- **Cọ chọn** (phím B): tô lên màn hình để chọn gaussian thừa / nhiễu rồi bấm Delete để xoá (Ctrl+Z hoàn tác)
- **Lưu**: gộp các lớp đang hiện (đã áp biến đổi) thành một file `.ply` (binary)
- Di chuyển camera xung quanh (xoay, dịch, phóng to, bay bằng WASD)

## Cài đặt

```
pip install -r requirements.txt
```

Cần Python 3.10+ và card đồ hoạ hỗ trợ OpenGL 3.3.

## Chạy

```
python -m splat_editor.io.sample sample.ply   # tạo file mẫu (nếu chưa có file .ply nào)
python main.py sample.ply                     # mở file (hoặc: python -m splat_editor sample.ply)
python main.py                                # mở cửa sổ trống, bấm Ctrl+O để chọn file
```

Chạy test (cần `pip install pytest`):

```
python -m pytest
```

## Giao diện

```
+--------------------------------------------------+
| File  Edit  View  Help                (menu)     |
+-------------+------------------------------------+
| Layers      |                                    |
| Transform   |           vùng 3D                  |
| Selection   |                                    |
| View        |                                    |
+-------------+------------------------------------+
| thông báo                  gaussians | selected | FPS |
+--------------------------------------------------+
```

Bấm **F1** (hoặc Help > Keyboard Shortcuts) để xem toàn bộ phím tắt.

## Điều khiển

| Phím / chuột | Chức năng |
|---|---|
| Giữ chuột phải + kéo | Nhìn quanh, bay kiểu Minecraft sáng tạo |
| W A S D | Bay tới / lùi / trái / phải (đi ngang, không chúi theo góc nhìn) |
| Space | Bay lên |
| Shift | Bay xuống |
| Ctrl (khi giữ chuột phải) | Bay nhanh |
| Chuột trái kéo | Xoay quanh |
| Chuột giữa kéo | Dịch chuyển (pan) |
| F | Đưa camera về nhìn toàn cảnh |
| G | Bật / tắt lưới |
| Ctrl+O | Mở file (thay cảnh hiện tại) |
| Ctrl+I, kéo thả file | Thêm file vào cảnh |
| Ctrl+S | Lưu (gộp các lớp đang hiện) |
| Ctrl+Q | Thoát |
| B | Bật / tắt cọ chọn gaussian |
| Chuột trái tô (khi bật cọ) | Chọn gaussian (tô màu vàng) |
| Ctrl + chuột trái tô | Bỏ chọn |
| Chuột giữa kéo (khi bật cọ) | Xoay quanh |
| [ / ] | Thu nhỏ / phóng to cọ |
| Esc | Tắt cọ |
| Ctrl+A / Ctrl+D | Chọn tất cả / bỏ chọn |
| Delete | Xoá gaussian đang chọn (không chọn gì thì xoá lớp đang chọn) |
| Ctrl+Z | Hoàn tác lần xoá gaussian |
| F1 | Bảng phím tắt |

## Cấu trúc

Chia theo tầng, tầng dưới không phụ thuộc tầng trên
(`core` / `io` / `editor` không dùng OpenGL hay ImGui nên test được mà không cần cửa sổ):

```
main.py                     điểm bắt đầu chương trình
splat_editor/
  app.py                    Application: ghép mọi thành phần, vòng lặp chính, khai báo hành động
  core/                     mô hình dữ liệu
    splats.py               Splats: các mảng gaussian đã giải mã
    transform.py            Transform: vị trí / góc xoay / tỉ lệ
    layer.py                Layer: một file PLY + biến đổi + vùng chọn
    scene.py                Scene: danh sách lớp, gộp dữ liệu để vẽ / lưu
    history.py              History, Command: hoàn tác (mẫu Command)
    math3d.py               ma trận chiếu, quaternion
    rect.py                 Rect: hình chữ nhật trên màn hình
  io/                       file
    ply.py                  PlyFile: đọc / ghi PLY
    codec.py                SplatCodec: cột PLY <-> Splats
    sample.py               tạo file PLY mẫu
  editor/                   logic chỉnh sửa
    editor.py               Editor: mở / lưu / chọn / xoá / hoàn tác
    brush.py                BrushTool: cọ chọn
  render/                   OpenGL
    shader.py               ShaderProgram
    shaders/*.vert, *.frag  mã GLSL
    camera.py               OrbitCamera
    splat_renderer.py       SplatRenderer: vẽ gaussian
    grid_renderer.py        GridRenderer: lưới sàn vô hạn
    viewport.py             Viewport: camera + lưới + gaussian trong một vùng màn hình
  ui/                       giao diện
    window.py               Window: cửa sổ GLFW
    gui.py, theme.py        ngữ cảnh ImGui, font, màu
    actions.py              Action, ActionRegistry: menu / nút / phím tắt dùng chung
    layout.py               Layout: chia màn hình
    menu_bar.py             MainMenuBar
    side_panel.py           SidePanel
    sections.py             PanelSection và các mục Layers / Transform / Selection / View
    status_bar.py           StatusBar
    shortcuts_window.py     ShortcutsWindow (F1)
    viewport_overlay.py     gợi ý khi cảnh trống, vòng tròn cọ
    input.py                InputController: chuột / bàn phím
    file_dialog.py          FileDialog: hộp thoại chọn file
tests/                      pytest
```

## Cách render hoạt động (tóm tắt)

1. **Đọc PLY**: mỗi gaussian có `x y z` (tâm), `f_dc_0..2` (màu), `opacity` (độ đục, dạng logit),
   `scale_0..2` (kích thước, dạng log), `rot_0..3` (quaternion xoay).
2. **Giải mã** (`io/codec.py`): màu = `0.5 + 0.282 * f_dc`, alpha = `sigmoid(opacity)`, scale = `exp(scale)`.
3. **Ma trận hiệp phương sai 3D** (`render/splat_renderer.py`): `Σ = R·S·Sᵀ·Rᵀ`, tính bằng numpy rồi đưa lên GPU.
4. **Vertex shader** (`render/shaders/splat.vert`): chiếu Σ xuống màn hình thành ellipse 2D `Σ' = J·W·Σ·Wᵀ·Jᵀ`
   (J là Jacobian của phép chiếu phối cảnh), tìm 2 trục của ellipse (trị riêng / vector riêng)
   và vẽ một hình vuông phủ ±3σ theo 2 trục đó.
5. **Fragment shader**: độ đục tại mỗi pixel = `alpha · exp(-r²/2)`.
6. **Sắp xếp**: alpha blending cần vẽ từ xa tới gần, nên mỗi khi camera thay đổi
   ta sắp xếp gaussian theo độ sâu bằng `numpy.argsort`.

Giới hạn (cố ý giữ đơn giản): chỉ dùng màu bậc 0 (bỏ qua `f_rest_*` – màu không đổi theo hướng nhìn);
khi lưu lớp đã xoay, `f_rest_*` được giữ nguyên chứ không xoay theo; chỉ đọc element `vertex`.
Lưu file luôn giữ quy ước toạ độ của file gốc (tuỳ chọn "Flip Y axis" chỉ ảnh hưởng cách hiển thị).
