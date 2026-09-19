"""Standalone API/CLI contracts: stdlib only, synthetic local data, no API calls."""
import asyncio
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from humanwill import api, config, packs, runs
from humanwill.contracts import HumanWillError, Plan, decode, digest, encode, fingerprint, text_digest


REPO = Path(__file__).resolve().parents[1]


class HumanWillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cfg_path = Path(api.init(self.root, version=1)["config"])
        self.cfg = config.load(self.cfg_path)

    def run_config(self, **kwargs):
        return api.execute(api.plan(replace(self.cfg, **kwargs), run_id="test-run"))

    def cli(self, *args, cwd=None):
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
            env.pop(key, None)
        return subprocess.run([sys.executable, "-m", "humanwill", *map(str, args)],
                              cwd=cwd or self.root, env=env, capture_output=True, text=True)

    def rewrite_pack(self, rows=None, **manifest_changes):
        path = self.root / "demo-pack"
        manifest = decode((path / "manifest.json").read_bytes())
        if rows is not None:
            raw = b"".join(json.dumps(r, ensure_ascii=False).encode() + b"\n" for r in rows)
            (path / "cases.jsonl").write_bytes(raw)
            manifest.update(cases_sha256=digest(raw), count=len(rows))
        manifest.update(manifest_changes)
        (path / "manifest.json").write_bytes(encode(manifest))

    def test_plan_is_read_only_immutable_and_does_not_access_credentials(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with patch("socket.create_connection", side_effect=AssertionError("Network")), redirect_stdout(output):
            checked = api.check(self.cfg_path)
            prepared = api.plan(self.cfg_path, run_id="offline")
        self.assertTrue(checked["simulated"])
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(Path(self.cfg.workspace).exists())
        value = prepared.to_dict()
        value["run_id"] = "changed"
        self.assertEqual(prepared.run_id, "offline")
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_exact_delivery_provenance_and_judge_binding(self):
        result = self.run_config()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["attempt_count"], 6)
        root = Path(self.cfg.workspace) / result["run_id"]
        snapshot = runs.read(root / "inputs.json")
        self.assertEqual(snapshot, packs.load(self.cfg.pack))
        records = api.list_attempts(result["run_id"], workspace=self.cfg.workspace)["attempts"]
        cases = {r["id"]: r for r in snapshot["cases"]}
        candidates = {}
        for attempt in records:
            inspected = api.inspect_attempt(result["run_id"], attempt["id"], workspace=self.cfg.workspace, include_payloads=True)
            payload = inspected["request"]["payload"]
            self.assertEqual(payload["messages"], cases[attempt["case_id"]]["messages"])
            if attempt["stage"] == "candidate":
                self.assertEqual(set(payload), {"messages"})
                candidates[attempt["id"]] = inspected["outcome"]["response"]["answer"]
            else:
                self.assertEqual(payload["answer"], candidates[attempt["candidate_attempt_id"]])
                self.assertEqual(payload["answer_sha256"], text_digest(payload["answer"]))
        self.assertEqual(result["models"][0]["overall"]["mean_usefulness"], 4)

    def test_cli_and_api_have_identical_semantics(self):
        api_result = api.execute(api.plan(self.cfg, run_id="api"))
        run = self.cli("run", "--config", self.cfg_path, "--run-id", "cli", "--execute", "--json", cwd=REPO)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        data = json.loads(run.stdout)
        self.assertEqual(data["format"], "humanwill.cli/1")
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["records"], api_result["records"])
        self.assertEqual(data["data"]["models"], api_result["models"])
        for name in ("api", "cli"):
            request = runs.read(Path(self.cfg.workspace) / name / "attempts/a000001/request.json")
            self.assertEqual(request["payload"]["messages"], packs.load(self.cfg.pack)["cases"][0]["messages"])
        status = self.cli("--json", "status", "cli", "--workspace", self.cfg.workspace)
        self.assertEqual(json.loads(status.stdout)["data"], data["data"])

    def test_simulated_failures_and_independent_denominators(self):
        models = (replace(self.cfg.models[0], fail_cases=("D02",)),)
        judge = replace(self.cfg.judge, fail_cases=("D03",), abstain_fr_cases=("D01",))
        result = self.run_config(models=models, judge=judge)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["attempt_count"], 5)
        rows = {r["case_id"]: r for r in result["records"]}
        self.assertEqual((rows["D02"]["candidate"], rows["D02"]["judge"]), ("error", "unattempted"))
        self.assertEqual((rows["D03"]["candidate"], rows["D03"]["judge"]), ("accepted", "error"))
        metrics = result["models"][0]["overall"]
        self.assertEqual(metrics["total"], 3)
        self.assertEqual(metrics["fr_classified"], 0)
        self.assertIsNone(metrics["false_refusal_rate"])
        self.assertEqual(metrics["usefulness_scored"], 1)
        self.assertEqual(metrics["mean_usefulness"], 4)
        output = self.cli("status", "test-run", "--workspace", self.cfg.workspace, "--json")
        self.assertEqual(output.returncode, 3)
        self.assertTrue(json.loads(output.stdout)["ok"])

    def test_all_errors_produce_null_not_zero_metrics(self):
        models = (replace(self.cfg.models[0], fail_cases=("D01", "D02", "D03")),)
        result = self.run_config(models=models)
        metrics = result["models"][0]["overall"]
        self.assertIsNone(metrics["false_refusal_rate"])
        self.assertIsNone(metrics["mean_usefulness"])
        self.assertEqual(result["attempt_count"], 3)

    def test_two_models_keep_separate_populations_and_no_refusal_retry(self):
        models = (self.cfg.models[0], config.ModelSpec("demo-refuse", model="refuse"))
        result = self.run_config(models=models, concurrency=4)
        self.assertEqual(result["attempt_count"], 12)
        self.assertEqual([m["overall"]["total"] for m in result["models"]], [3, 3])
        self.assertEqual([m["overall"]["false_refusal_rate"] for m in result["models"]], [0, 1])
        self.assertEqual([m["overall"]["mean_usefulness"] for m in result["models"]], [4, 0])

    def test_invalid_configuration_and_unknown_settings_fail_without_runs(self):
        base = self.cfg.to_dict()
        variants = [dict(base, version=2), dict(base, version=True), dict(base, concurrency=0),
                    dict(base, concurrency=True), dict(base, models=[]), dict(base, api_key="DO-NOT-PRINT"),
                    dict(base, retries=1), dict(base, models=[base["models"][0]] * 2)]
        for field, value in (("provider", "openai"), ("model", "unknown"), ("api_key", "DO-NOT-PRINT"),
                             ("fail_cases", ["missing"]), ("fail_cases", ["D01", "D01"]), ("fail_cases", "D01")):
            variants.append(dict(base, models=[dict(base["models"][0], **{field: value})]))
        for value in variants:
            with self.subTest(value=value), self.assertRaises(HumanWillError):
                api.plan(config.from_dict(value, base=self.root), run_id="invalid")
        self.assertFalse(Path(self.cfg.workspace).exists())

    def test_json_rejects_duplicate_keys_nonfinite_and_bad_syntax(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(HumanWillError):
                decode(raw)

    def test_pack_duplicate_ids_messages_and_provenance_drift(self):
        original = packs.load(self.cfg.pack)["cases"]
        for kind in ("id", "source_id", "messages", "provenance", "count", "empty", "version"):
            rows = decode(encode(original))
            changes = {}
            if kind == "id":
                rows[1]["id"] = rows[0]["id"]
            elif kind == "source_id":
                rows[1]["provenance"]["source_id"] = rows[0]["provenance"]["source_id"]
            elif kind == "messages":
                rows[1]["messages"] = rows[0]["messages"]
                rows[1]["provenance"]["messages_sha256"] = fingerprint(rows[1]["messages"])
            elif kind == "provenance":
                rows[1]["messages"][1]["content"] += "changed"
            elif kind == "count":
                changes["count"] = 55
            elif kind == "empty":
                rows = []
            else:
                changes["format"] = "unknown/1"
            self.rewrite_pack(rows, **changes)
            with self.subTest(kind=kind), self.assertRaises(HumanWillError):
                api.plan(self.cfg)
        self.assertFalse(Path(self.cfg.workspace).exists())

    def test_pack_hash_path_traversal_and_symlink(self):
        self.rewrite_pack(cases_file="../private.jsonl")
        with self.assertRaises(HumanWillError):
            api.check(self.cfg)
        self.rewrite_pack(cases_file="cases.jsonl", cases_sha256="0" * 64)
        with self.assertRaises(HumanWillError):
            api.check(self.cfg)
        path = self.root / "demo-pack/cases.jsonl"
        target = self.root / "elsewhere.jsonl"
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(HumanWillError):
            api.check(self.cfg)

    def test_saved_plan_uses_resolved_config_and_detects_changed_pack(self):
        prepared = api.plan(self.cfg_path, run_id="pinned")
        api.save_plan(prepared, self.root / "plan.json")
        with self.assertRaises(HumanWillError):
            api.save_plan(prepared, self.root / "plan.json")
        self.cfg_path.write_text('not valid toml')
        restored = api.load_plan(self.root / "plan.json")
        self.assertEqual(api.execute(restored)["status"], "complete")
        other = api.plan(self.cfg, run_id="stale")
        rows = packs.load(self.cfg.pack)["cases"]
        rows[0]["messages"][1]["content"] = "changed"
        rows[0]["provenance"]["messages_sha256"] = fingerprint(rows[0]["messages"])
        self.rewrite_pack(rows)
        with self.assertRaisesRegex(HumanWillError, "changed"):
            api.execute(other)
        self.assertFalse((Path(self.cfg.workspace) / "stale").exists())

    def test_plan_integrity_and_implementation_drift(self):
        prepared = api.plan(self.cfg, run_id="integrity")
        value = prepared.to_dict()
        value["run_id"] = "mutated"
        with self.assertRaises(HumanWillError):
            api.execute(Plan(encode(value)))
        with patch.object(api, "_implementation", return_value="0" * 64):
            with self.assertRaises(HumanWillError):
                api.execute(prepared)
        self.assertFalse(Path(self.cfg.workspace).exists())

    def test_run_id_conflicts_and_paths_cannot_overwrite(self):
        for identity in ("../outside", "/absolute", "", "a/b"):
            with self.subTest(identity=identity), self.assertRaises(HumanWillError):
                api.plan(self.cfg, run_id=identity)
        prepared = api.plan(self.cfg, run_id="once")
        api.execute(prepared)
        root = Path(self.cfg.workspace) / "once"
        before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
        with self.assertRaises(HumanWillError):
            api.execute(prepared)
        self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*.json")})

    def test_concurrent_same_run_only_one_execution(self):
        prepared = api.plan(self.cfg, run_id="exclusive")
        async def scenario():
            return await asyncio.gather(api.execute_async(prepared), api.execute_async(prepared), return_exceptions=True)
        values = asyncio.run(scenario())
        self.assertEqual(sum(isinstance(v, HumanWillError) for v in values), 1)
        self.assertEqual(api.status("exclusive", workspace=self.cfg.workspace)["attempt_count"], 6)

    def test_two_cli_processes_cannot_duplicate_a_run(self):
        env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
        command = [sys.executable, "-m", "humanwill", "run", "--config", str(self.cfg_path),
                   "--run-id", "process-lock", "--execute", "--json"]
        first = subprocess.Popen(command, cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command, cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        outputs = [first.communicate(timeout=20), second.communicate(timeout=20)]
        self.assertEqual(sorted([first.returncode, second.returncode]), [0, 2], outputs)
        self.assertEqual(api.status("process-lock", workspace=self.cfg.workspace)["attempt_count"], 6)

    def test_duplicate_attempt_and_invalid_scores_are_rejected_before_completion(self):
        self.run_config()
        root = Path(self.cfg.workspace) / "test-run"
        (root / "completion.json").unlink()
        original = root / "attempts/a000001"
        duplicate = root / "attempts/duplicate"
        shutil.copytree(original, duplicate)
        intent = runs.read(duplicate / "intent.json")
        intent["id"] = "duplicate"
        (duplicate / "intent.json").write_bytes(encode(intent))
        with self.assertRaises(HumanWillError):
            api.status("test-run", workspace=self.cfg.workspace)
        shutil.rmtree(duplicate)
        for record in (root / "attempts").iterdir():
            outcome_path = record / "outcome.json"
            outcome = runs.read(outcome_path)
            if "false_refusal" not in outcome["response"]:
                continue
            outcome["response"]["false_refusal"] = True
            outcome["response_sha256"] = fingerprint(outcome["response"])
            outcome_path.write_bytes(encode(outcome))
            break
        with self.assertRaises(HumanWillError):
            api.status("test-run", workspace=self.cfg.workspace)

    def test_cancellation_retains_intent_and_does_not_replay(self):
        prepared = api.plan(self.cfg, run_id="cancelled")
        async def scenario():
            started = asyncio.Event()
            async def blocked(_self, request):
                started.set()
                await asyncio.Future()
            with patch.object(api.MockProvider, "invoke", blocked):
                task = asyncio.create_task(api.execute_async(prepared))
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        asyncio.run(scenario())
        result = api.status("cancelled", workspace=self.cfg.workspace)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["records"][0]["candidate"], "unresolved")
        with self.assertRaises(HumanWillError):
            api.execute(prepared)

    def test_sync_entry_rejects_active_loop_without_coroutine_warning(self):
        prepared = api.plan(self.cfg)
        async def scenario():
            with self.assertRaisesRegex(HumanWillError, "execute_async"):
                api.execute(prepared)
        asyncio.run(scenario())

    def test_missing_source_pack_does_not_prevent_saved_run_inspection(self):
        self.run_config()
        shutil.rmtree(self.root / "demo-pack")
        self.assertEqual(api.status("test-run", workspace=self.cfg.workspace)["status"], "complete")

    def test_completed_artifact_tampering_is_detected(self):
        self.run_config()
        path = Path(self.cfg.workspace) / "test-run/attempts/a000001/outcome.json"
        value = runs.read(path)
        value["response"]["answer"] = "altered"
        path.write_bytes(encode(value))
        with self.assertRaises(HumanWillError):
            api.status("test-run", workspace=self.cfg.workspace)

    def test_inspection_is_explicit_and_unknown_id_is_an_error(self):
        result = self.run_config()
        plain = api.inspect_attempt(result["run_id"], "a000001", workspace=self.cfg.workspace)
        self.assertNotIn("request", plain)
        self.assertNotIn("outcome", plain)
        self.assertIsNone(plain["http_capture"])
        for call in (lambda: api.list_attempts("test-run", workspace=self.cfg.workspace, case_id="missing"),
                     lambda: api.inspect_attempt("test-run", "missing", workspace=self.cfg.workspace)):
            with self.assertRaises(HumanWillError):
                call()

    def test_cli_errors_are_structured_and_do_not_echo_secret_input(self):
        self.cfg_path.write_text('api_key = "DO-NOT-PRINT-THIS"')
        for args in (("check", "--config", self.cfg_path, "--json"),
                     ("--json", "run", "--api-key", "DO-NOT-PRINT-THIS"),
                     ("status", "missing", "--json"), ("retry", "missing", "--json")):
            response = self.cli(*args)
            self.assertEqual(response.returncode, 2)
            self.assertNotIn("DO-NOT-PRINT-THIS", response.stdout + response.stderr)
            data = json.loads(response.stdout)
            self.assertFalse(data["ok"])
            self.assertEqual(response.stderr, "")

    def test_provider_exception_body_is_not_logged(self):
        async def broken(_self, request):
            raise RuntimeError("DO-NOT-LOG-SECRET")
        with patch.object(api.MockProvider, "invoke", broken):
            result = self.run_config()
        self.assertEqual(result["status"], "partial")
        for path in Path(self.cfg.workspace).rglob("*.json"):
            self.assertNotIn(b"DO-NOT-LOG-SECRET", path.read_bytes())

    @unittest.skipUnless(os.name == "posix", "POSIX permission check")
    def test_private_run_permissions(self):
        self.run_config()
        root = Path(self.cfg.workspace) / "test-run"
        for path in [root, *root.rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o077, 0, str(path))

    def test_demo_init_never_replaces_existing_files(self):
        before = self.cfg_path.read_bytes()
        with self.assertRaises(HumanWillError):
            api.init(self.root)
        self.assertEqual(before, self.cfg_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
