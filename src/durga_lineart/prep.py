"""Threshold and skeletonize the reference line art."""

from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from skimage.morphology import skeletonize


def preprocess(image_path: str | Path, cache_dir: str | Path = "cache") -> np.ndarray:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    src = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if src is None:
        raise FileNotFoundError(image_path)
    # Otsu threshold retains the thin bright ink while removing the black field.
    _, binary = cv2.threshold(src, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    keep = np.zeros(n, dtype=np.uint8)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 6
    clean = (keep[labels] * 255).astype(np.uint8)
    skel = skeletonize(clean > 0)
    out = skel.astype(np.uint8) * 255
    # The reference has a solid white face. Skeletonizing a filled shape makes
    # its medial axis appear as an artificial diamond on the face. Replace
    # that component's medial axis with its smoothed boundary and enclosed
    # feature contours, while leaving all surrounding ornament strokes alone.
    h, w = clean.shape
    x0, x1 = int(0.35 * w), int(0.65 * w)
    y0, y1 = int(0.25 * h), int(0.42 * h)
    face_roi = clean[y0:y1, x0:x1]
    count, face_labels, face_stats, face_centers = cv2.connectedComponentsWithStats(face_roi, 8)
    if count > 1:
        largest = 1 + int(np.argmax(face_stats[1:, cv2.CC_STAT_AREA]))
        area = int(face_stats[largest, cv2.CC_STAT_AREA])
        fx, fy = face_centers[largest]
        if area >= 6000 and 0.30 * w < x0 + fx < 0.65 * w and 0.26 * h < y0 + fy < 0.43 * h:
            component = (face_labels == largest).astype(np.uint8) * 255
            contours, _ = cv2.findContours(component, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            component_mask = np.zeros_like(clean)
            component_mask[y0:y1, x0:x1] = component
            out[component_mask > 0] = 0
            for contour in contours:
                # A one-pixel contour feeds the same tracing/fitting pipeline.
                cv2.drawContours(out[y0:y1, x0:x1], [contour], -1, 255, 1, cv2.LINE_8)
    cv2.imwrite(str(cache / "skeleton.png"), out)
    preview = Image.new("RGB", (src.shape[1] * 2, src.shape[0]), (5, 6, 10))
    preview.paste(Image.fromarray(src).convert("RGB"), (0, 0))
    preview.paste(Image.fromarray(out).convert("RGB"), (src.shape[1], 0))
    preview.save(cache / "preprocess_preview.png")
    return out
