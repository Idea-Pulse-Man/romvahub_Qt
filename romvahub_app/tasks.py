"""Run a blocking call (an API request) off the UI thread and hand its result back on the UI thread."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_pool = QThreadPool.globalInstance()
_pool.setMaxThreadCount(max(4, _pool.maxThreadCount()))
_alive: set["_Signals"] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: _Signals):
        super().__init__()
        self.fn = fn
        self.signals = signals

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as error:  # noqa: BLE001 - every failure goes back to the UI
            if not hasattr(error, "status"):
                traceback.print_exc()
            self._emit(self.signals.failed, error)
        else:
            self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value) -> None:
        # The app (or the window that asked) may be gone by the time the call returns.
        try:
            signal.emit(value)
        except RuntimeError:
            pass


def run(fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None, owner: QObject | None = None) -> None:
    """Call `fn()` on a worker thread; then `on_done(result)` or `on_error(error)` on the UI thread.

    With `owner`, nothing is called back once the owner is gone.
    """
    signals = _Signals()
    if owner is not None:
        signals.setParent(None)
    _alive.add(signals)

    def finish(callback, value):
        _alive.discard(signals)
        signals.deleteLater()
        if owner is not None:
            try:
                owner.objectName()  # raises RuntimeError when the C++ object is gone
            except RuntimeError:
                return
        if callback:
            callback(value)

    signals.done.connect(lambda value: finish(on_done, value))
    signals.failed.connect(lambda error: finish(on_error, error))
    _pool.start(_Job(fn, signals))
