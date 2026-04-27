import math
import pytest

from logitechmouse.overlay.geometry import wedge_index


# 0 deg = 12 o'clock (up); angles increase clockwise.
# For N=4: wedges centered at 0, 90, 180, 270.
@pytest.mark.parametrize("dx,dy,n,expected", [
    # N=4, cursor straight up from center → wedge 0
    (0, -100, 4, 0),
    # N=4, cursor right of center → wedge 1
    (100, 0, 4, 1),
    # N=4, cursor straight down → wedge 2
    (0, 100, 4, 2),
    # N=4, cursor left → wedge 3
    (-100, 0, 4, 3),
    # N=8, slight clockwise from up → still wedge 0 (within ±22.5°)
    (10, -100, 8, 0),
    # N=8, NE diagonal → wedge 1
    (100, -100, 8, 1),
    # N=8, E → wedge 2
    (100, 0, 8, 2),
    # N=8, SE → wedge 3
    (100, 100, 8, 3),
    # N=8, S → wedge 4
    (0, 100, 8, 4),
    # N=8, SW → wedge 5
    (-100, 100, 8, 5),
    # N=8, W → wedge 6
    (-100, 0, 8, 6),
    # N=8, NW → wedge 7
    (-100, -100, 8, 7),
    # N=3 (120° each), straight up → wedge 0
    (0, -100, 3, 0),
    # N=3, 120° clockwise from up (= 240° standard math, lower-right) → wedge 1
    (math.sin(math.radians(120)) * 100, -math.cos(math.radians(120)) * 100, 3, 1),
    # N=12, 30° clockwise → wedge 1
    (math.sin(math.radians(30)) * 100, -math.cos(math.radians(30)) * 100, 12, 1),
])
def test_wedge_index(dx, dy, n, expected):
    assert wedge_index(dx, dy, n) == expected


def test_wedge_index_wraps_at_full_circle():
    # 359° clockwise from up should be wedge 0 again (within last half-wedge).
    angle = math.radians(359)
    dx = math.sin(angle) * 100
    dy = -math.cos(angle) * 100
    assert wedge_index(dx, dy, 8) == 0


from logitechmouse.overlay.geometry import is_in_dead_zone


def test_in_dead_zone_when_within_radius():
    assert is_in_dead_zone(dx=10, dy=10, dead_zone_radius=45) is True


def test_outside_dead_zone_when_beyond_radius():
    assert is_in_dead_zone(dx=50, dy=0, dead_zone_radius=45) is False


def test_at_exact_dead_zone_radius_is_outside():
    """Boundary is exclusive — at radius, you are out."""
    assert is_in_dead_zone(dx=45, dy=0, dead_zone_radius=45) is False


def test_at_origin_is_in_dead_zone():
    assert is_in_dead_zone(dx=0, dy=0, dead_zone_radius=45) is True


from logitechmouse.overlay.geometry import shifted_center_for_screen


def test_no_shift_when_ring_fits_at_cursor():
    cx, cy = shifted_center_for_screen(
        cursor_x=1000, cursor_y=500,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert (cx, cy) == (1000, 500)


def test_shifts_inward_from_left_edge():
    cx, cy = shifted_center_for_screen(
        cursor_x=10, cursor_y=500,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert cx == 180
    assert cy == 500


def test_shifts_inward_from_right_edge():
    cx, cy = shifted_center_for_screen(
        cursor_x=1910, cursor_y=500,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert cx == 1740
    assert cy == 500


def test_shifts_inward_from_top_edge():
    cx, cy = shifted_center_for_screen(
        cursor_x=1000, cursor_y=10,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert cx == 1000
    assert cy == 180


def test_shifts_inward_from_bottom_edge():
    cx, cy = shifted_center_for_screen(
        cursor_x=1000, cursor_y=1075,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert cx == 1000
    assert cy == 900


def test_shifts_inward_from_corner():
    cx, cy = shifted_center_for_screen(
        cursor_x=10, cursor_y=10,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert (cx, cy) == (180, 180)


def test_does_not_shift_cursor_only_ring_center():
    cx, cy = shifted_center_for_screen(
        cursor_x=10, cursor_y=10,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    assert (cx, cy) != (10, 10)
