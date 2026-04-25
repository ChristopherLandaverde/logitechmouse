import time

from logitechmouse.actions import run_action
from logitechmouse.config import Action


def test_dry_run_does_not_spawn():
    action = Action(name="x", kind="command", command="/bin/false")
    result = run_action(action, dry_run=True)
    assert result.ok is True
    assert "dry-run" in result.detail


def test_unsupported_kind_returns_error():
    action = Action(name="x", kind="overlay")
    result = run_action(action)
    assert result.ok is False
    assert "unsupported" in result.detail


def test_missing_command_returns_error():
    action = Action(name="x", kind="command", command=None)
    result = run_action(action)
    assert result.ok is False
    assert "missing command" in result.detail


def test_spawn_failure_is_caught():
    action = Action(name="x", kind="command", command="/no/such/binary --flag")
    result = run_action(action)
    assert result.ok is False
    assert "failed to spawn" in result.detail


def test_successful_spawn_does_not_block(tmp_path):
    marker = tmp_path / "marker"
    action = Action(
        name="x",
        kind="command",
        command=f"/bin/sh -c 'sleep 0.2 && touch {marker}'",
    )
    start = time.monotonic()
    result = run_action(action)
    elapsed = time.monotonic() - start
    assert result.ok is True
    assert elapsed < 0.15, f"run_action blocked for {elapsed:.2f}s"
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.05)
    assert marker.exists()
