"""Canonical geometry: provider [ymin,xmin,ymax,xmax] 0-1000 to app
[x0,y0,x1,y1] 0-1 normalized. One conversion, strict validation."""

import math


def provider_to_app(box_2d: list[float] | tuple[float, ...]) -> list[float]:
    """Convert a provider box [ymin,xmin,ymax,xmax] in 0-1000 to app
    [x0,y0,x1,y1] in 0-1. Raises ValueError on invalid geometry."""
    if not isinstance(box_2d, (list, tuple)) or len(box_2d) != 4:
        raise ValueError("box_2d must have exactly 4 numbers")
    ymin, xmin, ymax, xmax = (float(v) for v in box_2d)
    for v in (ymin, xmin, ymax, xmax):
        if not math.isfinite(v):
            raise ValueError("box coordinates must be finite numbers")
        if v < 0 or v > 1000:
            raise ValueError("box coordinates must be within [0, 1000]")
    if not (ymin < ymax and xmin < xmax):
        raise ValueError("box must satisfy ymin<ymax and xmin<xmax (non-zero area)")
    return [xmin / 1000.0, ymin / 1000.0, xmax / 1000.0, ymax / 1000.0]


def validate_app_box(box: list[float] | tuple[float, ...]) -> list[float]:
    """Validate an app-space box [x0,y0,x1,y1] in 0-1. Raises ValueError."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("box must have exactly 4 numbers")
    x0, y0, x1, y1 = (float(v) for v in box)
    for v in (x0, y0, x1, y1):
        if not math.isfinite(v):
            raise ValueError("box coordinates must be finite numbers")
        if v < 0 or v > 1:
            raise ValueError("box coordinates must be within [0, 1]")
    if not (x0 < x1 and y0 < y1):
        raise ValueError("box must satisfy x0<x1 and y0<y1 (non-zero area)")
    return [x0, y0, x1, y1]


def app_to_viewbox(box: list[float] | tuple[float, ...], size: float = 1000.0) -> list[float]:
    """Convert an app-space normalized box to SVG viewBox coordinates."""
    x0, y0, x1, y1 = validate_app_box(box)
    return [x0 * size, y0 * size, (x1 - x0) * size, (y1 - y0) * size]
