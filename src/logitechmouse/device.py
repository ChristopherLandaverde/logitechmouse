from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InputEvent:
    trigger: str


class DeviceBackend:
    """Placeholder backend until Linux event integration is implemented."""

    def describe(self) -> str:
        return "stub-device-backend"

    def poll(self) -> list[InputEvent]:
        return []
