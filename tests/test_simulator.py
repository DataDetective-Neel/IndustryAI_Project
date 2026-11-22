import tempfile
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


if __name__ == "__main__":
    unittest.main()
