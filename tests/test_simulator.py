import tempfile
import threading
import time
import unittest
from pathlib import Path

from pcb_landmarks.simulator import LineSimulator


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in ["b.png", "a.jpg", "ignore.txt"]:
            (self.root / name).write_bytes(b"fixture")

    def wait_for(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("simulator did not reach expected state")

    def test_processes_supported_images_in_filename_order(self):
        processed = []
        simulator = LineSimulator(lambda path: processed.append(path.name) or {"outcome": "present", "review_required": False})
        simulator.start(self.root, 0.01)
        self.wait_for(lambda: simulator.state()["status"] == "completed")
        self.assertEqual(processed, ["a.jpg", "b.png"])
        self.assertEqual(simulator.state()["passed"], 2)

    def test_pause_resume_stop_transitions(self):
        simulator = LineSimulator(lambda path: {"outcome": "review", "review_required": True})
        simulator.start(self.root, 0.5)
        simulator.pause()
        self.assertEqual(simulator.state()["status"], "paused")
        simulator.resume()
        self.assertEqual(simulator.state()["status"], "running")
        simulator.stop()
        self.wait_for(lambda: simulator.state()["status"] == "stopped")

    def test_stop_while_final_image_finishes_ends_stopped(self):
        for path in self.root.iterdir():
            if path.name != 'a.jpg':
                path.unlink()
        entered, release = threading.Event(), threading.Event()
        def process(_path):
            entered.set()
            release.wait(1)
            return {"outcome": "present", "review_required": False}
        simulator = LineSimulator(process)
        simulator.start(self.root, 0.01)
        self.assertTrue(entered.wait(1))
        simulator.stop()
        release.set()
        self.wait_for(lambda: simulator.state()["status"] in {"stopped", "completed"})
        self.assertEqual(simulator.state()["status"], "stopped")

    def test_start_pins_processor_and_run_metadata(self):
        processed = []
        simulator = LineSimulator(lambda _path: self.fail('default processor must not replace pinned run'))
        simulator.start(self.root, 0.01,
                        process_image=lambda path: processed.append(path.name) or {"outcome": "present"},
                        metadata={"golden_reference_id": "pinned-reference"})
        self.wait_for(lambda: simulator.state()["status"] == "completed")
        self.assertEqual(processed, ["a.jpg", "b.png"])
        self.assertEqual(simulator.state()["golden_reference_id"], "pinned-reference")


if __name__ == "__main__":
    unittest.main()
