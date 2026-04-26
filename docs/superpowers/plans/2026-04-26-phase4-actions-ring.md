# Phase 4 Actions Ring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the radial Actions Ring overlay — pressing and holding a configured mouse button opens a transparent ring at the cursor; releasing fires the wedge under the cursor (or cancels in the dead zone).

**Architecture:** PyQt6 + X11 only in v1. Pure geometry isolated in `overlay/geometry.py`. Worker-thread evdev listener feeds a Qt main thread that owns the widget, controller, and cursor-polling timer. Polymorphic binding `target = "ring:NAME" | "action:NAME"` replaces `action = "..."` (legacy form preserved with deprecation warning). PyQt6 ships as an optional `[ring]` extra so command-only users do not pay the install cost.

**Tech Stack:** Python 3.11+, `evdev>=1.6` (existing), `PyQt6 ~= 6.6` (new, optional), `pytest>=7` + `pytest-qt ~= 4.4` (dev), `tomllib` (stdlib).

**Spec:** `docs/superpowers/specs/2026-04-26-phase4-actions-ring-design.md` (commit `ecb6e14`)

**Branch:** `phase4-ring-prototype` (created in Task 0).

**Predecessor:** Phase 2 evdev listener (PR #2, commit `4cdfc43`). 35 existing tests must stay green throughout.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` (modify) | Add `PyQt6 ~= 6.6` to a new `[ring]` optional-dependency; add `pytest-qt ~= 4.4` to `dev`; add `requires_display` pytest marker. |
| `src/logitechmouse/config.py` (modify) | Add `Target`/`Segment`/`Ring` dataclasses. Replace `Binding.action` with `Binding.target`. Parse `target = "..."` and shim legacy `action = "..."`. Parse `[rings.X]`. Extend validation. |
| `src/logitechmouse/device.py` (modify) | Extend `InputEvent` with `pressed: bool`. `read_loop` emits both key-down (value=1) and key-up (value=0); ignores key-repeat (value=2). |
| `src/logitechmouse/cli/listen.py` (modify) | Refactor: QApplication entry point. Worker thread runs `read_loop`. Signal/slot bridge to a dispatcher on the main thread. Action targets fire on key-down only; ring targets fire `open`/`close`. |
| `src/logitechmouse/cli/check_config.py` (modify) | When config has ring bindings, fail fast with a clear error if PyQt6 is not importable. |
| `src/logitechmouse/overlay/__init__.py` (create) | Package marker. |
| `src/logitechmouse/overlay/geometry.py` (create) | Pure functions: `wedge_index`, `is_in_dead_zone`, `shifted_center_for_screen`. No Qt imports. |
| `src/logitechmouse/overlay/widget.py` (create) | `RingWidget(QWidget)`. Transparent frameless top-level. Renders ring + active wedge + cancel pip. 75ms open animation. |
| `src/logitechmouse/overlay/cursor.py` (create) | `CursorPoller`: thin wrapper over `QCursor.pos()` driven by a 8ms `QTimer`. Skips redraw if cursor unchanged. |
| `src/logitechmouse/overlay/ring.py` (create) | `RingController`: state machine (`IDLE`/`OPEN`), owns the widget + cursor poller, dispatches `run_action` on close-outside-deadzone. |
| `src/logitechmouse/overlay/__init__.py` (already listed) | exports `RingController` for the listener. |
| `examples/config.toml` (modify) | Add a 4-segment ring example bound to `BTN_TASK`. |
| `README.md` (modify) | Document ring schema, install with `[ring]` extra, X11 caveat. |
| `docs/PRD.md` (modify) | Mark optional radial overlay goal as implemented. |
| `tests/test_config.py` (modify) | Update existing tests to use `Binding.target` (legacy `Binding.action` is gone from the model; legacy TOML form still works). |
| `tests/test_config_ring.py` (create) | Target parsing, legacy shim, deprecation warning, `[rings.X]` parsing, all new validation rules. |
| `tests/test_device_readloop.py` (create) | `read_loop` emits key-down and key-up, ignores key-repeat. |
| `tests/test_listen_cli.py` (modify) | Update existing tests for `Binding.target`. Add tests for the dispatcher: action-target fires only on key-down; ring-target opens on down, closes on up. |
| `tests/test_geometry.py` (create) | Wedge index across `N ∈ {3,4,6,8,12}`, dead-zone hit-test, edge-shift function. |
| `tests/test_overlay_widget.py` (create) | pytest-qt smoke tests; mark `requires_display`. |
| `tests/test_ring_controller.py` (create) | State machine unit tests with a mocked widget + cursor poller. |
| `tests/conftest.py` (create) | Shared fixtures: `qtbot` is provided by pytest-qt; we add a `requires_display` skip-if-no-DISPLAY hook. |
| `.github/workflows/test.yml` (modify) | Install `xvfb`; wrap pytest in `xvfb-run -a` so widget tests run in CI. |

Files split by responsibility, not layer. `overlay/geometry.py` is the only place with angle math; `overlay/widget.py` is the only place with `paintEvent`; `overlay/ring.py` is the only state machine. Each is a single concern.

---

## Task 0: Create the implementation branch

**Files:** none (git only).

- [ ] **Step 1: Verify clean working tree on main**

```bash
git status --short
git rev-parse --abbrev-ref HEAD
```
Expected: empty output, then `main`.

- [ ] **Step 2: Pull latest main**

```bash
git pull --ff-only
```
Expected: `Already up to date.` (or fast-forward summary).

- [ ] **Step 3: Create and switch to the feature branch**

```bash
git checkout -b phase4-ring-prototype
```
Expected: `Switched to a new branch 'phase4-ring-prototype'`.

- [ ] **Step 4: Confirm baseline tests pass cold**

```bash
source .venv/bin/activate
pytest -q
```
Expected: 35 passed.

---

## Task 1: Add PyQt6 (optional) and pytest-qt (dev) dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `pyproject.toml`**

Replace the existing `[project.optional-dependencies]` and `[tool.pytest.ini_options]` blocks:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=7",
  "pytest-qt~=4.4",
]
ring = [
  "PyQt6~=6.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
markers = [
  "requires_display: skipped when DISPLAY env var is unset (Qt widget tests)",
]
```

- [ ] **Step 2: Reinstall in editable mode with both extras**

```bash
source .venv/bin/activate
pip install -e ".[dev,ring]"
```
Expected: PyQt6 and pytest-qt resolve and install. No errors.

- [ ] **Step 3: Confirm baseline still passes**

```bash
pytest -q
```
Expected: 35 passed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add PyQt6 [ring] extra and pytest-qt dev dep for phase 4"
```

---

## Task 2: Add `requires_display` skip hook in conftest.py

**Files:**
- Create: `tests/conftest.py`
- Test: `tests/conftest.py` is loaded automatically by pytest; verified by Task 3.

- [ ] **Step 1: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 2: Confirm baseline still passes**

```bash
pytest -q
```
Expected: 35 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add requires_display marker hook for X11-dependent tests"
```

---

## Task 3: Add `Target` dataclass and parser

**Files:**
- Modify: `src/logitechmouse/config.py`
- Test: `tests/test_config_ring.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_ring.py`:

```python
import pytest

from logitechmouse.config import Target, parse_target_string, ConfigError


def test_parse_action_target():
    t = parse_target_string("action:screenshot")
    assert t == Target(kind="action", name="screenshot")


def test_parse_ring_target():
    t = parse_target_string("ring:thumb_ring")
    assert t == Target(kind="ring", name="thumb_ring")


def test_parse_target_rejects_unknown_kind():
    with pytest.raises(ConfigError, match="unknown target kind 'macro'"):
        parse_target_string("macro:foo")


def test_parse_target_rejects_missing_separator():
    with pytest.raises(ConfigError, match="must be 'kind:name'"):
        parse_target_string("screenshot")


def test_parse_target_rejects_empty_name():
    with pytest.raises(ConfigError, match="empty name"):
        parse_target_string("action:")


def test_target_is_frozen():
    t = Target(kind="action", name="x")
    with pytest.raises(Exception):
        t.kind = "ring"  # frozen dataclasses raise FrozenInstanceError
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config_ring.py -v
```
Expected: ImportError or `AttributeError: ...has no attribute 'Target'`.

- [ ] **Step 3: Add `Target` and `parse_target_string` to `config.py`**

Add to `src/logitechmouse/config.py`, near the other dataclasses (after `Action`, before `Binding`):

```python
_VALID_TARGET_KINDS = ("action", "ring")


@dataclass(frozen=True)
class Target:
    kind: str   # "action" or "ring"
    name: str


def parse_target_string(raw: str) -> "Target":
    if ":" not in raw:
        raise ConfigError(
            f"target {raw!r} must be 'kind:name' (e.g. 'action:screenshot')"
        )
    kind, _, name = raw.partition(":")
    if kind not in _VALID_TARGET_KINDS:
        raise ConfigError(
            f"unknown target kind {kind!r} in {raw!r}; expected one of "
            + ", ".join(_VALID_TARGET_KINDS)
        )
    if not name:
        raise ConfigError(f"target {raw!r} has empty name after the ':'")
    return Target(kind=kind, name=name)
```

Move the existing `class ConfigError(Exception):` definition to appear **before** the `Target` dataclass so it can be referenced. (Currently it lives near the bottom of the file.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config_ring.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config_ring.py
git commit -m "feat(config): add Target dataclass and parse_target_string"
```

---

## Task 4: Replace `Binding.action` with `Binding.target` and shim legacy form

**Files:**
- Modify: `src/logitechmouse/config.py`
- Modify: `tests/test_config.py`
- Test: `tests/test_config_ring.py`

- [ ] **Step 1: Write failing tests for the legacy shim**

Append to `tests/test_config_ring.py`:

```python
import logging
import textwrap
from pathlib import Path

from logitechmouse.config import load_config


def write_cfg(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(body))
    return p


def test_modern_target_action_form_parses(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "action:shot"
    """)
    cfg = load_config(p)
    assert cfg.bindings["g"].target.kind == "action"
    assert cfg.bindings["g"].target.name == "shot"


def test_legacy_action_string_form_is_translated(tmp_path, caplog):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    with caplog.at_level(logging.INFO):
        cfg = load_config(p)
    assert cfg.bindings["g"].target.kind == "action"
    assert cfg.bindings["g"].target.name == "shot"
    # Migration nudge logged at INFO (not raised).
    assert any(
        "deprecated" in r.message.lower() and "g" in r.message
        for r in caplog.records
    )


def test_target_and_action_both_present_is_error(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        action = "shot"
        target = "action:shot"
    """)
    import pytest
    from logitechmouse.config import ConfigError
    with pytest.raises(ConfigError, match="cannot specify both 'action' and 'target'"):
        load_config(p)


def test_neither_target_nor_action_is_error(tmp_path):
    p = write_cfg(tmp_path, """
        [bindings.g]
        trigger = "BTN_TASK"
    """)
    import pytest
    from logitechmouse.config import ConfigError
    with pytest.raises(ConfigError, match="must specify 'target'"):
        load_config(p)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_ring.py -v
```
Expected: 4 new tests fail (`AttributeError: ...has no attribute 'target'` or KeyError on `'action'`).

- [ ] **Step 3: Update `Binding` dataclass and loader**

In `src/logitechmouse/config.py`, replace the existing `Binding` dataclass and the bindings-parsing block:

```python
@dataclass
class Binding:
    name: str
    trigger: str
    target: Target


def _parse_binding(name: str, data: dict) -> Binding:
    has_target = "target" in data
    has_action = "action" in data
    if has_target and has_action:
        raise ConfigError(
            f"binding {name!r}: cannot specify both 'action' and 'target'; "
            f"use 'target = \"action:NAME\"' (modern) or 'action = \"NAME\"' (legacy)"
        )
    if has_target:
        target = parse_target_string(data["target"])
    elif has_action:
        logging.info(
            "binding %r uses deprecated 'action = ...' form; the modern "
            "equivalent is 'target = \"action:%s\"'",
            name, data["action"],
        )
        target = Target(kind="action", name=data["action"])
    else:
        raise ConfigError(
            f"binding {name!r} must specify 'target' (e.g. 'target = \"action:screenshot\"')"
        )
    if "trigger" not in data:
        raise ConfigError(f"binding {name!r} missing 'trigger'")
    return Binding(name=name, trigger=data["trigger"], target=target)
```

Replace the existing bindings parsing inside `load_config`:

```python
bindings = {
    name: _parse_binding(name, data)
    for name, data in raw.get("bindings", {}).items()
}
```

Add `import logging` at the top of `config.py` if not already there.

- [ ] **Step 4: Update existing `tests/test_config.py` to use `target`**

In `tests/test_config.py`, update assertions that reference `cfg.bindings[X].action` (the dataclass field is now gone). The legacy TOML form `action = "..."` still works — the change is in what the parsed object looks like.

Replace `test_parses_actions_and_bindings`:

```python
def test_parses_actions_and_bindings(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.gesture]
        trigger = "BTN_TASK"
        action = "shot"
    """)
    cfg = load_config(p)
    assert cfg.actions["shot"].command == "true"
    assert cfg.bindings["gesture"].trigger == "BTN_TASK"
    assert cfg.bindings["gesture"].target.kind == "action"
    assert cfg.bindings["gesture"].target.name == "shot"
```

Replace `test_validate_rejects_unknown_action_reference` to assert the new error message and use the modern form:

```python
def test_validate_rejects_unknown_action_reference(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "action:missing"
    """)
    cfg = load_config(p)
    with pytest.raises(ConfigError, match="binding 'g' references unknown action 'missing'"):
        validate_config(cfg)
```

(`test_validate_rejects_unknown_trigger_code` and `test_validate_rejects_command_action_without_command` are unaffected.)

- [ ] **Step 5: Update `validate_config` to read from `binding.target`**

In `src/logitechmouse/config.py`, replace the `validate_config` function:

```python
def validate_config(config: AppConfig) -> None:
    for action in config.actions.values():
        if action.kind == "command" and not action.command:
            raise ConfigError(
                f"action {action.name!r} is type=command but has no command"
            )
    for binding in config.bindings.values():
        if binding.trigger not in ecodes.ecodes:
            raise ConfigError(
                f"binding {binding.name!r} has unknown trigger {binding.trigger!r}"
            )
        if binding.target.kind == "action":
            if binding.target.name not in config.actions:
                raise ConfigError(
                    f"binding {binding.name!r} references unknown action "
                    f"{binding.target.name!r}"
                )
        # binding.target.kind == "ring" is validated in Task 7.
```

- [ ] **Step 6: Update `src/logitechmouse/cli/listen.py` for the new field**

Replace this section in `src/logitechmouse/cli/listen.py` (currently around lines 52-64):

```python
    bindings_by_trigger = {b.trigger: b for b in cfg.bindings.values()}
    summary = ", ".join(
        f"{b.name}[{b.trigger}]->{b.target.kind}:{b.target.name}"
        for b in cfg.bindings.values()
    ) or "(none)"
    logging.info("listening on %s (%s)", device.path, device.name)
    logging.info("bindings: %s", summary)

    try:
        for event in backend.read_loop(device):
            binding = bindings_by_trigger.get(event.trigger)
            if binding is None:
                continue
            if binding.target.kind != "action":
                # Ring targets are wired in a later task; skip silently for now.
                continue
            action = cfg.actions[binding.target.name]
            result = run_action(action)
            if result.ok:
                logging.info("%s", result.detail)
            else:
                logging.warning("action %r %s", action.name, result.detail)
    except OSError as exc:
```

(The `event.trigger` access still works — `pressed` is added in Task 9.)

- [ ] **Step 7: Run full test suite**

```bash
pytest -q
```
Expected: all previous tests pass + 4 new ring tests pass. Total ~39 passed.

- [ ] **Step 8: Commit**

```bash
git add src/logitechmouse/config.py src/logitechmouse/cli/listen.py tests/test_config.py tests/test_config_ring.py
git commit -m "feat(config): replace Binding.action with Binding.target; shim legacy 'action = ...' form"
```

---

## Task 5: Add `Segment` and `Ring` dataclasses

**Files:**
- Modify: `src/logitechmouse/config.py`
- Test: `tests/test_config_ring.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_ring.py`:

```python
def test_parses_ring_with_segments(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "gnome-screenshot -a"

        [actions.full]
        type = "command"
        command = "gnome-screenshot"

        [actions.lock]
        type = "command"
        command = "loginctl lock-session"

        [rings.thumb]
        segments = [
          { action = "shot", label = "Area" },
          { action = "full", label = "Full" },
          { action = "lock", label = "Lock" },
        ]
    """)
    cfg = load_config(p)
    assert "thumb" in cfg.rings
    ring = cfg.rings["thumb"]
    assert ring.name == "thumb"
    assert len(ring.segments) == 3
    assert ring.segments[0].action == "shot"
    assert ring.segments[0].label == "Area"
    assert ring.segments[0].icon is None


def test_parses_ring_segment_with_icon(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "S", icon = "camera-photo" },
          { action = "shot", label = "S2" },
          { action = "shot", label = "S3" },
        ]
    """)
    cfg = load_config(p)
    assert cfg.rings["r"].segments[0].icon == "camera-photo"
    assert cfg.rings["r"].segments[1].icon is None


def test_no_rings_section_yields_empty_dict(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"
    """)
    cfg = load_config(p)
    assert cfg.rings == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_ring.py -v -k "ring"
```
Expected: 3 new tests fail (no `Ring`/`Segment` classes; `cfg.rings` does not exist).

- [ ] **Step 3: Add `Segment`, `Ring`, extend `AppConfig` and `load_config`**

In `src/logitechmouse/config.py`, after the `Target` dataclass:

```python
@dataclass
class Segment:
    action: str           # references actions[name]
    label: str
    icon: str | None = None


@dataclass
class Ring:
    name: str
    segments: list[Segment]
```

Update `AppConfig`:

```python
@dataclass
class AppConfig:
    actions: dict[str, Action] = field(default_factory=dict)
    bindings: dict[str, Binding] = field(default_factory=dict)
    rings: dict[str, Ring] = field(default_factory=dict)
    device: DeviceConfig = field(default_factory=DeviceConfig)
```

Add a `_parse_ring` helper after `_parse_binding`:

```python
def _parse_ring(name: str, data: dict) -> Ring:
    raw_segments = data.get("segments")
    if raw_segments is None:
        raise ConfigError(f"ring {name!r} missing 'segments' list")
    if not isinstance(raw_segments, list):
        raise ConfigError(f"ring {name!r}: 'segments' must be a list")
    segments: list[Segment] = []
    for i, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            raise ConfigError(
                f"ring {name!r}.segments[{i}] must be an inline table"
            )
        if "action" not in seg:
            raise ConfigError(f"ring {name!r}.segments[{i}] missing 'action'")
        if "label" not in seg:
            raise ConfigError(f"ring {name!r}.segments[{i}] missing 'label'")
        icon = seg.get("icon")
        if icon is not None and (not isinstance(icon, str) or not icon):
            raise ConfigError(
                f"ring {name!r}.segments[{i}] icon must be a non-empty string"
            )
        segments.append(
            Segment(action=seg["action"], label=seg["label"], icon=icon)
        )
    return Ring(name=name, segments=segments)
```

Inside `load_config`, after the `bindings = {...}` block, add:

```python
    rings = {
        name: _parse_ring(name, data)
        for name, data in raw.get("rings", {}).items()
    }
```

And update the final return:

```python
    return AppConfig(actions=actions, bindings=bindings, rings=rings, device=device)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config_ring.py -v
```
Expected: all parse tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config_ring.py
git commit -m "feat(config): add Ring/Segment dataclasses and [rings.X] parser"
```

---

## Task 6: Validate ring bindings reference an existing ring

**Files:**
- Modify: `src/logitechmouse/config.py`
- Test: `tests/test_config_ring.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_ring.py`:

```python
def test_validate_rejects_ring_target_to_missing_ring(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [bindings.g]
        trigger = "BTN_TASK"
        target = "ring:nonexistent"
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="binding 'g' references unknown ring 'nonexistent'"):
        validate_config(cfg)


def test_validate_passes_for_valid_ring_binding(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
          { action = "shot", label = "C" },
        ]

        [bindings.g]
        trigger = "BTN_TASK"
        target = "ring:r"
    """)
    cfg = load_config(p)
    from logitechmouse.config import validate_config
    validate_config(cfg)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_ring.py::test_validate_rejects_ring_target_to_missing_ring -v
```
Expected: fails — current `validate_config` doesn't check ring targets.

- [ ] **Step 3: Extend `validate_config`**

In `src/logitechmouse/config.py`, inside the `for binding in config.bindings.values():` loop, after the existing `if binding.target.kind == "action":` block:

```python
        elif binding.target.kind == "ring":
            if binding.target.name not in config.rings:
                raise ConfigError(
                    f"binding {binding.name!r} references unknown ring "
                    f"{binding.target.name!r}"
                )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config_ring.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config_ring.py
git commit -m "feat(config): validate ring-target bindings reference an existing ring"
```

---

## Task 7: Validate ring segments (count, label, action references)

**Files:**
- Modify: `src/logitechmouse/config.py`
- Test: `tests/test_config_ring.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_ring.py`:

```python
def test_validate_rejects_ring_with_too_few_segments(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="ring 'r' must have between 3 and 12 segments"):
        validate_config(cfg)


def test_validate_rejects_ring_with_too_many_segments(tmp_path):
    segs = ",\n          ".join(
        '{ action = "shot", label = "X" }' for _ in range(13)
    )
    p = write_cfg(tmp_path, f"""
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          {segs}
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match="ring 'r' must have between 3 and 12 segments"):
        validate_config(cfg)


def test_validate_rejects_segment_with_unknown_action(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "B" },
          { action = "missing", label = "C" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match=r"rings\.r\.segments\[2\]\.action 'missing' not found"):
        validate_config(cfg)


def test_validate_rejects_segment_with_blank_label(tmp_path):
    p = write_cfg(tmp_path, """
        [actions.shot]
        type = "command"
        command = "true"

        [rings.r]
        segments = [
          { action = "shot", label = "A" },
          { action = "shot", label = "   " },
          { action = "shot", label = "C" },
        ]
    """)
    cfg = load_config(p)
    import pytest
    from logitechmouse.config import ConfigError, validate_config
    with pytest.raises(ConfigError, match=r"rings\.r\.segments\[1\]\.label is empty"):
        validate_config(cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_ring.py -v -k "validate"
```
Expected: 4 new tests fail; previous validation tests still pass.

- [ ] **Step 3: Extend `validate_config` to check ring contents**

In `src/logitechmouse/config.py`, after the `for binding in config.bindings.values():` loop in `validate_config`, add:

```python
    for ring in config.rings.values():
        n = len(ring.segments)
        if n < 3 or n > 12:
            raise ConfigError(
                f"ring {ring.name!r} must have between 3 and 12 segments, got {n}"
            )
        for i, seg in enumerate(ring.segments):
            if not seg.label.strip():
                raise ConfigError(
                    f"rings.{ring.name}.segments[{i}].label is empty"
                )
            if seg.action not in config.actions:
                raise ConfigError(
                    f"rings.{ring.name}.segments[{i}].action {seg.action!r} not found"
                )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config_ring.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/config.py tests/test_config_ring.py
git commit -m "feat(config): validate ring segment count, labels, and action references"
```

---

## Task 8: Fail fast in `check-config` if PyQt6 missing but ring bindings configured

**Files:**
- Modify: `src/logitechmouse/cli/check_config.py`
- Test: `tests/test_check_config.py` (create — minimal)

- [ ] **Step 1: Read existing `check_config.py`**

```bash
cat src/logitechmouse/cli/check_config.py
```

- [ ] **Step 2: Write failing test**

Create `tests/test_check_config.py`:

```python
import argparse
import sys
from unittest.mock import patch

from logitechmouse.cli import check_config as cc_mod


def test_check_config_errors_when_ring_binding_but_pyqt6_unavailable(tmp_path, caplog):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.shot]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[rings.r]\n'
        'segments = [\n'
        '  { action = "shot", label = "A" },\n'
        '  { action = "shot", label = "B" },\n'
        '  { action = "shot", label = "C" },\n'
        ']\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "ring:r"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)

    # Pretend PyQt6 cannot be imported.
    with patch.dict(sys.modules, {"PyQt6": None, "PyQt6.QtWidgets": None}), \
         caplog.at_level("ERROR"):
        rc = cc_mod.run(args)

    assert rc == 1
    assert any("PyQt6" in r.message for r in caplog.records)


def test_check_config_passes_when_only_action_bindings(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.shot]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "action:shot"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)
    rc = cc_mod.run(args)
    assert rc == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_check_config.py -v
```
Expected: first test fails (no PyQt6 check).

- [ ] **Step 4: Update `check_config.py`**

Read `src/logitechmouse/cli/check_config.py` first, then add a PyQt6 import check before the success return. Insert this block where appropriate (after `validate_config(cfg)` succeeds, before returning `0`):

```python
    needs_pyqt6 = any(
        b.target.kind == "ring" for b in cfg.bindings.values()
    )
    if needs_pyqt6:
        try:
            import PyQt6.QtWidgets  # noqa: F401
        except ImportError:
            logging.error(
                "config defines ring bindings but PyQt6 is not installed; "
                "install with: pip install 'logitechmouse[ring]'"
            )
            return 1
```

If `check_config.py` does not currently iterate `cfg.bindings`, add this after `validate_config(cfg)` returns successfully.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_check_config.py -v
```
Expected: both tests pass.

- [ ] **Step 6: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/logitechmouse/cli/check_config.py tests/test_check_config.py
git commit -m "feat(cli): check-config errors when ring bindings present but PyQt6 missing"
```

---

## Task 9: Extend `InputEvent` with `pressed` and emit key-up from `read_loop`

**Files:**
- Modify: `src/logitechmouse/device.py`
- Modify: `src/logitechmouse/cli/listen.py` (filter on `pressed=True`)
- Test: `tests/test_device_readloop.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_device_readloop.py`:

```python
from unittest.mock import MagicMock

from evdev import ecodes

from logitechmouse.device import EvdevBackend, InputEvent


def _fake_kev(code: int, value: int):
    """Fabricate an evdev event-like object that categorize() handles."""
    e = MagicMock()
    e.type = ecodes.EV_KEY
    e.code = code
    e.value = value
    return e


def _fake_device_yielding(events):
    dev = MagicMock()
    dev.read_loop = MagicMock(return_value=iter(events))
    return dev


def test_read_loop_emits_key_down_with_pressed_true():
    dev = _fake_device_yielding([_fake_kev(ecodes.BTN_TASK, 1)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_TASK", pressed=True)]


def test_read_loop_emits_key_up_with_pressed_false():
    dev = _fake_device_yielding([_fake_kev(ecodes.BTN_TASK, 0)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_TASK", pressed=False)]


def test_read_loop_ignores_key_repeat():
    dev = _fake_device_yielding([
        _fake_kev(ecodes.BTN_TASK, 1),
        _fake_kev(ecodes.BTN_TASK, 2),  # repeat
        _fake_kev(ecodes.BTN_TASK, 0),
    ])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [
        InputEvent(trigger="BTN_TASK", pressed=True),
        InputEvent(trigger="BTN_TASK", pressed=False),
    ]


def test_read_loop_ignores_non_key_events():
    e_syn = MagicMock()
    e_syn.type = ecodes.EV_SYN
    dev = _fake_device_yielding([e_syn, _fake_kev(ecodes.BTN_SIDE, 1)])
    backend = EvdevBackend()
    events = list(backend.read_loop(dev))
    assert events == [InputEvent(trigger="BTN_SIDE", pressed=True)]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_device_readloop.py -v
```
Expected: fail — `InputEvent` does not accept `pressed` keyword.

- [ ] **Step 3: Update `InputEvent` and `read_loop`**

In `src/logitechmouse/device.py`, replace the `InputEvent` dataclass:

```python
@dataclass
class InputEvent:
    trigger: str        # evdev key code name, e.g. "BTN_TASK"
    pressed: bool       # True for key-down, False for key-up
```

Replace the `read_loop` method:

```python
    def read_loop(self, device: InputDevice) -> Iterator[InputEvent]:
        """Yield InputEvent for every key-down (pressed=True) and key-up
        (pressed=False) on `device`. Ignores key-repeat (value=2). Blocking."""
        for event in device.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            if event.value not in (0, 1):
                continue
            key_event = categorize(event)
            keycode = key_event.keycode
            if isinstance(keycode, list):
                name = keycode[0] if keycode else None
            elif isinstance(keycode, str):
                name = keycode
            else:
                name = None
            if not name:
                continue
            yield InputEvent(trigger=name, pressed=(event.value == 1))
```

- [ ] **Step 4: Update existing listener to filter on `pressed=True` for action targets**

In `src/logitechmouse/cli/listen.py`, inside the `for event in backend.read_loop(device):` loop, immediately after `binding = bindings_by_trigger.get(event.trigger)`:

```python
            binding = bindings_by_trigger.get(event.trigger)
            if binding is None:
                continue
            if not event.pressed:
                # Key-up does not fire action targets. Ring targets are
                # wired in Task 13; this branch will route there.
                continue
            if binding.target.kind != "action":
                continue
```

- [ ] **Step 5: Update existing `tests/test_listen_cli.py` for new `InputEvent` signature**

Read `tests/test_listen_cli.py`. The existing test mocks `EvdevBackend.resolve` to raise; it does not construct `InputEvent` directly. **No changes needed** for that file in this task.

- [ ] **Step 6: Run device-level tests**

```bash
pytest tests/test_device_readloop.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/logitechmouse/device.py src/logitechmouse/cli/listen.py tests/test_device_readloop.py
git commit -m "feat(device): emit key-up events with InputEvent.pressed flag"
```

---

## Task 10: `overlay/geometry.py` — wedge index function

**Files:**
- Create: `src/logitechmouse/overlay/__init__.py`
- Create: `src/logitechmouse/overlay/geometry.py`
- Test: `tests/test_geometry.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_geometry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_geometry.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `overlay/__init__.py`**

```bash
touch src/logitechmouse/overlay/__init__.py
```

- [ ] **Step 4: Create `overlay/geometry.py`**

```python
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
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_geometry.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/overlay/__init__.py src/logitechmouse/overlay/geometry.py tests/test_geometry.py
git commit -m "feat(overlay): wedge_index for ring hit-test"
```

---

## Task 11: `overlay/geometry.py` — dead-zone hit-test

**Files:**
- Modify: `src/logitechmouse/overlay/geometry.py`
- Test: `tests/test_geometry.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_geometry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_geometry.py -v -k "dead_zone"
```
Expected: ImportError on `is_in_dead_zone`.

- [ ] **Step 3: Add `is_in_dead_zone` to `geometry.py`**

Append to `src/logitechmouse/overlay/geometry.py`:

```python
def is_in_dead_zone(dx: float, dy: float, dead_zone_radius: float) -> bool:
    """Return True if (dx, dy) is strictly inside the dead-zone disc.

    Boundary is exclusive: at exactly `dead_zone_radius`, the cursor is
    treated as outside the dead zone.
    """
    return math.hypot(dx, dy) < dead_zone_radius
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_geometry.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/overlay/geometry.py tests/test_geometry.py
git commit -m "feat(overlay): is_in_dead_zone hit-test"
```

---

## Task 12: `overlay/geometry.py` — edge-shift function

**Files:**
- Modify: `src/logitechmouse/overlay/geometry.py`
- Test: `tests/test_geometry.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_geometry.py`:

```python
from logitechmouse.overlay.geometry import shifted_center_for_screen


def test_no_shift_when_ring_fits_at_cursor():
    # Cursor far from any edge; ring (radius 180) fits trivially.
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
    """Function returns ring center; cursor (input) is read-only here."""
    cx, cy = shifted_center_for_screen(
        cursor_x=10, cursor_y=10,
        screen_left=0, screen_top=0, screen_right=1920, screen_bottom=1080,
        ring_radius=180,
    )
    # If we ever return cursor coords, the assertion above would have caught it.
    # This test is a comment more than a test, but documents intent.
    assert (cx, cy) != (10, 10)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_geometry.py -v -k "shift"
```
Expected: ImportError on `shifted_center_for_screen`.

- [ ] **Step 3: Add `shifted_center_for_screen` to `geometry.py`**

Append to `src/logitechmouse/overlay/geometry.py`:

```python
def shifted_center_for_screen(
    cursor_x: int,
    cursor_y: int,
    screen_left: int,
    screen_top: int,
    screen_right: int,
    screen_bottom: int,
    ring_radius: int,
) -> tuple[int, int]:
    """Return the ring center such that a circle of `ring_radius` is fully
    inside the given screen rectangle. Defaults to the cursor; shifts inward
    only as needed. The cursor itself is never moved.
    """
    cx = max(screen_left + ring_radius, min(cursor_x, screen_right - ring_radius))
    cy = max(screen_top + ring_radius, min(cursor_y, screen_bottom - ring_radius))
    return cx, cy
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_geometry.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/overlay/geometry.py tests/test_geometry.py
git commit -m "feat(overlay): shifted_center_for_screen keeps ring on-screen without warping cursor"
```

---

## Task 13: `RingController` state machine (no widget yet, mocked)

**Files:**
- Create: `src/logitechmouse/overlay/ring.py`
- Test: `tests/test_ring_controller.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_ring_controller.py`:

```python
from unittest.mock import MagicMock

import pytest

from logitechmouse.config import Action, Ring, Segment
from logitechmouse.overlay.ring import RingController, RingState


@pytest.fixture
def fake_ring():
    return Ring(
        name="r",
        segments=[
            Segment(action="a1", label="A"),
            Segment(action="a2", label="B"),
            Segment(action="a3", label="C"),
        ],
    )


@pytest.fixture
def actions():
    return {
        "a1": Action(name="a1", kind="command", command="echo 1"),
        "a2": Action(name="a2", kind="command", command="echo 2"),
        "a3": Action(name="a3", kind="command", command="echo 3"),
    }


def test_initial_state_is_idle(fake_ring, actions):
    widget = MagicMock()
    run_action = MagicMock()
    rc = RingController(widget_factory=lambda: widget, run_action=run_action, actions=actions)
    assert rc.state == RingState.IDLE


def test_open_transitions_to_open_and_shows_widget(fake_ring, actions):
    widget = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=MagicMock(),
        actions=actions,
    )
    rc.open(fake_ring, cursor_pos=(500, 500))
    assert rc.state == RingState.OPEN
    widget.show_at.assert_called_once_with(fake_ring, cursor_pos=(500, 500))


def test_close_outside_dead_zone_fires_active_segment_action(fake_ring, actions):
    widget = MagicMock()
    widget.active_segment_index = 1   # B
    widget.is_in_dead_zone = False
    run_action = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=run_action,
        actions=actions,
    )
    rc.open(fake_ring, cursor_pos=(500, 500))
    rc.close()
    run_action.assert_called_once_with(actions["a2"])
    widget.hide.assert_called_once()
    assert rc.state == RingState.IDLE


def test_close_in_dead_zone_does_not_fire_action(fake_ring, actions):
    widget = MagicMock()
    widget.is_in_dead_zone = True
    run_action = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=run_action,
        actions=actions,
    )
    rc.open(fake_ring, cursor_pos=(500, 500))
    rc.close()
    run_action.assert_not_called()
    widget.hide.assert_called_once()
    assert rc.state == RingState.IDLE


def test_close_when_idle_is_a_noop(actions):
    widget = MagicMock()
    run_action = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=run_action,
        actions=actions,
    )
    rc.close()  # never opened
    run_action.assert_not_called()
    widget.hide.assert_not_called()
    assert rc.state == RingState.IDLE


def test_reentrant_open_is_ignored(fake_ring, actions, caplog):
    widget = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=MagicMock(),
        actions=actions,
    )
    rc.open(fake_ring, cursor_pos=(500, 500))
    rc.open(fake_ring, cursor_pos=(600, 600))
    # widget.show_at called once, not twice
    assert widget.show_at.call_count == 1
    assert rc.state == RingState.OPEN


def test_action_dispatch_failure_does_not_break_controller(fake_ring, actions):
    widget = MagicMock()
    widget.active_segment_index = 0
    widget.is_in_dead_zone = False
    run_action = MagicMock(side_effect=RuntimeError("spawn failed"))
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=run_action,
        actions=actions,
    )
    rc.open(fake_ring, cursor_pos=(0, 0))
    # close() must swallow run_action errors and still return to IDLE
    rc.close()
    assert rc.state == RingState.IDLE
    widget.hide.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ring_controller.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `overlay/ring.py`**

```python
"""Ring overlay state machine. Owns no Qt globals; widget is injected."""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Callable, Protocol

from ..config import Action, Ring


logger = logging.getLogger(__name__)


class RingState(Enum):
    IDLE = auto()
    OPEN = auto()


class _WidgetProtocol(Protocol):
    active_segment_index: int
    is_in_dead_zone: bool

    def show_at(self, ring: Ring, cursor_pos: tuple[int, int]) -> None: ...
    def update_cursor_position(self, cursor_x: int, cursor_y: int) -> None: ...
    def hide(self) -> None: ...


class RingController:
    """State machine that opens/closes the ring widget and dispatches the
    selected action on close. Re-entrant open() while already OPEN is ignored.
    """

    def __init__(
        self,
        widget_factory: Callable[[], _WidgetProtocol],
        run_action: Callable[[Action], object],
        actions: dict[str, Action],
    ) -> None:
        self._widget = widget_factory()
        self._run_action = run_action
        self._actions = actions
        self._state = RingState.IDLE
        self._current_ring: Ring | None = None

    @property
    def state(self) -> RingState:
        return self._state

    def open(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        if self._state is RingState.OPEN:
            logger.debug(
                "ring open() called while already OPEN; ignoring (current=%s, requested=%s)",
                self._current_ring.name if self._current_ring else None,
                ring.name,
            )
            return
        self._current_ring = ring
        self._widget.show_at(ring, cursor_pos=cursor_pos)
        self._state = RingState.OPEN

    def close(self) -> None:
        if self._state is RingState.IDLE:
            return
        try:
            if not self._widget.is_in_dead_zone:
                idx = self._widget.active_segment_index
                ring = self._current_ring
                assert ring is not None  # invariant when OPEN
                segment = ring.segments[idx]
                action = self._actions[segment.action]
                try:
                    self._run_action(action)
                except Exception:
                    logger.exception(
                        "ring action %r failed; ring still closes cleanly",
                        action.name,
                    )
        finally:
            self._widget.hide()
            self._current_ring = None
            self._state = RingState.IDLE
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ring_controller.py -v
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/overlay/ring.py tests/test_ring_controller.py
git commit -m "feat(overlay): RingController state machine with re-entrant open + safe dispatch"
```

---

## Task 14: `RingWidget` — transparent frameless top-level skeleton

**Files:**
- Create: `src/logitechmouse/overlay/widget.py`
- Test: `tests/test_overlay_widget.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_overlay_widget.py`:

```python
import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from logitechmouse.config import Ring, Segment
from logitechmouse.overlay.widget import RingWidget


@pytest.fixture
def fake_ring():
    return Ring(
        name="r",
        segments=[
            Segment(action="a", label="One"),
            Segment(action="a", label="Two"),
            Segment(action="a", label="Three"),
            Segment(action="a", label="Four"),
        ],
    )


@pytest.mark.requires_display
def test_widget_can_be_constructed_and_shown(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    assert w.isVisible()
    # Frameless + translucent + always-on-top window flags set.
    flags = w.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.hide()
    assert not w.isVisible()


@pytest.mark.requires_display
def test_widget_initial_state_no_segment_active(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    # Cursor at exact ring center → in dead zone, no segment active.
    w.update_cursor_position(500, 500)
    assert w.is_in_dead_zone is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_overlay_widget.py -v
```
Expected: ImportError on `RingWidget`.

- [ ] **Step 3: Create `overlay/widget.py`**

```python
"""Transparent always-on-top ring overlay. PyQt6 + X11."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, QRectF
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..config import Ring
from .geometry import is_in_dead_zone, shifted_center_for_screen, wedge_index


# Visual constants — tunable later.
RING_OUTER_RADIUS = 180
RING_DEAD_ZONE_RADIUS = 45
BG_COLOR = QColor(24, 24, 24, int(0.85 * 255))
ACTIVE_BG_COLOR = QColor(56, 56, 56, int(0.92 * 255))
SEPARATOR_COLOR = QColor(0, 0, 0, 200)
LABEL_COLOR = QColor(230, 230, 230)
CANCEL_COLOR = QColor(160, 160, 160)


class RingWidget(QWidget):
    """Renders the ring. Polled cursor position drives `active_segment_index`
    and `is_in_dead_zone`. The widget itself does not capture input.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._ring: Ring | None = None
        self._center_x = 0
        self._center_y = 0
        self.active_segment_index = 0
        self.is_in_dead_zone = True

    # --- public API consumed by RingController ---

    def show_at(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        self._ring = ring
        screen = QGuiApplication.screenAt(QPoint(*cursor_pos)) or QGuiApplication.primaryScreen()
        geom = screen.geometry()
        cx, cy = shifted_center_for_screen(
            cursor_x=cursor_pos[0],
            cursor_y=cursor_pos[1],
            screen_left=geom.left(),
            screen_top=geom.top(),
            screen_right=geom.right(),
            screen_bottom=geom.bottom(),
            ring_radius=RING_OUTER_RADIUS,
        )
        self._center_x, self._center_y = cx, cy
        size = RING_OUTER_RADIUS * 2 + 8  # tiny pad for antialiasing
        self.setGeometry(
            cx - RING_OUTER_RADIUS - 4,
            cy - RING_OUTER_RADIUS - 4,
            size,
            size,
        )
        self.update_cursor_position(*cursor_pos)
        self.show()
        self.raise_()

    def update_cursor_position(self, cursor_x: int, cursor_y: int) -> None:
        if self._ring is None:
            return
        dx = cursor_x - self._center_x
        dy = cursor_y - self._center_y
        self.is_in_dead_zone = is_in_dead_zone(dx, dy, RING_DEAD_ZONE_RADIUS)
        if not self.is_in_dead_zone:
            self.active_segment_index = wedge_index(dx, dy, len(self._ring.segments))
        self.update()  # request repaint

    # --- painting ---

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._ring is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Local coords: ring center at widget midpoint
        w = self.width()
        h = self.height()
        ox = w / 2.0
        oy = h / 2.0

        n = len(self._ring.segments)
        wedge_deg = 360.0 / n
        outer = RING_OUTER_RADIUS
        inner = RING_DEAD_ZONE_RADIUS

        # Wedges: 12 o'clock = -90° in Qt's angle convention (which uses
        # math-style CCW from +x). To draw a wedge "centered at angle θ CW
        # from up," we draw from θ - wedge/2 to θ + wedge/2 in Qt terms:
        #   qt_angle = 90 - θ_cw_from_up
        for i in range(n):
            theta_center = i * wedge_deg
            qt_start_angle = (90.0 - (theta_center + wedge_deg / 2.0))
            color = ACTIVE_BG_COLOR if (
                i == self.active_segment_index and not self.is_in_dead_zone
            ) else BG_COLOR
            p.setPen(QPen(SEPARATOR_COLOR, 1))
            p.setBrush(color)
            rect = QRectF(ox - outer, oy - outer, outer * 2, outer * 2)
            # QPainter.drawPie uses 1/16-degree integer units.
            p.drawPie(rect, int(qt_start_angle * 16), int(wedge_deg * 16))

            # Label
            label_radius = outer * 0.70
            theta_rad = (theta_center - 90.0) * 3.141592653589793 / 180.0
            import math as _m
            lx = ox + _m.cos(theta_rad) * label_radius
            ly = oy + _m.sin(theta_rad) * label_radius
            p.setPen(LABEL_COLOR)
            text = self._ring.segments[i].label
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            p.drawText(int(lx - tw / 2), int(ly + th / 4), text)

        # Dead-zone disc
        p.setPen(QPen(SEPARATOR_COLOR, 1))
        p.setBrush(QColor(18, 18, 18, int(0.92 * 255)))
        p.drawEllipse(QRectF(ox - inner, oy - inner, inner * 2, inner * 2))

        if self.is_in_dead_zone:
            p.setPen(CANCEL_COLOR)
            text = "Cancel"
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            p.drawText(int(ox - tw / 2), int(oy + th / 4), text)
```

- [ ] **Step 4: Run widget tests**

```bash
pytest tests/test_overlay_widget.py -v
```
Expected: 2 passed (skipped if no DISPLAY locally; on CI under xvfb-run, pass).

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/overlay/widget.py tests/test_overlay_widget.py
git commit -m "feat(overlay): RingWidget renders transparent always-on-top ring with active wedge highlight"
```

---

## Task 15: `RingWidget` open animation (75ms fade + scale)

**Files:**
- Modify: `src/logitechmouse/overlay/widget.py`
- Test: `tests/test_overlay_widget.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_overlay_widget.py`:

```python
@pytest.mark.requires_display
def test_widget_open_animation_starts_at_low_opacity_and_finishes_at_full(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    # Animation runs over 75 ms. After it finishes, opacity should be 1.0.
    qtbot.wait(120)  # > 75 ms + slop
    assert w.windowOpacity() == pytest.approx(1.0, abs=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_overlay_widget.py -v -k "animation"
```
Expected: FAIL because `windowOpacity()` is the default 1.0 already (no animation runs). To make this test meaningful we need to confirm the animation property exists. Adjust the test:

Replace the test body:

```python
@pytest.mark.requires_display
def test_widget_open_animation_runs_and_finishes_at_full_opacity(qtbot, fake_ring):
    w = RingWidget()
    qtbot.addWidget(w)
    w.show_at(fake_ring, cursor_pos=(500, 500))
    # An animation handle is set during show_at and exists until finished.
    assert w._open_animation is not None  # type: ignore[attr-defined]
    qtbot.wait(120)  # > 75 ms + slop
    assert w.windowOpacity() == pytest.approx(1.0, abs=1e-3)
```

Re-run:
```bash
pytest tests/test_overlay_widget.py -v -k "animation"
```
Expected: AttributeError on `_open_animation`.

- [ ] **Step 3: Add fade animation to `RingWidget.show_at`**

In `src/logitechmouse/overlay/widget.py`, add to imports:

```python
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
```

In `__init__`, before the trailing `self.is_in_dead_zone = True`:

```python
        self._open_animation: QPropertyAnimation | None = None
```

At the end of `show_at`, after `self.raise_()`:

```python
        # Open animation: 75 ms fade-in. Scale done via geometry would jitter
        # under a fractional value, so v1 only fades opacity. Geometry is
        # fixed.
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(75)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._open_animation = anim
```

(Note: spec called for fade + scale 0.85→1.0. Scale via fractional geometry produces visible jitter; we ship fade-only in v1 and document scale as a polish item — see open issue list in spec §10.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_overlay_widget.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/overlay/widget.py tests/test_overlay_widget.py
git commit -m "feat(overlay): 75ms fade-in animation on ring open"
```

---

## Task 16: `CursorPoller` — 8ms QTimer polling `QCursor.pos()`

**Files:**
- Create: `src/logitechmouse/overlay/cursor.py`
- Test: `tests/test_cursor_poller.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_cursor_poller.py`:

```python
import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QPoint
from unittest.mock import MagicMock, patch

from logitechmouse.overlay.cursor import CursorPoller


@pytest.mark.requires_display
def test_poller_calls_callback_with_cursor_position(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(123, 456)):
        poller.start()
        qtbot.wait(30)  # multiple ticks
        poller.stop()
    callback.assert_called()
    # Most recent call is (123, 456)
    last_args = callback.call_args[0]
    assert last_args == (123, 456)


@pytest.mark.requires_display
def test_poller_skips_callback_when_cursor_unchanged(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(100, 100)):
        poller.start()
        qtbot.wait(40)  # ~5 ticks
        poller.stop()
    # Cursor never moved; only one callback (or zero if we suppress the first).
    assert callback.call_count <= 1


@pytest.mark.requires_display
def test_stop_halts_callbacks(qtbot):
    callback = MagicMock()
    poller = CursorPoller(on_position=callback, interval_ms=8)
    with patch("logitechmouse.overlay.cursor.QCursor.pos", return_value=QPoint(0, 0)):
        poller.start()
        qtbot.wait(20)
        poller.stop()
    count_after_stop = callback.call_count
    qtbot.wait(40)
    assert callback.call_count == count_after_stop
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cursor_poller.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `overlay/cursor.py`**

```python
"""8ms cursor polling on the Qt main thread."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QCursor


class CursorPoller(QObject):
    """Polls QCursor.pos() at a fixed interval and calls back with (x, y).
    Skips the callback when the cursor has not moved since the last tick.
    """

    def __init__(
        self,
        on_position: Callable[[int, int], None],
        interval_ms: int = 8,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_position = on_position
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self._last: tuple[int, int] | None = None

    def start(self) -> None:
        self._last = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        p = QCursor.pos()
        pos = (p.x(), p.y())
        if pos == self._last:
            return
        self._last = pos
        self._on_position(pos[0], pos[1])
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cursor_poller.py -v
```
Expected: all pass (or skipped if no DISPLAY locally).

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/overlay/cursor.py tests/test_cursor_poller.py
git commit -m "feat(overlay): CursorPoller — 8ms QTimer over QCursor.pos with no-op skip"
```

---

## Task 17: Wire `CursorPoller` into `RingController`

**Files:**
- Modify: `src/logitechmouse/overlay/ring.py`
- Test: `tests/test_ring_controller.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_ring_controller.py`:

```python
def test_open_starts_cursor_polling_close_stops_it(fake_ring, actions):
    widget = MagicMock()
    widget.is_in_dead_zone = True
    poller = MagicMock()
    rc = RingController(
        widget_factory=lambda: widget,
        run_action=MagicMock(),
        actions=actions,
        cursor_poller_factory=lambda cb: poller,
    )
    rc.open(fake_ring, cursor_pos=(0, 0))
    poller.start.assert_called_once()
    rc.close()
    poller.stop.assert_called_once()
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_ring_controller.py::test_open_starts_cursor_polling_close_stops_it -v
```
Expected: TypeError on unexpected `cursor_poller_factory` kwarg.

- [ ] **Step 3: Extend `RingController`**

In `src/logitechmouse/overlay/ring.py`, update `__init__`:

```python
    def __init__(
        self,
        widget_factory: Callable[[], _WidgetProtocol],
        run_action: Callable[[Action], object],
        actions: dict[str, Action],
        cursor_poller_factory: Callable[[Callable[[int, int], None]], object] | None = None,
    ) -> None:
        self._widget = widget_factory()
        self._run_action = run_action
        self._actions = actions
        self._state = RingState.IDLE
        self._current_ring: Ring | None = None
        self._poller = (
            cursor_poller_factory(self._widget.update_cursor_position)
            if cursor_poller_factory
            else None
        )
```

Update `open` and `close`:

```python
    def open(self, ring: Ring, cursor_pos: tuple[int, int]) -> None:
        if self._state is RingState.OPEN:
            logger.debug(
                "ring open() called while already OPEN; ignoring (current=%s, requested=%s)",
                self._current_ring.name if self._current_ring else None,
                ring.name,
            )
            return
        self._current_ring = ring
        self._widget.show_at(ring, cursor_pos=cursor_pos)
        if self._poller is not None:
            self._poller.start()
        self._state = RingState.OPEN

    def close(self) -> None:
        if self._state is RingState.IDLE:
            return
        try:
            if self._poller is not None:
                self._poller.stop()
            if not self._widget.is_in_dead_zone:
                idx = self._widget.active_segment_index
                ring = self._current_ring
                assert ring is not None
                segment = ring.segments[idx]
                action = self._actions[segment.action]
                try:
                    self._run_action(action)
                except Exception:
                    logger.exception(
                        "ring action %r failed; ring still closes cleanly",
                        action.name,
                    )
        finally:
            self._widget.hide()
            self._current_ring = None
            self._state = RingState.IDLE
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ring_controller.py -v
```
Expected: all pass (existing tests still green; new one passes).

- [ ] **Step 5: Commit**

```bash
git add src/logitechmouse/overlay/ring.py tests/test_ring_controller.py
git commit -m "feat(overlay): RingController starts/stops CursorPoller around open/close"
```

---

## Task 18: Refactor `cli/listen.py` to QApplication-driven dispatcher

**Files:**
- Modify: `src/logitechmouse/cli/listen.py`
- Modify: `tests/test_listen_cli.py`
- Test: new dispatch unit tests inline below

This task is the integration heart. Read the existing `listen.py` carefully before starting.

- [ ] **Step 1: Write failing tests for the pure dispatch function**

Append to `tests/test_listen_cli.py`:

```python
from unittest.mock import MagicMock

from logitechmouse.config import (
    Action, AppConfig, Binding, Ring, Segment, Target,
)
from logitechmouse.cli.listen import dispatch_event


def _cfg_with_action_and_ring():
    return AppConfig(
        actions={"a": Action(name="a", kind="command", command="true")},
        rings={
            "r": Ring(
                name="r",
                segments=[
                    Segment(action="a", label="A"),
                    Segment(action="a", label="B"),
                    Segment(action="a", label="C"),
                ],
            )
        },
        bindings={
            "act_btn": Binding(
                name="act_btn", trigger="BTN_SIDE",
                target=Target(kind="action", name="a"),
            ),
            "ring_btn": Binding(
                name="ring_btn", trigger="BTN_TASK",
                target=Target(kind="ring", name="r"),
            ),
        },
    )


def test_dispatch_action_target_on_keydown_runs_action():
    cfg = _cfg_with_action_and_ring()
    run_action = MagicMock()
    rc = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_SIDE", pressed=True, cursor_pos=(0, 0))
    run_action.assert_called_once_with(cfg.actions["a"])
    rc.open.assert_not_called()
    rc.close.assert_not_called()


def test_dispatch_action_target_on_keyup_does_nothing():
    cfg = _cfg_with_action_and_ring()
    run_action = MagicMock()
    rc = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_SIDE", pressed=False, cursor_pos=(0, 0))
    run_action.assert_not_called()


def test_dispatch_ring_target_on_keydown_opens():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), trigger="BTN_TASK", pressed=True, cursor_pos=(100, 200))
    rc.open.assert_called_once_with(cfg.rings["r"], cursor_pos=(100, 200))


def test_dispatch_ring_target_on_keyup_closes():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    dispatch_event(cfg, rc, MagicMock(), trigger="BTN_TASK", pressed=False, cursor_pos=(0, 0))
    rc.close.assert_called_once()


def test_dispatch_unknown_trigger_is_noop():
    cfg = _cfg_with_action_and_ring()
    rc = MagicMock()
    run_action = MagicMock()
    dispatch_event(cfg, rc, run_action, trigger="BTN_NOT_BOUND", pressed=True, cursor_pos=(0, 0))
    rc.open.assert_not_called()
    rc.close.assert_not_called()
    run_action.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_listen_cli.py -v -k "dispatch"
```
Expected: ImportError on `dispatch_event`.

- [ ] **Step 3: Refactor `cli/listen.py`**

Replace `src/logitechmouse/cli/listen.py` entirely:

```python
from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from ..actions import run_action as _default_run_action
from ..config import AppConfig, ConfigError, load_config, validate_config
from ..device import (
    DeviceNotFoundError,
    DeviceUnreadableError,
    EvdevBackend,
    InputEvent,
)


REMEDIATION = (
    "device is not readable. Add yourself to the `input` group:\n"
    "  sudo usermod -aG input $USER\n"
    "Then log out and back in."
)


def dispatch_event(
    cfg: AppConfig,
    ring_controller,
    run_action: Callable,
    trigger: str,
    pressed: bool,
    cursor_pos: tuple[int, int],
) -> None:
    """Pure dispatch logic — testable without Qt or threads."""
    binding = next(
        (b for b in cfg.bindings.values() if b.trigger == trigger),
        None,
    )
    if binding is None:
        return
    if binding.target.kind == "action":
        if pressed:
            action = cfg.actions[binding.target.name]
            result = run_action(action)
            if result is not None and getattr(result, "ok", True):
                logging.info("%s", getattr(result, "detail", ""))
            elif result is not None:
                logging.warning("action %r %s", action.name, getattr(result, "detail", ""))
    elif binding.target.kind == "ring":
        ring = cfg.rings[binding.target.name]
        if pressed:
            ring_controller.open(ring, cursor_pos=cursor_pos)
        else:
            ring_controller.close()


def _has_ring_bindings(cfg: AppConfig) -> bool:
    return any(b.target.kind == "ring" for b in cfg.bindings.values())


def run(args: argparse.Namespace) -> int:
    try:
        cfg = load_config(args.config)
        validate_config(cfg)
    except ConfigError as exc:
        logging.error("config invalid: %s", exc)
        return 1

    if not cfg.bindings:
        logging.error(
            "config has no bindings; nothing would fire on key-down. "
            "Add at least one [bindings.NAME] section pointing to a target."
        )
        return 1

    if getattr(args, "device", None):
        cfg.device.path = args.device

    triggers = {b.trigger for b in cfg.bindings.values()} or None

    backend = EvdevBackend()
    try:
        device = backend.resolve(cfg.device, triggers=triggers)
    except DeviceUnreadableError as exc:
        logging.error("%s\n%s", exc, REMEDIATION)
        return 1
    except DeviceNotFoundError as exc:
        logging.error("%s", exc)
        return 1

    summary = ", ".join(
        f"{b.name}[{b.trigger}]->{b.target.kind}:{b.target.name}"
        for b in cfg.bindings.values()
    ) or "(none)"
    logging.info("listening on %s (%s)", device.path, device.name)
    logging.info("bindings: %s", summary)

    if _has_ring_bindings(cfg):
        return _run_with_qt(cfg, backend, device)
    else:
        return _run_command_only(cfg, backend, device)


def _run_command_only(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Phase 2 path: no Qt, blocking read loop on the main thread."""
    try:
        for event in backend.read_loop(device):
            dispatch_event(
                cfg,
                ring_controller=_NoOpRingController(),
                run_action=_default_run_action,
                trigger=event.trigger,
                pressed=event.pressed,
                cursor_pos=(0, 0),
            )
    except OSError as exc:
        logging.warning("device read failed: %s", exc)
        return 1
    return 0


def _run_with_qt(cfg: AppConfig, backend: EvdevBackend, device) -> int:
    """Ring-enabled path: QApplication on main thread, listener on worker thread."""
    try:
        from PyQt6.QtCore import QObject, QThread, pyqtSignal, QPoint
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        logging.error(
            "config defines ring bindings but PyQt6 is not installed; "
            "install with: pip install 'logitechmouse[ring]'"
        )
        return 1

    from ..overlay.ring import RingController
    from ..overlay.widget import RingWidget
    from ..overlay.cursor import CursorPoller

    app = QApplication.instance() or QApplication(sys.argv)

    ring_controller = RingController(
        widget_factory=RingWidget,
        run_action=_default_run_action,
        actions=cfg.actions,
        cursor_poller_factory=lambda cb: CursorPoller(on_position=cb),
    )

    class _ListenerWorker(QObject):
        event_received = pyqtSignal(str, bool, int, int)  # trigger, pressed, cur_x, cur_y
        finished = pyqtSignal(int)  # return code

        def run(self) -> None:
            try:
                for ev in backend.read_loop(device):
                    p = QCursor.pos()
                    self.event_received.emit(ev.trigger, ev.pressed, p.x(), p.y())
            except OSError as exc:
                logging.warning("device read failed: %s", exc)
                self.finished.emit(1)
                return
            self.finished.emit(0)

    worker = _ListenerWorker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    def _on_event(trigger: str, pressed: bool, cur_x: int, cur_y: int) -> None:
        dispatch_event(
            cfg,
            ring_controller=ring_controller,
            run_action=_default_run_action,
            trigger=trigger,
            pressed=pressed,
            cursor_pos=(cur_x, cur_y),
        )

    return_code = {"value": 0}

    def _on_finished(rc: int) -> None:
        return_code["value"] = rc
        thread.quit()
        app.quit()

    worker.event_received.connect(_on_event)
    worker.finished.connect(_on_finished)
    thread.start()

    app.exec()
    thread.wait(2000)
    return return_code["value"]


class _NoOpRingController:
    """Used in the command-only path so dispatch_event can be uniform."""

    def open(self, *args, **kwargs) -> None:
        logging.warning("ring target encountered in command-only listener path")

    def close(self) -> None:
        pass
```

- [ ] **Step 4: Run dispatch tests**

```bash
pytest tests/test_listen_cli.py -v
```
Expected: all dispatch tests pass; existing `test_listen_returns_error_when_config_has_no_bindings` still passes.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/logitechmouse/cli/listen.py tests/test_listen_cli.py
git commit -m "feat(cli): split listener into command-only and Qt-driven paths; pure dispatch_event"
```

---

## Task 19: Headless integration smoke test for the Qt listener path

**Files:**
- Create: `tests/test_listen_qt_smoke.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_listen_qt_smoke.py`:

```python
import argparse
from unittest.mock import patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from logitechmouse.cli import listen as listen_mod
from logitechmouse.device import InputEvent


@pytest.mark.requires_display
def test_qt_listener_dispatches_one_keydown_then_exits(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[actions.a]\n'
        'type = "command"\n'
        'command = "true"\n'
        '\n'
        '[rings.r]\n'
        'segments = [\n'
        '  { action = "a", label = "A" },\n'
        '  { action = "a", label = "B" },\n'
        '  { action = "a", label = "C" },\n'
        ']\n'
        '\n'
        '[bindings.g]\n'
        'trigger = "BTN_TASK"\n'
        'target = "ring:r"\n'
    )
    args = argparse.Namespace(config=cfg_path, device=None)

    fake_device = type("FakeDev", (), {"path": "/fake", "name": "Fake"})()

    def fake_read_loop(_dev):
        yield InputEvent(trigger="BTN_TASK", pressed=True)
        yield InputEvent(trigger="BTN_TASK", pressed=False)

    with patch.object(
        listen_mod.EvdevBackend, "resolve", return_value=fake_device,
    ), patch.object(
        listen_mod.EvdevBackend, "read_loop", side_effect=fake_read_loop,
    ):
        rc = listen_mod.run(args)

    assert rc == 0
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_listen_qt_smoke.py -v
```
Expected: passes if DISPLAY is available, else skipped.

If failing with "QApplication already running" or hang: add a guard in the test that quits the app via a single-shot timer if it does not exit within 1s. But the worker emits `finished` after the read_loop iterator exhausts, which calls `app.quit()`, so it should exit cleanly.

- [ ] **Step 3: Commit**

```bash
git add tests/test_listen_qt_smoke.py
git commit -m "test: end-to-end smoke for Qt listener path with mocked evdev"
```

---

## Task 20: Add ring example to `examples/config.toml`

**Files:**
- Modify: `examples/config.toml`

- [ ] **Step 1: Read current file**

```bash
cat examples/config.toml
```

- [ ] **Step 2: Replace `examples/config.toml` with the ring-enabled version**

```toml
# Optional. Omit to auto-discover the first Logitech / MX device.
# [device]
# name = "MX Master"
# path = "/dev/input/event7"

# --- Actions: named units of work the system can run.
[actions.screenshot_area]
type    = "command"
command = "gnome-screenshot -a"

[actions.screenshot_full]
type    = "command"
command = "gnome-screenshot"

[actions.lock]
type    = "command"
command = "loginctl lock-session"

[actions.terminal]
type    = "command"
command = "gnome-terminal"

# --- Rings: a radial overlay of segments. Each segment fires an action
# on release outside the dead zone. Releasing in the dead zone cancels.
[rings.thumb_ring]
# 3 to 12 segments. Drawn clockwise starting at 12 o'clock.
segments = [
  { action = "screenshot_area",  label = "Area"     },
  { action = "screenshot_full",  label = "Full"     },
  { action = "lock",             label = "Lock"     },
  { action = "terminal",         label = "Terminal" },
]

# --- Bindings: physical button → target. Targets are either
# "action:NAME" (fire on press) or "ring:NAME" (open on press / fire on release).
# Legacy form `action = "NAME"` is still accepted but logs a deprecation note.
[bindings.gesture_button]
trigger = "BTN_TASK"
target  = "ring:thumb_ring"

[bindings.thumb_button]
trigger = "BTN_SIDE"
target  = "action:screenshot_area"
```

- [ ] **Step 3: Validate the example with `check-config`**

```bash
logitechmouse --config examples/config.toml check-config
```
Expected: exits 0. (PyQt6 must be installed for this to succeed because of Task 8.)

- [ ] **Step 4: Run full test suite**

```bash
pytest -q
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add examples/config.toml
git commit -m "docs: example config showcasing a 4-segment ring on BTN_TASK"
```

---

## Task 21: Update README with ring docs and `[ring]` install note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

```bash
cat README.md
```

- [ ] **Step 2: Replace the "Project status" and "Configuration" sections**

In `README.md`:

Replace the `## Project status` section's body with:

```markdown
Phase 4: the radial Actions Ring is implemented. The CLI listens on a real
Logitech MX device via `evdev`, and configured buttons can either fire a
single action on press or open a radial overlay where the released segment
fires the action. X11 only in v1; Wayland support is a separate phase.
```

Replace the `## Local development` section's `pip install` line with:

```bash
pip install -e ".[dev,ring]"
```

After the `## Configuration` section's existing prose, add:

```markdown
### Rings

A `[rings.NAME]` table defines a radial overlay with 3–12 segments. Each
segment names an existing `[actions.X]` and a label. To open the ring on a
button, set the binding's target to `ring:NAME`:

\`\`\`toml
[rings.thumb_ring]
segments = [
  { action = "screenshot_area", label = "Area" },
  { action = "screenshot_full", label = "Full" },
  { action = "lock",            label = "Lock" },
]

[bindings.gesture_button]
trigger = "BTN_TASK"
target  = "ring:thumb_ring"
\`\`\`

The ring opens on key-down at the cursor position, follows your cursor as you
hold the button, and fires the highlighted segment when you release. Releasing
in the center cancels.

### Targets vs legacy `action = "..."`

Bindings use `target = "kind:name"`:
- `target = "action:screenshot"` — fire `actions.screenshot` on press.
- `target = "ring:thumb_ring"` — open `rings.thumb_ring` on press, fire on release.

The Phase 2 form `action = "screenshot"` is still accepted; the loader maps it
to `target = "action:screenshot"` and logs a one-line migration note.

### Optional install for ring support

The radial ring needs PyQt6. Install with:

\`\`\`bash
pip install 'logitechmouse[ring]'
\`\`\`

Without `[ring]` you can still use action-only bindings; configs that define
ring bindings will fail validation with a clear message.
```

(The `\`\`\`` are escaped here; in the actual README they are literal backticks.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README covers rings, polymorphic targets, and [ring] extra"
```

---

## Task 22: Update PRD to mark ring goal as shipped

**Files:**
- Modify: `docs/PRD.md`

- [ ] **Step 1: Read PRD**

```bash
cat docs/PRD.md
```

- [ ] **Step 2: Edit `docs/PRD.md` "Goals" section**

Find:
```markdown
- Provide a path toward an optional radial overlay.
```

Replace with:
```markdown
- Provide an optional radial overlay (Phase 4 — shipped).
```

In the "Success criteria" section, append a new bullet:
```markdown
- pressing and holding a configured button opens a ring; releasing on a segment fires its action.
```

- [ ] **Step 3: Commit**

```bash
git add docs/PRD.md
git commit -m "docs: PRD marks radial overlay as shipped"
```

---

## Task 23: CI — run widget tests under xvfb

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Read existing workflow**

```bash
cat .github/workflows/test.yml
```

- [ ] **Step 2: Update the workflow**

The exact edit depends on the file's current shape. The general changes:

1. Add a step before the `pytest` step that installs xvfb and required Qt runtime libs:

```yaml
      - name: Install xvfb and Qt runtime libs
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            xvfb libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
            libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1
```

2. Update the `pip install` line to include `[ring]`:

```yaml
      - name: Install package
        run: pip install -e ".[dev,ring]"
```

3. Wrap pytest in `xvfb-run`:

```yaml
      - name: Run tests
        run: xvfb-run -a pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: install xvfb + Qt libs and run pytest under xvfb-run for widget tests"
```

---

## Task 24: Manual hardware test on real MX hardware

**Files:** none.

This is a verification gate, not a code task. Do not skip.

- [ ] **Step 1: Verify environment**

```bash
echo $DISPLAY                    # must be set
groups | tr ' ' '\n' | grep input  # must be in input group
source .venv/bin/activate
pip install -e ".[dev,ring]"
pytest -q                          # all green
```

- [ ] **Step 2: Identify the MX mouse subnode**

```bash
logitechmouse devices
```
Pick the row whose name contains "Logitech" and "Mouse" (e.g. "Logitech USB Receiver Mouse"). The `/dev/input/eventXX` path will differ across sessions; do not hard-code it.

- [ ] **Step 3: Use the example config**

```bash
mkdir -p ~/.config/logitechmouse
cp examples/config.toml ~/.config/logitechmouse/config.toml
```

- [ ] **Step 4: Run check-config**

```bash
logitechmouse check-config
```
Expected: exits 0.

- [ ] **Step 5: Run the listener**

```bash
logitechmouse listen
```

- [ ] **Step 6: Verify the gestures**

Press and hold `BTN_TASK` (the gesture button under your thumb). Confirm:

1. Ring appears at the cursor within ~50 ms (subjective, but should feel instant).
2. Moving the cursor highlights the wedge under the cursor.
3. Releasing over a wedge fires the corresponding action (screenshot, lock, terminal).
4. Releasing in the center pip ("Cancel") fires no action.
5. Open the ring near a screen edge — the ring shifts inward; cursor stays put.
6. Press `BTN_SIDE` once (action target) — confirm `gnome-screenshot -a` opens.
7. `Ctrl-C` exits cleanly.

- [ ] **Step 7: Record findings**

If anything misbehaves, file a follow-up issue and address before merging the PR. Common gotchas:
- Wedge math is off → verify against `tests/test_geometry.py`.
- Cursor poll feels stuttery → `interval_ms` may need tuning.
- Ring leaves a stale frame on close → ensure `widget.hide()` is called in the `finally` block of `RingController.close`.

- [ ] **Step 8: Update phase 2 hardware test memory**

After confirming `BTN_TASK` does emit on physical press, update
`/home/chrisland/.claude/projects/-home-chrisland-projects-logitechmouse/memory/phase2_hardware_test.md`
to mark `BTN_TASK` as verified. (Carry-forward chore from the Phase 2 checkpoint.)

---

## Task 25: Open PR

**Files:** none.

- [ ] **Step 1: Push branch**

```bash
git push -u origin phase4-ring-prototype
```

- [ ] **Step 2: Create PR using gh**

```bash
gh pr create --title "Phase 4: radial Actions Ring overlay" --body "$(cat <<'EOF'
## Summary

- Adds the radial Actions Ring overlay (PyQt6, X11-only v1).
- Replaces `Binding.action` with polymorphic `Binding.target = "ring:NAME" | "action:NAME"`. Legacy `action = "..."` form preserved with a one-line deprecation log.
- Extends `device.read_loop` to emit both key-down and key-up via `InputEvent.pressed`.
- New `overlay/` package: pure geometry, `RingWidget` (transparent always-on-top), `CursorPoller`, `RingController` state machine.
- Listener splits into command-only path (no Qt) and Qt-driven path (worker thread + signal/slot bridge).
- Examples, README, PRD, and CI (xvfb) all updated.

Spec: `docs/superpowers/specs/2026-04-26-phase4-actions-ring-design.md`.
Plan: `docs/superpowers/plans/2026-04-26-phase4-actions-ring.md`.

## Test plan

- [x] All Phase 2 tests still pass (35).
- [x] New unit tests pass: `test_geometry.py`, `test_config_ring.py`, `test_device_readloop.py`, `test_ring_controller.py`, `test_check_config.py`.
- [x] Widget tests pass under xvfb (`test_overlay_widget.py`, `test_cursor_poller.py`, `test_listen_qt_smoke.py`).
- [x] Manual hardware test on real MX hardware (Task 24 in plan).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Confirm CI is green**

```bash
gh pr checks
```
Expected: all checks passing.

---

## Self-review notes

Plan covers spec sections:
- §1 Goal — Tasks 14, 15, 24 (widget renders, animation, manual verify of feel).
- §2 Non-goals — explicitly preserved (no Wayland tasks, no per-app profile tasks, etc.).
- §3 User-facing behavior — Tasks 9 (key-up), 14 (visual), 15 (animation), 17 (cursor wiring), 24 (verify).
- §4 Schema — Tasks 3 (Target), 4 (binding shim), 5 (Ring/Segment), 6, 7 (validation), 8 (PyQt6 graceful degrade).
- §5 Architecture — Tasks 10–12 (geometry), 13, 17 (controller), 14, 15 (widget), 16 (cursor), 18 (listener integration), 19 (smoke test).
- §6 Error handling — covered inside Tasks 8, 13, 18 (re-entrant open ignored, run_action failure handled, display-unavailable handled by the existing PyQt6 import check).
- §7 Testing strategy — every test file the spec names is created or extended in this plan.
- §8 Dependencies — Task 1.
- §9 Migration / rollout — Tasks 0, 20–25.
- §10 Open issues — explicitly carried as polish items (scale animation in Task 15 note; Esc-key cancel and `python-xlib` swap not implemented and that is correct per spec).

No placeholders remain. All step bodies contain executable code or commands.
