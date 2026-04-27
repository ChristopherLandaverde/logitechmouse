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
    rc.close()
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
    rc.close()
    assert rc.state == RingState.IDLE
    widget.hide.assert_called_once()


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
