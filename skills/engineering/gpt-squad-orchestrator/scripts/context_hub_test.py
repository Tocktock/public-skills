from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "scripts" / "gpt_squad_context.py"
PERSONA_CATALOG = HERE.parent.parent / "gpt-squad-installer" / "assets" / "persona-catalog.json"
REGISTERED_SPECIALISTS = [item["name"] for item in json.loads(PERSONA_CATALOG.read_text())["specialists"]]
SPEC = importlib.util.spec_from_file_location("gpt_squad_context", BACKEND)
assert SPEC and SPEC.loader
hub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hub)


class HubTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="gpt-squad-hub-test-")
        self.root = Path(self.temp.name).resolve()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, *args: str, expect: int = 0) -> dict:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = hub.main([*args, "--json"])
        self.assertEqual(code, expect, stdout.getvalue())
        return json.loads(stdout.getvalue() or "{}")

    def init(self, session: str = "session-1", run: str = "run-1") -> Path:
        result = self.call(
            "init",
            "--runtime-root", str(self.root / "runtime"),
            "--session-key", session,
            "--run-id", run,
            "--objective", "Deliver a coherent transactional result",
            "--intent", "Keep specialist views consistent without sharing transcripts",
            "--success-json", json.dumps(["all accepted results are current"]),
            "--constraints-json", json.dumps(["no production mutation"]),
        )
        return Path(result["runDir"])

    def add_mission(self, run_dir: Path, mission_id: str, **options) -> dict:
        args = [
            "mission-add", "--run-dir", str(run_dir),
            "--mission-id", mission_id,
            "--specialist", options.get("specialist", "data_systems"),
            "--relationship", options.get("relationship", "lead"),
            "--objective", options.get("objective", f"Own {mission_id}"),
            "--intent", options.get("intent", "Provide distinct specialist judgment"),
            "--surface", options.get("surface", f"src/{mission_id}"),
            "--distinct-value", options.get("distinct_value", f"distinct-{mission_id}"),
            "--write-mode", options.get("write_mode", "read-only"),
            "--effort", options.get("effort", "Standard"),
            "--success-json", json.dumps(options.get("success", ["owned claim verified"])),
            "--constraints-json", json.dumps(options.get("constraints", ["respect mission authority"])),
            "--verification-json", json.dumps(options.get("verification", ["targeted check"])),
            "--risks-json", json.dumps(options.get("risks", [])),
        ]
        if options.get("depends_on"):
            args += ["--depends-on", options["depends_on"]]
        if options.get("required_ids"):
            args += ["--required-ids", options["required_ids"]]
        if options.get("subscribe"):
            args += ["--subscribe", options["subscribe"]]
        if options.get("blind_first"):
            args += ["--blind-first"]
        return self.call(*args)

    def checkout(self, run_dir: Path, mission_id: str) -> dict:
        return self.call("checkout", "--run-dir", str(run_dir), "--mission-id", mission_id)

    def activate(self, run_dir: Path, mission_id: str) -> dict:
        return self.call("mission-status", "--run-dir", str(run_dir), "--mission-id", mission_id, "--status", "active")

    def propose(self, run_dir: Path, source: str, **options) -> dict:
        args = [
            "propose", "--run-dir", str(run_dir),
            "--mission-id", source,
            "--action", options.get("action", "create"),
            "--claim", options.get("claim", "A material claim"),
            "--evidence-json", json.dumps(options.get("evidence", {"source": "test"})),
        ]
        if "visible_to" in options:
            args += ["--visible-to", options["visible_to"]]
        if options.get("type"):
            args += ["--type", options["type"]]
        if options.get("entry_id"):
            args += ["--entry-id", options["entry_id"]]
        if options.get("rationale"):
            args += ["--rationale", options["rationale"]]
        if options.get("boundaries"):
            args += ["--boundaries", options["boundaries"]]
        if "topics" in options:
            args += ["--topics", options["topics"]]
        return self.call(*args)

    def promote(self, run_dir: Path, proposal_id: str, **options) -> dict:
        args = [
            "promote", "--run-dir", str(run_dir),
            "--proposal-id", proposal_id,
            "--rationale", options.get("rationale", "Root validated decisive evidence"),
        ]
        if options.get("additional_affected"):
            args += ["--additional-affected", options["additional_affected"]]
        if options.get("visible_to"):
            args += ["--visible-to", options["visible_to"]]
        if options.get("topics"):
            args += ["--topics", options["topics"]]
        return self.call(*args)

    def result_file(self, name: str, **options) -> Path:
        target = self.root / f"{name}.json"
        payload = {
            "status": options.get("status", "completed"),
            "outcome": options.get("outcome", "Delivered the owned outcome"),
            "verification": options.get("verification", [{"command": "targeted-test", "outcome": "PASS"}]),
        }
        if options.get("verdict"):
            payload["verdict"] = options["verdict"]
        if options.get("distinct_evidence"):
            payload["distinctEvidence"] = options["distinct_evidence"]
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return target

    def submit(self, run_dir: Path, mission_id: str, snapshot_hash: str, result_file: Path, expect: int = 0) -> dict:
        return self.call(
            "result-submit", "--run-dir", str(run_dir),
            "--mission-id", mission_id,
            "--snapshot-hash", snapshot_hash,
            "--result-file", str(result_file),
            expect=expect,
        )

    def test_init_creates_private_sqlite_and_generated_views(self) -> None:
        run_dir = self.init()
        database = self.root / "runtime/sessions/session-1/context-hub.sqlite3"
        self.assertEqual(database.stat().st_mode & 0o777, 0o600)
        self.assertIn("transactional Context Hub", (run_dir / "shared-context.md").read_text())
        self.assertEqual(self.call("check", "--run-dir", str(run_dir))["status"], "PASS")

    def test_context_hub_accepts_the_complete_installed_specialist_catalog(self) -> None:
        for index, specialist in enumerate(REGISTERED_SPECIALISTS, start=1):
            run_dir = self.init(session="catalog-session", run=f"catalog-{index:02d}")
            result = self.add_mission(
                run_dir,
                "M01",
                specialist=specialist,
                objective=f"Own a bounded {specialist} outcome",
                distinct_value=f"distinct-{specialist}",
                write_mode="read-only",
            )
            self.assertEqual(result["status"], "PASS")

    def test_change_review_specialist_can_receive_a_transactional_checkout(self) -> None:
        run_dir = self.init()
        self.add_mission(
            run_dir,
            "M01",
            specialist="change_review",
            objective="Review the accepted change for readiness",
            intent="Provide holistic coverage and a calibrated adversarial verdict",
            distinct_value="Assess simplicity, scope, compatibility, maintainability, and integration risk",
            write_mode="read-only",
        )
        view = self.checkout(run_dir, "M01")
        snapshot = json.loads(Path(view["snapshotFile"]).read_text())
        self.assertEqual(snapshot["mission"]["specialist"], "change_review")
        self.assertEqual(snapshot["mission"]["writeMode"], "read-only")

    def test_independent_reviewer_can_own_an_isolated_verification_surface(self) -> None:
        run_dir = self.init()
        result = self.add_mission(
            run_dir,
            "M01",
            specialist="change_review",
            relationship="independent-challenger",
            objective="Review the change independently",
            intent="Preserve an independent acceptance judgment",
            surface="review-artifacts/M01",
            distinct_value="Build isolated adversarial evidence without modifying the reviewed change",
            write_mode="writer",
            blind_first=True,
        )
        self.assertEqual(result["status"], "PASS")
        view = self.checkout(run_dir, "M01")
        snapshot = json.loads(Path(view["snapshotFile"]).read_text())
        self.assertTrue(snapshot["mission"]["blindFirst"] )
        self.assertEqual(snapshot["mission"]["writeMode"], "writer")

    def test_checkout_records_exact_entry_and_artifact_versions(self) -> None:
        run_dir = self.init()
        proposal = self.propose(run_dir, "root", type="decision", claim="Use transactional state", rationale="atomicity")
        promoted = self.promote(run_dir, proposal["proposalId"])
        self.call(
            "artifact-record", "--run-dir", str(run_dir),
            "--artifact-key", "repo:orchestrator", "--repository", "example-org/example-repo",
            "--commit", "abc123", "--path", "skills/engineering/gpt-squad-orchestrator/SKILL.md",
            "--summary", "Record orchestrator source",
        )
        self.add_mission(run_dir, "M01", required_ids=promoted["entryId"])
        view = self.checkout(run_dir, "M01")
        self.assertRegex(view["snapshotHash"], r"^[a-f0-9]{64}$")
        self.assertEqual(view["entries"], [{"entryId": promoted["entryId"], "version": 1}])
        self.assertEqual(view["artifacts"], [{"artifactKey": "repo:orchestrator", "version": 1}])
        snapshot = json.loads(Path(view["snapshotFile"]).read_text())
        self.assertEqual(snapshot["mission"]["successConditions"], ["owned claim verified"])

    def test_specialist_proposals_require_current_active_checkout(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        result = self.call(
            "propose", "--run-dir", str(run_dir), "--mission-id", "M01",
            "--type", "fact", "--claim", "stale", "--evidence-json", "{}",
            expect=2,
        )
        self.assertIn("active mission with a current checked-out context", result["message"])
        self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.assertEqual(self.propose(run_dir, "M01", type="fact")["proposalStatus"], "pending")
        self.assertEqual(self.propose(run_dir, "root", type="question", evidence={})["proposalStatus"], "pending")

    def test_entry_promotion_auto_invalidates_consumers_and_dependents(self) -> None:
        run_dir = self.init()
        entry = self.promote(run_dir, self.propose(run_dir, "root", type="fact", claim="Contract v1")["proposalId"])
        self.add_mission(run_dir, "M01", required_ids=entry["entryId"])
        self.add_mission(run_dir, "M02", specialist="domain_application", required_ids=entry["entryId"])
        self.add_mission(run_dir, "M03", specialist="integration_evolution", depends_on="M02")
        for mission in ("M01", "M02", "M03"):
            self.checkout(run_dir, mission)
        self.activate(run_dir, "M01")
        update = self.propose(run_dir, "M01", action="update", entry_id=entry["entryId"], claim="Contract v2", evidence={"path": "src/contract.ts:42"})
        promoted = self.promote(run_dir, update["proposalId"])
        self.assertEqual(promoted["affectedMissions"], ["M01", "M02", "M03"])
        status = self.call("status", "--run-dir", str(run_dir))
        self.assertEqual([item["contextState"] for item in status["missions"]], ["refresh-required"] * 3)

    def test_manual_affected_is_additive_and_topics_catch_new_entries(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01", subscribe="pricing")
        self.add_mission(run_dir, "M02", specialist="product_systems")
        self.checkout(run_dir, "M01")
        self.checkout(run_dir, "M02")
        proposal = self.propose(run_dir, "root", type="decision", claim="Pricing policy", rationale="user behavior", visible_to="M01", topics="pricing")
        promoted = self.promote(run_dir, proposal["proposalId"], additional_affected="M02")
        self.assertEqual(promoted["affectedMissions"], ["M01", "M02"])

    def test_artifact_changes_invalidate_recorded_consumers(self) -> None:
        run_dir = self.init()
        self.call(
            "artifact-record", "--run-dir", str(run_dir), "--artifact-key", "repo:file",
            "--repository", "repo", "--commit", "a1", "--path", "src/file.ts", "--summary", "Initial",
        )
        self.add_mission(run_dir, "M01", specialist="codebase_forensics")
        self.checkout(run_dir, "M01")
        updated = self.call(
            "artifact-record", "--run-dir", str(run_dir), "--artifact-key", "repo:file",
            "--repository", "repo", "--commit", "a2", "--path", "src/file.ts", "--summary", "Changed",
        )
        self.assertEqual(updated["affectedMissions"], ["M01"])

    def test_results_are_sealed_and_require_active_current_view(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        view = self.checkout(run_dir, "M01")
        result_file = self.result_file("result")
        failed = self.submit(run_dir, "M01", view["snapshotHash"], result_file, expect=2)
        self.assertIn("requires an active mission", failed["message"])
        self.activate(run_dir, "M01")
        result = self.submit(run_dir, "M01", view["snapshotHash"], result_file)
        self.assertRegex(result["resultHash"], r"^[a-f0-9]{64}$")
        second = self.submit(run_dir, "M01", view["snapshotHash"], result_file, expect=2)
        self.assertIn("requires an active mission", second["message"])

    def test_reopen_creates_new_result_version_after_fresh_checkout(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(run_dir, "M01", view["snapshotHash"], self.result_file("v1"))
        self.call("mission-reopen", "--run-dir", str(run_dir), "--mission-id", "M01", "--reason", "Correct result")
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        result = self.submit(run_dir, "M01", view["snapshotHash"], self.result_file("v2"))
        self.assertEqual(result["resultVersion"], 2)

    def test_challenger_failure_blocks_closure_until_disposition(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01", specialist="quality_falsification", relationship="independent-challenger", blind_first=True)
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(run_dir, "M01", view["snapshotHash"], self.result_file("challenge", verdict="FAIL", distinct_evidence="failure injection"))
        checked = self.call("check", "--run-dir", str(run_dir), "--for-close", expect=4)
        self.assertIn("blocking verdict FAIL without disposition", " ".join(checked["errors"]))
        self.call(
            "challenge-disposition", "--run-dir", str(run_dir), "--mission-id", "M01",
            "--type", "challenge-rejected-with-evidence", "--rationale", "False positive",
            "--evidence-json", json.dumps({"check": "PASS"}),
        )
        self.assertEqual(self.call("check", "--run-dir", str(run_dir), "--for-close")["status"], "PASS")

    def test_dependencies_and_context_change_reopen_completed_chain(self) -> None:
        run_dir = self.init()
        entry = self.promote(run_dir, self.propose(run_dir, "root", type="fact", claim="Dependency fact")["proposalId"])
        self.add_mission(run_dir, "M01", required_ids=entry["entryId"])
        self.add_mission(run_dir, "M02", specialist="integration_evolution", depends_on="M01", required_ids=entry["entryId"])
        view1 = self.checkout(run_dir, "M01")
        view2 = self.checkout(run_dir, "M02")
        self.activate(run_dir, "M01")
        self.activate(run_dir, "M02")
        failed = self.submit(run_dir, "M02", view2["snapshotHash"], self.result_file("m2"), expect=2)
        self.assertIn("before dependencies: M01", failed["message"])
        self.submit(run_dir, "M01", view1["snapshotHash"], self.result_file("m1"))
        self.submit(run_dir, "M02", view2["snapshotHash"], self.result_file("m2"))
        self.call("mission-reopen", "--run-dir", str(run_dir), "--mission-id", "M01", "--reason", "Update fact")
        self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        update = self.propose(run_dir, "M01", action="update", entry_id=entry["entryId"], claim="Dependency fact v2")
        promoted = self.promote(run_dir, update["proposalId"])
        self.assertEqual(promoted["affectedMissions"], ["M01", "M02"])
        status = self.call("status", "--run-dir", str(run_dir))
        self.assertEqual([item["status"] for item in status["missions"]], ["blocked", "blocked"])

    def test_generated_views_are_regenerable_and_drift_fails(self) -> None:
        run_dir = self.init()
        ledger = run_dir / "shared-context.md"
        ledger.write_text(ledger.read_text() + "manual edit\n")
        checked = self.call("check", "--run-dir", str(run_dir), expect=4)
        self.assertIn("generated views drifted", " ".join(checked["errors"]))
        self.call("render", "--run-dir", str(run_dir))
        self.assertEqual(self.call("check", "--run-dir", str(run_dir))["status"], "PASS")

    def test_checkout_delivers_shared_core_but_not_other_missions_private_context(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        self.add_mission(run_dir, "M02", specialist="domain_application")
        global_entry = self.promote(
            run_dir,
            self.propose(run_dir, "root", type="fact", claim="Global accepted fact")["proposalId"],
        )
        private_entry = self.promote(
            run_dir,
            self.propose(
                run_dir,
                "root",
                type="decision",
                claim="M01 private decision",
                rationale="mission-specific",
                visible_to="M01",
            )["proposalId"],
        )
        view_m01 = self.checkout(run_dir, "M01")
        view_m02 = self.checkout(run_dir, "M02")
        snapshot_m01 = json.loads(Path(view_m01["snapshotFile"]).read_text())
        snapshot_m02 = json.loads(Path(view_m02["snapshotFile"]).read_text())
        self.assertEqual(snapshot_m01["sharedCanonicalCore"]["objective"], "Deliver a coherent transactional result")
        self.assertEqual(
            {item["entryId"] for item in snapshot_m01["entries"]},
            {global_entry["entryId"], private_entry["entryId"]},
        )
        self.assertEqual({item["entryId"] for item in snapshot_m02["entries"]}, {global_entry["entryId"]})
        ledger = (run_dir / "shared-context.md").read_text()
        self.assertIn("Global accepted fact", ledger)
        self.assertNotIn("M01 private decision", ledger)

    def test_context_views_are_immutable_and_reused_after_reopen(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        first = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(run_dir, "M01", first["snapshotHash"], self.result_file("first-result"))
        self.call("mission-reopen", "--run-dir", str(run_dir), "--mission-id", "M01", "--reason", "correct result")
        second = self.checkout(run_dir, "M01")
        self.assertEqual(first["viewId"], second["viewId"])
        database = run_dir.parent.parent / "context-hub.sqlite3"
        with sqlite3.connect(database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM context_views WHERE run_id = ?", ("run-1",)).fetchone()[0]
            sealed = connection.execute("SELECT COUNT(*) FROM results WHERE run_id = ?", ("run-1",)).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(sealed, 1)

    def test_entry_updates_preserve_scope_and_reject_no_op_versions(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01", subscribe="pricing")
        self.add_mission(run_dir, "M02", specialist="domain_application")
        created = self.promote(
            run_dir,
            self.propose(
                run_dir,
                "root",
                type="decision",
                claim="Pricing v1",
                rationale="initial",
                visible_to="M01",
                topics="pricing",
            )["proposalId"],
        )
        updated_proposal = self.propose(
            run_dir,
            "root",
            action="update",
            entry_id=created["entryId"],
            claim="Pricing v2",
            rationale="validated change",
        )
        updated = self.promote(run_dir, updated_proposal["proposalId"])
        self.assertEqual(updated["affectedMissions"], ["M01"])
        database = run_dir.parent.parent / "context-hub.sqlite3"
        with sqlite3.connect(database) as connection:
            visibility, topics = connection.execute(
                "SELECT visibility_json, topics_json FROM context_entries WHERE run_id = ? AND entry_id = ?",
                ("run-1", created["entryId"]),
            ).fetchone()
        self.assertEqual(json.loads(visibility), ["M01"])
        self.assertEqual(json.loads(topics), ["pricing"])
        no_op = self.propose(
            run_dir,
            "root",
            action="update",
            entry_id=created["entryId"],
            claim="Pricing v2",
            rationale="validated change",
        )
        failed = self.call(
            "promote",
            "--run-dir", str(run_dir),
            "--proposal-id", no_op["proposalId"],
            "--rationale", "same semantic state",
            expect=2,
        )
        self.assertIn("no-op version", failed["message"])

    def test_context_view_read_set_corruption_fails_integrity_check(self) -> None:
        run_dir = self.init()
        entry = self.promote(run_dir, self.propose(run_dir, "root", type="fact", claim="Delivered fact")["proposalId"])
        self.add_mission(run_dir, "M01", required_ids=entry["entryId"])
        view = self.checkout(run_dir, "M01")
        database = run_dir.parent.parent / "context-hub.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE context_view_entries SET content_hash = ? WHERE view_id = ? AND entry_id = ?",
                ("0" * 64, view["viewId"], entry["entryId"]),
            )
            connection.commit()
        checked = self.call("check", "--run-dir", str(run_dir), expect=4)
        self.assertIn("context view", " ".join(checked["errors"]))

    def test_closed_run_views_remain_stable_across_later_session_mode_changes(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(run_dir, "M01", view["snapshotHash"], self.result_file("closed-stable"))
        self.call("close", "--run-dir", str(run_dir))
        ledger_before = (run_dir / "shared-context.md").read_text()
        events_before = (run_dir / "events.jsonl").read_text()
        runtime_root = self.root / "runtime"
        self.call("session-set", "--runtime-root", str(runtime_root), "--session-key", "session-1", "--mode", "disabled")
        self.call("session-set", "--runtime-root", str(runtime_root), "--session-key", "session-1", "--mode", "active")
        self.assertEqual((run_dir / "shared-context.md").read_text(), ledger_before)
        self.assertEqual((run_dir / "events.jsonl").read_text(), events_before)
        self.assertEqual(self.call("check", "--run-dir", str(run_dir))["status"], "PASS")

    def test_inactive_accepted_risk_decision_blocks_closure(self) -> None:
        run_dir = self.init()
        self.add_mission(
            run_dir,
            "M01",
            specialist="quality_falsification",
            relationship="independent-challenger",
            blind_first=True,
        )
        self.add_mission(run_dir, "M02", specialist="product_systems")
        decision = self.promote(
            run_dir,
            self.propose(
                run_dir,
                "root",
                type="decision",
                claim="Accept known residual risk",
                rationale="temporary operational trade-off",
                visible_to="M02",
            )["proposalId"],
        )
        self.call("mission-status", "--run-dir", str(run_dir), "--mission-id", "M02", "--status", "rejected", "--reason", "decision-only mission")
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(
            run_dir,
            "M01",
            view["snapshotHash"],
            self.result_file("challenge-risk", verdict="FAIL", distinct_evidence="independent failure injection"),
        )
        self.call(
            "challenge-disposition",
            "--run-dir", str(run_dir),
            "--mission-id", "M01",
            "--type", "accepted-risk",
            "--rationale", "Root accepts the documented temporary risk",
            "--decision-id", decision["entryId"],
        )
        supersede = self.propose(
            run_dir,
            "root",
            action="supersede",
            entry_id=decision["entryId"],
            claim="The risk acceptance is withdrawn",
            rationale="conditions changed",
            visible_to="M02",
        )
        self.promote(run_dir, supersede["proposalId"])
        checked = self.call("check", "--run-dir", str(run_dir), "--for-close", expect=4)
        self.assertIn("inactive decision", " ".join(checked["errors"]))

    def test_delta_rejects_a_future_revision(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        failed = self.call(
            "delta", "--run-dir", str(run_dir), "--mission-id", "M01", "--since-revision", "2",
            expect=2,
        )
        self.assertIn("newer than current revision", failed["message"])

    def test_closed_runs_are_immutable(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01")
        view = self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.submit(run_dir, "M01", view["snapshotHash"], self.result_file("done"))
        self.call("close", "--run-dir", str(run_dir))
        for args in (
            ("checkout", "--run-dir", str(run_dir), "--mission-id", "M01"),
            ("mission-reopen", "--run-dir", str(run_dir), "--mission-id", "M01", "--reason", "no"),
            ("propose", "--run-dir", str(run_dir), "--mission-id", "root", "--type", "question", "--claim", "no"),
            ("artifact-record", "--run-dir", str(run_dir), "--artifact-key", "a:b", "--repository", "r", "--commit", "c", "--path", "p", "--summary", "s"),
        ):
            failed = self.call(*args, expect=2)
            self.assertIn("immutable while status is closed", failed["message"])
        self.assertEqual(self.call("status", "--run-dir", str(run_dir))["runStatus"], "closed")

    def test_delta_filters_other_mission_private_events(self) -> None:
        run_dir = self.init()
        self.add_mission(run_dir, "M01", subscribe="topic-a")
        self.add_mission(run_dir, "M02", specialist="domain_application")
        self.checkout(run_dir, "M01")
        self.activate(run_dir, "M01")
        self.propose(run_dir, "M01", type="fact", claim="private proposal")
        promoted = self.promote(run_dir, self.propose(run_dir, "root", type="decision", claim="Visible to M01", rationale="needed", visible_to="M01", topics="topic-a")["proposalId"])
        delta = self.call("delta", "--run-dir", str(run_dir), "--mission-id", "M02", "--since-revision", "1")
        self.assertEqual(delta["currentRevision"], promoted["revision"])
        self.assertFalse(any(event["eventType"] == "proposal.submitted" and event["payload"].get("source") == "M01" for event in delta["events"]))

    def test_legacy_migration_is_fail_closed(self) -> None:
        run_dir = self.root / "runtime/sessions/legacy-session/runs/legacy-run"
        run_dir.mkdir(parents=True)
        (run_dir / "run-state.json").write_text(json.dumps({
            "runStatus": "active",
            "objective": "Legacy objective",
            "intent": "Legacy intent",
            "missions": {"M01": {"id": "M01", "specialist": "data_systems", "relationship": "lead", "effort": "Standard", "objective": "Legacy mission", "intent": "Revalidate", "responsibilitySurface": "legacy/path", "distinctValue": "legacy evidence", "writeMode": "read-only"}},
        }))
        (run_dir / "shared-context.md").write_text("# Shared\n\n## Confirmed facts\n\n- `F-001` — Legacy fact\n")
        (run_dir / "work-map.md").write_text("legacy\n")
        migrated = self.call("migrate-legacy", "--run-dir", str(run_dir))
        self.assertTrue(migrated["missionsRequireFreshCheckout"])
        self.assertEqual(self.call("status", "--run-dir", str(run_dir))["runStatus"], "active")
        self.assertEqual(self.call("status", "--run-dir", str(run_dir))["missions"][0]["contextState"], "refresh-required")
        self.assertTrue((Path(migrated["backupDir"]) / "run-state.json").exists())

    def test_sqlite_begin_immediate_serializes_mutations(self) -> None:
        run_dir = self.init()
        database = run_dir.parent.parent / "context-hub.sqlite3"
        script = """
import sqlite3, sys, time
c=sqlite3.connect(sys.argv[1], timeout=1, isolation_level=None)
c.execute('PRAGMA journal_mode=WAL')
c.execute('BEGIN IMMEDIATE')
print('locked', flush=True)
time.sleep(0.5)
c.execute('COMMIT')
"""
        process = subprocess.Popen(["python3", "-c", script, str(database)], stdout=subprocess.PIPE, text=True)
        self.assertEqual(process.stdout.readline().strip(), "locked")
        started = time.monotonic()
        proposal = self.propose(run_dir, "root", type="question", claim="Serialized?", evidence={})
        elapsed = time.monotonic() - started
        self.assertEqual(process.wait(timeout=3), 0)
        assert process.stdout is not None
        process.stdout.close()
        self.assertGreaterEqual(elapsed, 0.35)
        self.assertEqual(proposal["proposalStatus"], "pending")


if __name__ == "__main__":
    unittest.main()
