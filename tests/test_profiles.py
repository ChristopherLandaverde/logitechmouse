"""Tests for app-specific profile matching and config parsing."""
from __future__ import annotations
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from logitechmouse.config import AppConfig, Binding, Profile, Target, load_config, validate_config, ConfigError
from logitechmouse.cli.listen import _active_profile, dispatch_event

def _write_config(tmp_path: Path, toml: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(toml))
    return p

def test_profile_parsed_from_config(tmp_path):
    cfg_path = _write_config(tmp_path, """
[actions.lock]
type = "command"
command = "loginctl lock-session"
[rings.dev_ring]
segments = [{action="lock",label="L"},{action="lock",label="L2"},{action="lock",label="L3"}]
[bindings.thumb]
trigger = "BTN_BACK"
target = "ring:dev_ring"
[profiles.firefox]
match_wm_class = "firefox"
[profiles.firefox.bindings.thumb]
trigger = "BTN_BACK"
target = "ring:dev_ring"
    """)
    cfg = load_config(cfg_path)
    assert "firefox" in cfg.profiles
    assert cfg.profiles["firefox"].match_wm_class == "firefox"
    assert "thumb" in cfg.profiles["firefox"].bindings

def test_profile_missing_match_wm_class_raises(tmp_path):
    cfg_path = _write_config(tmp_path, "[profiles.bad]\n")
    with pytest.raises(ConfigError, match="match_wm_class"):
        load_config(cfg_path)

def test_profile_unknown_ring_fails_validation(tmp_path):
    cfg_path = _write_config(tmp_path, """
[actions.lock]
type = "command"
command = "loginctl lock-session"
[bindings.thumb]
trigger = "BTN_BACK"
target = "action:lock"
[profiles.firefox]
match_wm_class = "firefox"
[profiles.firefox.bindings.thumb]
trigger = "BTN_BACK"
target = "ring:nonexistent"
    """)
    cfg = load_config(cfg_path)
    with pytest.raises(ConfigError, match="nonexistent"):
        validate_config(cfg)

def _make_cfg_with_profile(match: str) -> AppConfig:
    binding = Binding(name="thumb", trigger="BTN_BACK", target=Target(kind="ring", name="dev"))
    profile = Profile(name="firefox", match_wm_class=match, bindings={"thumb": binding})
    return AppConfig(profiles={"firefox": profile})

def test_active_profile_matches_substring():
    assert _active_profile(_make_cfg_with_profile("firefox"), "firefox-esr") is not None

def test_active_profile_case_insensitive():
    assert _active_profile(_make_cfg_with_profile("firefox"), "Firefox") is not None

def test_active_profile_no_match_returns_none():
    assert _active_profile(_make_cfg_with_profile("firefox"), "code") is None

def test_active_profile_none_wm_class_returns_none():
    assert _active_profile(_make_cfg_with_profile("firefox"), None) is None

def test_active_profile_no_profiles_returns_none():
    assert _active_profile(AppConfig(), "firefox") is None

def _make_dispatch_cfg() -> AppConfig:
    from logitechmouse.config import Action, Ring, Segment
    lock = Action(name="lock", kind="command", command="loginctl lock-session")
    segs = [Segment(action="lock",label="L"), Segment(action="lock",label="L2"), Segment(action="lock",label="L3")]
    thumb_ring = Ring(name="thumb_ring", segments=segs)
    dev_ring = Ring(name="dev_ring", segments=segs)
    gb = Binding(name="thumb", trigger="BTN_BACK", target=Target(kind="ring", name="thumb_ring"))
    pb = Binding(name="thumb", trigger="BTN_BACK", target=Target(kind="ring", name="dev_ring"))
    profile = Profile(name="firefox", match_wm_class="firefox", bindings={"thumb": pb})
    return AppConfig(actions={"lock":lock}, bindings={"thumb":gb}, rings={"thumb_ring":thumb_ring,"dev_ring":dev_ring}, profiles={"firefox":profile})

def test_dispatch_uses_profile_ring_when_wm_class_matches():
    cfg = _make_dispatch_cfg()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), "BTN_BACK", True, (0,0), active_wm_class="firefox-esr")
    assert rc.open.call_args[0][0].name == "dev_ring"

def test_dispatch_uses_global_ring_when_no_profile_match():
    cfg = _make_dispatch_cfg()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), "BTN_BACK", True, (0,0), active_wm_class="code")
    assert rc.open.call_args[0][0].name == "thumb_ring"

def test_dispatch_uses_global_ring_when_wm_class_is_none():
    cfg = _make_dispatch_cfg()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), "BTN_BACK", True, (0,0), active_wm_class=None)
    assert rc.open.call_args[0][0].name == "thumb_ring"

def test_active_wm_class_returns_lower():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Firefox\n")
        from logitechmouse.x11 import active_wm_class
        assert active_wm_class() == "firefox"

def test_active_wm_class_returns_none_on_nonzero():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from logitechmouse.x11 import active_wm_class
        assert active_wm_class() is None

def test_active_wm_class_returns_none_when_xdotool_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        from logitechmouse.x11 import active_wm_class
        assert active_wm_class() is None
