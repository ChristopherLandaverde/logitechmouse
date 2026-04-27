"""Pure geometry for the Actions Ring. No Qt imports."""

from __future__ import annotations

import math


def wedge_index(dx: float, dy: float, n: int) -> int:
    """Return the wedge index in [0, n) for a cursor offset from ring center.

    Convention: wedge 0 is centered at 12 o'clock (straight up). Wedges
    proceed clockwise. dx is right-positive, dy is down-positive (Qt screen
    coords). N must be >= 1.

    The cursor position relative to the ring center is converted to an angle
    in degrees clockwise from up; that angle, offset by half a wedge so that
    each wedge straddles its center direction, is divided by the wedge size.
    """
    if n < 1:
        raise ValueError(f"wedge_index requires n >= 1, got {n}")
    # angle in radians, math convention (CCW from +x). atan2(dy, dx) with
    # screen-down dy gives angle CCW from +x in screen space — for our
    # convention we want CW from +y-up, which is equivalent to (90 - math_angle)
    # mod 360 with sign flips. Easiest: convert (dx, dy) directly.
    #
    # CW-from-up angle = atan2(dx, -dy)
    angle_rad = math.atan2(dx, -dy)
    angle_deg = math.degrees(angle_rad) % 360.0
    wedge_size = 360.0 / n
    shifted = (angle_deg + wedge_size / 2.0) % 360.0
    return int(shifted // wedge_size) % n
