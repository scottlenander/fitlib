"""Running work in worker processes, or inline when one worker is enough."""

from __future__ import annotations

import os
from concurrent.futures import Executor, Future, ProcessPoolExecutor


class _InlineExecutor(Executor):
    """Runs work immediately in this process: for one worker, and for tests."""

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
        """Run ``fn`` now and wrap its result in a completed future.

        Args:
            fn: The function to run.
            *args: Positional arguments for ``fn``.
            **kwargs: Keyword arguments for ``fn``.

        Returns:
            A future that already holds ``fn``'s result or exception.
        """
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - analyse() returns Failed instead
            future.set_exception(exc)
        return future


def default_workers() -> int:
    """How many decoding processes to use when none is asked for.

    Returns:
        The number of CPUs, between 1 and 4.
    """
    return max(1, min(4, os.cpu_count() or 1))


def make_executor(workers: int) -> Executor:
    """Choose where work runs.

    Args:
        workers: How many processes to use.

    Returns:
        A process pool for more than one worker, otherwise an executor that runs each task
        immediately in this process.
    """
    return ProcessPoolExecutor(workers) if workers > 1 else _InlineExecutor()
