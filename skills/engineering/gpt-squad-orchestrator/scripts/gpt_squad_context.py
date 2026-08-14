#!/usr/bin/env python3
"""Transactional GPT Squad Context Hub.

Canonical state lives in a per-session SQLite database. Markdown and JSON files
under each run directory are generated views, never the source of truth.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCHEMA_VERSION = 1
HUB_DB_NAME = "context-hub.sqlite3"
MAX_CONTEXT_VIEW_BYTES = 64 * 1024
DEFAULT_BUDGETS = {
    "max_ledger_bytes": 32 * 1024,
    "max_missions": 16,
    "max_result_bytes": 32 * 1024,
    "max_active_ids": 120,
    "max_revision_history": 64,
}
SPECIALISTS = {
    "product_systems",
    "product_design",
    "experience_design",
    "domain_application",
    "data_systems",
    "distributed_systems",
    "integration_evolution",
    "platform_reliability",
    "security_trust",
    "change_review",
    "quality_falsification",
    "performance_economics",
    "codebase_forensics",
    "technical_communication",
}
RELATIONSHIPS = {"lead", "advisor", "parallel-owner", "independent-challenger"}
EFFORTS = {"Lean", "Standard", "Deep"}
WRITE_MODES = {"read-only", "writer"}
MISSION_STATUSES = {"planned", "active", "blocked", "completed", "superseded", "rejected"}
CONTEXT_STATES = {"pending-checkout", "current", "refresh-required", "not-required", "terminal-not-applicable"}
SESSION_MODES = {"active", "disabled"}
RUN_STATUSES = {"active", "blocked", "closed"}
PROPOSAL_ACTIONS = {"create", "update", "supersede"}
PROPOSAL_TYPES = {"fact", "decision", "invariant", "ownership", "constraint", "risk", "question"}
ENTRY_PREFIX = {
    "fact": "F",
    "decision": "D",
    "invariant": "I",
    "ownership": "O",
    "constraint": "C",
    "risk": "R",
    "question": "Q",
}
ENTRY_SECTION = {
    "fact": "Confirmed facts",
    "decision": "Accepted decisions",
    "invariant": "Global contracts and invariants",
    "ownership": "Ownership and responsibility surfaces",
    "constraint": "Constraints and non-goals",
    "risk": "Material risks",
    "question": "Open cross-specialty questions",
}
TERMINAL_MISSION_STATUSES = {"completed", "superseded", "rejected"}
DISCARDED_MISSION_STATUSES = {"superseded", "rejected"}
BLOCKING_CHALLENGE_VERDICTS = {"FAIL", "UNRESOLVED"}
CHALLENGE_DISPOSITIONS = {
    "resolved",
    "accepted-risk",
    "mission-reopened",
    "challenge-rejected-with-evidence",
    "claim-withdrawn",
}
SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MISSION_ID = re.compile(r"^M\d{2,3}$")
ENTRY_ID = re.compile(r"^(?:F|D|I|O|C|R|Q)-\d{3}$")
ARTIFACT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class HubError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    items = [item.strip() for item in value.split(",") if item.strip()]
    duplicate = next((item for index, item in enumerate(items) if item in items[:index]), None)
    if duplicate:
        raise HubError(f"duplicate list item: {duplicate}")
    return items


def parse_json_value(value: str | None, *, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HubError(f"invalid JSON: {exc}") from exc


def parse_json_file(path_value: str | None, *, default: Any) -> Any:
    if path_value is None:
        return default
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise HubError(f"JSON file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HubError(f"invalid JSON file {path}: {exc}") from exc


def require_non_placeholder(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned.startswith("<") or cleaned.lower() in {"none", "none."}:
        raise HubError(f"{label} must contain a concrete value")
    return cleaned


def validate_safe_key(value: str, label: str) -> None:
    if not SAFE_KEY.fullmatch(value):
        raise HubError(f"{label} must match {SAFE_KEY.pattern}")


def validate_mission_id(value: str) -> None:
    if not MISSION_ID.fullmatch(value):
        raise HubError(f"mission ID must match {MISSION_ID.pattern}")


def validate_entry_ids(values: Iterable[str], label: str) -> None:
    for value in values:
        if not ENTRY_ID.fullmatch(value):
            raise HubError(f"{label} contains invalid entry ID: {value}")


def validate_artifact_key(value: str) -> None:
    if not ARTIFACT_KEY.fullmatch(value):
        raise HubError(f"artifact key must match {ARTIFACT_KEY.pattern}")


def visibility_list(value: str | None) -> list[str]:
    if not value or value == "all":
        return ["*"]
    missions = parse_csv(value)
    for mission in missions:
        validate_mission_id(mission)
    return missions


def visible_to(visibility_json: str, mission_id: str) -> bool:
    values = json.loads(visibility_json)
    return "*" in values or mission_id in values


def ensure_no_symlink(path: Path, trusted_root: Path | None = None) -> None:
    path = path.expanduser().absolute()
    root = (trusted_root.expanduser().absolute() if trusted_root else Path(path.anchor))
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise HubError(f"path escapes trusted root: {path}") from exc
    current = root
    if current.exists() and current.is_symlink():
        raise HubError(f"trusted root is a symlink: {current}")
    for part in relative.parts:
        current = current / part
        if not current.exists():
            break
        if current.is_symlink():
            raise HubError(f"managed path contains a symlink: {current}")


def private_dir(path: Path, trusted_root: Path | None = None) -> Path:
    path = path.expanduser().absolute()
    if trusted_root is not None:
        ensure_no_symlink(path, trusted_root)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    directory = private_dir(path.parent)
    ensure_no_symlink(path, directory)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, mode)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def run_dir_parts(run_dir: Path) -> tuple[Path, Path, str, str]:
    run_dir = run_dir.expanduser().resolve()
    if run_dir.parent.name != "runs":
        raise HubError(f"run directory must be under sessions/<session-key>/runs/<run-id>: {run_dir}")
    session_dir = run_dir.parent.parent
    session_key = session_dir.name
    run_id = run_dir.name
    validate_safe_key(session_key, "session key")
    validate_safe_key(run_id, "run ID")
    ensure_no_symlink(run_dir, session_dir)
    return run_dir, session_dir, session_key, run_id


def db_path_for_run(run_dir: Path) -> Path:
    _, session_dir, _, _ = run_dir_parts(run_dir)
    return session_dir / HUB_DB_NAME


def connect_db(
    db_path: Path,
    *,
    create: bool = False,
    read_only: bool = False,
) -> sqlite3.Connection:
    db_path = db_path.expanduser().absolute()
    if create and read_only:
        raise HubError("a Context Hub connection cannot be both create and read-only")
    if read_only:
        if not db_path.exists():
            raise HubError(f"Context Hub database does not exist: {db_path}")
        ensure_no_symlink(db_path, db_path.parent)
        try:
            connection = sqlite3.connect(
                f"{db_path.as_uri()}?mode=ro",
                uri=True,
                timeout=5.0,
                isolation_level=None,
            )
        except sqlite3.OperationalError as read_only_error:
            # A live WAL database can require a read/write-capable file handle to
            # attach its existing shared-memory sidecar. Keep SQL query-only and
            # avoid chmod/journal changes while providing that compatibility path.
            try:
                connection = sqlite3.connect(
                    f"{db_path.as_uri()}?mode=rw",
                    uri=True,
                    timeout=5.0,
                    isolation_level=None,
                )
            except sqlite3.OperationalError:
                raise read_only_error
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA query_only = ON")
        return connection

    private_dir(db_path.parent)
    ensure_no_symlink(db_path, db_path.parent)
    if not create and not db_path.exists():
        raise HubError(f"Context Hub database does not exist: {db_path}")
    connection = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    if db_path.exists():
        os.chmod(db_path, 0o600)
    return connection


@contextlib.contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


@contextlib.contextmanager
def read_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    try:
        connection.execute("BEGIN")
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
          session_key TEXT PRIMARY KEY,
          mode TEXT NOT NULL CHECK (mode IN ('active', 'disabled')),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          session_key TEXT NOT NULL REFERENCES sessions(session_key),
          status TEXT NOT NULL CHECK (status IN ('active', 'blocked', 'closed')),
          objective TEXT NOT NULL,
          intent TEXT NOT NULL,
          success_json TEXT NOT NULL,
          constraints_json TEXT NOT NULL,
          revision INTEGER NOT NULL CHECK (revision >= 1),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          closed_at TEXT,
          closure_reason TEXT,
          closed_session_mode TEXT,
          blocked_reason TEXT,
          max_ledger_bytes INTEGER NOT NULL,
          max_missions INTEGER NOT NULL,
          max_result_bytes INTEGER NOT NULL,
          max_active_ids INTEGER NOT NULL,
          max_revision_history INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS missions (
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          mission_id TEXT,
          specialist TEXT NOT NULL,
          relationship TEXT NOT NULL,
          effort TEXT NOT NULL,
          status TEXT NOT NULL,
          objective TEXT NOT NULL,
          intent TEXT NOT NULL,
          success_json TEXT NOT NULL,
          constraints_json TEXT NOT NULL,
          verification_expectations_json TEXT NOT NULL,
          known_risks_json TEXT NOT NULL,
          responsibility_surface TEXT NOT NULL,
          distinct_value TEXT NOT NULL,
          write_mode TEXT NOT NULL,
          blind_first INTEGER NOT NULL DEFAULT 0,
          context_state TEXT NOT NULL,
          required_revision INTEGER NOT NULL,
          current_view_id TEXT,
          latest_result_version INTEGER,
          blocked_reason TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id)
        );

        CREATE TABLE IF NOT EXISTS mission_dependencies (
          run_id TEXT NOT NULL,
          mission_id TEXT NOT NULL,
          depends_on TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id, depends_on),
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE,
          FOREIGN KEY (run_id, depends_on) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS mission_required_entries (
          run_id TEXT NOT NULL,
          mission_id TEXT NOT NULL,
          entry_id TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id, entry_id),
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS mission_subscriptions (
          run_id TEXT NOT NULL,
          mission_id TEXT NOT NULL,
          topic TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id, topic),
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS proposals (
          proposal_seq INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          mission_id TEXT,
          action TEXT NOT NULL,
          proposal_type TEXT,
          target_entry_id TEXT,
          claim TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          rationale TEXT,
          boundaries TEXT,
          visibility_json TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          resolved_at TEXT,
          promoted_entry_id TEXT,
          resolution_reason TEXT,
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS context_entries (
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          entry_id TEXT NOT NULL,
          entry_type TEXT NOT NULL,
          current_version INTEGER NOT NULL,
          superseded INTEGER NOT NULL DEFAULT 0,
          visibility_json TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          created_revision INTEGER NOT NULL,
          updated_revision INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (run_id, entry_id)
        );

        CREATE TABLE IF NOT EXISTS context_entry_versions (
          run_id TEXT NOT NULL,
          entry_id TEXT NOT NULL,
          version INTEGER NOT NULL,
          revision INTEGER NOT NULL,
          claim TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          rationale TEXT,
          boundaries TEXT,
          superseded INTEGER NOT NULL,
          visibility_json TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          promotion_rationale TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          proposal_seq INTEGER,
          created_at TEXT NOT NULL,
          PRIMARY KEY (run_id, entry_id, version),
          FOREIGN KEY (run_id, entry_id) REFERENCES context_entries(run_id, entry_id) ON DELETE CASCADE,
          FOREIGN KEY (proposal_seq) REFERENCES proposals(proposal_seq)
        );

        CREATE TABLE IF NOT EXISTS artifacts (
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          artifact_key TEXT NOT NULL,
          repository TEXT NOT NULL,
          path TEXT NOT NULL,
          current_version INTEGER NOT NULL,
          visibility_json TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          created_revision INTEGER NOT NULL,
          updated_revision INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (run_id, artifact_key)
        );

        CREATE TABLE IF NOT EXISTS artifact_versions (
          run_id TEXT NOT NULL,
          artifact_key TEXT NOT NULL,
          version INTEGER NOT NULL,
          revision INTEGER NOT NULL,
          repository TEXT NOT NULL,
          path TEXT NOT NULL,
          commit_sha TEXT NOT NULL,
          content_sha256 TEXT,
          metadata_json TEXT NOT NULL,
          visibility_json TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (run_id, artifact_key, version),
          FOREIGN KEY (run_id, artifact_key) REFERENCES artifacts(run_id, artifact_key) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS context_views (
          view_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          mission_id TEXT NOT NULL,
          revision INTEGER NOT NULL,
          snapshot_hash TEXT NOT NULL,
          snapshot_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE,
          UNIQUE (view_id, run_id, mission_id),
          UNIQUE (view_id, run_id)
        );

        CREATE TABLE IF NOT EXISTS context_view_entries (
          view_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          entry_id TEXT NOT NULL,
          entry_version INTEGER NOT NULL,
          content_hash TEXT NOT NULL,
          PRIMARY KEY (view_id, entry_id),
          FOREIGN KEY (view_id, run_id) REFERENCES context_views(view_id, run_id) ON DELETE CASCADE,
          FOREIGN KEY (run_id, entry_id, entry_version)
            REFERENCES context_entry_versions(run_id, entry_id, version)
        );

        CREATE TABLE IF NOT EXISTS context_view_artifacts (
          view_id TEXT NOT NULL,
          run_id TEXT NOT NULL,
          artifact_key TEXT NOT NULL,
          artifact_version INTEGER NOT NULL,
          content_hash TEXT NOT NULL,
          PRIMARY KEY (view_id, artifact_key),
          FOREIGN KEY (view_id, run_id) REFERENCES context_views(view_id, run_id) ON DELETE CASCADE,
          FOREIGN KEY (run_id, artifact_key, artifact_version)
            REFERENCES artifact_versions(run_id, artifact_key, version)
        );

        CREATE TABLE IF NOT EXISTS results (
          run_id TEXT NOT NULL,
          mission_id TEXT NOT NULL,
          version INTEGER NOT NULL,
          status TEXT NOT NULL,
          result_hash TEXT NOT NULL,
          context_view_id TEXT NOT NULL,
          context_view_hash TEXT NOT NULL,
          content_json TEXT NOT NULL,
          verification_json TEXT NOT NULL,
          verdict TEXT,
          distinct_evidence TEXT,
          supersedes_version INTEGER,
          sealed_at TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id, version),
          FOREIGN KEY (run_id, mission_id) REFERENCES missions(run_id, mission_id) ON DELETE CASCADE,
          FOREIGN KEY (context_view_id, run_id, mission_id)
            REFERENCES context_views(view_id, run_id, mission_id)
        );

        CREATE TABLE IF NOT EXISTS challenge_dispositions (
          run_id TEXT NOT NULL,
          mission_id TEXT NOT NULL,
          result_version INTEGER NOT NULL,
          disposition_type TEXT NOT NULL,
          rationale TEXT NOT NULL,
          decision_id TEXT,
          remediation_mission_id TEXT,
          evidence_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (run_id, mission_id, result_version),
          FOREIGN KEY (run_id, mission_id, result_version) REFERENCES results(run_id, mission_id, version) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS run_revisions (
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          revision INTEGER NOT NULL,
          snapshot_hash TEXT NOT NULL,
          summary TEXT NOT NULL,
          changed_entries_json TEXT NOT NULL,
          changed_artifacts_json TEXT NOT NULL,
          affected_missions_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (run_id, revision)
        );

        CREATE TABLE IF NOT EXISTS events (
          event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
          revision INTEGER NOT NULL,
          event_type TEXT NOT NULL,
          mission_id TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_context_view_entries_entry
          ON context_view_entries(entry_id, entry_version);
        CREATE INDEX IF NOT EXISTS idx_context_view_artifacts_artifact
          ON context_view_artifacts(artifact_key, artifact_version);
        CREATE INDEX IF NOT EXISTS idx_events_run_revision
          ON events(run_id, revision, event_seq);
        CREATE INDEX IF NOT EXISTS idx_proposals_run_status
          ON proposals(run_id, status);
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    validate_schema(connection)


def validate_schema(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    ).fetchone()
    if table is None:
        raise HubError("Context Hub schema is not initialized")
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        raise HubError("Context Hub schema version is missing")
    try:
        version = int(row[0])
    except (TypeError, ValueError) as exc:
        raise HubError(f"invalid Context Hub schema version: {row[0]}") from exc
    if version != SCHEMA_VERSION:
        raise HubError(f"unsupported Context Hub schema version: {version}")
    return version


def fetch_one(connection: sqlite3.Connection, sql: str, params: Sequence[Any], label: str) -> sqlite3.Row:
    row = connection.execute(sql, params).fetchone()
    if row is None:
        raise HubError(f"{label} does not exist")
    return row


def load_run(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    return fetch_one(connection, "SELECT * FROM runs WHERE run_id = ?", (run_id,), f"run {run_id}")


def load_session(connection: sqlite3.Connection, session_key: str) -> sqlite3.Row:
    return fetch_one(connection, "SELECT * FROM sessions WHERE session_key = ?", (session_key,), f"session {session_key}")


def load_mission(connection: sqlite3.Connection, run_id: str, mission_id: str) -> sqlite3.Row:
    return fetch_one(
        connection,
        "SELECT * FROM missions WHERE run_id = ? AND mission_id = ?",
        (run_id, mission_id),
        f"mission {mission_id}",
    )


def assert_open_run(connection: sqlite3.Connection, run_id: str) -> tuple[sqlite3.Row, sqlite3.Row]:
    run = load_run(connection, run_id)
    session = load_session(connection, run["session_key"])
    if run["status"] == "closed":
        raise HubError("run is immutable while status is closed")
    return run, session


def assert_mutable_run(connection: sqlite3.Connection, run_id: str, *, allow_blocked: bool = False) -> tuple[sqlite3.Row, sqlite3.Row]:
    run = load_run(connection, run_id)
    session = load_session(connection, run["session_key"])
    if session["mode"] != "active":
        raise HubError("session squad mode is disabled")
    allowed = {"active", "blocked"} if allow_blocked else {"active"}
    if run["status"] not in allowed:
        raise HubError(f"run is immutable while status is {run['status']}")
    if run["status"] == "blocked" and run["blocked_reason"] == "session-disabled":
        raise HubError("run is blocked because session squad mode is disabled")
    return run, session


def dependencies(connection: sqlite3.Connection, run_id: str, mission_id: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT depends_on FROM mission_dependencies WHERE run_id = ? AND mission_id = ? ORDER BY depends_on",
            (run_id, mission_id),
        )
    ]


def required_entries(connection: sqlite3.Connection, run_id: str, mission_id: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT entry_id FROM mission_required_entries WHERE run_id = ? AND mission_id = ? ORDER BY entry_id",
            (run_id, mission_id),
        )
    ]


def subscriptions(connection: sqlite3.Connection, run_id: str, mission_id: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT topic FROM mission_subscriptions WHERE run_id = ? AND mission_id = ? ORDER BY topic",
            (run_id, mission_id),
        )
    ]


def current_entries(connection: sqlite3.Connection, run_id: str, *, include_superseded: bool = True) -> list[sqlite3.Row]:
    where = "" if include_superseded else "AND e.superseded = 0"
    return list(
        connection.execute(
            f"""
            SELECT e.*, v.claim, v.evidence_json, v.rationale, v.boundaries,
                   v.content_hash, v.promotion_rationale
            FROM context_entries e
            JOIN context_entry_versions v
              ON v.run_id = e.run_id AND v.entry_id = e.entry_id AND v.version = e.current_version
            WHERE e.run_id = ? {where}
            ORDER BY e.entry_id
            """,
            (run_id,),
        )
    )


def current_artifacts(connection: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT a.*, v.commit_sha, v.content_sha256, v.metadata_json, v.content_hash
            FROM artifacts a
            JOIN artifact_versions v
              ON v.run_id = a.run_id AND v.artifact_key = a.artifact_key AND v.version = a.current_version
            WHERE a.run_id = ?
            ORDER BY a.artifact_key
            """,
            (run_id,),
        )
    )


def run_snapshot_payload(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    run = load_run(connection, run_id)
    entries = [
        {
            "entryId": row["entry_id"],
            "type": row["entry_type"],
            "version": row["current_version"],
            "contentHash": row["content_hash"],
            "superseded": bool(row["superseded"]),
        }
        for row in current_entries(connection, run_id)
    ]
    artifacts = [
        {
            "artifactKey": row["artifact_key"],
            "version": row["current_version"],
            "contentHash": row["content_hash"],
        }
        for row in current_artifacts(connection, run_id)
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "objective": run["objective"],
        "intent": run["intent"],
        "successCriteria": json.loads(run["success_json"]),
        "hardConstraints": json.loads(run["constraints_json"]),
        "revision": run["revision"],
        "entries": entries,
        "artifacts": artifacts,
    }


def insert_event(
    connection: sqlite3.Connection,
    run_id: str,
    revision: int,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    mission_id: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO events(run_id, revision, event_type, mission_id, payload_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
        (run_id, revision, event_type, mission_id, canonical_json(dict(payload)), utc_now()),
    )


def record_revision(
    connection: sqlite3.Connection,
    run_id: str,
    revision: int,
    summary: str,
    *,
    changed_entries: Sequence[str] = (),
    changed_artifacts: Sequence[str] = (),
    affected_missions: Sequence[str] = (),
) -> str:
    payload = run_snapshot_payload(connection, run_id)
    snapshot_hash = sha256_text(canonical_json(payload))
    connection.execute(
        """
        INSERT INTO run_revisions(
          run_id, revision, snapshot_hash, summary,
          changed_entries_json, changed_artifacts_json, affected_missions_json, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            revision,
            snapshot_hash,
            summary,
            canonical_json(list(changed_entries)),
            canonical_json(list(changed_artifacts)),
            canonical_json(list(affected_missions)),
            utc_now(),
        ),
    )
    return snapshot_hash


def hard_budget_usage(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> dict[str, int]:
    run = load_run(connection, run_id)
    return {
        "ledgerBytes": len(render_ledger(connection, run_id, run_dir).encode("utf-8")),
        "activeIds": connection.execute(
            "SELECT COUNT(*) FROM context_entries WHERE run_id = ? AND superseded = 0",
            (run_id,),
        ).fetchone()[0],
        "missions": connection.execute(
            "SELECT COUNT(*) FROM missions WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
        "revisions": connection.execute(
            "SELECT COUNT(*) FROM run_revisions WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0],
        "maxLedgerBytes": run["max_ledger_bytes"],
        "maxActiveIds": run["max_active_ids"],
        "maxMissions": run["max_missions"],
        "maxRevisions": run["max_revision_history"],
    }


def enforce_hard_budgets(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> dict[str, int]:
    usage = hard_budget_usage(connection, run_id, run_dir)
    violations: list[str] = []
    if usage["ledgerBytes"] > usage["maxLedgerBytes"]:
        violations.append(
            f"generated shared ledger would exceed configured budget: "
            f"{usage['ledgerBytes']} > {usage['maxLedgerBytes']} bytes"
        )
    if usage["activeIds"] > usage["maxActiveIds"]:
        violations.append(
            f"active context entry count would exceed configured budget: "
            f"{usage['activeIds']} > {usage['maxActiveIds']}"
        )
    if usage["missions"] > usage["maxMissions"]:
        violations.append(
            f"mission count would exceed configured budget: "
            f"{usage['missions']} > {usage['maxMissions']}"
        )
    if usage["revisions"] > usage["maxRevisions"]:
        violations.append(
            f"revision history would exceed configured budget: "
            f"{usage['revisions']} > {usage['maxRevisions']}"
        )
    if violations:
        raise HubError("hard budget rejected mutation before commit: " + "; ".join(violations))
    return usage


def terminal_context_state(status: str, current_state: str) -> str:
    return "terminal-not-applicable" if status in DISCARDED_MISSION_STATUSES else current_state


def allocate_entry_id(connection: sqlite3.Connection, run_id: str, entry_type: str) -> str:
    prefix = ENTRY_PREFIX[entry_type]
    rows = connection.execute(
        "SELECT entry_id FROM context_entries WHERE run_id = ? AND entry_id LIKE ?",
        (run_id, f"{prefix}-%"),
    )
    highest = max((int(row[0].split("-", 1)[1]) for row in rows), default=0)
    if highest >= 999:
        raise HubError(f"entry ID space exhausted for {entry_type}")
    return f"{prefix}-{highest + 1:03d}"


def proposal_display_id(sequence: int) -> str:
    return f"P-{sequence:06d}"


def parse_proposal_id(value: str) -> int:
    match = re.fullmatch(r"P-(\d{6})", value)
    if not match:
        raise HubError("proposal ID must match P-000001")
    return int(match.group(1))


def normalize_topics(value: str | None) -> list[str]:
    topics = parse_csv(value)
    for topic in topics:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}", topic):
            raise HubError(f"invalid topic: {topic}")
    return topics


def visibility_text(raw: str) -> str:
    values = json.loads(raw)
    return "all" if values == ["*"] else ", ".join(values)


def merge_visibility(*values: Sequence[str]) -> list[str]:
    flattened = {item for group in values for item in group}
    if "*" in flattened:
        return ["*"]
    return sorted(flattened)


def json_inline(raw: str | None) -> str:
    if not raw:
        return "None"
    value = json.loads(raw)
    if value in ({}, [], None, ""):
        return "None"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def generated_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "ledger": run_dir / "shared-context.md",
        "work_map": run_dir / "work-map.md",
        "missions": run_dir / "missions",
        "results": run_dir / "results",
        "checkouts": run_dir / "checkouts",
        "proposals": run_dir / "proposals",
        "events": run_dir / "events.jsonl",
    }


def effective_session_mode(run: sqlite3.Row, session: sqlite3.Row) -> str:
    if run["status"] == "closed":
        return run["closed_session_mode"] or "closed"
    return session["mode"]


def render_ledger(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> str:
    run = load_run(connection, run_id)
    session = load_session(connection, run["session_key"])
    revision_row = fetch_one(
        connection,
        "SELECT * FROM run_revisions WHERE run_id = ? AND revision = ?",
        (run_id, run["revision"]),
        "current run revision",
    )
    lines = [
        f"# Shared Context Ledger — {run_id}",
        "",
        f"- Session key: `{run['session_key']}`",
        f"- Session squad mode: `{effective_session_mode(run, session)}`",
        f"- Context revision: `{run['revision']}`",
        f"- Canonical snapshot SHA-256: `{revision_row['snapshot_hash']}`",
        f"- Run status: `{run['status']}`",
        f"- Canonical store: `{run_dir.parent.parent / HUB_DB_NAME}`",
        "",
        "This Markdown file is generated from the transactional Context Hub. Do not edit it manually.",
        "",
        "## Complete objective and intent",
        "",
        f"Objective: {run['objective']}",
        "",
        f"Intent: {run['intent']}",
        "",
        "Success criteria:",
        "",
        f"```json\n{json.dumps(json.loads(run['success_json']), ensure_ascii=False, sort_keys=True, indent=2)}\n```",
        "",
        "Hard constraints:",
        "",
        f"```json\n{json.dumps(json.loads(run['constraints_json']), ensure_ascii=False, sort_keys=True, indent=2)}\n```",
        "",
    ]
    by_type: dict[str, list[sqlite3.Row]] = {kind: [] for kind in ENTRY_SECTION}
    mission_scoped_entries = 0
    for row in current_entries(connection, run_id):
        if json.loads(row["visibility_json"]) == ["*"]:
            by_type[row["entry_type"]].append(row)
        else:
            mission_scoped_entries += 1
    for entry_type, heading in ENTRY_SECTION.items():
        lines.extend([f"## {heading}", ""])
        rows = by_type[entry_type]
        if not rows:
            lines.extend(["None.", ""])
            continue
        for row in rows:
            state = "superseded" if row["superseded"] else "active"
            lines.append(f"- `{row['entry_id']}` v{row['current_version']} [{state}] — {row['claim']}")
            if json_inline(row["evidence_json"]) != "None":
                lines.append(f"  - Evidence: {json_inline(row['evidence_json'])}")
            if row["rationale"]:
                lines.append(f"  - Rationale: {row['rationale']}")
            if row["boundaries"]:
                lines.append(f"  - Shared boundaries: {row['boundaries']}")
            lines.append(f"  - Visibility: {visibility_text(row['visibility_json'])}")
            topics = json.loads(row["topics_json"])
            lines.append(f"  - Topics: {', '.join(topics) if topics else 'None'}")
            lines.append(f"  - Content SHA-256: `{row['content_hash']}`")
        lines.append("")
    lines.extend(["## Artifact versions", ""])
    all_artifacts = current_artifacts(connection, run_id)
    artifacts = [row for row in all_artifacts if json.loads(row["visibility_json"]) == ["*"]]
    mission_scoped_artifacts = len(all_artifacts) - len(artifacts)
    if not artifacts:
        lines.extend(["None.", ""])
    else:
        for row in artifacts:
            lines.append(
                f"- `{row['artifact_key']}` v{row['current_version']} — "
                f"`{row['repository']}@{row['commit_sha']}:{row['path']}`"
            )
            if row["content_sha256"]:
                lines.append(f"  - Content SHA-256: `{row['content_sha256']}`")
            lines.append(f"  - Reference SHA-256: `{row['content_hash']}`")
            lines.append(f"  - Visibility: {visibility_text(row['visibility_json'])}")
        lines.append("")
    lines.extend([
        "## Mission-scoped context",
        "",
        f"- Mission-scoped canonical entries omitted from this shared view: `{mission_scoped_entries}`",
        f"- Mission-scoped artifacts omitted from this shared view: `{mission_scoped_artifacts}`",
        "- Mission-specific entries and artifacts are delivered only through recorded checkout views.",
        "",
    ])
    lines.extend(["## Revision history", "", "| Revision | Timestamp | Summary | Changed entries | Changed artifacts | Affected missions |", "| ---: | --- | --- | --- | --- | --- |"])
    for row in connection.execute(
        "SELECT * FROM run_revisions WHERE run_id = ? ORDER BY revision",
        (run_id,),
    ):
        entries = ", ".join(json.loads(row["changed_entries_json"])) or "None"
        artifacts_changed = ", ".join(json.loads(row["changed_artifacts_json"])) or "None"
        affected = ", ".join(json.loads(row["affected_missions_json"])) or "None"
        summary = row["summary"].replace("|", "\\|")
        lines.append(f"| {row['revision']} | `{row['created_at']}` | {summary} | {entries} | {artifacts_changed} | {affected} |")
    lines.extend([
        "",
        "## Run closure and later-turn reuse",
        "",
        f"- Closure reason: {run['closure_reason'] or 'open'}",
        "- Reusable in later active-session turns: conditional",
        f"- Latest reusable revision: `{run['revision']}`",
        "",
    ])
    return "\n".join(lines)


def mission_rows(connection: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    return list(connection.execute("SELECT * FROM missions WHERE run_id = ? ORDER BY mission_id", (run_id,)))


def render_work_map(connection: sqlite3.Connection, run_id: str) -> str:
    run = load_run(connection, run_id)
    session = load_session(connection, run["session_key"])
    lines = [
        f"# Work Map — {run_id}",
        "",
        f"- Session key: `{run['session_key']}`",
        f"- Session squad mode: `{effective_session_mode(run, session)}`",
        f"- Ledger revision: `{run['revision']}`",
        f"- Run status: `{run['status']}`",
        "",
        "| Mission | Specialist | Relationship | Effort | Write mode | Status | Dependencies | Responsibility surface | Distinct value | Context state | Checkout | Result |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = mission_rows(connection, run_id)
    if not rows:
        lines.append("| — | — | — | — | — | — | — | — | — | — | — | — |")
    for row in rows:
        deps = ", ".join(dependencies(connection, run_id, row["mission_id"])) or "—"
        checkout = row["current_view_id"] or "—"
        result = f"v{row['latest_result_version']}" if row["latest_result_version"] else "—"
        responsibility_surface = row["responsibility_surface"].replace("|", "\\|")
        distinct_value = row["distinct_value"].replace("|", "\\|")
        lines.append(
            f"| {row['mission_id']} | `{row['specialist']}` | {row['relationship']} | {row['effort']} | "
            f"{row['write_mode']} | {row['status']} | {deps} | {responsibility_surface} | "
            f"{distinct_value} | `{row['context_state']}` | `{checkout}` | {result} |"
        )
    lines.extend([
        "",
        "This file is generated from SQLite state. Use the Context Hub CLI for every mutation.",
        "",
    ])
    return "\n".join(lines)


def latest_view(connection: sqlite3.Connection, run_id: str, mission_id: str) -> sqlite3.Row | None:
    mission = load_mission(connection, run_id, mission_id)
    if not mission["current_view_id"]:
        return None
    return connection.execute("SELECT * FROM context_views WHERE view_id = ?", (mission["current_view_id"],)).fetchone()


def context_view_integrity_errors(
    connection: sqlite3.Connection,
    view: sqlite3.Row,
) -> list[str]:
    errors: list[str] = []
    view_id = view["view_id"]
    try:
        payload = json.loads(view["snapshot_json"])
    except json.JSONDecodeError:
        return [f"context view snapshot is invalid JSON: {view_id}"]
    if sha256_text(view["snapshot_json"]) != view["snapshot_hash"]:
        errors.append(f"context view hash mismatch: {view_id}")
    if payload.get("runId") != view["run_id"] or payload.get("missionId") != view["mission_id"]:
        errors.append(f"context view identity mismatch: {view_id}")
    if payload.get("revision") != view["revision"]:
        errors.append(f"context view revision mismatch: {view_id}")
    run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (view["run_id"],)).fetchone()
    mission = connection.execute(
        "SELECT * FROM missions WHERE run_id = ? AND mission_id = ?",
        (view["run_id"], view["mission_id"]),
    ).fetchone()
    if run is None or mission is None:
        errors.append(f"context view references a missing run or mission: {view_id}")
    else:
        expected_core = {
            "objective": run["objective"],
            "intent": run["intent"],
            "successCriteria": json.loads(run["success_json"]),
            "hardConstraints": json.loads(run["constraints_json"]),
        }
        if payload.get("sharedCanonicalCore") != expected_core:
            errors.append(f"context view shared canonical core mismatch: {view_id}")
        mission_payload = payload.get("mission", {})
        expected_mission = {
            "specialist": mission["specialist"],
            "relationship": mission["relationship"],
            "objective": mission["objective"],
            "intent": mission["intent"],
            "successConditions": json.loads(mission["success_json"]),
            "hardConstraints": json.loads(mission["constraints_json"]),
            "verificationExpectations": json.loads(mission["verification_expectations_json"]),
            "knownRisks": json.loads(mission["known_risks_json"]),
            "responsibilitySurface": mission["responsibility_surface"],
            "distinctValue": mission["distinct_value"],
            "writeMode": mission["write_mode"],
            "blindFirst": bool(mission["blind_first"]),
            "dependencies": dependencies(connection, view["run_id"], view["mission_id"]),
            "requiredEntries": required_entries(connection, view["run_id"], view["mission_id"]),
            "subscriptions": subscriptions(connection, view["run_id"], view["mission_id"]),
        }
        if mission_payload != expected_mission:
            errors.append(f"context view mission contract mismatch: {view_id}")
    revision = connection.execute(
        "SELECT snapshot_hash FROM run_revisions WHERE run_id = ? AND revision = ?",
        (view["run_id"], view["revision"]),
    ).fetchone()
    if revision is None or payload.get("canonicalSnapshotHash") != revision["snapshot_hash"]:
        errors.append(f"context view canonical snapshot mismatch: {view_id}")

    stored_entries = {
        row["entry_id"]: (row["entry_version"], row["content_hash"])
        for row in connection.execute(
            "SELECT entry_id, entry_version, content_hash FROM context_view_entries WHERE view_id = ?",
            (view_id,),
        )
    }
    payload_entry_items = payload.get("entries", [])
    payload_entries = {
        item.get("entryId"): (item.get("version"), item.get("contentHash"))
        for item in payload_entry_items
        if isinstance(item, dict) and item.get("entryId")
    }
    if len(payload_entry_items) != len(payload_entries):
        errors.append(f"context view contains duplicate or malformed delivered entries: {view_id}")
    if stored_entries != payload_entries:
        errors.append(f"context view delivered-entry set mismatch: {view_id}")
    for entry_id, (version, content_hash) in stored_entries.items():
        version_row = connection.execute(
            """
            SELECT content_hash FROM context_entry_versions
            WHERE run_id = ? AND entry_id = ? AND version = ?
            """,
            (view["run_id"], entry_id, version),
        ).fetchone()
        if version_row is None or version_row["content_hash"] != content_hash:
            errors.append(f"context view entry version mismatch: {view_id}:{entry_id}")

    stored_artifacts = {
        row["artifact_key"]: (row["artifact_version"], row["content_hash"])
        for row in connection.execute(
            "SELECT artifact_key, artifact_version, content_hash FROM context_view_artifacts WHERE view_id = ?",
            (view_id,),
        )
    }
    payload_artifact_items = payload.get("artifacts", [])
    payload_artifacts = {
        item.get("artifactKey"): (item.get("version"), item.get("referenceHash"))
        for item in payload_artifact_items
        if isinstance(item, dict) and item.get("artifactKey")
    }
    if len(payload_artifact_items) != len(payload_artifacts):
        errors.append(f"context view contains duplicate or malformed delivered artifacts: {view_id}")
    if stored_artifacts != payload_artifacts:
        errors.append(f"context view delivered-artifact set mismatch: {view_id}")
    for artifact_key, (version, content_hash) in stored_artifacts.items():
        version_row = connection.execute(
            """
            SELECT content_hash FROM artifact_versions
            WHERE run_id = ? AND artifact_key = ? AND version = ?
            """,
            (view["run_id"], artifact_key, version),
        ).fetchone()
        if version_row is None or version_row["content_hash"] != content_hash:
            errors.append(f"context view artifact version mismatch: {view_id}:{artifact_key}")
    return errors


def render_mission(connection: sqlite3.Connection, run_id: str, mission_id: str, run_dir: Path) -> str:
    mission = load_mission(connection, run_id, mission_id)
    view = latest_view(connection, run_id, mission_id)
    required = required_entries(connection, run_id, mission_id)
    deps = dependencies(connection, run_id, mission_id)
    topics = subscriptions(connection, run_id, mission_id)
    lines = [
        f"# Mission {mission_id} — {mission['objective']}",
        "",
        f"- Specialist: `{mission['specialist']}`",
        f"- Relationship: `{mission['relationship']}`",
        f"- Effort: `{mission['effort']}`",
        f"- Write mode: `{mission['write_mode']}`",
        f"- Responsibility surface: {mission['responsibility_surface']}",
        f"- Distinct decision value: {mission['distinct_value']}",
        f"- Dependencies: {', '.join(deps) if deps else 'None'}",
        f"- Required entries: {', '.join(required) if required else 'None'}",
        f"- Topic subscriptions: {', '.join(topics) if topics else 'None'}",
        "",
        "## Objective",
        "",
        mission["objective"],
        "",
        "## Intent",
        "",
        mission["intent"],
        "",
        "## Success conditions",
        "",
        "```json",
        json.dumps(json.loads(mission["success_json"]), ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
        "## Hard constraints",
        "",
        "```json",
        json.dumps(json.loads(mission["constraints_json"]), ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
        "## Verification expectations",
        "",
        "```json",
        json.dumps(json.loads(mission["verification_expectations_json"]), ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
        "## Known risks",
        "",
        "```json",
        json.dumps(json.loads(mission["known_risks_json"]), ensure_ascii=False, sort_keys=True, indent=2),
        "```",
        "",
        "## Checked-out context view",
        "",
    ]
    if view:
        lines.extend([
            f"- View ID: `{view['view_id']}`",
            f"- Revision delivered: `{view['revision']}`",
            f"- Snapshot SHA-256: `{view['snapshot_hash']}`",
            f"- Snapshot file: `{run_dir / 'checkouts' / (view['view_id'] + '.json')}`",
        ])
    else:
        lines.append("No context view has been checked out yet.")
    lines.extend([
        "",
        "## Authority and guard contract",
        "",
        "- The specialist may work end to end inside the declared authority envelope.",
        "- The specialist cannot edit canonical SQLite state or generated Markdown views.",
        "- Decision-relevant findings are submitted as proposals with evidence.",
        "- A result must cite the exact checked-out snapshot hash.",
        "- A blind-first challenger must reach an initial judgment before seeing the lead's advocacy.",
        "",
    ])
    return "\n".join(lines)


def render_result(connection: sqlite3.Connection, run_id: str, mission_id: str) -> str:
    mission = load_mission(connection, run_id, mission_id)
    if not mission["latest_result_version"]:
        return f"# Result {mission_id}\n\nNo sealed result has been submitted.\n"
    row = fetch_one(
        connection,
        "SELECT * FROM results WHERE run_id = ? AND mission_id = ? AND version = ?",
        (run_id, mission_id, mission["latest_result_version"]),
        f"result {mission_id} v{mission['latest_result_version']}",
    )
    content = json.loads(row["content_json"])
    verification = json.loads(row["verification_json"])
    lines = [
        f"# Result {mission_id} v{row['version']}",
        "",
        f"- Status: `{row['status']}`",
        f"- Result SHA-256: `{row['result_hash']}`",
        f"- Context view: `{row['context_view_id']}`",
        f"- Context view SHA-256: `{row['context_view_hash']}`",
        f"- Sealed at: `{row['sealed_at']}`",
    ]
    if row["verdict"]:
        lines.append(f"- Challenger verdict: `{row['verdict']}`")
    if row["distinct_evidence"]:
        lines.append(f"- Distinct evidence path or method: {row['distinct_evidence']}")
    lines.extend(["", "## Structured result", "", "```json", json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2), "```", "", "## Verification", "", "```json", json.dumps(verification, ensure_ascii=False, sort_keys=True, indent=2), "```", ""])
    return "\n".join(lines)


def render_events(connection: sqlite3.Connection, run_id: str) -> str:
    lines = []
    for row in connection.execute("SELECT * FROM events WHERE run_id = ? ORDER BY event_seq", (run_id,)):
        lines.append(
            canonical_json(
                {
                    "eventSeq": row["event_seq"],
                    "revision": row["revision"],
                    "eventType": row["event_type"],
                    "missionId": row["mission_id"],
                    "payload": json.loads(row["payload_json"]),
                    "createdAt": row["created_at"],
                }
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def render_run(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> None:
    paths = generated_paths(run_dir)
    for key in ("missions", "results", "checkouts", "proposals"):
        private_dir(paths[key], run_dir)
    atomic_write(paths["ledger"], render_ledger(connection, run_id, run_dir))
    atomic_write(paths["work_map"], render_work_map(connection, run_id))
    for mission in mission_rows(connection, run_id):
        mission_id = mission["mission_id"]
        atomic_write(paths["missions"] / f"{mission_id}.md", render_mission(connection, run_id, mission_id, run_dir))
        atomic_write(paths["results"] / f"{mission_id}.md", render_result(connection, run_id, mission_id))
    for row in connection.execute("SELECT * FROM context_views WHERE run_id = ? ORDER BY created_at, view_id", (run_id,)):
        atomic_write(paths["checkouts"] / f"{row['view_id']}.json", pretty_json(json.loads(row["snapshot_json"])))
    for row in connection.execute("SELECT * FROM proposals WHERE run_id = ? ORDER BY proposal_seq", (run_id,)):
        proposal = dict(row)
        proposal["proposalId"] = proposal_display_id(row["proposal_seq"])
        atomic_write(paths["proposals"] / f"{proposal['proposalId']}.json", pretty_json(proposal))
    atomic_write(paths["events"], render_events(connection, run_id))


def render_run_serialized(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> None:
    """Render one coherent generated view while holding the SQLite writer lock."""

    with transaction(connection):
        render_run(connection, run_id, run_dir)


def generated_drift(connection: sqlite3.Connection, run_id: str, run_dir: Path) -> list[str]:
    expected: dict[Path, str] = {
        run_dir / "shared-context.md": render_ledger(connection, run_id, run_dir),
        run_dir / "work-map.md": render_work_map(connection, run_id),
        run_dir / "events.jsonl": render_events(connection, run_id),
    }
    for mission in mission_rows(connection, run_id):
        mission_id = mission["mission_id"]
        expected[run_dir / "missions" / f"{mission_id}.md"] = render_mission(connection, run_id, mission_id, run_dir)
        expected[run_dir / "results" / f"{mission_id}.md"] = render_result(connection, run_id, mission_id)
    for row in connection.execute("SELECT * FROM context_views WHERE run_id = ?", (run_id,)):
        expected[run_dir / "checkouts" / f"{row['view_id']}.json"] = pretty_json(json.loads(row["snapshot_json"]))
    for row in connection.execute("SELECT * FROM proposals WHERE run_id = ?", (run_id,)):
        proposal = dict(row)
        proposal["proposalId"] = proposal_display_id(row["proposal_seq"])
        expected[run_dir / "proposals" / f"{proposal['proposalId']}.json"] = pretty_json(proposal)
    drift = []
    for path, content in expected.items():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            drift.append(str(path.relative_to(run_dir)))
    return sorted(drift)


def path_like_surfaces(surface: str) -> list[str]:
    tokens = [token.strip().replace("\\", "/").rstrip("/") for token in re.split(r"[,;\n]", surface) if token.strip()]
    return tokens


def writer_surfaces_overlap(left: str, right: str) -> bool:
    left_tokens = path_like_surfaces(left)
    right_tokens = path_like_surfaces(right)
    for a in left_tokens:
        for b in right_tokens:
            al = a.lower()
            bl = b.lower()
            if al == bl:
                return True
            if "/" in al and "/" in bl and (al.startswith(bl + "/") or bl.startswith(al + "/")):
                return True
    return False


def mission_descendants(connection: sqlite3.Connection, run_id: str, seeds: Iterable[str]) -> set[str]:
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        for row in connection.execute("SELECT mission_id, depends_on FROM mission_dependencies WHERE run_id = ?", (run_id,)):
            if row["depends_on"] in affected and row["mission_id"] not in affected:
                affected.add(row["mission_id"])
                changed = True
    return affected


def latest_context_consumers_for_entry(connection: sqlite3.Connection, run_id: str, entry_id: str) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            SELECT m.mission_id
            FROM missions m
            JOIN context_view_entries cve ON cve.view_id = m.current_view_id
            WHERE m.run_id = ? AND cve.entry_id = ?
            """,
            (run_id, entry_id),
        )
    }


def latest_context_consumers_for_artifact(connection: sqlite3.Connection, run_id: str, artifact_key: str) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            SELECT m.mission_id
            FROM missions m
            JOIN context_view_artifacts cva ON cva.view_id = m.current_view_id
            WHERE m.run_id = ? AND cva.artifact_key = ?
            """,
            (run_id, artifact_key),
        )
    }


def mission_topic_consumers(connection: sqlite3.Connection, run_id: str, topics: Sequence[str]) -> set[str]:
    if not topics:
        return set()
    placeholders = ",".join("?" for _ in topics)
    return {
        row[0]
        for row in connection.execute(
            f"SELECT DISTINCT mission_id FROM mission_subscriptions WHERE run_id = ? AND topic IN ({placeholders})",
            (run_id, *topics),
        )
    }


def all_relevant_missions(connection: sqlite3.Connection, run_id: str) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT mission_id FROM missions WHERE run_id = ? AND status NOT IN ('superseded', 'rejected')",
            (run_id,),
        )
    }


def affected_by_entry_change(
    connection: sqlite3.Connection,
    run_id: str,
    entry_id: str,
    visibility: Sequence[str],
    topics: Sequence[str],
    additional: Sequence[str],
) -> list[str]:
    affected = set(additional)
    affected.update(latest_context_consumers_for_entry(connection, run_id, entry_id))
    affected.update(
        row[0]
        for row in connection.execute(
            "SELECT mission_id FROM mission_required_entries WHERE run_id = ? AND entry_id = ?",
            (run_id, entry_id),
        )
    )
    affected.update(mission_topic_consumers(connection, run_id, topics))
    if "*" in visibility:
        affected.update(all_relevant_missions(connection, run_id))
    else:
        affected.update(visibility)
    existing = {row[0] for row in connection.execute("SELECT mission_id FROM missions WHERE run_id = ?", (run_id,))}
    unknown = affected - existing
    if unknown:
        raise HubError(f"affected mission does not exist: {', '.join(sorted(unknown))}")
    return sorted(mission_descendants(connection, run_id, affected))


def affected_by_artifact_change(
    connection: sqlite3.Connection,
    run_id: str,
    artifact_key: str,
    visibility: Sequence[str],
    topics: Sequence[str],
    additional: Sequence[str],
) -> list[str]:
    affected = set(additional)
    affected.update(latest_context_consumers_for_artifact(connection, run_id, artifact_key))
    affected.update(mission_topic_consumers(connection, run_id, topics))
    if "*" in visibility:
        affected.update(all_relevant_missions(connection, run_id))
    else:
        affected.update(visibility)
    existing = {row[0] for row in connection.execute("SELECT mission_id FROM missions WHERE run_id = ?", (run_id,))}
    unknown = affected - existing
    if unknown:
        raise HubError(f"affected mission does not exist: {', '.join(sorted(unknown))}")
    return sorted(mission_descendants(connection, run_id, affected))


def invalidate_missions(connection: sqlite3.Connection, run_id: str, affected: Sequence[str], revision: int, reason: str) -> None:
    timestamp = utc_now()
    for mission_id in affected:
        row = load_mission(connection, run_id, mission_id)
        if row["status"] in {"superseded", "rejected"}:
            continue
        connection.execute(
            """
            UPDATE missions
            SET status = 'blocked', context_state = 'refresh-required', required_revision = ?,
                blocked_reason = ?, updated_at = ?
            WHERE run_id = ? AND mission_id = ?
            """,
            (revision, reason, timestamp, run_id, mission_id),
        )


def ensure_dependency_graph_acyclic(connection: sqlite3.Connection, run_id: str) -> None:
    graph: dict[str, list[str]] = {row[0]: [] for row in connection.execute("SELECT mission_id FROM missions WHERE run_id = ?", (run_id,))}
    for row in connection.execute("SELECT mission_id, depends_on FROM mission_dependencies WHERE run_id = ?", (run_id,)):
        graph.setdefault(row["mission_id"], []).append(row["depends_on"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise HubError(f"mission dependency cycle includes {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def ensure_writer_safety(connection: sqlite3.Connection, run_id: str) -> None:
    writers = list(
        connection.execute(
            """
            SELECT * FROM missions
            WHERE run_id = ? AND write_mode = 'writer'
              AND status IN ('planned', 'active', 'blocked')
            ORDER BY mission_id
            """,
            (run_id,),
        )
    )
    for index, left in enumerate(writers):
        for right in writers[index + 1 :]:
            if writer_surfaces_overlap(left["responsibility_surface"], right["responsibility_surface"]):
                raise HubError(f"writer responsibility collision: {left['mission_id']} and {right['mission_id']}")


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = Path(args.runtime_root).expanduser().absolute()
    validate_safe_key(args.session_key, "session key")
    validate_safe_key(args.run_id, "run ID")
    objective = require_non_placeholder(args.objective, "objective")
    intent = require_non_placeholder(args.intent, "intent")
    success = parse_json_value(args.success_json, default=[])
    constraints = parse_json_value(args.constraints_json, default=[])
    private_dir(runtime_root)
    session_dir = private_dir(runtime_root / "sessions" / args.session_key, runtime_root)
    run_dir = session_dir / "runs" / args.run_id
    if run_dir.exists():
        raise HubError(f"run already exists: {run_dir}")
    private_dir(run_dir, session_dir)
    db_path = session_dir / HUB_DB_NAME
    connection = connect_db(db_path, create=True)
    committed = False
    try:
        initialize_schema(connection)
        with transaction(connection):
            timestamp = utc_now()
            session = connection.execute("SELECT * FROM sessions WHERE session_key = ?", (args.session_key,)).fetchone()
            if session is None:
                connection.execute(
                    "INSERT INTO sessions(session_key, mode, created_at, updated_at) VALUES(?, 'active', ?, ?)",
                    (args.session_key, timestamp, timestamp),
                )
            elif session["mode"] != "active":
                raise HubError("session is disabled; reactivate it before starting a run")
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (args.run_id,)).fetchone():
                raise HubError(f"run ID already exists in session database: {args.run_id}")
            connection.execute(
                """
                INSERT INTO runs(
                  run_id, session_key, status, objective, intent, success_json, constraints_json, revision,
                  created_at, updated_at, max_ledger_bytes, max_missions,
                  max_result_bytes, max_active_ids, max_revision_history
                ) VALUES(?, ?, 'active', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.run_id,
                    args.session_key,
                    objective,
                    intent,
                    canonical_json(success),
                    canonical_json(constraints),
                    timestamp,
                    timestamp,
                    DEFAULT_BUDGETS["max_ledger_bytes"],
                    DEFAULT_BUDGETS["max_missions"],
                    DEFAULT_BUDGETS["max_result_bytes"],
                    DEFAULT_BUDGETS["max_active_ids"],
                    DEFAULT_BUDGETS["max_revision_history"],
                ),
            )
            snapshot_hash = record_revision(connection, args.run_id, 1, "Initial objective and intent")
            insert_event(connection, args.run_id, 1, "run.initialized", {"snapshotHash": snapshot_hash})
            budget_usage = enforce_hard_budgets(connection, args.run_id, run_dir)
        committed = True
        render_run_serialized(connection, args.run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "init",
            "sessionKey": args.session_key,
            "runId": args.run_id,
            "runDir": str(run_dir),
            "database": str(db_path),
            "revision": 1,
            "budgetUsage": budget_usage,
        }
    except BaseException:
        if not committed and run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        raise
    finally:
        connection.close()


def command_session_set(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = Path(args.runtime_root).expanduser().absolute()
    validate_safe_key(args.session_key, "session key")
    if args.mode not in SESSION_MODES:
        raise HubError(f"mode must be one of: {', '.join(sorted(SESSION_MODES))}")
    session_dir = runtime_root / "sessions" / args.session_key
    db_path = session_dir / HUB_DB_NAME
    connection = connect_db(db_path)
    try:
        initialize_schema(connection)
        with transaction(connection):
            session = load_session(connection, args.session_key)
            timestamp = utc_now()
            connection.execute("UPDATE sessions SET mode = ?, updated_at = ? WHERE session_key = ?", (args.mode, timestamp, args.session_key))
            if args.mode == "disabled":
                connection.execute(
                    """
                    UPDATE runs SET status = 'blocked', blocked_reason = 'session-disabled', updated_at = ?
                    WHERE session_key = ? AND status = 'active'
                    """,
                    (timestamp, args.session_key),
                )
            else:
                connection.execute(
                    """
                    UPDATE runs SET status = 'active', blocked_reason = NULL, updated_at = ?
                    WHERE session_key = ? AND status = 'blocked' AND blocked_reason = 'session-disabled'
                    """,
                    (timestamp, args.session_key),
                )
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT run_id FROM runs WHERE session_key = ? AND status != 'closed'",
                    (args.session_key,),
                )
            ]
            for run_id in run_ids:
                insert_event(connection, run_id, load_run(connection, run_id)["revision"], "session.mode-changed", {"mode": args.mode})
        for run_id in run_ids:
            render_run_serialized(connection, run_id, session_dir / "runs" / run_id)
        return {"status": "PASS", "operation": "session-set", "sessionKey": session["session_key"], "mode": args.mode, "updatedRuns": run_ids}
    finally:
        connection.close()


def command_mission_add(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    if args.specialist not in SPECIALISTS:
        raise HubError(f"unregistered specialist: {args.specialist}")
    if args.relationship not in RELATIONSHIPS:
        raise HubError(f"invalid relationship: {args.relationship}")
    if args.effort not in EFFORTS:
        raise HubError(f"invalid effort: {args.effort}")
    if args.write_mode not in WRITE_MODES:
        raise HubError(f"invalid write mode: {args.write_mode}")
    objective = require_non_placeholder(args.objective, "objective")
    intent = require_non_placeholder(args.intent, "intent")
    surface = require_non_placeholder(args.surface, "surface")
    distinct_value = require_non_placeholder(args.distinct_value, "distinct-value")
    success = parse_json_value(args.success_json, default=[])
    constraints = parse_json_value(args.constraints_json, default=[])
    verification_expectations = parse_json_value(args.verification_json, default=[])
    known_risks = parse_json_value(args.risks_json, default=[])
    deps = parse_csv(args.depends_on)
    for dependency in deps:
        validate_mission_id(dependency)
    required_ids = parse_csv(args.required_ids)
    validate_entry_ids(required_ids, "required IDs")
    topics = normalize_topics(args.subscribe)
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id)
            if connection.execute("SELECT 1 FROM missions WHERE run_id = ? AND mission_id = ?", (run_id, args.mission_id)).fetchone():
                raise HubError(f"mission already exists: {args.mission_id}")
            count = connection.execute("SELECT COUNT(*) FROM missions WHERE run_id = ?", (run_id,)).fetchone()[0]
            if count >= run["max_missions"]:
                raise HubError("mission budget exhausted")
            existing = {row[0] for row in connection.execute("SELECT mission_id FROM missions WHERE run_id = ?", (run_id,))}
            missing_deps = sorted(set(deps) - existing)
            if missing_deps:
                raise HubError(f"dependency does not exist: {', '.join(missing_deps)}")
            current_ids = {row["entry_id"]: row for row in current_entries(connection, run_id, include_superseded=True)}
            for entry_id in required_ids:
                row = current_ids.get(entry_id)
                if row is None:
                    raise HubError(f"required entry does not exist: {entry_id}")
                if row["superseded"]:
                    raise HubError(f"required entry is superseded: {entry_id}")
                if not visible_to(row["visibility_json"], args.mission_id):
                    raise HubError(f"required entry is not visible to {args.mission_id}: {entry_id}")
            timestamp = utc_now()
            blind_first = int(args.blind_first or args.relationship == "independent-challenger")
            connection.execute(
                """
                INSERT INTO missions(
                  run_id, mission_id, specialist, relationship, effort, status,
                  objective, intent, success_json, constraints_json,
                  verification_expectations_json, known_risks_json,
                  responsibility_surface, distinct_value, write_mode, blind_first, context_state, required_revision,
                  created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending-checkout', ?, ?, ?)
                """,
                (
                    run_id,
                    args.mission_id,
                    args.specialist,
                    args.relationship,
                    args.effort,
                    objective,
                    intent,
                    canonical_json(success),
                    canonical_json(constraints),
                    canonical_json(verification_expectations),
                    canonical_json(known_risks),
                    surface,
                    distinct_value,
                    args.write_mode,
                    blind_first,
                    run["revision"],
                    timestamp,
                    timestamp,
                ),
            )
            connection.executemany(
                "INSERT INTO mission_dependencies(run_id, mission_id, depends_on) VALUES(?, ?, ?)",
                [(run_id, args.mission_id, dependency) for dependency in deps],
            )
            connection.executemany(
                "INSERT INTO mission_required_entries(run_id, mission_id, entry_id) VALUES(?, ?, ?)",
                [(run_id, args.mission_id, entry_id) for entry_id in required_ids],
            )
            connection.executemany(
                "INSERT INTO mission_subscriptions(run_id, mission_id, topic) VALUES(?, ?, ?)",
                [(run_id, args.mission_id, topic) for topic in topics],
            )
            ensure_dependency_graph_acyclic(connection, run_id)
            ensure_writer_safety(connection, run_id)
            insert_event(connection, run_id, run["revision"], "mission.added", {"specialist": args.specialist, "relationship": args.relationship}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "mission-add", "runId": run_id, "missionId": args.mission_id, "requiredRevision": run["revision"], "blindFirst": bool(blind_first)}
    finally:
        connection.close()


def context_view_payload(connection: sqlite3.Connection, run_id: str, mission_id: str) -> dict[str, Any]:
    run = load_run(connection, run_id)
    mission = load_mission(connection, run_id, mission_id)
    revision = fetch_one(
        connection,
        "SELECT snapshot_hash FROM run_revisions WHERE run_id = ? AND revision = ?",
        (run_id, run["revision"]),
        "current canonical revision",
    )
    required = required_entries(connection, run_id, mission_id)
    entries = []
    for row in current_entries(connection, run_id, include_superseded=False):
        if visible_to(row["visibility_json"], mission_id) or row["entry_id"] in required:
            entries.append(
                {
                    "entryId": row["entry_id"],
                    "type": row["entry_type"],
                    "version": row["current_version"],
                    "claim": row["claim"],
                    "evidence": json.loads(row["evidence_json"]),
                    "rationale": row["rationale"],
                    "boundaries": row["boundaries"],
                    "contentHash": row["content_hash"],
                }
            )
    delivered_ids = {item["entryId"] for item in entries}
    missing = sorted(set(required) - delivered_ids)
    if missing:
        raise HubError(f"required entries are not deliverable: {', '.join(missing)}")
    artifacts = []
    for row in current_artifacts(connection, run_id):
        if visible_to(row["visibility_json"], mission_id):
            artifacts.append(
                {
                    "artifactKey": row["artifact_key"],
                    "repository": row["repository"],
                    "path": row["path"],
                    "version": row["current_version"],
                    "commit": row["commit_sha"],
                    "contentSha256": row["content_sha256"],
                    "referenceHash": row["content_hash"],
                }
            )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sessionKey": run["session_key"],
        "runId": run_id,
        "missionId": mission_id,
        "revision": run["revision"],
        "canonicalSnapshotHash": revision["snapshot_hash"],
        "sharedCanonicalCore": {
            "objective": run["objective"],
            "intent": run["intent"],
            "successCriteria": json.loads(run["success_json"]),
            "hardConstraints": json.loads(run["constraints_json"]),
        },
        "mission": {
            "specialist": mission["specialist"],
            "relationship": mission["relationship"],
            "objective": mission["objective"],
            "intent": mission["intent"],
            "successConditions": json.loads(mission["success_json"]),
            "hardConstraints": json.loads(mission["constraints_json"]),
            "verificationExpectations": json.loads(mission["verification_expectations_json"]),
            "knownRisks": json.loads(mission["known_risks_json"]),
            "responsibilitySurface": mission["responsibility_surface"],
            "distinctValue": mission["distinct_value"],
            "writeMode": mission["write_mode"],
            "blindFirst": bool(mission["blind_first"]),
            "dependencies": dependencies(connection, run_id, mission_id),
            "requiredEntries": required,
            "subscriptions": subscriptions(connection, run_id, mission_id),
        },
        "entries": sorted(entries, key=lambda item: item["entryId"]),
        "artifacts": sorted(artifacts, key=lambda item: item["artifactKey"]),
    }


def command_checkout(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = load_mission(connection, run_id, args.mission_id)
            if mission["status"] in {"completed", "superseded", "rejected"}:
                raise HubError(f"cannot checkout context for terminal mission status {mission['status']}")
            payload = context_view_payload(connection, run_id, args.mission_id)
            snapshot_json = canonical_json(payload)
            snapshot_bytes = len(snapshot_json.encode("utf-8"))
            if snapshot_bytes > MAX_CONTEXT_VIEW_BYTES:
                raise HubError(
                    "mission context view exceeds compiled delivery budget: "
                    f"{snapshot_bytes} > {MAX_CONTEXT_VIEW_BYTES} bytes"
                )
            snapshot_hash = sha256_text(snapshot_json)
            view_id = f"V-{args.mission_id}-{run['revision']:04d}-{snapshot_hash[:12]}"
            timestamp = utc_now()
            existing_view = connection.execute(
                "SELECT * FROM context_views WHERE view_id = ?",
                (view_id,),
            ).fetchone()
            if existing_view is None:
                connection.execute(
                    """
                    INSERT INTO context_views(
                      view_id, run_id, mission_id, revision, snapshot_hash, snapshot_json, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (view_id, run_id, args.mission_id, run["revision"], snapshot_hash, snapshot_json, timestamp),
                )
                connection.executemany(
                    "INSERT INTO context_view_entries(view_id, run_id, entry_id, entry_version, content_hash) VALUES(?, ?, ?, ?, ?)",
                    [(view_id, run_id, item["entryId"], item["version"], item["contentHash"]) for item in payload["entries"]],
                )
                connection.executemany(
                    "INSERT INTO context_view_artifacts(view_id, run_id, artifact_key, artifact_version, content_hash) VALUES(?, ?, ?, ?, ?)",
                    [(view_id, run_id, item["artifactKey"], item["version"], item["referenceHash"]) for item in payload["artifacts"]],
                )
            elif (
                existing_view["run_id"] != run_id
                or existing_view["mission_id"] != args.mission_id
                or existing_view["revision"] != run["revision"]
                or existing_view["snapshot_hash"] != snapshot_hash
                or existing_view["snapshot_json"] != snapshot_json
            ):
                raise HubError(f"immutable context view collision: {view_id}")
            next_status = "planned" if mission["status"] == "planned" else "blocked"
            connection.execute(
                """
                UPDATE missions SET current_view_id = ?, context_state = 'current',
                    required_revision = ?, status = ?, blocked_reason = NULL, updated_at = ?
                WHERE run_id = ? AND mission_id = ?
                """,
                (view_id, run["revision"], next_status, timestamp, run_id, args.mission_id),
            )
            insert_event(connection, run_id, run["revision"], "context.checked-out", {"viewId": view_id, "snapshotHash": snapshot_hash, "entryIds": [item["entryId"] for item in payload["entries"]], "artifactKeys": [item["artifactKey"] for item in payload["artifacts"]]}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "checkout",
            "runId": run_id,
            "missionId": args.mission_id,
            "revision": run["revision"],
            "viewId": view_id,
            "snapshotHash": snapshot_hash,
            "snapshotBytes": snapshot_bytes,
            "entries": [{"entryId": item["entryId"], "version": item["version"]} for item in payload["entries"]],
            "artifacts": [{"artifactKey": item["artifactKey"], "version": item["version"]} for item in payload["artifacts"]],
            "snapshotFile": str(run_dir / "checkouts" / f"{view_id}.json"),
        }
    finally:
        connection.close()


def command_ack(args: argparse.Namespace) -> dict[str, Any]:
    if args.revision is not None:
        run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
        connection = connect_db(db_path_for_run(run_dir), read_only=True)
        try:
            validate_schema(connection)
            run = load_run(connection, run_id)
            if int(args.revision) != run["revision"]:
                raise HubError(f"legacy ack revision {args.revision} does not match current revision {run['revision']}; use checkout")
        finally:
            connection.close()
    result = command_checkout(args)
    result["operation"] = "ack"
    result["deprecated"] = True
    result["replacement"] = "checkout"
    return result


def command_mission_status(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    if args.status not in MISSION_STATUSES:
        raise HubError(f"invalid mission status: {args.status}")
    if args.status == "completed":
        raise HubError("mission-status completed is removed; use result-submit to seal a completed result")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = load_mission(connection, run_id, args.mission_id)
            allowed: dict[str, set[str]] = {
                "planned": {"active", "blocked", "rejected", "superseded"},
                "active": {"blocked", "rejected", "superseded"},
                "blocked": {"active", "rejected", "superseded"},
                "completed": set(),
                "rejected": set(),
                "superseded": set(),
            }
            if args.status not in allowed[mission["status"]]:
                raise HubError(f"invalid mission transition: {mission['status']} -> {args.status}")
            if args.status in {"blocked", "rejected", "superseded"} and not args.reason:
                raise HubError(f"mission transition to {args.status} requires --reason")
            if args.status == "active" and mission["context_state"] != "current":
                raise HubError("mission must checkout current context before becoming active")
            next_context_state = terminal_context_state(args.status, mission["context_state"])
            connection.execute(
                """
                UPDATE missions
                SET status = ?, context_state = ?, blocked_reason = ?, updated_at = ?
                WHERE run_id = ? AND mission_id = ?
                """,
                (
                    args.status,
                    next_context_state,
                    args.reason if args.status != "active" else None,
                    utc_now(),
                    run_id,
                    args.mission_id,
                ),
            )
            ensure_writer_safety(connection, run_id)
            insert_event(connection, run_id, load_run(connection, run_id)["revision"], "mission.status-changed", {"from": mission["status"], "to": args.status, "reason": args.reason}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "mission-status",
            "runId": run_id,
            "missionId": args.mission_id,
            "missionStatus": args.status,
            "contextState": next_context_state,
        }
    finally:
        connection.close()


def command_mission_reopen(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    reason = require_non_placeholder(args.reason, "reason")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = load_mission(connection, run_id, args.mission_id)
            if mission["status"] != "completed":
                raise HubError("only a completed mission can be explicitly reopened")
            connection.execute(
                """
                UPDATE missions SET status = 'blocked', context_state = 'pending-checkout',
                    current_view_id = NULL, blocked_reason = ?, updated_at = ?
                WHERE run_id = ? AND mission_id = ?
                """,
                (reason, utc_now(), run_id, args.mission_id),
            )
            insert_event(connection, run_id, load_run(connection, run_id)["revision"], "mission.reopened", {"reason": reason}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "mission-reopen", "runId": run_id, "missionId": args.mission_id, "missionStatus": "blocked"}
    finally:
        connection.close()


def command_propose(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    is_root_proposal = args.mission_id == "root"
    if not is_root_proposal:
        validate_mission_id(args.mission_id)
    if args.action not in PROPOSAL_ACTIONS:
        raise HubError(f"invalid proposal action: {args.action}")
    claim = require_non_placeholder(args.claim, "claim")
    evidence = parse_json_value(args.evidence_json, default={})
    if args.evidence_file:
        evidence = parse_json_file(args.evidence_file, default={})
    target_entry_id = args.entry_id
    if args.action == "create":
        if args.type not in PROPOSAL_TYPES:
            raise HubError(f"create proposal type must be one of: {', '.join(sorted(PROPOSAL_TYPES))}")
        if target_entry_id:
            raise HubError("create proposal must not specify --entry-id")
        visibility = visibility_list(args.visible_to or "all")
        topics = normalize_topics(args.topics)
    else:
        if not target_entry_id or not ENTRY_ID.fullmatch(target_entry_id):
            raise HubError(f"{args.action} proposal requires a valid --entry-id")
        if args.type:
            raise HubError(f"{args.action} proposal must not specify --type")
        visibility = []
        topics = []
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = None if is_root_proposal else load_mission(connection, run_id, args.mission_id)
            if mission is not None and (mission["status"] != "active" or mission["context_state"] != "current"):
                raise HubError("specialist proposal requires an active mission with a current checked-out context view")
            if target_entry_id:
                entry = connection.execute("SELECT * FROM context_entries WHERE run_id = ? AND entry_id = ?", (run_id, target_entry_id)).fetchone()
                if entry is None:
                    raise HubError(f"target entry does not exist: {target_entry_id}")
                if entry["superseded"]:
                    raise HubError(f"target entry is already superseded: {target_entry_id}")
                visibility = visibility_list(args.visible_to) if args.visible_to else json.loads(entry["visibility_json"])
                topics = normalize_topics(args.topics) if args.topics is not None else json.loads(entry["topics_json"])
            timestamp = utc_now()
            cursor = connection.execute(
                """
                INSERT INTO proposals(
                  run_id, mission_id, action, proposal_type, target_entry_id, claim,
                  evidence_json, rationale, boundaries, visibility_json, topics_json,
                  status, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    run_id,
                    None if is_root_proposal else args.mission_id,
                    args.action,
                    args.type,
                    target_entry_id,
                    claim,
                    canonical_json(evidence),
                    args.rationale,
                    args.boundaries,
                    canonical_json(visibility),
                    canonical_json(topics),
                    timestamp,
                ),
            )
            proposal_id = proposal_display_id(cursor.lastrowid)
            insert_event(connection, run_id, run["revision"], "proposal.submitted", {"proposalId": proposal_id, "action": args.action, "targetEntryId": target_entry_id, "source": "root" if is_root_proposal else args.mission_id}, mission_id=None if is_root_proposal else args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "propose", "runId": run_id, "proposalId": proposal_id, "proposalStatus": "pending"}
    finally:
        connection.close()


def command_proposal_reject(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    proposal_seq = parse_proposal_id(args.proposal_id)
    reason = require_non_placeholder(args.reason, "reason")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id, allow_blocked=True)
            proposal = fetch_one(connection, "SELECT * FROM proposals WHERE run_id = ? AND proposal_seq = ?", (run_id, proposal_seq), f"proposal {args.proposal_id}")
            if proposal["status"] != "pending":
                raise HubError(f"proposal is already {proposal['status']}")
            connection.execute(
                "UPDATE proposals SET status = 'rejected', resolved_at = ?, resolution_reason = ? WHERE proposal_seq = ?",
                (utc_now(), reason, proposal_seq),
            )
            insert_event(connection, run_id, run["revision"], "proposal.rejected", {"proposalId": args.proposal_id, "reason": reason}, mission_id=proposal["mission_id"])
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "proposal-reject", "proposalId": args.proposal_id, "proposalStatus": "rejected"}
    finally:
        connection.close()


def entry_version_content(
    entry_type: str,
    claim: str,
    evidence: Any,
    rationale: str | None,
    boundaries: str | None,
    visibility: Sequence[str],
    topics: Sequence[str],
    superseded: bool,
) -> dict[str, Any]:
    return {
        "type": entry_type,
        "claim": claim,
        "evidence": evidence,
        "rationale": rationale,
        "boundaries": boundaries,
        "visibility": list(visibility),
        "topics": list(topics),
        "superseded": superseded,
    }


def command_promote(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    proposal_seq = parse_proposal_id(args.proposal_id)
    promotion_rationale = require_non_placeholder(args.rationale, "rationale")
    additional = parse_csv(args.additional_affected)
    for mission in additional:
        validate_mission_id(mission)
    override_visibility = visibility_list(args.visible_to) if args.visible_to else None
    override_topics = normalize_topics(args.topics) if args.topics is not None else None
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id)
            proposal = fetch_one(connection, "SELECT * FROM proposals WHERE run_id = ? AND proposal_seq = ?", (run_id, proposal_seq), f"proposal {args.proposal_id}")
            if proposal["status"] != "pending":
                raise HubError(f"proposal is already {proposal['status']}")
            action = proposal["action"]
            target_entry_id = proposal["target_entry_id"]
            old_visibility: list[str] = []
            old_topics: list[str] = []
            current_content_hash: str | None = None
            if action == "create":
                entry_type = proposal["proposal_type"]
                entry_id = allocate_entry_id(connection, run_id, entry_type)
                version = 1
            else:
                existing = fetch_one(connection, "SELECT * FROM context_entries WHERE run_id = ? AND entry_id = ?", (run_id, target_entry_id), f"entry {target_entry_id}")
                if existing["superseded"]:
                    raise HubError(f"entry is already superseded: {target_entry_id}")
                entry_type = existing["entry_type"]
                entry_id = target_entry_id
                version = existing["current_version"] + 1
                old_visibility = json.loads(existing["visibility_json"])
                old_topics = json.loads(existing["topics_json"])
                current_content_hash = fetch_one(
                    connection,
                    "SELECT content_hash FROM context_entry_versions WHERE run_id = ? AND entry_id = ? AND version = ?",
                    (run_id, entry_id, existing["current_version"]),
                    f"entry {entry_id} current version",
                )["content_hash"]
            evidence = json.loads(proposal["evidence_json"])
            rationale = proposal["rationale"]
            boundaries = proposal["boundaries"]
            visibility = override_visibility or json.loads(proposal["visibility_json"])
            topics = override_topics or json.loads(proposal["topics_json"])
            if entry_type == "fact" and evidence in ({}, [], None, ""):
                raise HubError("confirmed fact promotion requires evidence")
            if entry_type == "decision" and not (rationale or promotion_rationale):
                raise HubError("accepted decision promotion requires rationale")
            if entry_type == "ownership" and not boundaries:
                raise HubError("ownership promotion requires shared-boundary detail")
            claim = proposal["claim"]
            if action == "supersede":
                claim = f"Superseded: {claim}"
            timestamp = utc_now()
            next_revision = run["revision"] + 1
            content = entry_version_content(
                entry_type,
                claim,
                evidence,
                rationale,
                boundaries,
                visibility,
                topics,
                action == "supersede",
            )
            content_hash = sha256_text(canonical_json(content))
            if action == "update" and content_hash == current_content_hash:
                raise HubError(f"proposal would create a no-op version for {entry_id}")
            if action == "create":
                connection.execute(
                    """
                    INSERT INTO context_entries(
                      run_id, entry_id, entry_type, current_version, superseded,
                      visibility_json, topics_json, created_revision, updated_revision,
                      created_at, updated_at
                    ) VALUES(?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, entry_id, entry_type, version, canonical_json(visibility), canonical_json(topics), next_revision, next_revision, timestamp, timestamp),
                )
            else:
                connection.execute(
                    """
                    UPDATE context_entries
                    SET current_version = ?, superseded = ?, visibility_json = ?, topics_json = ?,
                        updated_revision = ?, updated_at = ?
                    WHERE run_id = ? AND entry_id = ?
                    """,
                    (version, int(action == "supersede"), canonical_json(visibility), canonical_json(topics), next_revision, timestamp, run_id, entry_id),
                )
            connection.execute(
                """
                INSERT INTO context_entry_versions(
                  run_id, entry_id, version, revision, claim, evidence_json, rationale,
                  boundaries, superseded, visibility_json, topics_json, promotion_rationale,
                  content_hash, proposal_seq, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    entry_id,
                    version,
                    next_revision,
                    claim,
                    canonical_json(evidence),
                    rationale,
                    boundaries,
                    int(action == "supersede"),
                    canonical_json(visibility),
                    canonical_json(topics),
                    promotion_rationale,
                    content_hash,
                    proposal_seq,
                    timestamp,
                ),
            )
            impact_visibility = merge_visibility(old_visibility, visibility)
            impact_topics = sorted(set(old_topics) | set(topics))
            affected = affected_by_entry_change(
                connection,
                run_id,
                entry_id,
                impact_visibility,
                impact_topics,
                additional,
            )
            connection.execute("UPDATE runs SET revision = ?, updated_at = ? WHERE run_id = ?", (next_revision, timestamp, run_id))
            invalidate_missions(connection, run_id, affected, next_revision, f"entry-changed:{entry_id}")
            connection.execute(
                """
                UPDATE proposals SET status = 'promoted', resolved_at = ?, promoted_entry_id = ?, resolution_reason = ?
                WHERE proposal_seq = ?
                """,
                (timestamp, entry_id, promotion_rationale, proposal_seq),
            )
            snapshot_hash = record_revision(connection, run_id, next_revision, promotion_rationale, changed_entries=[entry_id], affected_missions=affected)
            insert_event(connection, run_id, next_revision, "context.promoted", {"proposalId": args.proposal_id, "entryId": entry_id, "entryVersion": version, "action": action, "affectedMissions": affected, "snapshotHash": snapshot_hash})
            budget_usage = enforce_hard_budgets(connection, run_id, run_dir)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "promote", "runId": run_id, "proposalId": args.proposal_id, "entryId": entry_id, "entryVersion": version, "revision": next_revision, "affectedMissions": affected, "snapshotHash": snapshot_hash, "budgetUsage": budget_usage}
    finally:
        connection.close()


def command_artifact_record(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_artifact_key(args.artifact_key)
    repository = require_non_placeholder(args.repository, "repository")
    artifact_path = require_non_placeholder(args.path, "path")
    commit_sha = require_non_placeholder(args.commit, "commit")
    if args.content_sha256 and not SHA256_RE.fullmatch(args.content_sha256):
        raise HubError("content SHA-256 must be 64 lowercase hexadecimal characters")
    visibility = visibility_list(args.visible_to)
    topics = normalize_topics(args.topics)
    metadata = parse_json_value(args.metadata_json, default={})
    if args.metadata_file:
        metadata = parse_json_file(args.metadata_file, default={})
    additional = parse_csv(args.additional_affected)
    for mission in additional:
        validate_mission_id(mission)
    summary = require_non_placeholder(args.summary, "summary")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id)
            existing = connection.execute("SELECT * FROM artifacts WHERE run_id = ? AND artifact_key = ?", (run_id, args.artifact_key)).fetchone()
            version = 1 if existing is None else existing["current_version"] + 1
            next_revision = run["revision"] + 1
            timestamp = utc_now()
            content = {
                "artifactKey": args.artifact_key,
                "repository": repository,
                "path": artifact_path,
                "commit": commit_sha,
                "contentSha256": args.content_sha256,
                "metadata": metadata,
                "visibility": visibility,
                "topics": topics,
            }
            content_hash = sha256_text(canonical_json(content))
            old_visibility = json.loads(existing["visibility_json"]) if existing is not None else []
            old_topics = json.loads(existing["topics_json"]) if existing is not None else []
            if existing is not None:
                current_hash = fetch_one(
                    connection,
                    "SELECT content_hash FROM artifact_versions WHERE run_id = ? AND artifact_key = ? AND version = ?",
                    (run_id, args.artifact_key, existing["current_version"]),
                    f"artifact {args.artifact_key} current version",
                )["content_hash"]
                if current_hash == content_hash:
                    raise HubError(f"artifact update is a no-op: {args.artifact_key}")
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO artifacts(
                      run_id, artifact_key, repository, path, current_version,
                      visibility_json, topics_json, created_revision, updated_revision,
                      created_at, updated_at
                    ) VALUES(?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, args.artifact_key, repository, artifact_path, canonical_json(visibility), canonical_json(topics), next_revision, next_revision, timestamp, timestamp),
                )
            else:
                connection.execute(
                    """
                    UPDATE artifacts SET repository = ?, path = ?, current_version = ?,
                        visibility_json = ?, topics_json = ?, updated_revision = ?, updated_at = ?
                    WHERE run_id = ? AND artifact_key = ?
                    """,
                    (repository, artifact_path, version, canonical_json(visibility), canonical_json(topics), next_revision, timestamp, run_id, args.artifact_key),
                )
            connection.execute(
                """
                INSERT INTO artifact_versions(
                  run_id, artifact_key, version, revision, repository, path, commit_sha, content_sha256,
                  metadata_json, visibility_json, topics_json, content_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    args.artifact_key,
                    version,
                    next_revision,
                    repository,
                    artifact_path,
                    commit_sha,
                    args.content_sha256,
                    canonical_json(metadata),
                    canonical_json(visibility),
                    canonical_json(topics),
                    content_hash,
                    timestamp,
                ),
            )
            affected = affected_by_artifact_change(
                connection,
                run_id,
                args.artifact_key,
                merge_visibility(old_visibility, visibility),
                sorted(set(old_topics) | set(topics)),
                additional,
            )
            connection.execute("UPDATE runs SET revision = ?, updated_at = ? WHERE run_id = ?", (next_revision, timestamp, run_id))
            invalidate_missions(connection, run_id, affected, next_revision, f"artifact-changed:{args.artifact_key}")
            snapshot_hash = record_revision(connection, run_id, next_revision, summary, changed_artifacts=[args.artifact_key], affected_missions=affected)
            insert_event(connection, run_id, next_revision, "artifact.recorded", {"artifactKey": args.artifact_key, "artifactVersion": version, "affectedMissions": affected, "snapshotHash": snapshot_hash})
            budget_usage = enforce_hard_budgets(connection, run_id, run_dir)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "artifact-record", "runId": run_id, "artifactKey": args.artifact_key, "artifactVersion": version, "revision": next_revision, "affectedMissions": affected, "snapshotHash": snapshot_hash, "budgetUsage": budget_usage}
    finally:
        connection.close()


def command_delta(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    since = int(args.since_revision)
    if since < 0:
        raise HubError("since revision must be non-negative")
    connection = connect_db(db_path_for_run(run_dir), read_only=True)
    try:
        validate_schema(connection)
        with read_transaction(connection):
            load_mission(connection, run_id, args.mission_id)
            run = load_run(connection, run_id)
            if since > run["revision"]:
                raise HubError(f"since revision {since} is newer than current revision {run['revision']}")
            events = []
            for row in connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND revision > ? ORDER BY event_seq",
                (run_id, since),
            ):
                payload = json.loads(row["payload_json"])
                affected = payload.get("affectedMissions", [])
                if affected and args.mission_id not in affected:
                    continue
                if row["mission_id"] and row["mission_id"] != args.mission_id and args.mission_id not in affected:
                    continue
                events.append({"eventSeq": row["event_seq"], "revision": row["revision"], "eventType": row["event_type"], "payload": payload, "createdAt": row["created_at"]})
            return {"status": "PASS", "operation": "delta", "runId": run_id, "missionId": args.mission_id, "sinceRevision": since, "currentRevision": run["revision"], "events": events}
    finally:
        connection.close()


def validate_result_payload(payload: Any) -> tuple[str, list[Any], str | None, str | None]:
    if not isinstance(payload, dict):
        raise HubError("result file must contain a JSON object")
    status = payload.get("status")
    if status not in {"completed", "partial", "blocked", "needs-root-decision"}:
        raise HubError("result status must be completed, partial, blocked, or needs-root-decision")
    outcome = payload.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip():
        raise HubError("result outcome is required")
    verification = payload.get("verification")
    if not isinstance(verification, list) or not verification:
        raise HubError("result verification must be a non-empty array")
    verdict = payload.get("verdict")
    distinct_evidence = payload.get("distinctEvidence")
    return status, verification, verdict, distinct_evidence


def command_result_submit(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    if not SHA256_RE.fullmatch(args.snapshot_hash):
        raise HubError("snapshot hash must be 64 lowercase hexadecimal characters")
    result_payload = parse_json_file(args.result_file, default={})
    status, verification, verdict, distinct_evidence = validate_result_payload(result_payload)
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = load_mission(connection, run_id, args.mission_id)
            if mission["status"] != "active":
                raise HubError(f"result submission requires an active mission, found {mission['status']}")
            if mission["context_state"] != "current" or not mission["current_view_id"]:
                raise HubError("mission must checkout current context before submitting a result")
            view = fetch_one(connection, "SELECT * FROM context_views WHERE view_id = ?", (mission["current_view_id"],), "current context view")
            if view["snapshot_hash"] != args.snapshot_hash:
                raise HubError("result snapshot hash does not match the mission's current checked-out view")
            incomplete_dependencies = [
                dependency
                for dependency in dependencies(connection, run_id, args.mission_id)
                if load_mission(connection, run_id, dependency)["status"] not in {"completed", "superseded"}
            ]
            if status == "completed" and incomplete_dependencies:
                raise HubError(f"mission cannot complete before dependencies: {', '.join(incomplete_dependencies)}")
            if mission["blind_first"]:
                if verdict not in {"PASS", "FAIL", "UNRESOLVED"}:
                    raise HubError("blind-first challenger result requires PASS, FAIL, or UNRESOLVED verdict")
                if not isinstance(distinct_evidence, str) or not distinct_evidence.strip():
                    raise HubError("blind-first challenger result requires a distinct evidence path or method")
            elif verdict is not None and verdict not in {"PASS", "FAIL", "UNRESOLVED"}:
                raise HubError("result verdict must be PASS, FAIL, or UNRESOLVED when present")
            normalized_result = canonical_json(result_payload)
            result_hash = sha256_text(normalized_result)
            if len(normalized_result.encode("utf-8")) > run["max_result_bytes"]:
                raise HubError("result exceeds the configured result-size budget")
            previous_version = mission["latest_result_version"]
            version = 1 if previous_version is None else previous_version + 1
            timestamp = utc_now()
            connection.execute(
                """
                INSERT INTO results(
                  run_id, mission_id, version, status, result_hash, context_view_id,
                  context_view_hash, content_json, verification_json, verdict,
                  distinct_evidence, supersedes_version, sealed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, args.mission_id, version, status, result_hash, view["view_id"], view["snapshot_hash"], normalized_result, canonical_json(verification), verdict, distinct_evidence, previous_version, timestamp),
            )
            next_mission_status = "completed" if status == "completed" else "blocked"
            blocked_reason = None if status == "completed" else f"result-status:{status}"
            connection.execute(
                """
                UPDATE missions SET status = ?, latest_result_version = ?, blocked_reason = ?, updated_at = ?
                WHERE run_id = ? AND mission_id = ?
                """,
                (next_mission_status, version, blocked_reason, timestamp, run_id, args.mission_id),
            )
            insert_event(connection, run_id, run["revision"], "result.submitted", {"version": version, "status": status, "resultHash": result_hash, "contextViewHash": view["snapshot_hash"], "verdict": verdict}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "result-submit", "runId": run_id, "missionId": args.mission_id, "resultVersion": version, "resultHash": result_hash, "contextViewHash": view["snapshot_hash"], "missionStatus": next_mission_status, "verdict": verdict}
    finally:
        connection.close()


def command_challenge_disposition(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    validate_mission_id(args.mission_id)
    if args.type not in CHALLENGE_DISPOSITIONS:
        raise HubError(f"invalid challenge disposition: {args.type}")
    rationale = require_non_placeholder(args.rationale, "rationale")
    evidence = parse_json_value(args.evidence_json, default={})
    if args.evidence_file:
        evidence = parse_json_file(args.evidence_file, default={})
    if args.decision_id and not ENTRY_ID.fullmatch(args.decision_id):
        raise HubError("decision ID must be a canonical entry ID")
    if args.remediation_mission:
        validate_mission_id(args.remediation_mission)
    if args.type == "accepted-risk" and (not args.decision_id or not args.decision_id.startswith("D-")):
        raise HubError("accepted-risk disposition requires a D-### decision ID")
    if args.type in {"resolved", "challenge-rejected-with-evidence"} and evidence in ({}, [], None, ""):
        raise HubError(f"{args.type} disposition requires evidence")
    if args.type == "mission-reopened" and not args.remediation_mission:
        raise HubError("mission-reopened disposition requires --remediation-mission")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, _ = assert_mutable_run(connection, run_id, allow_blocked=True)
            mission = load_mission(connection, run_id, args.mission_id)
            if mission["relationship"] != "independent-challenger":
                raise HubError("challenge disposition requires an independent-challenger mission")
            if not mission["latest_result_version"]:
                raise HubError("challenger has no sealed result")
            result = fetch_one(
                connection,
                "SELECT * FROM results WHERE run_id = ? AND mission_id = ? AND version = ?",
                (run_id, args.mission_id, mission["latest_result_version"]),
                "challenger result",
            )
            if result["verdict"] not in BLOCKING_CHALLENGE_VERDICTS:
                raise HubError("challenge disposition is only valid for FAIL or UNRESOLVED verdicts")
            if args.decision_id:
                decision = connection.execute("SELECT * FROM context_entries WHERE run_id = ? AND entry_id = ?", (run_id, args.decision_id)).fetchone()
                if decision is None or decision["entry_type"] != "decision" or decision["superseded"]:
                    raise HubError(f"decision ID is not an active accepted decision: {args.decision_id}")
            if args.remediation_mission:
                remediation = load_mission(connection, run_id, args.remediation_mission)
                if remediation["mission_id"] == args.mission_id:
                    raise HubError("challenger cannot be its own remediation mission")
            timestamp = utc_now()
            connection.execute(
                """
                INSERT OR REPLACE INTO challenge_dispositions(
                  run_id, mission_id, result_version, disposition_type, rationale,
                  decision_id, remediation_mission_id, evidence_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, args.mission_id, result["version"], args.type, rationale, args.decision_id, args.remediation_mission, canonical_json(evidence), timestamp),
            )
            insert_event(connection, run_id, run["revision"], "challenge.disposition-recorded", {"resultVersion": result["version"], "type": args.type, "decisionId": args.decision_id, "remediationMissionId": args.remediation_mission}, mission_id=args.mission_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "challenge-disposition", "runId": run_id, "missionId": args.mission_id, "resultVersion": result["version"], "disposition": args.type}
    finally:
        connection.close()


def challenge_disposition_error(connection: sqlite3.Connection, run_id: str, mission: sqlite3.Row) -> str | None:
    if mission["relationship"] != "independent-challenger" or not mission["latest_result_version"]:
        return None
    result = connection.execute(
        "SELECT * FROM results WHERE run_id = ? AND mission_id = ? AND version = ?",
        (run_id, mission["mission_id"], mission["latest_result_version"]),
    ).fetchone()
    if result is None or result["verdict"] not in BLOCKING_CHALLENGE_VERDICTS:
        return None
    disposition = connection.execute(
        "SELECT * FROM challenge_dispositions WHERE run_id = ? AND mission_id = ? AND result_version = ?",
        (run_id, mission["mission_id"], result["version"]),
    ).fetchone()
    if disposition is None:
        return f"challenger {mission['mission_id']} has blocking verdict {result['verdict']} without disposition"
    disposition_type = disposition["disposition_type"]
    if disposition_type == "accepted-risk":
        decision_id = disposition["decision_id"]
        decision = connection.execute(
            "SELECT * FROM context_entries WHERE run_id = ? AND entry_id = ?",
            (run_id, decision_id),
        ).fetchone()
        if decision is None or decision["entry_type"] != "decision" or decision["superseded"]:
            return f"challenger {mission['mission_id']} accepted-risk disposition references an inactive decision: {decision_id}"
    if disposition_type in {"resolved", "challenge-rejected-with-evidence"}:
        evidence = json.loads(disposition["evidence_json"])
        if evidence in ({}, [], None, ""):
            return f"challenger {mission['mission_id']} {disposition_type} disposition lacks evidence"
    if disposition_type == "mission-reopened":
        remediation_id = disposition["remediation_mission_id"]
        if not remediation_id:
            return f"challenger {mission['mission_id']} mission-reopened disposition lacks remediation mission"
        remediation = connection.execute("SELECT * FROM missions WHERE run_id = ? AND mission_id = ?", (run_id, remediation_id)).fetchone()
        if remediation is None or remediation["status"] not in {"completed", "superseded"}:
            return f"challenger {mission['mission_id']} remediation mission is not complete: {remediation_id}"
    return None


def evaluate_run(
    connection: sqlite3.Connection,
    run_dir: Path,
    run_id: str,
    *,
    for_close: bool = False,
    check_generated_views: bool = True,
    check_database_integrity: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if check_database_integrity:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append(f"SQLite integrity check failed: {integrity}")
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_violations:
            errors.append(f"SQLite foreign-key check failed: {len(foreign_key_violations)} violation(s)")

    run = load_run(connection, run_id)
    session = load_session(connection, run["session_key"])
    historical_abandonment = run["status"] == "closed" and run["closure_reason"] == "abandoned"

    def budget_violation(message: str) -> None:
        if historical_abandonment:
            warnings.append(f"abandoned historical run: {message}")
        else:
            errors.append(message)

    for column, maximum in (
        ("max_ledger_bytes", DEFAULT_BUDGETS["max_ledger_bytes"]),
        ("max_missions", DEFAULT_BUDGETS["max_missions"]),
        ("max_result_bytes", DEFAULT_BUDGETS["max_result_bytes"]),
        ("max_active_ids", DEFAULT_BUDGETS["max_active_ids"]),
        ("max_revision_history", DEFAULT_BUDGETS["max_revision_history"]),
    ):
        if run[column] <= 0 or run[column] > maximum:
            budget_violation(f"{column} exceeds the compiled Context Hub guard maximum")

    revision_rows = list(
        connection.execute(
            "SELECT * FROM run_revisions WHERE run_id = ? ORDER BY revision",
            (run_id,),
        )
    )
    revisions = [row["revision"] for row in revision_rows]
    if revisions != list(range(1, run["revision"] + 1)):
        errors.append("run revision history is not contiguous")
    current_revision_row = revision_rows[-1] if revision_rows else None
    if current_revision_row is None or current_revision_row["revision"] != run["revision"]:
        errors.append("run revision does not match latest run-revision record")
    elif current_revision_row["snapshot_hash"] != sha256_text(canonical_json(run_snapshot_payload(connection, run_id))):
        errors.append("current run snapshot hash does not match canonical state")

    for entry in connection.execute("SELECT * FROM context_entries WHERE run_id = ?", (run_id,)):
        versions = list(
            connection.execute(
                "SELECT * FROM context_entry_versions WHERE run_id = ? AND entry_id = ? ORDER BY version",
                (run_id, entry["entry_id"]),
            )
        )
        if [row["version"] for row in versions] != list(range(1, entry["current_version"] + 1)):
            errors.append(f"{entry['entry_id']} version history is not contiguous")
        for version in versions:
            expected = entry_version_content(
                entry["entry_type"],
                version["claim"],
                json.loads(version["evidence_json"]),
                version["rationale"],
                version["boundaries"],
                json.loads(version["visibility_json"]),
                json.loads(version["topics_json"]),
                bool(version["superseded"]),
            )
            if sha256_text(canonical_json(expected)) != version["content_hash"]:
                errors.append(f"{entry['entry_id']} v{version['version']} content hash mismatch")
        if not versions or versions[-1]["version"] != entry["current_version"]:
            errors.append(f"{entry['entry_id']} current version does not match version history")
        elif bool(versions[-1]["superseded"]) != bool(entry["superseded"]):
            errors.append(f"{entry['entry_id']} superseded state does not match current version")

    for artifact in connection.execute("SELECT * FROM artifacts WHERE run_id = ?", (run_id,)):
        versions = list(
            connection.execute(
                "SELECT * FROM artifact_versions WHERE run_id = ? AND artifact_key = ? ORDER BY version",
                (run_id, artifact["artifact_key"]),
            )
        )
        if [row["version"] for row in versions] != list(range(1, artifact["current_version"] + 1)):
            errors.append(f"{artifact['artifact_key']} version history is not contiguous")
        for version in versions:
            expected = {
                "artifactKey": artifact["artifact_key"],
                "repository": version["repository"],
                "path": version["path"],
                "commit": version["commit_sha"],
                "contentSha256": version["content_sha256"],
                "metadata": json.loads(version["metadata_json"]),
                "visibility": json.loads(version["visibility_json"]),
                "topics": json.loads(version["topics_json"]),
            }
            if sha256_text(canonical_json(expected)) != version["content_hash"]:
                errors.append(f"{artifact['artifact_key']} v{version['version']} content hash mismatch")
        if not versions or versions[-1]["version"] != artifact["current_version"]:
            errors.append(f"{artifact['artifact_key']} current version does not match artifact history")

    for view in connection.execute("SELECT * FROM context_views WHERE run_id = ?", (run_id,)):
        errors.extend(context_view_integrity_errors(connection, view))

    if session["mode"] == "disabled" and run["status"] == "active":
        errors.append("disabled session has an active run")
    if run["status"] == "closed" and not run["closed_session_mode"]:
        errors.append("closed run does not record its session mode at closure")

    revision_count = len(revision_rows)
    if revision_count > run["max_revision_history"]:
        budget_violation("revision history exceeds configured budget")
    elif revision_count > run["max_revision_history"] * 0.8:
        warnings.append("revision history is above 80% of its budget")

    active_ids = connection.execute(
        "SELECT COUNT(*) FROM context_entries WHERE run_id = ? AND superseded = 0",
        (run_id,),
    ).fetchone()[0]
    if active_ids > run["max_active_ids"]:
        budget_violation("active context entry count exceeds configured budget")
    elif active_ids > run["max_active_ids"] * 0.8:
        warnings.append("active context entry count is above 80% of its budget")

    ledger = render_ledger(connection, run_id, run_dir)
    ledger_bytes = len(ledger.encode("utf-8"))
    if ledger_bytes > run["max_ledger_bytes"]:
        budget_violation("generated shared ledger exceeds configured budget")
    elif ledger_bytes > run["max_ledger_bytes"] * 0.8:
        warnings.append("generated shared ledger is above 80% of its budget")

    mission_list = mission_rows(connection, run_id)
    if len(mission_list) > run["max_missions"]:
        budget_violation("mission count exceeds configured budget")
    try:
        ensure_dependency_graph_acyclic(connection, run_id)
    except HubError as exc:
        errors.append(str(exc))
    try:
        ensure_writer_safety(connection, run_id)
    except HubError as exc:
        errors.append(str(exc))

    for mission in mission_list:
        mission_id = mission["mission_id"]
        if mission["status"] in DISCARDED_MISSION_STATUSES and mission["context_state"] != "terminal-not-applicable":
            errors.append(
                f"{mission_id} discarded mission must use terminal-not-applicable context state"
            )
        if mission["status"] not in DISCARDED_MISSION_STATUSES and mission["context_state"] == "terminal-not-applicable":
            errors.append(
                f"{mission_id} non-discarded mission cannot use terminal-not-applicable context state"
            )
        current_view = latest_view(connection, run_id, mission_id)
        if mission["current_view_id"] and current_view is None:
            errors.append(f"{mission_id} references a missing context view")
        if current_view is not None:
            if current_view["run_id"] != run_id or current_view["mission_id"] != mission_id:
                errors.append(f"{mission_id} current view belongs to another mission or run")
            if mission["context_state"] == "current" and current_view["revision"] < mission["required_revision"]:
                errors.append(f"{mission_id} current view predates its required revision")
            delivered_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT entry_id FROM context_view_entries WHERE view_id = ?",
                    (current_view["view_id"],),
                )
            }
            missing_required = sorted(set(required_entries(connection, run_id, mission_id)) - delivered_ids)
            if mission["context_state"] == "current" and missing_required:
                errors.append(f"{mission_id} current view omits required entries: {', '.join(missing_required)}")

        if mission["context_state"] == "current":
            if current_view is None:
                errors.append(f"{mission_id} is current without a context view")
            else:
                stale_entries = connection.execute(
                    """
                    SELECT cve.entry_id
                    FROM context_view_entries cve
                    JOIN context_entries e ON e.run_id = ? AND e.entry_id = cve.entry_id
                    WHERE cve.view_id = ? AND (e.current_version != cve.entry_version OR e.superseded = 1)
                    """,
                    (run_id, current_view["view_id"]),
                ).fetchall()
                stale_artifacts = connection.execute(
                    """
                    SELECT cva.artifact_key
                    FROM context_view_artifacts cva
                    JOIN artifacts a ON a.run_id = ? AND a.artifact_key = cva.artifact_key
                    WHERE cva.view_id = ? AND a.current_version != cva.artifact_version
                    """,
                    (run_id, current_view["view_id"]),
                ).fetchall()
                if stale_entries or stale_artifacts:
                    errors.append(f"{mission_id} is marked current with stale delivered versions")

        result_rows = list(
            connection.execute(
                "SELECT * FROM results WHERE run_id = ? AND mission_id = ? ORDER BY version",
                (run_id, mission_id),
            )
        )
        expected_result_versions = list(range(1, len(result_rows) + 1))
        if [row["version"] for row in result_rows] != expected_result_versions:
            errors.append(f"{mission_id} result versions are not contiguous")
        for index, result in enumerate(result_rows):
            expected_supersedes = None if index == 0 else result_rows[index - 1]["version"]
            if result["supersedes_version"] != expected_supersedes:
                errors.append(f"{mission_id} result v{result['version']} has an invalid supersedes chain")
            if sha256_text(result["content_json"]) != result["result_hash"]:
                errors.append(f"{mission_id} sealed result v{result['version']} hash does not match content")
            if len(result["content_json"].encode("utf-8")) > run["max_result_bytes"]:
                errors.append(f"{mission_id} sealed result v{result['version']} exceeds configured budget")
            result_view = connection.execute(
                "SELECT * FROM context_views WHERE view_id = ?",
                (result["context_view_id"],),
            ).fetchone()
            if (
                result_view is None
                or result_view["run_id"] != run_id
                or result_view["mission_id"] != mission_id
                or result_view["snapshot_hash"] != result["context_view_hash"]
            ):
                errors.append(f"{mission_id} sealed result v{result['version']} references an invalid context view")
        latest_version = result_rows[-1]["version"] if result_rows else None
        if mission["latest_result_version"] != latest_version:
            errors.append(f"{mission_id} latest result pointer does not match sealed result history")

        if mission["status"] == "completed":
            if not mission["latest_result_version"]:
                errors.append(f"{mission_id} is completed without a sealed result")
            incomplete = [
                dependency
                for dependency in dependencies(connection, run_id, mission_id)
                if load_mission(connection, run_id, dependency)["status"] not in {"completed", "superseded"}
            ]
            if incomplete:
                errors.append(f"{mission_id} completed before dependencies: {', '.join(incomplete)}")

        disposition_error = challenge_disposition_error(connection, run_id, mission)
        if disposition_error:
            warnings.append(disposition_error)

    pending_proposals = connection.execute(
        "SELECT COUNT(*) FROM proposals WHERE run_id = ? AND status = 'pending'",
        (run_id,),
    ).fetchone()[0]
    drift = generated_drift(connection, run_id, run_dir) if check_generated_views else []
    if drift:
        errors.append(f"generated views drifted from SQLite canonical state: {', '.join(drift)}")

    if for_close:
        if run["status"] == "closed":
            errors.append("run is already closed")
        unfinished = [
            mission["mission_id"]
            for mission in mission_list
            if mission["status"] not in TERMINAL_MISSION_STATUSES
        ]
        if unfinished:
            errors.append(f"cannot close with unfinished missions: {', '.join(unfinished)}")
        stale = [
            mission["mission_id"]
            for mission in mission_list
            if mission["status"] not in DISCARDED_MISSION_STATUSES
            and mission["context_state"] in {"pending-checkout", "refresh-required"}
        ]
        if stale:
            errors.append(f"cannot close with stale missions: {', '.join(stale)}")
        if pending_proposals:
            errors.append(f"cannot close with pending proposals: {pending_proposals}")
        for mission in mission_list:
            disposition_error = challenge_disposition_error(connection, run_id, mission)
            if disposition_error:
                errors.append(disposition_error)

    return {
        "status": "FAIL" if errors else "PASS",
        "operation": "check-for-close" if for_close else "check",
        "runId": run_id,
        "runStatus": run["status"],
        "sessionMode": effective_session_mode(run, session),
        "revision": run["revision"],
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "generatedDrift": drift,
        "budgetUsage": {
            "ledgerBytes": ledger_bytes,
            "activeIds": active_ids,
            "missions": len(mission_list),
            "revisions": revision_count,
            "maxLedgerBytes": run["max_ledger_bytes"],
            "maxActiveIds": run["max_active_ids"],
            "maxMissions": run["max_missions"],
            "maxRevisions": run["max_revision_history"],
        },
    }

def command_check(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    connection = connect_db(db_path_for_run(run_dir), read_only=True)
    try:
        validate_schema(connection)
        with read_transaction(connection):
            return evaluate_run(connection, run_dir, run_id, for_close=bool(args.for_close))
    finally:
        connection.close()

def command_render(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        load_run(connection, run_id)
        render_run_serialized(connection, run_id, run_dir)
        return {"status": "PASS", "operation": "render", "runId": run_id}
    finally:
        connection.close()


def command_close(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    reason = args.reason or "completed"
    if reason not in {"completed", "superseded"}:
        raise HubError("close reason must be completed or superseded; use run-abandon for non-acceptance closure")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, session = assert_mutable_run(connection, run_id, allow_blocked=True)
            # BEGIN IMMEDIATE serializes closure against every other Context Hub mutation.
            check = evaluate_run(connection, run_dir, run_id, for_close=True)
            if check["status"] != "PASS":
                raise HubError("run cannot close: " + "; ".join(check["errors"]))
            timestamp = utc_now()
            connection.execute(
                """
                UPDATE runs
                SET status = 'closed', closure_reason = ?, closed_at = ?, updated_at = ?,
                    closed_session_mode = ?, blocked_reason = NULL
                WHERE run_id = ?
                """,
                (reason, timestamp, timestamp, session["mode"], run_id),
            )
            insert_event(connection, run_id, run["revision"], "run.closed", {"reason": reason})
        render_run_serialized(connection, run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "close",
            "runId": run_id,
            "revision": run["revision"],
            "reason": reason,
            "sessionMode": session["mode"],
        }
    finally:
        connection.close()

def command_status(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    connection = connect_db(db_path_for_run(run_dir), read_only=True)
    try:
        validate_schema(connection)
        with read_transaction(connection):
            run = load_run(connection, run_id)
            session = load_session(connection, run["session_key"])
            missions = []
            for mission in mission_rows(connection, run_id):
                view = latest_view(connection, run_id, mission["mission_id"])
                missions.append(
                    {
                        "missionId": mission["mission_id"],
                        "specialist": mission["specialist"],
                        "status": mission["status"],
                        "contextState": mission["context_state"],
                        "currentViewId": mission["current_view_id"],
                        "snapshotHash": view["snapshot_hash"] if view else None,
                        "latestResultVersion": mission["latest_result_version"],
                        "dependencies": dependencies(connection, run_id, mission["mission_id"]),
                        "requiredEntries": required_entries(connection, run_id, mission["mission_id"]),
                    }
                )
            pending = [proposal_display_id(row[0]) for row in connection.execute("SELECT proposal_seq FROM proposals WHERE run_id = ? AND status = 'pending' ORDER BY proposal_seq", (run_id,))]
            return {"status": "PASS", "operation": "status", "sessionKey": run["session_key"], "sessionMode": session["mode"], "runId": run_id, "runStatus": run["status"], "revision": run["revision"], "missions": missions, "pendingProposals": pending, "database": str(db_path_for_run(run_dir))}
    finally:
        connection.close()



def _abandon_run_rows(
    connection: sqlite3.Connection,
    run: sqlite3.Row,
    session: sqlite3.Row,
    run_dir: Path,
    reason: str,
    successor_run_id: str | None,
) -> dict[str, int]:
    run_id = run["run_id"]
    timestamp = utc_now()
    pending_count = connection.execute(
        "SELECT COUNT(*) FROM proposals WHERE run_id = ? AND status = 'pending'",
        (run_id,),
    ).fetchone()[0]
    connection.execute(
        """
        UPDATE proposals
        SET status = 'rejected', resolved_at = ?, resolution_reason = ?
        WHERE run_id = ? AND status = 'pending'
        """,
        (timestamp, f"run-abandoned: {reason}", run_id),
    )
    unfinished_count = connection.execute(
        """
        SELECT COUNT(*) FROM missions
        WHERE run_id = ? AND status NOT IN ('completed', 'superseded', 'rejected')
        """,
        (run_id,),
    ).fetchone()[0]
    connection.execute(
        """
        UPDATE missions
        SET status = 'superseded', context_state = 'terminal-not-applicable',
            blocked_reason = ?, updated_at = ?
        WHERE run_id = ? AND status NOT IN ('completed', 'superseded', 'rejected')
        """,
        (f"run-abandoned: {reason}", timestamp, run_id),
    )
    repaired_terminal_count = connection.execute(
        """
        SELECT COUNT(*) FROM missions
        WHERE run_id = ? AND status IN ('superseded', 'rejected')
          AND context_state != 'terminal-not-applicable'
        """,
        (run_id,),
    ).fetchone()[0]
    connection.execute(
        """
        UPDATE missions
        SET context_state = 'terminal-not-applicable', updated_at = ?
        WHERE run_id = ? AND status IN ('superseded', 'rejected')
          AND context_state != 'terminal-not-applicable'
        """,
        (timestamp, run_id),
    )
    connection.execute(
        """
        UPDATE runs
        SET status = 'closed', closure_reason = 'abandoned', closed_at = ?, updated_at = ?,
            closed_session_mode = ?, blocked_reason = ?
        WHERE run_id = ?
        """,
        (
            timestamp,
            timestamp,
            session["mode"],
            f"abandoned: {reason}" + (f"; successor={successor_run_id}" if successor_run_id else ""),
            run_id,
        ),
    )
    insert_event(
        connection,
        run_id,
        run["revision"],
        "run.abandoned",
        {
            "reason": reason,
            "successorRunId": successor_run_id,
            "rejectedPendingProposals": pending_count,
            "supersededUnfinishedMissions": unfinished_count,
            "repairedTerminalMissions": repaired_terminal_count,
        },
    )
    integrity = evaluate_run(
        connection,
        run_dir,
        run_id,
        for_close=False,
        check_generated_views=False,
    )
    if integrity["status"] != "PASS":
        raise HubError(
            "run cannot be abandoned because canonical integrity failed: "
            + "; ".join(integrity["errors"])
        )
    return {
        "rejectedPendingProposals": pending_count,
        "supersededUnfinishedMissions": unfinished_count,
        "repairedTerminalMissions": repaired_terminal_count,
    }


def command_repair_terminal_context(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    connection = connect_db(db_path_for_run(run_dir))

    def invalid_rows() -> list[sqlite3.Row]:
        return list(
            connection.execute(
                """
                SELECT mission_id, status, context_state
                FROM missions
                WHERE run_id = ? AND status IN ('superseded', 'rejected')
                  AND context_state != 'terminal-not-applicable'
                ORDER BY mission_id
                """,
                (run_id,),
            )
        )

    try:
        initialize_schema(connection)
        if args.apply:
            with transaction(connection):
                run, _ = assert_open_run(connection, run_id)
                rows = invalid_rows()
                timestamp = utc_now()
                connection.execute(
                    """
                    UPDATE missions
                    SET context_state = 'terminal-not-applicable', updated_at = ?
                    WHERE run_id = ? AND status IN ('superseded', 'rejected')
                      AND context_state != 'terminal-not-applicable'
                    """,
                    (timestamp, run_id),
                )
                if rows:
                    insert_event(
                        connection,
                        run_id,
                        run["revision"],
                        "mission.terminal-context-repaired",
                        {"missions": [row["mission_id"] for row in rows]},
                    )
        else:
            with read_transaction(connection):
                load_run(connection, run_id)
                rows = invalid_rows()
        changes = [
            {
                "missionId": row["mission_id"],
                "status": row["status"],
                "fromContextState": row["context_state"],
                "toContextState": "terminal-not-applicable",
            }
            for row in rows
        ]
        if args.apply and rows:
            render_run_serialized(connection, run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "repair-terminal-context",
            "runId": run_id,
            "apply": bool(args.apply),
            "changeCount": len(changes),
            "changes": changes,
        }
    finally:
        connection.close()


def command_run_abandon(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, _, run_id = run_dir_parts(Path(args.run_dir))
    reason = require_non_placeholder(args.reason, "reason")
    successor_run_id = args.successor_run_id
    if successor_run_id:
        validate_safe_key(successor_run_id, "successor run ID")
    connection = connect_db(db_path_for_run(run_dir))
    try:
        initialize_schema(connection)
        with transaction(connection):
            run, session = assert_open_run(connection, run_id)
            if successor_run_id == run_id:
                raise HubError("successor run must differ from the abandoned run")
            if successor_run_id:
                successor = connection.execute(
                    "SELECT * FROM runs WHERE run_id = ? AND session_key = ?",
                    (successor_run_id, run["session_key"]),
                ).fetchone()
                if successor is None:
                    raise HubError(f"successor run does not exist in the session: {successor_run_id}")
                if successor["status"] == "closed":
                    raise HubError(f"successor run is already closed: {successor_run_id}")
            summary = _abandon_run_rows(connection, run, session, run_dir, reason, successor_run_id)
        render_run_serialized(connection, run_id, run_dir)
        return {
            "status": "PASS",
            "operation": "run-abandon",
            "runId": run_id,
            "reason": reason,
            "successorRunId": successor_run_id,
            **summary,
        }
    finally:
        connection.close()


def command_session_audit(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = Path(args.runtime_root).expanduser().absolute()
    validate_safe_key(args.session_key, "session key")
    stale_hours = float(args.stale_hours)
    if stale_hours <= 0:
        raise HubError("stale hours must be positive")
    session_dir = runtime_root / "sessions" / args.session_key
    connection = connect_db(session_dir / HUB_DB_NAME, read_only=True)
    try:
        validate_schema(connection)
        with read_transaction(connection):
            session = load_session(connection, args.session_key)
            database_errors: list[str] = []
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                database_errors.append(f"SQLite integrity check failed: {integrity}")
            foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_violations:
                database_errors.append(
                    f"SQLite foreign-key check failed: {len(foreign_key_violations)} violation(s)"
                )
            now = dt.datetime.now(dt.timezone.utc)
            reports: list[dict[str, Any]] = []
            overall = "FAIL" if database_errors else "PASS"
            for run in connection.execute(
                "SELECT * FROM runs WHERE session_key = ? ORDER BY created_at",
                (args.session_key,),
            ):
                run_dir = session_dir / "runs" / run["run_id"]
                terminal_stale = connection.execute(
                    """
                    SELECT COUNT(*) FROM missions
                    WHERE run_id = ? AND status IN ('superseded', 'rejected')
                      AND context_state != 'terminal-not-applicable'
                    """,
                    (run["run_id"],),
                ).fetchone()[0]
                refresh_required = connection.execute(
                    "SELECT COUNT(*) FROM missions WHERE run_id = ? AND context_state = 'refresh-required'",
                    (run["run_id"],),
                ).fetchone()[0]
                pending_proposals = connection.execute(
                    "SELECT COUNT(*) FROM proposals WHERE run_id = ? AND status = 'pending'",
                    (run["run_id"],),
                ).fetchone()[0]
                updated = dt.datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                age_hours = max(0.0, (now - updated).total_seconds() / 3600.0)
                check = evaluate_run(
                    connection,
                    run_dir,
                    run["run_id"],
                    for_close=False,
                    check_database_integrity=False,
                )
                usage = check["budgetUsage"]
                budget_warning = any(
                    usage[key] > usage[max_key] * 0.8
                    for key, max_key in (
                        ("ledgerBytes", "maxLedgerBytes"),
                        ("activeIds", "maxActiveIds"),
                        ("missions", "maxMissions"),
                        ("revisions", "maxRevisions"),
                    )
                )
                active_warning = run["status"] != "closed" and bool(check["warnings"])
                severity = "PASS"
                if database_errors or check["status"] == "FAIL" or terminal_stale:
                    severity = "FAIL"
                    overall = "FAIL"
                elif (
                    (run["status"] != "closed" and age_hours >= stale_hours)
                    or budget_warning
                    or refresh_required
                    or pending_proposals
                    or active_warning
                ):
                    severity = "WARN"
                    if overall == "PASS":
                        overall = "WARN"
                reports.append(
                    {
                        "runId": run["run_id"],
                        "runStatus": run["status"],
                        "severity": severity,
                        "ageHours": round(age_hours, 2),
                        "budgetUsage": usage,
                        "terminalStaleMissions": terminal_stale,
                        "refreshRequiredMissions": refresh_required,
                        "pendingProposals": pending_proposals,
                        "checkErrors": check["errors"],
                        "checkWarnings": check["warnings"],
                    }
                )
            return {
                "status": overall,
                "operation": "session-audit",
                "sessionKey": session["session_key"],
                "sessionMode": session["mode"],
                "staleHours": stale_hours,
                "databaseErrors": database_errors,
                "runs": reports,
            }
    finally:
        connection.close()

def command_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    run_dir, _, session_key, run_id = run_dir_parts(Path(args.run_dir))
    source_db = db_path_for_run(run_dir)
    output_dir = Path(args.output_dir).expanduser().absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise HubError(f"snapshot output already exists: {output_dir}")
    parent = output_dir.parent
    if not parent.exists():
        parent.mkdir(parents=True, mode=0o700)
    ensure_no_symlink(parent)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=parent))
    os.chmod(temp_dir, 0o700)
    snapshot_db = temp_dir / HUB_DB_NAME
    manifest_path = temp_dir / "manifest.json"
    source = connect_db(source_db, read_only=True)
    destination: sqlite3.Connection | None = None
    try:
        source_schema_version = validate_schema(source)
        with read_transaction(source):
            source_run = load_run(source, run_id)
            if source_run["session_key"] != session_key:
                raise HubError("snapshot run does not belong to the requested session")
            destination = sqlite3.connect(snapshot_db)
            source.backup(destination)
        destination.row_factory = sqlite3.Row
        destination.execute("PRAGMA foreign_keys = ON")
        destination_schema_version = validate_schema(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = destination.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise HubError("snapshot verification failed")
        if destination_schema_version != source_schema_version:
            raise HubError("snapshot schema version differs from source")
        destination.close()
        destination = None
        os.chmod(snapshot_db, 0o600)
        manifest = {
            "schemaVersion": source_schema_version,
            "sessionKey": session_key,
            "sourceRunId": run_id,
            "sourceRunRevision": source_run["revision"],
            "sourceRunStatus": source_run["status"],
            "createdAt": utc_now(),
            "databaseFile": HUB_DB_NAME,
            "databaseSha256": sha256_bytes(snapshot_db.read_bytes()),
            "integrityCheck": integrity,
            "foreignKeyViolations": len(foreign_keys),
        }
        atomic_write(manifest_path, pretty_json(manifest), 0o600)
        os.replace(temp_dir, output_dir)
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return {
            "status": "PASS",
            "operation": "snapshot",
            "sessionKey": session_key,
            "sourceRunId": run_id,
            "outputDir": str(output_dir),
            "database": str(output_dir / HUB_DB_NAME),
            "manifest": str(output_dir / "manifest.json"),
            "databaseSha256": manifest["databaseSha256"],
        }
    finally:
        if destination is not None:
            destination.close()
        source.close()
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def command_run_rollover(args: argparse.Namespace) -> dict[str, Any]:
    source_run_dir, session_dir, session_key, source_run_id = run_dir_parts(Path(args.run_dir))
    validate_safe_key(args.new_run_id, "new run ID")
    selected_entry_ids = parse_csv(args.entry_ids)
    validate_entry_ids(selected_entry_ids, "entry IDs")
    selected_artifact_keys = parse_csv(args.artifact_keys)
    for key in selected_artifact_keys:
        validate_artifact_key(key)
    reason = require_non_placeholder(args.reason, "reason")
    if args.abandon_source:
        raise HubError(
            "--abandon-source is intentionally unsupported; verify the successor first, "
            "then call run-abandon with --successor-run-id"
        )
    connection = connect_db(db_path_for_run(source_run_dir))
    new_run_dir = session_dir / "runs" / args.new_run_id
    try:
        initialize_schema(connection)
        with transaction(connection):
            source_run = load_run(connection, source_run_id)
            session = load_session(connection, session_key)
            source_revision = fetch_one(
                connection,
                "SELECT * FROM run_revisions WHERE run_id = ? AND revision = ?",
                (source_run_id, source_run["revision"]),
                "source run revision",
            )
            computed_source_snapshot = sha256_text(
                canonical_json(run_snapshot_payload(connection, source_run_id))
            )
            if source_revision["snapshot_hash"] != computed_source_snapshot:
                raise HubError("source run canonical snapshot hash does not match current state")
            if session["mode"] != "active":
                raise HubError("session squad mode is disabled")
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (args.new_run_id,)).fetchone():
                raise HubError(f"run ID already exists in session database: {args.new_run_id}")
            if new_run_dir.exists():
                raise HubError(f"successor run directory already exists: {new_run_dir}")
            objective = require_non_placeholder(args.objective or source_run["objective"], "objective")
            intent = require_non_placeholder(args.intent or source_run["intent"], "intent")
            timestamp = utc_now()
            connection.execute(
                """
                INSERT INTO runs(
                  run_id, session_key, status, objective, intent, success_json, constraints_json, revision,
                  created_at, updated_at, max_ledger_bytes, max_missions,
                  max_result_bytes, max_active_ids, max_revision_history
                ) VALUES(?, ?, 'active', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.new_run_id,
                    session_key,
                    objective,
                    intent,
                    source_run["success_json"],
                    source_run["constraints_json"],
                    timestamp,
                    timestamp,
                    DEFAULT_BUDGETS["max_ledger_bytes"],
                    DEFAULT_BUDGETS["max_missions"],
                    DEFAULT_BUDGETS["max_result_bytes"],
                    DEFAULT_BUDGETS["max_active_ids"],
                    DEFAULT_BUDGETS["max_revision_history"],
                ),
            )
            source_entries = {row["entry_id"]: row for row in current_entries(connection, source_run_id)}
            if args.include_global_active:
                selected_entry_ids = sorted(
                    set(selected_entry_ids)
                    | {
                        row["entry_id"]
                        for row in source_entries.values()
                        if not row["superseded"] and json.loads(row["visibility_json"]) == ["*"]
                    }
                )
            for entry_id in selected_entry_ids:
                row = source_entries.get(entry_id)
                if row is None:
                    raise HubError(f"rollover entry does not exist: {entry_id}")
                if row["superseded"]:
                    raise HubError(f"rollover entry is superseded: {entry_id}")
                if json.loads(row["visibility_json"]) != ["*"]:
                    raise HubError(f"rollover entry is not globally visible: {entry_id}")
                content = entry_version_content(
                    row["entry_type"],
                    row["claim"],
                    json.loads(row["evidence_json"]),
                    row["rationale"],
                    row["boundaries"],
                    ["*"],
                    json.loads(row["topics_json"]),
                    False,
                )
                content_hash = sha256_text(canonical_json(content))
                if content_hash != row["content_hash"]:
                    raise HubError(f"rollover source entry hash mismatch: {entry_id}")
                connection.execute(
                    """
                    INSERT INTO context_entries(
                      run_id, entry_id, entry_type, current_version, superseded,
                      visibility_json, topics_json, created_revision, updated_revision,
                      created_at, updated_at
                    ) VALUES(?, ?, ?, 1, 0, ?, ?, 1, 1, ?, ?)
                    """,
                    (
                        args.new_run_id,
                        entry_id,
                        row["entry_type"],
                        canonical_json(["*"]),
                        row["topics_json"],
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO context_entry_versions(
                      run_id, entry_id, version, revision, claim, evidence_json, rationale,
                      boundaries, superseded, visibility_json, topics_json, promotion_rationale,
                      content_hash, proposal_seq, created_at
                    ) VALUES(?, ?, 1, 1, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        args.new_run_id,
                        entry_id,
                        row["claim"],
                        row["evidence_json"],
                        row["rationale"],
                        row["boundaries"],
                        canonical_json(["*"]),
                        row["topics_json"],
                        f"Rolled over from {source_run_id}:{entry_id}@v{row['current_version']}",
                        content_hash,
                        timestamp,
                    ),
                )
            source_artifacts = {row["artifact_key"]: row for row in current_artifacts(connection, source_run_id)}
            for artifact_key in selected_artifact_keys:
                row = source_artifacts.get(artifact_key)
                if row is None:
                    raise HubError(f"rollover artifact does not exist: {artifact_key}")
                if json.loads(row["visibility_json"]) != ["*"]:
                    raise HubError(f"rollover artifact is not globally visible: {artifact_key}")
                content = {
                    "artifactKey": artifact_key,
                    "repository": row["repository"],
                    "path": row["path"],
                    "commit": row["commit_sha"],
                    "contentSha256": row["content_sha256"],
                    "metadata": json.loads(row["metadata_json"]),
                    "visibility": ["*"],
                    "topics": json.loads(row["topics_json"]),
                }
                content_hash = sha256_text(canonical_json(content))
                if content_hash != row["content_hash"]:
                    raise HubError(f"rollover source artifact hash mismatch: {artifact_key}")
                connection.execute(
                    """
                    INSERT INTO artifacts(
                      run_id, artifact_key, repository, path, current_version,
                      visibility_json, topics_json, created_revision, updated_revision,
                      created_at, updated_at
                    ) VALUES(?, ?, ?, ?, 1, ?, ?, 1, 1, ?, ?)
                    """,
                    (
                        args.new_run_id,
                        artifact_key,
                        row["repository"],
                        row["path"],
                        canonical_json(["*"]),
                        row["topics_json"],
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO artifact_versions(
                      run_id, artifact_key, version, revision, repository, path, commit_sha,
                      content_sha256, metadata_json, visibility_json, topics_json,
                      content_hash, created_at
                    ) VALUES(?, ?, 1, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.new_run_id,
                        artifact_key,
                        row["repository"],
                        row["path"],
                        row["commit_sha"],
                        row["content_sha256"],
                        row["metadata_json"],
                        canonical_json(["*"]),
                        row["topics_json"],
                        content_hash,
                        timestamp,
                    ),
                )
            snapshot_hash = record_revision(
                connection,
                args.new_run_id,
                1,
                f"Minimal rollover from {source_run_id}: {reason}",
                changed_entries=selected_entry_ids,
                changed_artifacts=selected_artifact_keys,
            )
            insert_event(
                connection,
                args.new_run_id,
                1,
                "run.rolled-over",
                {
                    "sourceRunId": source_run_id,
                    "reason": reason,
                    "entries": selected_entry_ids,
                    "artifacts": selected_artifact_keys,
                    "snapshotHash": snapshot_hash,
                },
            )
            budget_usage = enforce_hard_budgets(connection, args.new_run_id, new_run_dir)
            semantic_check = evaluate_run(
                connection,
                new_run_dir,
                args.new_run_id,
                for_close=False,
                check_generated_views=False,
                check_database_integrity=False,
            )
            if semantic_check["status"] != "PASS":
                raise HubError(
                    "successor run failed pre-commit validation: "
                    + "; ".join(semantic_check["errors"])
                )
        try:
            private_dir(new_run_dir, session_dir)
            render_run_serialized(connection, args.new_run_id, new_run_dir)
        except BaseException as exc:
            with transaction(connection):
                connection.execute("DELETE FROM runs WHERE run_id = ?", (args.new_run_id,))
            shutil.rmtree(new_run_dir, ignore_errors=True)
            raise HubError(
                f"successor projection failed and canonical successor was removed: {exc}"
            ) from exc
        return {
            "status": "PASS",
            "operation": "run-rollover",
            "sourceRunId": source_run_id,
            "newRunId": args.new_run_id,
            "newRunDir": str(new_run_dir),
            "entryIds": selected_entry_ids,
            "artifactKeys": selected_artifact_keys,
            "snapshotHash": snapshot_hash,
            "sourceSnapshotHash": source_revision["snapshot_hash"],
            "budgetUsage": budget_usage,
            "sourceAbandoned": False,
            "nextAction": (
                "After verifying the successor, call run-abandon on the source with "
                f"--successor-run-id {args.new_run_id}"
            ),
        }
    finally:
        connection.close()


def command_advance_removed(_: argparse.Namespace) -> dict[str, Any]:
    raise HubError("advance was removed because manual ledger editing is no longer canonical; use propose followed by root-only promote")


def command_migrate_legacy(args: argparse.Namespace) -> dict[str, Any]:
    legacy_run_dir, session_dir, session_key, run_id = run_dir_parts(Path(args.run_dir))
    legacy_state_path = legacy_run_dir / "run-state.json"
    legacy_ledger_path = legacy_run_dir / "shared-context.md"
    if not legacy_state_path.is_file() or not legacy_ledger_path.is_file():
        raise HubError("legacy run-state.json and shared-context.md are required")
    legacy_state = json.loads(legacy_state_path.read_text(encoding="utf-8"))
    if legacy_state.get("runStatus") == "closed":
        raise HubError("closed legacy runs should remain archived; migrate only an active or blocked run")
    db_path = session_dir / HUB_DB_NAME
    connection = connect_db(db_path, create=True)
    try:
        initialize_schema(connection)
        with transaction(connection):
            timestamp = utc_now()
            connection.execute(
                "INSERT OR IGNORE INTO sessions(session_key, mode, created_at, updated_at) VALUES(?, 'active', ?, ?)",
                (session_key, timestamp, timestamp),
            )
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone():
                raise HubError(f"run is already present in Context Hub: {run_id}")
            objective = str(legacy_state.get("objective") or "Legacy imported objective")
            intent = str(legacy_state.get("intent") or "Revalidate legacy specialist work against a transactional context view")
            connection.execute(
                """
                INSERT INTO runs(
                  run_id, session_key, status, objective, intent, success_json, constraints_json, revision,
                  created_at, updated_at, blocked_reason, max_ledger_bytes,
                  max_missions, max_result_bytes, max_active_ids, max_revision_history
                ) VALUES(?, ?, 'active', ?, ?, ?, ?, 1, ?, ?, NULL, ?, ?, ?, ?, ?)
                """,
                (run_id, session_key, objective, intent, canonical_json([]), canonical_json([]), timestamp, timestamp, DEFAULT_BUDGETS["max_ledger_bytes"], DEFAULT_BUDGETS["max_missions"], DEFAULT_BUDGETS["max_result_bytes"], DEFAULT_BUDGETS["max_active_ids"], DEFAULT_BUDGETS["max_revision_history"]),
            )
            ledger = legacy_ledger_path.read_text(encoding="utf-8")
            entries = re.findall(r"^- `((?:F|D|I|O|C|R|Q)-\d{3})`[^—]*—\s*(.+)$", ledger, flags=re.MULTILINE)
            prefix_type = {value: key for key, value in ENTRY_PREFIX.items()}
            for entry_id, claim in entries:
                entry_type = prefix_type[entry_id[0]]
                content = entry_version_content(entry_type, claim.strip(), {"legacyImport": True}, "Imported; root must revalidate", "Imported legacy boundary", ["*"], ["legacy-import"], False)
                content_hash = sha256_text(canonical_json(content))
                connection.execute(
                    """
                    INSERT INTO context_entries(
                      run_id, entry_id, entry_type, current_version, superseded,
                      visibility_json, topics_json, created_revision, updated_revision,
                      created_at, updated_at
                    ) VALUES(?, ?, ?, 1, 0, ?, ?, 1, 1, ?, ?)
                    """,
                    (run_id, entry_id, entry_type, canonical_json(["*"]), canonical_json(["legacy-import"]), timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO context_entry_versions(
                      run_id, entry_id, version, revision, claim, evidence_json,
                      rationale, boundaries, superseded, visibility_json, topics_json,
                      promotion_rationale, content_hash, created_at
                    ) VALUES(?, ?, 1, 1, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (run_id, entry_id, claim.strip(), canonical_json({"legacyImport": True}), "Imported; root must revalidate", "Imported legacy boundary", canonical_json(["*"]), canonical_json(["legacy-import"]), "Legacy import", content_hash, timestamp),
                )
            missions = legacy_state.get("missions") or {}
            if isinstance(missions, dict):
                mission_values = missions.values()
            else:
                mission_values = missions
            for raw in mission_values:
                mission_id = raw.get("id") or raw.get("missionId")
                specialist = raw.get("specialist")
                if not mission_id or not MISSION_ID.fullmatch(mission_id) or specialist not in SPECIALISTS:
                    continue
                connection.execute(
                    """
                    INSERT INTO missions(
                      run_id, mission_id, specialist, relationship, effort, status,
                      objective, intent, success_json, constraints_json,
                      verification_expectations_json, known_risks_json, responsibility_surface, distinct_value,
                      write_mode, blind_first, context_state, required_revision,
                      blocked_reason, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, 'blocked', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'refresh-required', 1, 'legacy-import-requires-checkout', ?, ?)
                    """,
                    (run_id, mission_id, specialist, raw.get("relationship", "advisor"), raw.get("effort", "Standard"), raw.get("objective", f"Revalidate {mission_id}"), raw.get("intent", "Revalidate imported legacy mission"), canonical_json([]), canonical_json([]), canonical_json([]), canonical_json([]), raw.get("responsibilitySurface", f"legacy/{mission_id}"), raw.get("distinctValue", f"legacy imported mission {mission_id}"), raw.get("writeMode", "read-only"), int(bool(raw.get("blindFirst"))), timestamp, timestamp),
                )
            snapshot_hash = record_revision(connection, run_id, 1, "Imported legacy file-based guard state")
            insert_event(connection, run_id, 1, "legacy.imported", {"source": str(legacy_run_dir), "snapshotHash": snapshot_hash, "missionsRequireFreshCheckout": True})
            budget_usage = enforce_hard_budgets(connection, run_id, legacy_run_dir)
        backup_dir = legacy_run_dir / "legacy-file-guard-backup"
        private_dir(backup_dir, legacy_run_dir)
        for name in ("run-state.json", "shared-context.md", "work-map.md"):
            source = legacy_run_dir / name
            if source.exists():
                shutil.copy2(source, backup_dir / name)
                os.chmod(backup_dir / name, 0o600)
        render_run_serialized(connection, run_id, legacy_run_dir)
        return {"status": "PASS", "operation": "migrate-legacy", "runId": run_id, "database": str(db_path), "snapshotHash": snapshot_hash, "missionsRequireFreshCheckout": True, "backupDir": str(backup_dir), "budgetUsage": budget_usage}
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transactional GPT Squad Context Hub")
    parser.add_argument("--json", action="store_true", dest="global_json", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_json(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--json", action="store_true")

    init = subparsers.add_parser("init")
    init.add_argument("--runtime-root", required=True)
    init.add_argument("--session-key", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--intent", required=True)
    init.add_argument("--success-json")
    init.add_argument("--constraints-json")
    add_json(init)

    session_set = subparsers.add_parser("session-set")
    session_set.add_argument("--runtime-root", required=True)
    session_set.add_argument("--session-key", required=True)
    session_set.add_argument("--mode", required=True)
    add_json(session_set)

    mission_add = subparsers.add_parser("mission-add")
    mission_add.add_argument("--run-dir", required=True)
    mission_add.add_argument("--mission-id", required=True)
    mission_add.add_argument("--specialist", required=True)
    mission_add.add_argument("--relationship", required=True)
    mission_add.add_argument("--objective", required=True)
    mission_add.add_argument("--intent", required=True)
    mission_add.add_argument("--surface", required=True)
    mission_add.add_argument("--distinct-value", required=True)
    mission_add.add_argument("--success-json")
    mission_add.add_argument("--constraints-json")
    mission_add.add_argument("--verification-json")
    mission_add.add_argument("--risks-json")
    mission_add.add_argument("--write-mode", default="read-only")
    mission_add.add_argument("--effort", default="Standard")
    mission_add.add_argument("--depends-on")
    mission_add.add_argument("--required-ids")
    mission_add.add_argument("--subscribe")
    mission_add.add_argument("--blind-first", action="store_true")
    add_json(mission_add)

    checkout = subparsers.add_parser("checkout")
    checkout.add_argument("--run-dir", required=True)
    checkout.add_argument("--mission-id", required=True)
    add_json(checkout)

    ack = subparsers.add_parser("ack")
    ack.add_argument("--run-dir", required=True)
    ack.add_argument("--mission-id", required=True)
    ack.add_argument("--revision")
    add_json(ack)

    mission_status = subparsers.add_parser("mission-status")
    mission_status.add_argument("--run-dir", required=True)
    mission_status.add_argument("--mission-id", required=True)
    mission_status.add_argument("--status", required=True)
    mission_status.add_argument("--reason")
    add_json(mission_status)

    reopen = subparsers.add_parser("mission-reopen")
    reopen.add_argument("--run-dir", required=True)
    reopen.add_argument("--mission-id", required=True)
    reopen.add_argument("--reason", required=True)
    add_json(reopen)

    propose = subparsers.add_parser("propose")
    propose.add_argument("--run-dir", required=True)
    propose.add_argument("--mission-id", required=True)
    propose.add_argument("--action", default="create")
    propose.add_argument("--type")
    propose.add_argument("--entry-id")
    propose.add_argument("--claim", required=True)
    propose.add_argument("--evidence-json")
    propose.add_argument("--evidence-file")
    propose.add_argument("--rationale")
    propose.add_argument("--boundaries")
    propose.add_argument("--visible-to")
    propose.add_argument("--topics")
    add_json(propose)

    proposal_reject = subparsers.add_parser("proposal-reject")
    proposal_reject.add_argument("--run-dir", required=True)
    proposal_reject.add_argument("--proposal-id", required=True)
    proposal_reject.add_argument("--reason", required=True)
    add_json(proposal_reject)

    promote = subparsers.add_parser("promote")
    promote.add_argument("--run-dir", required=True)
    promote.add_argument("--proposal-id", required=True)
    promote.add_argument("--rationale", required=True)
    promote.add_argument("--visible-to")
    promote.add_argument("--topics")
    promote.add_argument("--additional-affected")
    add_json(promote)

    artifact = subparsers.add_parser("artifact-record")
    artifact.add_argument("--run-dir", required=True)
    artifact.add_argument("--artifact-key", required=True)
    artifact.add_argument("--repository", required=True)
    artifact.add_argument("--commit", required=True)
    artifact.add_argument("--path", required=True)
    artifact.add_argument("--content-sha256")
    artifact.add_argument("--metadata-json")
    artifact.add_argument("--metadata-file")
    artifact.add_argument("--visible-to", default="all")
    artifact.add_argument("--topics")
    artifact.add_argument("--additional-affected")
    artifact.add_argument("--summary", required=True)
    add_json(artifact)

    delta = subparsers.add_parser("delta")
    delta.add_argument("--run-dir", required=True)
    delta.add_argument("--mission-id", required=True)
    delta.add_argument("--since-revision", required=True)
    add_json(delta)

    result_submit = subparsers.add_parser("result-submit")
    result_submit.add_argument("--run-dir", required=True)
    result_submit.add_argument("--mission-id", required=True)
    result_submit.add_argument("--snapshot-hash", required=True)
    result_submit.add_argument("--result-file", required=True)
    add_json(result_submit)

    disposition = subparsers.add_parser("challenge-disposition")
    disposition.add_argument("--run-dir", required=True)
    disposition.add_argument("--mission-id", required=True)
    disposition.add_argument("--type", required=True)
    disposition.add_argument("--rationale", required=True)
    disposition.add_argument("--decision-id")
    disposition.add_argument("--remediation-mission")
    disposition.add_argument("--evidence-json")
    disposition.add_argument("--evidence-file")
    add_json(disposition)

    check = subparsers.add_parser("check")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--for-close", action="store_true")
    add_json(check)

    render = subparsers.add_parser("render")
    render.add_argument("--run-dir", required=True)
    add_json(render)

    close = subparsers.add_parser("close")
    close.add_argument("--run-dir", required=True)
    close.add_argument("--reason", default="completed")
    add_json(close)

    status = subparsers.add_parser("status")
    status.add_argument("--run-dir", required=True)
    add_json(status)

    repair_terminal = subparsers.add_parser("repair-terminal-context")
    repair_terminal.add_argument("--run-dir", required=True)
    repair_terminal.add_argument("--apply", action="store_true")
    add_json(repair_terminal)

    run_abandon = subparsers.add_parser("run-abandon")
    run_abandon.add_argument("--run-dir", required=True)
    run_abandon.add_argument("--reason", required=True)
    run_abandon.add_argument("--successor-run-id")
    add_json(run_abandon)

    session_audit = subparsers.add_parser("session-audit")
    session_audit.add_argument("--runtime-root", required=True)
    session_audit.add_argument("--session-key", required=True)
    session_audit.add_argument("--stale-hours", default="24")
    add_json(session_audit)

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--run-dir", required=True)
    snapshot.add_argument("--output-dir", required=True)
    add_json(snapshot)

    rollover = subparsers.add_parser("run-rollover")
    rollover.add_argument("--run-dir", required=True)
    rollover.add_argument("--new-run-id", required=True)
    rollover.add_argument("--reason", required=True)
    rollover.add_argument("--objective")
    rollover.add_argument("--intent")
    rollover.add_argument("--entry-ids")
    rollover.add_argument("--artifact-keys")
    rollover.add_argument("--include-global-active", action="store_true")
    rollover.add_argument("--abandon-source", action="store_true")
    add_json(rollover)

    advance = subparsers.add_parser("advance")
    advance.add_argument("--run-dir")
    add_json(advance)

    migrate = subparsers.add_parser("migrate-legacy")
    migrate.add_argument("--run-dir", required=True)
    add_json(migrate)

    return parser


COMMANDS = {
    "init": command_init,
    "session-set": command_session_set,
    "mission-add": command_mission_add,
    "checkout": command_checkout,
    "ack": command_ack,
    "mission-status": command_mission_status,
    "mission-reopen": command_mission_reopen,
    "propose": command_propose,
    "proposal-reject": command_proposal_reject,
    "promote": command_promote,
    "artifact-record": command_artifact_record,
    "delta": command_delta,
    "result-submit": command_result_submit,
    "challenge-disposition": command_challenge_disposition,
    "check": command_check,
    "render": command_render,
    "close": command_close,
    "status": command_status,
    "repair-terminal-context": command_repair_terminal_context,
    "run-abandon": command_run_abandon,
    "session-audit": command_session_audit,
    "snapshot": command_snapshot,
    "run-rollover": command_run_rollover,
    "advance": command_advance_removed,
    "migrate-legacy": command_migrate_legacy,
}


def emit(result: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        sys.stdout.write(pretty_json(dict(result)))
        return
    sys.stdout.write(f"{result.get('operation', 'context-hub')}: {result.get('status', 'PASS')}\n")
    for key in ("sessionKey", "runId", "missionId", "revision", "snapshotHash", "resultHash"):
        if result.get(key) is not None:
            sys.stdout.write(f"{key}: {result[key]}\n")


def main(argv: Sequence[str] | None = None) -> int:
    os.umask(0o077)
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = COMMANDS[args.command]
    try:
        result = handler(args)
        as_json = bool(getattr(args, "json", False) or getattr(args, "global_json", False))
        emit(result, as_json)
        if result.get("status") == "FAIL":
            return 4
        return 0
    except HubError as exc:
        as_json = bool(getattr(args, "json", False) or getattr(args, "global_json", False))
        result = {"status": "FAIL", "operation": args.command, "message": str(exc)}
        if as_json:
            sys.stdout.write(pretty_json(result))
        else:
            sys.stderr.write(f"{args.command}: FAIL\n{exc}\n")
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - defensive boundary
        as_json = bool(getattr(args, "json", False) or getattr(args, "global_json", False))
        result = {"status": "FAIL", "operation": args.command, "message": f"unexpected error: {exc}"}
        if as_json:
            sys.stdout.write(pretty_json(result))
        else:
            sys.stderr.write(f"{args.command}: FAIL\nunexpected error: {exc}\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
