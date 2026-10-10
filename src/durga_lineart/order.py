"""Region/tier ordering with a local nearest-endpoint walk."""

import numpy as np
from scipy.spatial import cKDTree
from .regions import REGION_ORDER


def order_strokes(strokes):
    for s in strokes:
        n = s["length_px"]
        s["tier"] = "A" if n > 60 else "B" if n >= 20 else "C"
    result = []
    for region in REGION_ORDER:
        group = [s for s in strokes if s["region"] == region]
        # Large contours first; nearest-neighbour order within similarly sized strokes.
        for tier in ("A", "B", "C"):
            items = [s for s in group if s["tier"] == tier]
            if not items:
                continue
            ends = []
            for s in items:
                p = np.asarray(s["points"], dtype=np.float32)
                ends.extend([p[0], p[-1]])
            tree = cKDTree(np.asarray(ends))
            unused = set(range(len(items)))
            here = np.array([0.0, 0.0])
            arranged = []
            while unused:
                _, candidates = tree.query(here, k=min(64, len(ends)))
                if np.isscalar(candidates):
                    candidates = [int(candidates)]
                pick = next(
                    (int(q) // 2 for q in np.atleast_1d(candidates) if int(q) // 2 in unused), None
                )
                if pick is None:
                    pick = min(unused)
                s = items[pick]
                p = np.asarray(s["points"], dtype=np.float32)
                if np.linalg.norm(here - p[-1]) < np.linalg.norm(here - p[0]):
                    p = p[::-1].copy()
                    s["points"] = p.tolist()
                here = p[-1]
                unused.remove(pick)
                arranged.append(s)
            result.extend(arranged)
    for i, s in enumerate(result):
        s["order"] = i
    return result
