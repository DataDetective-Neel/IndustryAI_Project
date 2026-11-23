"""SQLite persistence for the production-inspired AOI workflow."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROLES = {"administrator", "supervisor", "operator"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AOIStore:
    """Small transactional store; one connection per operation is thread-safe."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS inspections (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    photo_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    algorithm_outcome TEXT NOT NULL,
                    defect_type TEXT,
                    review_required INTEGER NOT NULL,
                    final_decision TEXT,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS inspections_created ON inspections(created_at DESC);
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspection_id TEXT NOT NULL UNIQUE REFERENCES inspections(id),
                    decision TEXT NOT NULL CHECK(decision IN ('confirmed_reject', 'false_alarm')),
                    actor TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    preferences_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS golden_configs (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    reference_id TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS golden_library (
                    reference_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

    @staticmethod
    def _password(password: str, salt: bytes | None = None):
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters")
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return salt.hex(), digest.hex()

    def bootstrap_admin(self):
        """Create first admin only from environment; never embed credentials."""
        username = os.environ.get("PCB_ADMIN_USERNAME", "admin").strip().lower()
        password = os.environ.get("PCB_ADMIN_PASSWORD")
        with self.connect() as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone() or not password:
                return False
        self.create_user(username, "AOI Administrator", "administrator", password)
        return True

    def create_user(self, username, display_name, role, password):
        username = username.strip().lower()
        if not username or role not in ROLES:
            raise ValueError("Valid username and role are required")
        salt, digest = self._password(password)
        with self.connect() as db:
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, 1, '{}', ?)",
                       (username, display_name.strip() or username, role, salt, digest, utc_now()))

    def authenticate(self, username, password):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=? AND active=1",
                             (username.strip().lower(),)).fetchone()
            if not row:
                return None
            _, digest = self._password(password, bytes.fromhex(row["password_salt"]))
            if not hmac.compare_digest(digest, row["password_hash"]):
                return None
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (hashlib.sha256(token.encode()).hexdigest(), row["username"], utc_now()))
            return token, self._public_user(row)

    def user_for_token(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.username=s.username
                              WHERE s.token_hash=? AND u.active=1""", (digest,)).fetchone()
            return self._public_user(row) if row else None

    @staticmethod
    def _public_user(row):
        return dict(username=row["username"], display_name=row["display_name"], role=row["role"],
                    preferences=json.loads(row["preferences_json"]), active=bool(row["active"]))

    def list_users(self):
        with self.connect() as db:
            return [self._public_user(row) for row in db.execute("SELECT * FROM users ORDER BY username")]

    def update_preferences(self, username, preferences):
        allowed = {"alarm_sound", "inspection_interval", "simulation_directory"}
        clean = {key: preferences[key] for key in allowed if key in preferences}
        with self.connect() as db:
            current = db.execute("SELECT preferences_json FROM users WHERE username=?", (username,)).fetchone()
            if not current:
                raise ValueError("Unknown user")
            merged = {**json.loads(current[0]), **clean}
            db.execute("UPDATE users SET preferences_json=? WHERE username=?", (json.dumps(merged), username))
        return merged

    def change_password(self, username, current_password, new_password):
        if not self.authenticate(username, current_password):
            raise ValueError("Current password is incorrect")
        salt, digest = self._password(new_password)
        with self.connect() as db:
            db.execute("UPDATE users SET password_salt=?, password_hash=? WHERE username=?",
                       (salt, digest, username))
            db.execute("DELETE FROM sessions WHERE username=?", (username,))

    def save_golden(self, reference_id, config, actor):
        with self.connect() as db:
            db.execute("""INSERT INTO golden_configs VALUES (1, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET reference_id=excluded.reference_id,
                        config_json=excluded.config_json, updated_by=excluded.updated_by,
                        updated_at=excluded.updated_at""",
                       (reference_id, json.dumps(config), actor, utc_now()))

    def golden(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM golden_configs WHERE id=1").fetchone()
            return ({"reference_id": row["reference_id"], **json.loads(row["config_json"]),
                     "updated_by": row["updated_by"], "updated_at": row["updated_at"]} if row else None)

    def clear_golden(self):
        with self.connect() as db:
            db.execute("DELETE FROM golden_configs")

    def save_library_golden(self, reference_id, name, config, actor):
        with self.connect() as db:
            db.execute("""INSERT INTO golden_library VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(reference_id) DO UPDATE SET name=excluded.name,
                config_json=excluded.config_json, updated_by=excluded.updated_by,
                updated_at=excluded.updated_at""",
                (reference_id, name, json.dumps(config), actor, utc_now()))

    def golden_library(self):
        with self.connect() as db:
            return [dict(row, **json.loads(row["config_json"])) for row in db.execute(
                "SELECT reference_id,name,config_json,updated_by,updated_at FROM golden_library ORDER BY name COLLATE NOCASE")]

    def delete_library_golden(self, reference_id):
        with self.connect() as db:
            return db.execute("DELETE FROM golden_library WHERE reference_id=?", (reference_id,)).rowcount > 0

    def record_batch(self, batch):
        now = utc_now()
        with self.connect() as db:
            for result in batch["photos"]:
                components = result.get("components", [])
                defect = next((part.get("status") for part in components
                               if part.get("status") in {"missing", "misaligned"}), None)
                review = bool(result.get("review_required", result.get("outcome") in {"review", "error"}))
                identifier = f'{batch["batch_id"]}:{result["photo_id"]}'
                db.execute("""INSERT OR REPLACE INTO inspections
                            (id,batch_id,photo_id,filename,algorithm_outcome,defect_type,review_required,
                             final_decision,evidence_json,created_at) VALUES (?,?,?,?,?,?,?,NULL,?,?)""",
                           (identifier, batch["batch_id"], result["photo_id"], result["filename"],
                            result.get("outcome", "review"), defect, int(review), json.dumps(result), now))

    def decide(self, inspection_id, decision, actor, note=""):
        with self.connect() as db:
            row = db.execute("SELECT review_required, final_decision FROM inspections WHERE id=?",
                             (inspection_id,)).fetchone()
            if not row:
                raise KeyError("Unknown inspection")
            if row["final_decision"]:
                raise RuntimeError("Inspection already has an operator decision")
            if not row["review_required"]:
                raise ValueError("Inspection does not require review")
            now = utc_now()
            db.execute("INSERT INTO decisions(inspection_id,decision,actor,note,created_at) VALUES (?,?,?,?,?)",
                       (inspection_id, decision, actor, note[:500], now))
            db.execute("UPDATE inspections SET final_decision=? WHERE id=?", (decision, inspection_id))

    def dashboard(self):
        with self.connect() as db:
            counts = db.execute("""SELECT COUNT(*) total,
                SUM(CASE WHEN review_required=0 THEN 1 ELSE 0 END) passed,
                SUM(CASE WHEN final_decision='confirmed_reject' THEN 1 ELSE 0 END) rejected,
                SUM(CASE WHEN review_required=1 AND final_decision IS NULL THEN 1 ELSE 0 END) pending,
                SUM(CASE WHEN final_decision='false_alarm' THEN 1 ELSE 0 END) false_alarms
                FROM inspections""").fetchone()
            values = {key: int(counts[key] or 0) for key in counts.keys()}
            evidence_rows = list(db.execute("SELECT algorithm_outcome,evidence_json FROM inspections"))
            distribution = Counter()
            for row in evidence_rows:
                evidence = json.loads(row['evidence_json'])
                defect_types = {component.get('status') for component in evidence.get('components', [])
                                if component.get('status') in {'missing', 'misaligned'}}
                if defect_types:
                    distribution.update(defect_types)
                else:
                    distribution[row['algorithm_outcome']] += 1
            values['missing'] = distribution['missing']
            values['misaligned'] = distribution['misaligned']
            decisions = values["rejected"] + values["false_alarms"]
            values["first_pass_yield"] = round(100 * values["passed"] / values["total"], 1) if values["total"] else None
            values["false_alarm_rate"] = round(100 * values["false_alarms"] / decisions, 1) if decisions else None
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec='seconds')
            values["throughput_per_hour"] = db.execute(
                "SELECT COUNT(*) FROM inspections WHERE created_at >= ?", (cutoff,)).fetchone()[0]
            recent = [dict(row) for row in db.execute("""SELECT id,filename,algorithm_outcome,defect_type,
                review_required,final_decision,evidence_json,created_at FROM inspections ORDER BY created_at DESC""")]
            alarms = [dict(row) for row in db.execute("""SELECT i.id,i.filename,i.defect_type,i.final_decision,
                i.evidence_json,d.actor,d.note,COALESCE(d.created_at,i.created_at) created_at FROM inspections i
                LEFT JOIN decisions d ON d.inspection_id=i.id WHERE i.review_required=1
                ORDER BY created_at DESC""")]
            for row in [*recent, *alarms]:
                evidence = json.loads(row.pop('evidence_json'))
                row['simulated'] = bool(evidence.get('simulated'))
                row['current_image_url'] = evidence.get('current_image_url')
            daily = {row["day"]: int(row["count"]) for row in db.execute(
                "SELECT substr(created_at,1,10) day, COUNT(*) count FROM inspections GROUP BY day")}
            today = datetime.now(timezone.utc).date()
            trend = [{"date": str(day), "count": daily.get(str(day), 0)}
                     for day in (today - timedelta(days=offset) for offset in range(6, -1, -1))]
            return {"metrics": values, "recent_inspections": recent, "recent_alarms": alarms,
                    "production_trend": trend,
                    "defect_distribution": [{"name": name, "count": count}
                                            for name, count in distribution.most_common()],
                    "sample_data": values["total"] == 0}

    def pending(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,filename,algorithm_outcome,defect_type,
                evidence_json,created_at FROM inspections WHERE review_required=1 AND final_decision IS NULL
                ORDER BY created_at""")]
