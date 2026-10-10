"""Fit traced curves to lines, circular arcs, or cubic Bezier chains."""

import json
from pathlib import Path
import cv2
import numpy as np
from .regions import classify


def _circle(points):
    x, y = points[:, 0], points[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones_like(x)]
    b = x * x + y * y
    try:
        h, k, c = np.linalg.lstsq(A, b, rcond=None)[0]
        r = np.sqrt(max(0, c + h * h + k * k))
    except Exception:
        return None
    err = np.abs(np.hypot(x - h, y - k) - r)
    if r > 2 and np.mean(err) < 0.65 and np.max(err) <= 1.2:
        return [float(h), float(k), float(r)], float(np.sqrt(np.mean(err**2))), float(np.max(err))
    return None


def _ellipse(points, length):
    if len(points) < 5:
        return None
    (cx, cy), (d1, d2), angle = cv2.fitEllipse(points.astype(np.float32).reshape(-1, 1, 2))
    a, b = float(d1) / 2, float(d2) / 2
    phi = float(np.deg2rad(angle))
    if min(a, b) < 2:
        return None
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    xr = dx * np.cos(phi) + dy * np.sin(phi)
    yr = -dx * np.sin(phi) + dy * np.cos(phi)
    theta = np.unwrap(np.arctan2(yr / b, xr / a))
    px = cx + a * np.cos(theta) * np.cos(phi) - b * np.sin(theta) * np.sin(phi)
    py = cy + a * np.cos(theta) * np.sin(phi) + b * np.sin(theta) * np.cos(phi)
    err = np.hypot(points[:, 0] - px, points[:, 1] - py)
    if float(err.max()) > 1.2:
        return None
    ts = np.linspace(theta[0], theta[-1], max(3, int(length / 3)))
    samples = np.c_[
        cx + a * np.cos(ts) * np.cos(phi) - b * np.sin(ts) * np.sin(phi),
        cy + a * np.cos(ts) * np.sin(phi) + b * np.sin(ts) * np.cos(phi),
    ]
    return (
        (float(cx), float(cy), a, b, phi, float(theta[0]), float(theta[-1])),
        float(np.sqrt(np.mean(err**2))),
        samples,
        float(err.max()),
    )


def _beziers(points):
    # Catmull-Rom to cubic Bezier conversion gives a smooth, equation-driven chain.
    out = []
    n = len(points)
    for i in range(n - 1):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(n - 1, i + 2)]
        out.append(
            [p1.tolist(), (p1 + (p2 - p0) / 6).tolist(), (p2 - (p3 - p1) / 6).tolist(), p2.tolist()]
        )
    return out


def _linear_beziers(points):
    """Exact cubic representation of each simplified line segment."""
    out = []
    for p0, p3 in zip(points[:-1], points[1:]):
        delta = (p3 - p0) / 3
        out.append([p0.tolist(), (p0 + delta).tolist(), (p0 + 2 * delta).tolist(), p3.tolist()])
    return out


def _sample(curves, per=8):
    t = np.linspace(0, 1, per, endpoint=False, dtype=np.float32)[:, None]
    pts = []
    for b in curves:
        p = np.asarray(b, dtype=np.float32)
        u = 1 - t
        pts.append(u**3 * p[0] + 3 * u * u * t * p[1] + 3 * u * t * t * p[2] + t**3 * p[3])
    pts.append(np.asarray(curves[-1][3], dtype=np.float32)[None, :])
    return np.concatenate(pts)


def fit_strokes(traced, shape):
    h, w = shape
    strokes = []
    rms = []
    for raw, length in traced:
        p = cv2.approxPolyDP(raw.astype(np.float32).reshape(-1, 1, 2), 0.7, False).reshape(-1, 2)
        if len(p) < 2:
            continue
        # Use a line equation only when its perpendicular fit stays within tolerance.
        center = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - center, full_matrices=False)
        axis = vt[0]
        proj = (p - center) @ axis
        residual = np.abs((p - center) @ vt[1]) if len(vt) > 1 else np.zeros(len(p))
        if residual.max() <= 1.2:
            a = center + axis * proj.min()
            b = center + axis * proj.max()
            samples = np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / 3)))
            typ = "line"
            params = {"p0": a.tolist(), "p1": b.tolist()}
            err = float(np.sqrt(np.mean(residual**2)))
            maxerr = float(residual.max())
            conv = lambda q: [round(float(q[0]) / 10 - w / 20, 1), round(float(h - q[1]) / 10, 1)]
            eq = f"P(t)=P₀+t(P₁−P₀); P₀={conv(a)}, P₁={conv(b)}"
        else:
            circ = _circle(p)
            if circ:
                (cx, cy, r), err, maxerr = circ
                ang = np.unwrap(np.arctan2(-(p[:, 1] - cy), p[:, 0] - cx))
                ts = np.linspace(ang[0], ang[-1], max(3, int(length / 3)))
                samples = np.c_[cx + r * np.cos(ts), cy - r * np.sin(ts)]
                typ = "circle"
                params = {
                    "center": [cx, cy],
                    "radius": r,
                    "angle_start": float(ang[0]),
                    "angle_end": float(ang[-1]),
                }
                eq = f"x={cx/10-w/20:.1f}+{r/10:.1f} cos(t), y={h/10-cy/10:.1f}+{r/10:.1f} sin(t)"
            else:
                ellipse = _ellipse(p, length)
                if ellipse:
                    (cx, cy, a, b, phi, t0, t1), err, samples, maxerr = ellipse
                    typ = "ellipse"
                    params = {
                        "center": [cx, cy],
                        "a": a,
                        "b": b,
                        "phi": phi,
                        "angle_start": t0,
                        "angle_end": t1,
                    }
                    grid_phi = -phi
                    gx = cx / 10 - w / 20
                    gy = (h - cy) / 10
                    eq = f"x={gx:.1f}+{a/10:.1f}cos(t)cos({grid_phi:.2f})−{b/10:.1f}sin(t)sin({grid_phi:.2f}); y={gy:.1f}−{a/10:.1f}cos(t)sin({phi:.2f})−{b/10:.1f}sin(t)cos({phi:.2f})"
                else:
                    # Bound dense skeleton branches to a manageable but precise chain.
                    curves = _beziers(p)
                    samples = _sample(curves, 24)
                    # Split corner-heavy curves more finely when smoothing would
                    # move the fitted chain too far from the traced centerline.
                    from scipy.spatial import cKDTree

                    raw2 = raw[:: max(1, len(raw) // 3000)]
                    residual = cKDTree(samples).query(raw2)[0]
                    if float(residual.max()) > 1.2:
                        # Preserve each traced centerline turn at the original
                        # pixel spacing if the smoothed chain rounds a corner.
                        curves = _linear_beziers(raw)
                        samples = _sample(curves, 6)
                        residual = cKDTree(samples).query(raw2)[0]
                    err = float(np.sqrt(np.mean(residual**2)))
                    maxerr = float(residual.max())
                    typ = "bezier"
                    params = {"segments": curves}
                    b = curves[0]
                    conv = lambda q: (
                        round(float(q[0]) / 10 - w / 20, 1),
                        round(float(h - q[1]) / 10, 1),
                    )
                    controls = " ".join(f"{x:.1f},{y:.1f}" for x, y in (conv(q) for q in b))
                    eq = "B(t)=u³P₀+3u²tP₁+3ut²P₂+t³P₃; u=1−t\n" + controls
        rms.append(err)
        # Grid coordinates origin bottom centre; retain pixels for rendering and normalized bbox.
        bb = [
            float(p[:, 0].min()),
            float(p[:, 1].min()),
            float(p[:, 0].max()),
            float(p[:, 1].max()),
        ]
        grid_samples = [
            [round(float(x) / 10 - w / 20, 3), round(float(h - y) / 10, 3)] for x, y in samples
        ]
        strokes.append(
            {
                "id": len(strokes),
                "region": classify(bb, w, h),
                "type": typ,
                "points": grid_samples,
                "params": params,
                "equation_text": eq,
                "length_px": round(float(length), 2),
                "bbox": bb,
                "fit_error_px": round(float(maxerr), 3),
                "fit_rms_px": round(float(err), 3),
            }
        )
    return strokes, rms


def save_strokes(strokes, path="cache/strokes.json"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(strokes, separators=(",", ":")), encoding="utf-8")
