"""Precomputed, UI-agnostic stepping through a cube action sequence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

try:  # Support both direct-script and package imports.
    from .cube_model import CubeState, build_timeline
except ImportError:  # pragma: no cover - exercised by direct script launch.
    from cube_model import CubeState, build_timeline


@dataclass
class ReplaySession:
    """A timeline controller whose rendering is owned by the caller.

    ``states`` is built once and contains the initial state at index zero plus
    one state after each action.  This class intentionally owns no timer: a
    Qt view may call ``next`` from its own animation timer while ``playing`` is
    true, and tests can use it without creating a GUI application.
    """

    initial: CubeState
    actions: Sequence[str]
    states: tuple[CubeState, ...] = field(init=False)
    index: int = 0
    playing: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.actions, str):
            raise TypeError("actions 必须是一组动作，而不是单个字符串。")
        self.actions = tuple(self.actions)
        self.states = tuple(build_timeline(self.initial, self.actions))
        if len(self.states) != len(self.actions) + 1:
            raise RuntimeError("build_timeline 必须返回初始状态和每一步后的状态。")
        self.seek(self.index)

    @property
    def current_state(self) -> CubeState:
        return self.states[self.index]

    @property
    def total_steps(self) -> int:
        return len(self.actions)

    @property
    def completed(self) -> bool:
        return self.index == self.total_steps

    @property
    def completion(self) -> float:
        """A normalized progress value in ``[0.0, 1.0]``."""
        return 1.0 if self.total_steps == 0 else self.index / self.total_steps

    @property
    def current_action(self) -> str | None:
        """The action that produced ``current_state``, or ``None`` initially."""
        return None if self.index == 0 else self.actions[self.index - 1]

    @property
    def next_action(self) -> str | None:
        return None if self.completed else self.actions[self.index]

    def play(self) -> CubeState:
        """Mark the session as playing unless it is already complete."""
        self.playing = not self.completed
        return self.current_state

    def pause(self) -> CubeState:
        self.playing = False
        return self.current_state

    def next(self) -> CubeState:
        """Advance one action; reaching the end automatically pauses."""
        if not self.completed:
            self.index += 1
        if self.completed:
            self.playing = False
        return self.current_state

    def previous(self) -> CubeState:
        """Step backward once and pause for deliberate inspection."""
        self.playing = False
        if self.index > 0:
            self.index -= 1
        return self.current_state

    def seek(self, index: int) -> CubeState:
        """Jump to an exact timeline index and pause.

        Invalid indexes are errors rather than silently clamping, so the UI
        cannot conceal a malformed slider/action mapping.
        """
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("回放位置必须是整数。")
        if not 0 <= index < len(self.states):
            raise IndexError(f"回放位置必须在 0 到 {len(self.states) - 1} 之间。")
        self.index = index
        self.playing = False
        return self.current_state
