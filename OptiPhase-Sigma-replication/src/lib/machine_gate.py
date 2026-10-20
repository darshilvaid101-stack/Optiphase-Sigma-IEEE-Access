"""Readers-writer gate that keeps timed runs quiet: compilations share it, timed executions hold it alone."""

import contextlib


class MachineGate:
    """Process-shared gate. Writers (timed runs) wait for active readers and block new readers."""

    def __init__(self, context):
        self._condition = context.Condition()
        self._active_shared = context.Value("i", 0)
        self._writers_waiting = context.Value("i", 0)
        self._exclusive_held = context.Value("b", False)

    @contextlib.contextmanager
    def shared(self):
        with self._condition:
            self._condition.wait_for(
                lambda: not self._exclusive_held.value and self._writers_waiting.value == 0
            )
            self._active_shared.value += 1
        try:
            yield
        finally:
            with self._condition:
                self._active_shared.value -= 1
                self._condition.notify_all()

    @contextlib.contextmanager
    def exclusive(self):
        with self._condition:
            self._writers_waiting.value += 1
            self._condition.wait_for(
                lambda: self._active_shared.value == 0 and not self._exclusive_held.value
            )
            self._writers_waiting.value -= 1
            self._exclusive_held.value = True
        try:
            yield
        finally:
            with self._condition:
                self._exclusive_held.value = False
                self._condition.notify_all()


class NullGate:
    """Single-process stand-in with the same interface, used when no worker pool is involved."""

    @contextlib.contextmanager
    def shared(self):
        yield

    @contextlib.contextmanager
    def exclusive(self):
        yield
