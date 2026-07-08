"""Progress bar interface for CLI (tqdm) and TUI (Textual) backends."""

from typing import Any, Protocol


class ProgressBarInterface(Protocol):
    """Protocol for progress bars used by the engine (tqdm or TUI adapter).

    The engine calls update(1) per crawler response, increments total when
    enqueueing URLs, and uses set_postfix for yielded/depth info.
    """

    total: int
    """Total number of steps (read/write). Engine does pbar.total += 1 when enqueueing."""

    def update(self, n: int = 1) -> None:
        """Advance progress by n steps (e.g. one per HTTP response)."""
        ...

    def refresh(self) -> None:
        """Refresh the display (no-op for some backends)."""
        ...

    def set_postfix(self, **kwargs: Any) -> None:
        """Set optional suffix info (e.g. yielded=..., depth=...)."""
        ...

    def close(self) -> None:
        """Finish and optionally hide the progress bar."""
        ...
