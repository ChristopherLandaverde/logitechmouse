import os
import pytest


def _uinput_writable() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def pytest_collection_modifyitems(config, items):
    """Skip markers when their environment isn't available.

    - requires_display: needs an X11 DISPLAY (use xvfb-run on CI).
    - requires_uinput: needs /dev/uinput writable by the current user.
    """
    no_display = not os.environ.get("DISPLAY")
    no_uinput = not _uinput_writable()
    skip_display = pytest.mark.skip(reason="DISPLAY unset; needs X11 (xvfb-run in CI)")
    skip_uinput = pytest.mark.skip(reason="/dev/uinput not writable (skip on CI without uinput)")
    for item in items:
        if no_display and "requires_display" in item.keywords:
            item.add_marker(skip_display)
        if no_uinput and "requires_uinput" in item.keywords:
            item.add_marker(skip_uinput)
