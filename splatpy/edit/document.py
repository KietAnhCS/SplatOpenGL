from __future__ import annotations

import dataclasses
import io
import json
import os
import zipfile

import numpy as np

from ..core.splat import ColorAdjust, Splat, SplatData

DOCUMENT_VERSION = 1
PROJECT_EXT = '.ssproj'

_PLY_TYPES = {
    'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
    'short': 'i2', 'int16': 'i2', 'ushort': 'u2', 'uint16': 'u2',
    'int': 'i4', 'int32': 'i4', 'uint': 'u4', 'uint32': 'u4',
    'float': 'f4', 'float32': 'f4', 'double': 'f8', 'float64': 'f8',
}
_NP_TO_PLY = {'i1': 'char', 'u1': 'uchar', 'i2': 'short', 'u2': 'ushort', 'i4': 'int', 'u4': 'uint',
              'f4': 'float', 'f8': 'double'}


# ----------------------------------------------------------------------------- PLY

def _ply_columns(data: SplatData, state: np.ndarray | None):


def write_ply(fp, data: SplatData, state: np.ndarray | None = None, chunk: int = 1 << 18) -> None:


def read_ply(buf: bytes) -> tuple[SplatData, np.ndarray | None]:


# ----------------------------------------------------------------------------- helpers

def _jsonable(v):


def _camera_to_dict(camera):


def _camera_from_dict(camera, d, events=None):


def _settings_to_dict(settings):


def _settings_from_dict(settings, d):


def _color_from_dict(d) -> ColorAdjust:


# ----------------------------------------------------------------------------- save / load

def save_document(scene, camera, path) -> None:


def load_document(path, events, scene, camera) -> None:


__all__ = ['save_document', 'load_document', 'write_ply', 'read_ply', 'PROJECT_EXT', 'DOCUMENT_VERSION']
