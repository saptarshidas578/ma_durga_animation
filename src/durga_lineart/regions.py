"""Image-coordinate region classification for the Durga reference."""

REGION_ORDER = [
    "halo",
    "crown",
    "face",
    "necklaces",
    "body",
    "arms_left",
    "arms_right",
    "weapons",
    "garlands",
    "lion",
    "mandalas",
]


def classify(bbox, width, height):
    x0, y0, x1, y1 = bbox
    x = (x0 + x1) / 2 / width
    y = (y0 + y1) / 2 / height
    if y > 0.79 and 0.27 < x < 0.75:
        return "lion"
    if y > 0.65 and x < 0.26:
        return "mandalas"
    if y < 0.18:
        return "halo"
    if 0.20 < y < 0.45 and 0.25 < x < 0.75:
        return "crown" if y < 0.34 else "face"
    if 0.37 < y < 0.57 and 0.35 < x < 0.65:
        return "necklaces"
    if 0.30 < y < 0.78 and (x < 0.30 or x > 0.70):
        if (x < 0.22 or x > 0.78) and y < 0.70:
            return "weapons"
        return "arms_left" if x < 0.5 else "arms_right"
    if (x < 0.36 or x > 0.64) and 0.45 < y < 0.9:
        return "garlands"
    if 0.38 < y < 0.95:
        return "body"
    if y < 0.26:
        return "halo"
    return "body"
