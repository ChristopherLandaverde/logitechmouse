"""Tests for the LOGITECHMOUSE_THEME env-var switch.

Themes are baked at import time, so each test importlib-reloads
the widget module under a chosen env var. Marked requires_display
because the module pulls in PyQt6.QtWidgets at import.
"""
import importlib
import os
import sys

import pytest

pytest.importorskip("PyQt6.QtWidgets")


def _reload_widget(theme_value: str | None):
    """Set LOGITECHMOUSE_THEME and reload logitechmouse.overlay.widget."""
    if theme_value is None:
        os.environ.pop("LOGITECHMOUSE_THEME", None)
    else:
        os.environ["LOGITECHMOUSE_THEME"] = theme_value
    mod_name = "logitechmouse.overlay.widget"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


@pytest.mark.requires_display
def test_default_theme_is_dark():
    widget = _reload_widget(None)
    # rgb(40,40,40) is the dark theme background.
    assert widget.BG_COLOR.red() == 40
    assert widget.BG_COLOR.green() == 40
    assert widget.BG_COLOR.blue() == 40


@pytest.mark.requires_display
def test_brazil_theme_swaps_palette():
    widget = _reload_widget("brazil")
    # Bandeira do Brasil green: rgb(0, 156, 59).
    assert widget.BG_COLOR.red() == 0
    assert widget.BG_COLOR.green() == 156
    assert widget.BG_COLOR.blue() == 59
    # Yellow dead zone.
    assert widget.DEAD_ZONE_COLOR.red() == 255
    assert widget.DEAD_ZONE_COLOR.green() == 223
    # Blue active wedge.
    assert widget.ACTIVE_BG_COLOR.blue() == 118


@pytest.mark.requires_display
def test_unknown_theme_falls_back_to_dark():
    widget = _reload_widget("nonsense")
    # Falls back to dark.
    assert widget.BG_COLOR.red() == 40


@pytest.fixture(autouse=True)
def _restore_default_theme_after_test():
    yield
    _reload_widget(None)
