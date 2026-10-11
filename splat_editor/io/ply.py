"""Đọc / ghi file PLY."""

import numpy as np 

class PlyError(ValueError):
    "File PLY sai định dạng hoặc không được hỗ trợ"

class PlyFile:

    TYPES = {

    }
    NUMPY_TO_PLY = {}

    @classmethod 
    def read(cls, path):
        with open(path, 'rb') as f:
            fmt, elements = cls._read_header(f)
            if not elemements or element[0][0] != 'vertex':
                raise PlyError("Error")
            _ , count, props = elements[0]
            if fmt == 'ascii':
                return cls._read_ascii(f, count, props)
            if fmt in ('binary_little_endian', 'binary_big_endian'):
                return cls._read_binary(f, count, props,'<' if fmt == 'binary_little_endian' else '>')
            raise PlyError(f"Unsupported PLY format: {fmt}")