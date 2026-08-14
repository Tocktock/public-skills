from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

import context_hub_test


class OperationalHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = context_hub_test.HubTestCase(methodName="runTest")
        self.helper.setUp()
        self.root = self.helper.root

    def tearDown(self) -> None:
        self.helper.tearDown()

    def call(self, *args: str, expect: int = 0) -> dict:
        return self.helper.call(*args, expect=expect)

    def init(self, session: str = "session-1", run: str = "run-1") -> Path:
        return self.helper.init(session=session, run=run)

    def add_mission(self, run_dir: Path, mission_id: str, **options) -> dict:
        return self.helper.add_mission(run_dir, mission_id, **options)

    def checkout(self, run_dir: Path, mission_id: str) -> dict:
        return self.helper.checkout(run_dir, mission_id)

    def activate(self, run_dir: Path, mission_id: str) -> dict:
        return self.helper.activate(run_dir, mission_id)

    def propose(self, run_dir: Path, source: str, **options) -> dict:
        return self.helper.propose(run_dir, source, **options)

    def promote(self, run_dir: Path, proposal_id: str, **options) -> dict:
        return self.helper.promote(run_dir, proposal_id, **options)

    def result_file(self, name: str, **options) -> Path:
        return self.helper.result_file(name, **options)

    def submit(self, run_dir: Path, mission_id: str, snapshot_hash: str, result_file: Path, expect: int = 0) -> dict:
        return self.helper.submit(run_dir, mission_id, snapshot_hash, result_file, expect=expect)

    def database(self, run_dir: Path) -> Path:
        return run_dir.parent.parent / "context-hub.sqlite3"

    def scalar(self, run_dir: Path, sql: str, params: tuple = ()):
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            return connection.execute(sql, params).fetchone()[0]

    def test_terminal_transition_is_atomic_and_closable(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        changed = self.call(
            "mission-status", "--run-dir", str(run_dir), "--mission-id", "M01",
            "--status", "superseded", "--reason", "No longer required",
        )
        self.assertEqual(changed["contextState"], "terminal-not-applicable")
        status = self.call("status", "--run-dir", str(run_dir))["missions"][0]
        self.assertEqual((status["status"], status["contextState"]), ("superseded", "terminal-not-applicable"))
        self.assertEqual(self.call("check", "--run-dir", str(run_dir), "--for-close")["status"], "PASS")
        self.call("close", "--run-dir", str(run_dir))
        self.assertEqual(self.call("status", "--run-dir", str(run_dir))["runStatus"], "closed")

    def test_existing_terminal_stale_rows_have_dry_run_and_apply_repair(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        self.call(
            "mission-status", "--run-dir", str(run_dir), "--mission-id", "M01",
            "--status", "rejected", "--reason", "Duplicate mission",
        )
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute(
                "UPDATE missions SET context_state = 'refresh-required' WHERE run_id = 'run-1' AND mission_id = 'M01'"
            )
            connection.commit()
        failed = self.call("check", "--run-dir", str(run_dir), expect=4)
        self.assertIn("discarded mission", " ".join(failed["errors"]))
        preview = self.call("repair-terminal-context", "--run-dir", str(run_dir))
        self.assertFalse(preview["apply"])
        self.assertEqual(preview["changeCount"], 1)
        self.assertEqual(
            self.scalar(run_dir, "SELECT context_state FROM missions WHERE run_id='run-1' AND mission_id='M01'"),
            "refresh-required",
        )
        applied = self.call("repair-terminal-context", "--run-dir", str(run_dir), "--apply")
        self.assertTrue(applied["apply"])
        self.assertEqual(
            self.scalar(run_dir, "SELECT context_state FROM missions WHERE run_id='run-1' AND mission_id='M01'"),
            "terminal-not-applicable",
        )
        self.assertEqual(self.call("check", "--run-dir", str(run_dir), "--for-close")["status"], "PASS")

    def test_revision_budget_exact_max_succeeds_and_plus_one_rolls_back_everything(self) -> None:
        run_dir = self.init()
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE runs SET max_revision_history = 2 WHERE run_id = 'run-1'")
            connection.commit()
        first = self.propose(run_dir, "root", type="fact", claim="Contract v1")
        promoted = self.promote(run_dir, first["proposalId"])
        self.assertEqual(promoted["revision"], 2)
        update = self.propose(
            run_dir,
            "root",
            action="update",
            entry_id=promoted["entryId"],
            claim="Contract v2",
            rationale="New evidence",
        )
        before = {
            "revision": self.scalar(run_dir, "SELECT revision FROM runs WHERE run_id='run-1'"),
            "versions": self.scalar(run_dir, "SELECT COUNT(*) FROM context_entry_versions WHERE run_id='run-1'"),
            "events": self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'"),
            "proposal": self.scalar(run_dir, "SELECT status FROM proposals WHERE proposal_seq = 2"),
        }
        failed = self.call(
            "promote", "--run-dir", str(run_dir), "--proposal-id", update["proposalId"],
            "--rationale", "Validated update",
            expect=2,
        )
        self.assertIn("hard budget rejected mutation before commit", failed["message"])
        after = {
            "revision": self.scalar(run_dir, "SELECT revision FROM runs WHERE run_id='run-1'"),
            "versions": self.scalar(run_dir, "SELECT COUNT(*) FROM context_entry_versions WHERE run_id='run-1'"),
            "events": self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'"),
            "proposal": self.scalar(run_dir, "SELECT status FROM proposals WHERE proposal_seq = 2"),
        }
        self.assertEqual(after, before)
        self.assertEqual(after["proposal"], "pending")

    def test_ledger_budget_accepts_exact_projected_bytes_and_rejects_one_less(self) -> None:
        run_dir = self.init()
        proposal = self.propose(run_dir, "root", type="fact", claim="Ledger boundary fact")
        database = self.database(run_dir)
        baseline = self.root / "baseline.sqlite3"
        with contextlib.closing(sqlite3.connect(database)) as source, contextlib.closing(sqlite3.connect(baseline)) as target:
            source.backup(target)
        first = self.promote(run_dir, proposal["proposalId"])
        exact_bytes = first["budgetUsage"]["ledgerBytes"]

        def restore_baseline() -> None:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{database}{suffix}").unlink(missing_ok=True)
            shutil.copy2(baseline, database)
            os.chmod(database, 0o600)

        restore_baseline()
        with contextlib.closing(sqlite3.connect(database)) as connection:
            connection.execute("UPDATE runs SET max_ledger_bytes=? WHERE run_id='run-1'", (exact_bytes,))
            connection.commit()
        exact = self.promote(run_dir, proposal["proposalId"])
        self.assertEqual(exact["budgetUsage"]["ledgerBytes"], exact_bytes)

        restore_baseline()
        with contextlib.closing(sqlite3.connect(database)) as connection:
            connection.execute("UPDATE runs SET max_ledger_bytes=? WHERE run_id='run-1'", (exact_bytes - 1,))
            connection.commit()
        failed = self.call(
            "promote", "--run-dir", str(run_dir), "--proposal-id", proposal["proposalId"],
            "--rationale", "Root validated decisive evidence", expect=2,
        )
        self.assertIn("generated shared ledger", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT revision FROM runs WHERE run_id='run-1'"), 1)
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM context_entries WHERE run_id='run-1'"), 0)
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM proposals WHERE proposal_seq=1"), "pending")
        self.call("render", "--run-dir", str(run_dir))

    def test_active_id_budget_rejects_promotion_without_partial_state(self) -> None:
        run_dir = self.init()
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE runs SET max_active_ids = 0 WHERE run_id = 'run-1'")
            connection.commit()
        proposal = self.propose(run_dir, "root", type="fact", claim="Must not commit")
        before_events = self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'")
        failed = self.call(
            "promote", "--run-dir", str(run_dir), "--proposal-id", proposal["proposalId"],
            "--rationale", "Would exceed active ID budget", expect=2,
        )
        self.assertIn("active context entry count", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM context_entries WHERE run_id='run-1'"), 0)
        self.assertEqual(self.scalar(run_dir, "SELECT revision FROM runs WHERE run_id='run-1'"), 1)
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'"), before_events)
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM proposals WHERE proposal_seq=1"), "pending")

    def test_artifact_budget_failure_is_atomic(self) -> None:
        run_dir = self.init()
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE runs SET max_revision_history = 1 WHERE run_id = 'run-1'")
            connection.commit()
        before_events = self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'")
        failed = self.call(
            "artifact-record", "--run-dir", str(run_dir),
            "--artifact-key", "repo:test", "--repository", "example/repo",
            "--commit", "abc123", "--path", "src", "--summary", "Record source",
            expect=2,
        )
        self.assertIn("revision history", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM artifacts WHERE run_id='run-1'"), 0)
        self.assertEqual(self.scalar(run_dir, "SELECT revision FROM runs WHERE run_id='run-1'"), 1)
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM events WHERE run_id='run-1'"), before_events)

    def test_render_failure_after_commit_preserves_canonical_run_for_repair(self) -> None:
        original = context_hub_test.hub.render_run_serialized
        with mock.patch.object(context_hub_test.hub, "render_run_serialized", side_effect=RuntimeError("render failed")):
            failed = self.call(
                "init",
                "--runtime-root", str(self.root / "runtime"),
                "--session-key", "session-1",
                "--run-id", "render-failure",
                "--objective", "Persist canonical state",
                "--intent", "Generated views remain repairable",
                expect=3,
            )
        self.assertIn("render failed", failed["message"])
        run_dir = self.root / "runtime/sessions/session-1/runs/render-failure"
        self.assertTrue(run_dir.is_dir())
        database = self.root / "runtime/sessions/session-1/context-hub.sqlite3"
        with contextlib.closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs WHERE run_id='render-failure'").fetchone()[0], 1)
        self.assertIs(context_hub_test.hub.render_run_serialized, original)
        self.assertEqual(self.call("render", "--run-dir", str(run_dir))["status"], "PASS")
        self.assertEqual(self.call("check", "--run-dir", str(run_dir))["status"], "PASS")

    def test_huge_init_is_rejected_before_run_commit_and_directory_is_removed(self) -> None:
        result = self.call(
            "init",
            "--runtime-root", str(self.root / "runtime"),
            "--session-key", "session-1",
            "--run-id", "oversized-run",
            "--objective", "x" * (40 * 1024),
            "--intent", "Reject an oversized initial ledger",
            expect=2,
        )
        self.assertIn("generated shared ledger", result["message"])
        run_dir = self.root / "runtime/sessions/session-1/runs/oversized-run"
        self.assertFalse(run_dir.exists())
        database = self.root / "runtime/sessions/session-1/context-hub.sqlite3"
        with contextlib.closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_normal_close_cannot_claim_abandonment_without_cleanup(self) -> None:
        run_dir = self.init()
        failed = self.call(
            "close", "--run-dir", str(run_dir), "--reason", "abandoned", expect=2
        )
        self.assertIn("use run-abandon", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM runs WHERE run_id='run-1'"), "active")

    def test_abandon_closes_overbudget_run_without_claiming_acceptance(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        proposal = self.propose(run_dir, "root", type="question", claim="Pending work", evidence={})
        self.assertEqual(proposal["proposalStatus"], "pending")
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE runs SET max_ledger_bytes = 1 WHERE run_id = 'run-1'")
            connection.commit()
        abandoned = self.call(
            "run-abandon", "--run-dir", str(run_dir), "--reason", "Budget exceeded and work was replaced"
        )
        self.assertEqual(abandoned["sourceAbandoned"] if "sourceAbandoned" in abandoned else abandoned["operation"], "run-abandon")
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM runs WHERE run_id='run-1'"), "closed")
        self.assertEqual(self.scalar(run_dir, "SELECT closure_reason FROM runs WHERE run_id='run-1'"), "abandoned")
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM proposals WHERE proposal_seq=1"), "rejected")
        mission = self.call("status", "--run-dir", str(run_dir))["missions"][0]
        self.assertEqual((mission["status"], mission["contextState"]), ("superseded", "terminal-not-applicable"))
        checked = self.call("check", "--run-dir", str(run_dir))
        self.assertEqual(checked["status"], "PASS")
        self.assertTrue(any("abandoned historical run" in warning for warning in checked["warnings"]))

    def test_abandon_can_clean_up_historically_raised_guard_limits(self) -> None:
        run_dir = self.init()
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE runs SET max_ledger_bytes=? WHERE run_id='run-1'", (64 * 1024,))
            connection.commit()
        self.call("run-abandon", "--run-dir", str(run_dir), "--reason", "Invalid historical guard override")
        checked = self.call("check", "--run-dir", str(run_dir))
        self.assertEqual(checked["status"], "PASS")
        self.assertTrue(any("compiled Context Hub guard maximum" in warning for warning in checked["warnings"]))

    def test_abandon_rolls_back_if_canonical_integrity_is_corrupt(self) -> None:
        run_dir = self.init()
        promoted = self.promote(
            run_dir,
            self.propose(run_dir, "root", type="fact", claim="Integrity protected")["proposalId"],
        )
        self.add_mission(run_dir, "M01", required_ids=promoted["entryId"])
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute(
                "UPDATE context_entry_versions SET content_hash=? WHERE run_id='run-1' AND entry_id=? AND version=1",
                ("0" * 64, promoted["entryId"]),
            )
            connection.commit()
        failed = self.call(
            "run-abandon", "--run-dir", str(run_dir), "--reason", "Must not hide corruption", expect=2
        )
        self.assertIn("canonical integrity failed", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM runs WHERE run_id='run-1'"), "active")
        mission = self.call("status", "--run-dir", str(run_dir))["missions"][0]
        self.assertEqual((mission["status"], mission["contextState"]), ("planned", "pending-checkout"))

    def test_abandon_rejects_self_or_closed_successor(self) -> None:
        run_dir = self.init()
        self.assertIn(
            "must differ",
            self.call(
                "run-abandon", "--run-dir", str(run_dir), "--reason", "bad",
                "--successor-run-id", "run-1", expect=2,
            )["message"],
        )
        rolled = self.call(
            "run-rollover", "--run-dir", str(run_dir), "--new-run-id", "run-2",
            "--reason", "successor",
        )
        new_run_dir = Path(rolled["newRunDir"])
        self.call("close", "--run-dir", str(new_run_dir), "--reason", "completed")
        failed = self.call(
            "run-abandon", "--run-dir", str(run_dir), "--reason", "bad",
            "--successor-run-id", "run-2", expect=2,
        )
        self.assertIn("already closed", failed["message"])

    def test_failed_rollover_leaves_no_successor_row_or_directory(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        private_entry = self.promote(
            run_dir,
            self.propose(
                run_dir, "root", type="decision", claim="Private decision",
                rationale="Mission-only", visible_to="M01",
            )["proposalId"],
        )
        failed = self.call(
            "run-rollover", "--run-dir", str(run_dir),
            "--new-run-id", "run-2", "--reason", "Must stay private",
            "--entry-ids", private_entry["entryId"], expect=2,
        )
        self.assertIn("not globally visible", failed["message"])
        self.assertEqual(
            self.scalar(run_dir, "SELECT COUNT(*) FROM runs WHERE run_id='run-2'"), 0
        )
        self.assertFalse((run_dir.parent / "run-2").exists())

    def test_rollover_copies_only_selected_global_state_then_abandons_source_explicitly(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        global_entry = self.promote(
            run_dir,
            self.propose(run_dir, "root", type="fact", claim="Global fact")["proposalId"],
        )
        private_entry = self.promote(
            run_dir,
            self.propose(
                run_dir, "root", type="decision", claim="Private decision",
                rationale="Mission-only", visible_to="M01",
            )["proposalId"],
        )
        self.call(
            "artifact-record", "--run-dir", str(run_dir),
            "--artifact-key", "repo:test", "--repository", "example/repo",
            "--commit", "abc123", "--path", "src", "--summary", "Record source",
        )
        rejected = self.call(
            "run-rollover", "--run-dir", str(run_dir),
            "--new-run-id", "unsafe-run", "--reason", "Do not combine lifecycle transitions",
            "--abandon-source", expect=2,
        )
        self.assertIn("run-abandon", rejected["message"])
        rolled = self.call(
            "run-rollover", "--run-dir", str(run_dir),
            "--new-run-id", "run-2", "--reason", "Compact canonical successor",
            "--include-global-active", "--artifact-keys", "repo:test",
        )
        self.assertEqual(rolled["entryIds"], [global_entry["entryId"]])
        self.assertNotIn(private_entry["entryId"], rolled["entryIds"])
        self.assertFalse(rolled["sourceAbandoned"])
        new_run_dir = Path(rolled["newRunDir"])
        self.assertTrue(new_run_dir.is_dir())
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM missions WHERE run_id='run-2'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM proposals WHERE run_id='run-2'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM results WHERE run_id='run-2'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM context_entries WHERE run_id='run-2'").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM artifacts WHERE run_id='run-2'").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT status FROM runs WHERE run_id='run-1'").fetchone()[0], "active")
        self.assertEqual(self.call("check", "--run-dir", str(new_run_dir))["status"], "PASS")
        self.call(
            "run-abandon", "--run-dir", str(run_dir),
            "--reason", "Successor verified", "--successor-run-id", "run-2",
        )
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM runs WHERE run_id='run-1'"), "closed")

    def test_rollover_projection_failure_removes_canonical_successor(self) -> None:
        run_dir = self.init()
        original = context_hub_test.hub.render_run_serialized

        def fail_successor(connection, run_id, rendered_run_dir):
            if run_id == "run-2":
                raise RuntimeError("projection failed")
            return original(connection, run_id, rendered_run_dir)

        with mock.patch.object(context_hub_test.hub, "render_run_serialized", side_effect=fail_successor):
            failed = self.call(
                "run-rollover", "--run-dir", str(run_dir),
                "--new-run-id", "run-2", "--reason", "Projection must be atomic",
                expect=2,
            )
        self.assertIn("canonical successor was removed", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM runs WHERE run_id='run-2'"), 0)
        self.assertFalse((run_dir.parent / "run-2").exists())
        self.assertEqual(self.scalar(run_dir, "SELECT status FROM runs WHERE run_id='run-1'"), "active")


    def test_snapshot_uses_consistent_backup_and_refuses_overwrite(self) -> None:
        run_dir = self.init()
        output = self.root / "snapshots/session-1"
        snapped = self.call("snapshot", "--run-dir", str(run_dir), "--output-dir", str(output))
        self.assertEqual(Path(snapped["database"]).stat().st_mode & 0o777, 0o600)
        manifest = json.loads(Path(snapped["manifest"]).read_text())
        self.assertEqual(manifest["integrityCheck"], "ok")
        self.assertEqual(manifest["sourceRunId"], "run-1")
        self.assertNotIn("sourceDatabase", manifest)
        with contextlib.closing(sqlite3.connect(snapped["database"])) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        failed = self.call("snapshot", "--run-dir", str(run_dir), "--output-dir", str(output), expect=2)
        self.assertIn("already exists", failed["message"])

    def test_rollover_rejects_corrupt_source_snapshot_without_successor(self) -> None:
        run_dir = self.init()
        promoted = self.promote(
            run_dir,
            self.propose(run_dir, "root", type="fact", claim="Trusted source state")["proposalId"],
        )
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute(
                "UPDATE context_entry_versions SET content_hash=? "
                "WHERE run_id='run-1' AND entry_id=? AND version=1",
                ("0" * 64, promoted["entryId"]),
            )
            connection.commit()
        failed = self.call(
            "run-rollover", "--run-dir", str(run_dir),
            "--new-run-id", "run-2", "--reason", "Do not carry corrupt state",
            "--entry-ids", promoted["entryId"], expect=2,
        )
        self.assertIn("source run canonical snapshot hash", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM runs WHERE run_id='run-2'"), 0)
        self.assertFalse((run_dir.parent / "run-2").exists())

    def test_rollover_directory_creation_failure_compensates_successor(self) -> None:
        run_dir = self.init()
        original = context_hub_test.hub.private_dir

        def fail_successor(path, trusted_root=None):
            if Path(path).name == "run-2":
                raise PermissionError("directory creation denied")
            return original(path, trusted_root)

        with mock.patch.object(context_hub_test.hub, "private_dir", side_effect=fail_successor):
            failed = self.call(
                "run-rollover", "--run-dir", str(run_dir),
                "--new-run-id", "run-2", "--reason", "Filesystem failure must compensate",
                expect=2,
            )
        self.assertIn("canonical successor was removed", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM runs WHERE run_id='run-2'"), 0)
        self.assertFalse((run_dir.parent / "run-2").exists())

    def test_snapshot_requires_an_existing_run(self) -> None:
        run_dir = self.init()
        missing = run_dir.parent / "missing-run"
        failed = self.call(
            "snapshot", "--run-dir", str(missing),
            "--output-dir", str(self.root / "snapshots/missing"), expect=2,
        )
        self.assertIn("run missing-run does not exist", failed["message"])
        self.assertFalse((self.root / "snapshots/missing").exists())

    def test_read_oriented_status_does_not_change_database_mode(self) -> None:
        run_dir = self.init()
        database = self.database(run_dir)
        os.chmod(database, 0o640)
        self.call("status", "--run-dir", str(run_dir))
        self.assertEqual(database.stat().st_mode & 0o777, 0o640)

    def test_read_oriented_connection_falls_back_to_query_only_rw_for_live_wal(self) -> None:
        run_dir = self.init()
        database = self.database(run_dir)
        real_connect = sqlite3.connect
        calls = []

        def flaky_connect(target, *args, **kwargs):
            calls.append(str(target))
            if len(calls) == 1 and "mode=ro" in str(target):
                raise sqlite3.OperationalError("simulated read-only WAL open failure")
            return real_connect(target, *args, **kwargs)

        with mock.patch.object(context_hub_test.hub.sqlite3, "connect", side_effect=flaky_connect):
            connection = context_hub_test.hub.connect_db(database, read_only=True)
            try:
                self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("UPDATE runs SET objective='forbidden'")
            finally:
                connection.close()
        self.assertIn("mode=ro", calls[0])
        self.assertIn("mode=rw", calls[1])

    def test_mission_private_context_view_has_a_compiled_delivery_limit(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        proposal = self.propose(
            run_dir, "root", type="fact", claim="x" * (70 * 1024), visible_to="M01",
        )
        self.promote(run_dir, proposal["proposalId"], visible_to="M01")
        failed = self.call("checkout", "--run-dir", str(run_dir), "--mission-id", "M01", expect=2)
        self.assertIn("context view exceeds compiled delivery budget", failed["message"])
        self.assertEqual(self.scalar(run_dir, "SELECT COUNT(*) FROM context_views WHERE run_id='run-1'"), 0)

    def test_session_audit_runs_database_integrity_once_and_surfaces_active_warnings(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01", relationship="independent-challenger", blind_first=True)
        checkout = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        result = self.result_file(
            "challenger-fail.json",
            status="completed",
            outcome="Material issue remains",
            verification=[{"check": "independent", "outcome": "FAIL"}],
            verdict="FAIL",
            distinct_evidence="Independent reproduction",
        )
        self.submit(run_dir, "M01", checkout["snapshotHash"], result)
        original = context_hub_test.hub.evaluate_run
        calls = []

        def wrapped(*args, **kwargs):
            calls.append(kwargs.get("check_database_integrity", True))
            return original(*args, **kwargs)

        with mock.patch.object(context_hub_test.hub, "evaluate_run", side_effect=wrapped):
            audit = self.call(
                "session-audit", "--runtime-root", str(self.root / "runtime"),
                "--session-key", "session-1", "--stale-hours", "24",
            )
        self.assertEqual(calls, [False])
        self.assertEqual(audit["status"], "WARN")
        self.assertEqual(audit["databaseErrors"], [])
        self.assertTrue(any("blocking verdict" in warning for warning in audit["runs"][0]["checkWarnings"]))

    def test_session_audit_reports_terminal_stale_and_budget_failure(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        self.call(
            "mission-status", "--run-dir", str(run_dir), "--mission-id", "M01",
            "--status", "superseded", "--reason", "No longer needed",
        )
        with contextlib.closing(sqlite3.connect(self.database(run_dir))) as connection:
            connection.execute("UPDATE missions SET context_state='refresh-required' WHERE run_id='run-1' AND mission_id='M01'")
            connection.execute("UPDATE runs SET max_ledger_bytes=1 WHERE run_id='run-1'")
            connection.commit()
        audit = self.call(
            "session-audit", "--runtime-root", str(self.root / "runtime"),
            "--session-key", "session-1", "--stale-hours", "1", expect=4,
        )
        self.assertEqual(audit["status"], "FAIL")
        self.assertEqual(audit["runs"][0]["terminalStaleMissions"], 1)
        self.assertIn("generated shared ledger", " ".join(audit["runs"][0]["checkErrors"]))


if __name__ == "__main__":
    unittest.main()
