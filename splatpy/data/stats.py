"""Per-gaussian property values, histograms and select-by-range
(port of supersplat data-processor/calc-histogram.ts, select-by-range.ts, splat-value-compute.ts,
shaders/splat-value-shader.ts and the ui/data-panel.ts property list), CPU / numpy.

Value semantics follow splat-value-shader.ts:
  x, y, z, distance      world-space centre (distance = |world pos|)
  camera_depth           -(view @ world).z for the scene camera
  red, green, blue       final on-screen colour: DC + SH evaluated for the current camera direction,
                         then the layer colour grade (unclamped)
  opacity                sigmoid(opacity) * grade transparency
  scale_x/y/z            linear local scale exp(scale_i); volume = sx*sy*sz; surface_area = sx²+sy²+sz²
  rot_w/x/y/z            local quaternion (canonicalised to w >= 0)
  hue (deg), saturation, value   HSV of the clamped final colour
  f_dc_0..2, f_rest_N    raw coefficients (extras, 'show all')
Supersplat names (scale_0, rot_0, 'surface-area', 'camera-depth', ...) are accepted as aliases.

"Visible" gaussians (what the histogram counts) are those with state 0 or SELECTED only, i.e.
not deleted and not locked, exactly like the GPU `readSplat` filter.
"""

from __future__ import annotations

import numpy as np

from ..core.splat import DELETED, LOCKED, SELECTED, SH_C0, Splat

HISTOGRAM_PROPERTIES: list[str] = [
    'x', 'y', 'z', 'opacity', 'red', 'green', 'blue',
    'scale_x', 'scale_y', 'scale_z', 'rot_w', 'rot_x', 'rot_y', 'rot_z',
    'distance', 'camera_depth', 'volume', 'surface_area', 'hue', 'saturation', 'value',
]

PROPERTY_LABELS: dict[str, str] = {
    'x': 'Position X', 'y': 'Position Y', 'z': 'Position Z', 'opacity': 'Opacity',
    'red': 'Red', 'green': 'Green', 'blue': 'Blue',
    'scale_x': 'Scale X', 'scale_y': 'Scale Y', 'scale_z': 'Scale Z',
    'rot_w': 'Quaternion W', 'rot_x': 'Quaternion X', 'rot_y': 'Quaternion Y', 'rot_z': 'Quaternion Z',
    'distance': 'Distance', 'camera_depth': 'Camera Depth', 'volume': 'Volume',
    'surface_area': 'Surface Area', 'hue': 'Hue', 'saturation': 'Saturation', 'value': 'Value',
    'f_dc_0': 'DC Red', 'f_dc_1': 'DC Green', 'f_dc_2': 'DC Blue',
}

_ALIASES = {
    'scale_0': 'scale_x', 'scale_1': 'scale_y', 'scale_2': 'scale_z',
    'rot_0': 'rot_w', 'rot_1': 'rot_x', 'rot_2': 'rot_y', 'rot_3': 'rot_z',
    'surface-area': 'surface_area', 'camera-depth': 'camera_depth',
}

# property-dependency classes (used for histogram cache invalidation)
CAMERA_DEPENDENT = {'camera_depth', 'red', 'green', 'blue', 'hue', 'saturation', 'value'}
POSITION_DEPENDENT = {'x', 'y', 'z', 'distance'} | CAMERA_DEPENDENT
GRADE_DEPENDENT = {'opacity', 'red', 'green', 'blue', 'hue', 'saturation', 'value'}


def canonical_name(name: str) -> str:


def extra_properties(splat: Splat) -> list[str]:


def property_label(name: str, splat: Splat | None = None) -> str:


def visible_mask(splat: Splat) -> np.ndarray:


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:


def _camera_of(splat, camera):


def final_colors(splat: Splat, camera=None) -> np.ndarray:


def compute_property(splat: Splat, name: str, camera=None) -> np.ndarray:

def signed_log1p(v):


def signed_expm1(v):


def bin_indices(tvalues: np.ndarray, tmin: float, tmax: float, bins: int) -> np.ndarray:


class HistogramResult:

    @property
    def bins(self) -> int:

    @property
    def counts(self) -> np.ndarray:

    @property
    def num_values(self) -> int:

    def value_at(self, t: float) -> float:

    def edges(self) -> np.ndarray:


def histogram_split(values, mask, selected=None, bins: int = 256, log_scale: bool = False) -> HistogramResult:


def histogram(values, mask, bins: int = 100, log_scale: bool = False):


def range_mask(values, hist: HistogramResult, start_bin: int, end_bin: int) -> np.ndarray:


def select_by_range(splat: Splat, name: str, vmin: float, vmax: float, camera=None) -> np.ndarray:
