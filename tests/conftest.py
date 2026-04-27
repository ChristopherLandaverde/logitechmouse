import os
import pytest


def pytest_collection_modifyitems(config, items):
    """Skip @pytest.mark.requires_display tests when DISPLAY is unset.

    Local dev machines (with X11) run these. Headless CI must wrap pytest
    in `xvfb-run -a` to enable them.
    """
    if os.environ.get("DISPLAY"):
        return
    skip = pytest.mark.skip(reason="DISPLAY unset; needs X11 (xvfb-run in CI)")
    for item in items:
        if "requires_display" in item.keywords:
            item.add_marker(skip)
