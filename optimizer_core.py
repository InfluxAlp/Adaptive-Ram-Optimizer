"""ctypes bridge for the event-driven optimizer_core.dll."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class TelemetryData(ctypes.Structure):
    _fields_ = [
        ("process_id", wintypes.DWORD),
        ("process_name", ctypes.c_wchar * 256),
        ("window_title", ctypes.c_wchar * 512),
        ("timestamp", ctypes.c_uint64),
        ("previous_focus_duration_ms", ctypes.c_uint64),
    ]


TelemetryCallback = ctypes.WINFUNCTYPE(None, TelemetryData)


class OptimizerCore:
    def __init__(self, dll_path: str | None = None):
        path = dll_path or os.path.join(os.path.dirname(__file__), "optimizer_core.dll")
        self._dll = ctypes.WinDLL(path, use_last_error=True)
        self._dll.optimizer_start.argtypes = [TelemetryCallback]
        self._dll.optimizer_start.restype = wintypes.BOOL
        self._dll.optimizer_stop.argtypes = []
        self._dll.optimizer_stop.restype = wintypes.BOOL
        self._dll.optimizer_is_running.argtypes = []
        self._dll.optimizer_is_running.restype = wintypes.BOOL
        self._callback = None

    def start(self, callback):
        if self._callback is not None:
            raise RuntimeError("Optimizer core is already started")
        self._callback = TelemetryCallback(callback)
        if not self._dll.optimizer_start(self._callback):
            self._callback = None
            error = ctypes.get_last_error()
            raise OSError(error, "optimizer_start failed")

    def stop(self):
        if self._callback is None:
            return
        if not self._dll.optimizer_stop():
            error = ctypes.get_last_error()
            raise OSError(error, "optimizer_stop failed")
        self._callback = None

    def is_running(self):
        return bool(self._dll.optimizer_is_running())

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()
