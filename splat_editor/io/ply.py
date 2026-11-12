"""Đọc / ghi file PLY.

PlyFile.read(path)        -> mảng numpy có cấu trúc (mỗi property là một cột: data['x'], data['opacity'], ...)
PlyFile.write(path, data) -> ghi lại mảng đó ra file PLY nhị phân (binary_little_endian)

File binary_little_endian (loại phổ biến nhất) được ánh xạ thẳng vào bộ nhớ (np.memmap):
mở file 15 triệu gaussian (~4 GB) gần như tức thì và không chiếm RAM, hệ điều hành chỉ nạp
phần nào đang được đọc. Lưu ý: trên Windows không ghi đè được file đang được ánh xạ
(xem Editor.save_file).
"""

"""
data = PlyFile.read("scene.ply")        # binary được ánh xạ memmap, mở file 15 triệu gaussian gần như tức thì
print(data.dtype.names)                 # ('x', 'y', 'z', 'f_dc_0', ..., 'rot_3')
xyz = data['x'], data['y'], data['z']

PlyFile.write("copy.ply", data)        # ghi cả mảng ra binary_little_endian

# Ghi từng khối để không giữ cả file trong RAM
PlyFile.write_blocks("big.ply", dtype, count, blocks)   # blocks: iterator các mảng cùng dtype
"""

import os

import numpy as np


def read_block(data, start, end):
    """Hàng [start, end) của `data` (có thể là memmap): chép liền một mạch vào RAM rồi trả về
    (khối, ma trận float32 (n, số cột) nếu mọi cột đều là float32 little endian, ngược lại None).
    Đọc cột qua ma trận nhanh hơn nhiều so với truy cập từng trường của mảng có cấu trúc."""
    block = np.array(data[start:end])
    dtype = block.dtype
    if all(dtype[name] == np.dtype('<f4') for name in dtype.names) and dtype.itemsize == 4 * len(dtype.names):
        return block, block.view(np.float32).reshape(len(block), len(dtype.names))
    return block, None


class PlyError(ValueError):
    """File PLY sai định dạng hoặc không được hỗ trợ."""


class PlyFile:
    # Kiểu dữ liệu trong header PLY -> kiểu numpy
    TYPES = {
        'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
        'short': 'i2', 'int16': 'i2', 'ushort': 'u2', 'uint16': 'u2',
        'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'uint32': 'u4',
        'float': 'f4', 'float32': 'f4', 'double': 'f8', 'float64': 'f8',
    }
    NUMPY_TO_PLY = {'i1': 'char', 'u1': 'uchar', 'i2': 'short', 'u2': 'ushort',
                    'i4': 'int', 'u4': 'uint', 'f4': 'float', 'f8': 'double'}

    # ------------------------------------------------------------------ đọc
    @classmethod
    def read(cls, path):
        """Đọc phần 'element vertex' của file PLY. Hỗ trợ ascii và binary (little/big endian)."""
        with open(path, 'rb') as f:
            fmt, elements = cls._read_header(f)
            if not elements or elements[0][0] != 'vertex':
                raise PlyError("The first element in the file must be 'vertex'")
            _, count, props = elements[0]
            if fmt == 'ascii':
                return cls._read_ascii(f, count, props)
            if fmt in ('binary_little_endian', 'binary_big_endian'):
                return cls._read_binary(f, count, props, '<' if fmt == 'binary_little_endian' else '>')
            raise PlyError(f"Unsupported PLY format: {fmt}")

    @classmethod
    def _read_header(cls, f):
        """-> (định dạng, [(tên element, số lượng, [(tên property, kiểu numpy)])])"""
        if f.readline().strip() != b'ply':
            raise PlyError("Not a PLY file")
        fmt = None
        elements = []
        while True:
            line = f.readline()
            if not line:
                raise PlyError("PLY header has no 'end_header'")
            parts = line.decode('ascii', errors='replace').split()
            if not parts or parts[0] in ('comment', 'obj_info'):
                continue
            if parts[0] == 'end_header':
                return fmt, elements
            if parts[0] == 'format':
                fmt = parts[1]
            elif parts[0] == 'element':
                elements.append((parts[1], int(parts[2]), []))
            elif parts[0] == 'property':
                if parts[1] == 'list':
                    raise PlyError("List properties are not supported (mesh files)")
                elements[-1][2].append((parts[2], cls.TYPES[parts[1]]))

    @staticmethod
    def _read_ascii(f, count, props):
        dtype = np.dtype([(name, '<' + t) for name, t in props])
        values = np.loadtxt(f, max_rows=count, ndmin=2)
        data = np.empty(count, dtype)
        for i, (name, _) in enumerate(props):
            data[name] = values[:, i]
        return data

    @staticmethod
    def _read_binary(f, count, props, endian):
        dtype = np.dtype([(name, endian + t) for name, t in props])
        offset = f.tell()
        if os.fstat(f.fileno()).st_size < offset + count * dtype.itemsize:
            raise PlyError("PLY file is truncated")
        if endian == '<':
            if count == 0:
                return np.zeros(0, dtype)
            return np.memmap(f.name, dtype=dtype, mode='r', offset=offset, shape=(count,))
        # big endian: đọc vào RAM rồi đổi sang little endian cho thống nhất
        return np.fromfile(f, dtype=dtype, count=count).astype(dtype.newbyteorder('<'))

    # ------------------------------------------------------------------ ghi
    @classmethod
    def write(cls, path, data):
        """Ghi mảng có cấu trúc (giống kết quả read) ra file PLY binary_little_endian."""
        cls.write_blocks(path, data.dtype, len(data), [data])

    @classmethod
    def write_blocks(cls, path, dtype, count, blocks):
        """Ghi `count` gaussian kiểu `dtype` từ các khối (mảng có cấu trúc) lần lượt, để không
        phải gộp cả cảnh thành một mảng lớn trong RAM."""
        dtype = dtype.newbyteorder('<')
        lines = ['ply', 'format binary_little_endian 1.0', f'element vertex {count}']
        for name in dtype.names:
            lines.append(f'property {cls.NUMPY_TO_PLY[dtype[name].str[1:]]} {name}')
        lines.append('end_header')
        with open(path, 'wb') as f:
            f.write(('\n'.join(lines) + '\n').encode('ascii'))
            for block in blocks:
                np.ascontiguousarray(block.astype(dtype, copy=False)).tofile(f)
