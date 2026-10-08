"""Back-to-front depth sorting of gaussians (CPU, numpy), optionally in a background thread.

Depth of a local-space point p is linear: depth = dot(axis, p) (+ const), where
axis = -(view @ model)[2, :3] (distance in front of the camera along its forward axis).
The constant offset doesn't change the order, so a re-sort is only needed when the
axis (camera orientation relative to the layer) changes, or the gaussian set changes.

    order = sort_back_to_front(positions, indices, axis)        # synchronous
    s = AsyncSorter(); s.request(key, positions, indices, axis, token)
    res = s.poll(key)  -> (token, order) | None                  # main thread, non-blocking
"""

from __future__ import annotations

import threading

import numpy as np


def depth_axis(view: np.ndarray, model: np.ndarray) -> np.ndarray:
    """(3,) float64 axis so that dot(axis, p_local) = view-space distance in front of the camera (+const)."""
    mv = np.asarray(view, np.float64) @ np.asarray(model, np.float64)
    return -mv[2, :3]


def sort_back_to_front(positions: np.ndarray, indices: np.ndarray | None, axis, method: str = 'float') -> np.ndarray:
    """Return uint32 gaussian indices ordered farthest -> nearest along `axis`.

    positions: (N,3) float32 local positions. indices: subset of gaussians to sort (None = all).
    method: 'float' (exact argsort of float depths) or 'radix16' (16-bit quantised keys, numpy radix sort).
    """
    a = np.asarray(axis, np.float32).reshape(3)
    if indices is None:
        d = positions @ a
        idx = None
    else:
        idx = np.asarray(indices, np.uint32)
        if len(idx) == len(positions):
            d = (positions @ a)[idx]     # nothing excluded: matvec on all, then permute
        else:
            d = positions[idx] @ a
    n = len(d)
    if n == 0:
        return np.zeros(0, np.uint32)
    if method == 'radix16':
        mn = float(d.min())
        mx = float(d.max())
        rng = mx - mn
        scale = 65535.0 / rng if rng > 0 else 0.0
        keys = ((mx - d) * scale).astype(np.uint16)      # farthest -> key 0
        order = np.argsort(keys, kind='stable')
    else:
        order = np.argsort(d)[::-1]                      # descending depth = back to front
    if idx is None:
        return np.ascontiguousarray(order, dtype=np.uint32)
    return np.ascontiguousarray(idx[order])


class AsyncSorter:
    """Single background worker; one pending request per key (newer requests replace older ones)."""

    def __init__(self, method: str = 'float'):
        self.method = method
        self._cv = threading.Condition()
        self._requests: dict = {}      # key -> (token, positions, indices, axis)
        self._results: dict = {}       # key -> (token, order)
        self._busy_key = None
        self._discarded: set = set()
        self._stop = False
        self._thread = threading.Thread(target=self._run, name='splat-sorter', daemon=True)
        self._thread.start()

    def request(self, key, positions, indices, axis, token=None):
        with self._cv:
            self._discarded.discard(key)
            self._requests[key] = (token, positions, indices, np.array(axis, np.float64))
            self._cv.notify()

    def poll(self, key):
        """Latest finished result for key (removed from the queue), or None."""
        with self._cv:
            return self._results.pop(key, None)

    def pending(self, key=None) -> bool:
        with self._cv:
            if key is None:
                return bool(self._requests) or self._busy_key is not None or bool(self._results)
            return key in self._requests or self._busy_key == key or key in self._results

    def discard(self, key):
        with self._cv:
            self._requests.pop(key, None)
            self._results.pop(key, None)
            if self._busy_key == key:
                self._discarded.add(key)

    def wait_idle(self, timeout=10.0) -> bool:
        """Block until no request is queued or running (tests)."""
        with self._cv:
            return self._cv.wait_for(lambda: not self._requests and self._busy_key is None, timeout)

    def shutdown(self):
        with self._cv:
            self._stop = True
            self._requests.clear()
            self._cv.notify_all()
        self._thread.join(timeout=2.0)

    def _run(self):
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._stop or self._requests)
                if self._stop:
                    return
                key = next(iter(self._requests))
                token, positions, indices, axis = self._requests.pop(key)
                self._busy_key = key
            try:
                order = sort_back_to_front(positions, indices, axis, self.method)
            except Exception:          # pragma: no cover - keep the worker alive
                import traceback
                traceback.print_exc()
                order = None
            with self._cv:
                self._busy_key = None
                if order is not None and key not in self._discarded:
                    self._results[key] = (token, order)
                self._discarded.discard(key)
                self._cv.notify_all()
