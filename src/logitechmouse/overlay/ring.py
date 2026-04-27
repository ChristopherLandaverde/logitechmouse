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
