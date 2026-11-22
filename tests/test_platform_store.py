import tempfile
import unittest
from pathlib import Path

from pcb_landmarks.platform_store import AOIStore


class PlatformStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = AOIStore(Path(self.folder.name) / "aoi.db")

    def test_auth_roles_and_preferences(self):
        self.store.create_user("boss", "Line Supervisor", "supervisor", "correct horse battery")
        authenticated = self.store.authenticate("boss", "correct horse battery")
        self.assertIsNotNone(authenticated)
        token, user = authenticated
        self.assertEqual(user["role"], "supervisor")
        self.assertEqual(self.store.user_for_token(token)["username"], "boss")
        preferences = self.store.update_preferences("boss", {"alarm_sound": False, "ignored": "x"})
        self.assertEqual(preferences, {"alarm_sound": False})
        self.store.change_password("boss", "correct horse battery", "new secure password")
        self.assertIsNone(self.store.user_for_token(token))
        self.assertIsNotNone(self.store.authenticate("boss", "new secure password"))

    def test_dashboard_decisions_are_consistent_and_unique(self):
        batch = {"batch_id": "batch", "photos": [
            {"photo_id": "pass", "filename": "pass.png", "outcome": "present",
             "review_required": False, "components": []},
            {"photo_id": "alarm", "filename": "alarm.png", "outcome": "review",
             "review_required": True, "components": [{"status": "missing"}]},
        ]}
        self.store.record_batch(batch)
        metrics = self.store.dashboard()["metrics"]
        self.assertEqual((metrics["total"], metrics["passed"], metrics["pending"]), (2, 1, 1))
        self.store.decide("batch:alarm", "false_alarm", "operator")
        metrics = self.store.dashboard()["metrics"]
        self.assertEqual((metrics["pending"], metrics["false_alarms"], metrics["rejected"]), (0, 1, 0))
        with self.assertRaises(RuntimeError):
            self.store.decide("batch:alarm", "confirmed_reject", "operator")

    def test_golden_configuration_round_trip(self):
        self.store.save_golden("photo", {"components": [{"id": "U1"}], "mode": "automatic"}, "boss")
        saved = self.store.golden()
        self.assertEqual(saved["reference_id"], "photo")
        self.assertEqual(saved["components"][0]["id"], "U1")
        self.store.clear_golden()
        self.assertIsNone(self.store.golden())


if __name__ == "__main__":
    unittest.main()
