"""X11 helpers for reading window manager state."""
from __future__ import annotations

import logging
import subprocess


def active_wm_class() -> str | None:
    """Return the WM_CLASS of the currently focused X11 window, lower-cased.

    Uses xdotool so no Python Xlib dependency is needed. Returns None when
    xdotool is unavailable, times out, or the query fails (e.g. on Wayland).
    """
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowclassname"],
            capture_output=True,
            text=True,
            timeout=0.1,
        )
        if result.returncode == 0:
            return result.stdout.strip().lower()
    except FileNotFoundError:
        logging.debug("xdotool not found; app-specific profiles disabled")
    except subprocess.TimeoutExpired:
        logging.debug("xdotool timed out querying active window")
    except Exception as exc:
        logging.debug("xdotool failed: %s", exc)
    return None
