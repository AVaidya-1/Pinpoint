from __future__ import annotations


def provider_to_app(box_2d: list[int]) -> list[float]:
    """Convert provider [ymin, xmin, ymax, xmax] on 0-1000 scale
    to app [x0, y0, x1, y1] normalized 0-1."""
    ymin, xmin, ymax, xmax = box_2d
    return [xmin / 1000.0, ymin / 1000.0, xmax / 1000.0, ymax / 1000.0]


def validate_provider_box(box: list[int]) -> bool:
    if len(box) != 4:
        return False
    if not all(isinstance(v, (int, float)) for v in box):
        return False
    ymin, xmin, ymax, xmax = box
    if not (0 <= ymin < ymax <= 1000 and 0 <= xmin < xmax <= 1000):
        return False
    return True


def validate_app_box(box: list[float]) -> bool:
    if len(box) != 4:
        return False
    x0, y0, x1, y1 = box
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def crop_bounds_with_padding(
    boxes: list[list[float]], pad_x: float = 0.05, pad_y: float = 0.05
) -> list[float]:
    """Compute union of app-format boxes with padding, clipped to [0,1]."""
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return [
        max(0.0, x0 - pad_x),
        max(0.0, y0 - pad_y),
        min(1.0, x1 + pad_x),
        min(1.0, y1 + pad_y),
    ]
