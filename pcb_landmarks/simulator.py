"""Sequential production-line simulator with explicit lifecycle controls."""
from __future__ import annotations

import threading
import time
from pathlib import Path


class LineSimulator:
    def __init__(self, process_image):
        self.process_image = process_image
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._state = self._empty_state()

    @staticmethod
    def _empty_state():
        return {"status": "stopped", "directory": None, "interval": 3.0, "current": None,
                "processed": 0, "alarms": 0, "passed": 0, "errors": 0, "last_result": None}

    def state(self):
        with self._lock:
            return dict(self._state)

    def start(self, directory, interval, process_image=None, metadata=None):
        root = Path(directory).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Simulation directory does not exist")
        images = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if not images:
            raise ValueError("Simulation directory contains no JPEG or PNG images")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Simulation is already active")
            self._state = {**self._empty_state(), "status": "running", "directory": str(root),
                           "interval": float(interval), "queued": len(images), **(metadata or {})}
            self._stop.clear()
            self._wake.set()
            processor = process_image or self.process_image
            self._thread = threading.Thread(target=self._run, args=(images, processor), daemon=True, name="pcb-line-simulator")
            self._thread.start()
        return self.state()

    def _run(self, images, processor):
        for path in images:
            while not self._wake.wait(0.2):
                if self._stop.is_set():
                    return self._finish("stopped")
            if self._stop.is_set():
                return self._finish("stopped")
            with self._lock:
                self._state["current"] = path.name
            try:
                result = processor(path)
                alarm = bool(result.get("review_required", result.get("outcome") in {"review", "error"}))
                with self._lock:
                    self._state["processed"] += 1
                    self._state["alarms" if alarm else "passed"] += 1
                    self._state["last_result"] = result
            except Exception as error:
                with self._lock:
                    self._state["processed"] += 1
                    self._state["errors"] += 1
                    self._state["last_result"] = {"outcome": "error", "reason": f"{type(error).__name__}: {error}"}
            deadline = time.monotonic() + self.state()["interval"]
            while time.monotonic() < deadline and not self._stop.is_set():
                time.sleep(min(0.1, deadline - time.monotonic()))
        self._finish("stopped" if self._stop.is_set() else "completed")

    def _finish(self, status):
        with self._lock:
            self._state["status"] = status
            self._state["current"] = None

    def pause(self):
        with self._lock:
            if self._state["status"] != "running":
                raise RuntimeError("Only a running simulation can be paused")
            self._state["status"] = "paused"
            self._wake.clear()
        return self.state()

    def resume(self):
        with self._lock:
            if self._state["status"] != "paused":
                raise RuntimeError("Only a paused simulation can be resumed")
            self._state["status"] = "running"
            self._wake.set()
        return self.state()

    def stop(self):
        with self._lock:
            if self._state["status"] not in {"running", "paused"}:
                raise RuntimeError("Simulation is not active")
            self._state["status"] = "stopping"
            self._stop.set()
            self._wake.set()
        return self.state()
