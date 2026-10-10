"""Convert a one-pixel skeleton into ordered branch polylines."""

from collections import defaultdict
import numpy as np
from scipy.signal import savgol_filter


def _neighbors(p, pixels):
    y, x = p
    found = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dx or dy):
                continue
            q = (y + dy, x + dx)
            if q not in pixels:
                continue
            # Suppress redundant diagonal links around orthogonal connections.
            if dx and dy and ((y, x + dx) in pixels or (y + dy, x) in pixels):
                continue
            found.append(q)
    return found


def trace_skeleton(skeleton: np.ndarray, min_length: float = 4.0):
    ys, xs = np.nonzero(skeleton)
    pixels = set(zip(ys.tolist(), xs.tolist()))
    graph = {p: _neighbors(p, pixels) for p in pixels}
    nodes = {p for p, ns in graph.items() if len(ns) != 2}
    visited = set()
    paths = []

    def edge(a, b):
        return (a, b) if a < b else (b, a)

    for start in nodes:
        for nxt in graph[start]:
            if edge(start, nxt) in visited:
                continue
            path = [start, nxt]
            visited.add(edge(start, nxt))
            prev, cur = start, nxt
            while cur not in nodes:
                options = [q for q in graph[cur] if q != prev]
                if not options:
                    break
                q = options[0]
                if edge(cur, q) in visited:
                    break
                path.append(q)
                visited.add(edge(cur, q))
                prev, cur = cur, q
            if len(path) > 1:
                paths.append(path)
    # Remaining all-degree-two components are closed loops.
    for start in pixels:
        for nxt in graph[start]:
            if edge(start, nxt) in visited:
                continue
            path = [start, nxt]
            visited.add(edge(start, nxt))
            prev, cur = start, nxt
            while cur != start:
                opts = [q for q in graph[cur] if q != prev]
                if not opts:
                    break
                q = opts[0]
                if edge(cur, q) in visited:
                    break
                path.append(q)
                visited.add(edge(cur, q))
                prev, cur = cur, q
            if len(path) > 2:
                paths.append(path)
    out = []
    for path in paths:
        # Convert row/column to x/y. Keep original endpoints fixed while smoothing.
        p = np.asarray([(x, y) for y, x in path], dtype=np.float32)
        if len(p) < 2:
            continue
        length = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
        if length < min_length:
            continue
        if len(p) >= 7:
            cx = (p[:, 0].min() + p[:, 0].max()) / 2 / skeleton.shape[1]
            cy = (p[:, 1].min() + p[:, 1].max()) / 2 / skeleton.shape[0]
            in_face = 0.37 < cx < 0.63 and 0.27 < cy < 0.41
            width = 9 if in_face else 7
            degree = 3 if in_face else 2
            width = min(width, len(p) if len(p) % 2 else len(p) - 1)
            p[1:-1] = savgol_filter(p, width, degree, axis=0, mode="interp")[1:-1]
        out.append((p, length))
    return out
