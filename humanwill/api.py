"""Shared operations for the CLI and agents. Importing this module has no effects."""
import asyncio
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
import uuid

from . import __version__, config, packs, runs
from .contracts import (HumanWillError, Plan, decode, digest, encode, fields,
                        fingerprint, identifier, nonempty, require, text_digest)
from .providers import MockProvider, Request


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_pack(destination, *, extends=None):
    """Create an editable local question pack, optionally pinning a compiled base."""
    from . import authoring
    return authoring.init_pack(destination, extends=extends)


def validate_pack(source):
    """Read-only source/compiled-pack validation, with metadata-only results."""
    from . import authoring
    return authoring.validate_pack(source)


def build_pack(source, *, output):
    """Build a self-contained immutable local question pack without model calls."""
    from . import authoring
    return authoring.build_pack(source, output=output)


def init_policy(destination):
    """Create an editable local policy bundle; no overwrite or network calls."""
    from . import policies
    return policies.init(destination)


def preview_policy(bundle, *, pack, case_ids=()):
    """Show effective judge instructions and rule provenance before execution."""
    from . import policies, sources
    snapshot = sources.load(pack); sources.validate(snapshot)
    return policies.preview(policies.load(bundle,snapshot),snapshot,case_ids=case_ids)


def inspect_policy(run_id, *, workspace, operation_id=None, case_ids=()):
    """Inspect a saved operation's exact policy, without consulting source files."""
    from . import engine, policies
    run_id = resolve_run(run_id,workspace=workspace)
    require(_v2(run_id,workspace), 'read_only_history', 'Policy inspection requires a version-2 run.')
    root, initial, pack, operations, _ = engine.load(run_id,workspace)
    if operation_id is None:
        operation_id = max(operations.values(),key=lambda op:op['created_at'])['operation_id']
    identifier(operation_id)
    require(operation_id in operations, 'not_found', 'Unknown policy operation.')
    selected = list(case_ids) if case_ids else initial['case_ids']
    require(not isinstance(case_ids,str) and set(selected)<=set(initial['case_ids']), message='Policy inspection requires selected run cases.')
    policy = runs.read(root/'operations'/operation_id/'policy.json')
    result = policies.preview(policy,pack,case_ids=selected)
    require(policy['sha256']==operations[operation_id]['policy_sha256'], 'integrity_error','Saved policy changed.')
    return {**result,'run_id':run_id,'operation_id':operation_id}


def _implementation():
    # Do not bind paths, timestamps, documentation, or unrelated historical code.
    root = Path(__file__).parent
    return fingerprint({p.name: digest(p.read_bytes()) for p in sorted(root.glob("*.py"))})


def init(destination: str | Path = ".", *, version=2) -> dict:
    """Create a harmless local demo. Refuse to replace any existing demo file."""
    require(type(version) is int and version in (1, 2), message="Unsupported demo version.")
    base = Path(destination).expanduser().resolve()
    targets = [base / "benchmark.toml", base / "demo-pack"]
    require(not any(p.exists() or p.is_symlink() for p in targets), "already_exists",
            "Demo files already exist; choose an empty destination.")
    runs.directory(base)
    source = files("humanwill").joinpath("data", "demo")
    pack_dir = base / "demo-pack"
    pack_dir.mkdir(mode=0o700)
    for name in ("manifest.json", "cases.jsonl", "README.md", "LICENSE"):
        _write_bytes(pack_dir / name, source.joinpath(name).read_bytes())
    raw_config = source.joinpath("benchmark.toml").read_bytes()
    if version == 2:
        raw_config = raw_config.replace(b"version = 1", b"version = 2\nbudget_micro_usd = 0", 1)
    _write_bytes(base / "benchmark.toml", raw_config)
    return {"config": str(base / "benchmark.toml"), "pack": str(pack_dir / "manifest.json"),
            "simulated": True, "license": decode(source.joinpath("manifest.json").read_bytes())["license"]}


def _write_bytes(path, raw):
    # Small installation artifacts are never replaced; no model data is involved.
    import os
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise HumanWillError("already_exists", "File already exists.") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)


def _inputs(value):
    settings = config.load(value)
    pack = packs.load(settings.pack)
    ids = {c["id"] for c in pack["cases"]}
    for spec in (*settings.models, settings.judge):
        require(set(spec.fail_cases) | set(spec.abstain_fr_cases) <= ids,
                message="A mock case selection references an unknown question.")
    return settings, pack


def check(value: str | Path | config.RunConfig) -> dict:
    if config.load(value).to_dict()["version"] == 2:
        from . import engine
        return engine.check(value)
    settings, pack = _inputs(value)
    return {"valid": True, "simulated": True, "pack_id": pack["manifest"]["id"],
            "questions": len(pack["cases"]), "models": [m.id for m in settings.models],
            "judge": settings.judge.id, "credentials_required": False,
            "estimated_cost_micro_usd": 0}


def _plan_dict(settings, pack, run_id, created_at):
    value = {"format": "humanwill.plan/1", "run_id": identifier(run_id),
             "created_at": nonempty(created_at), "config": settings.to_dict(),
             "pack": {"id": pack["manifest"]["id"], "version": pack["manifest"]["version"],
                      "manifest_sha256": pack["manifest_sha256"], "cases_sha256": pack["cases_sha256"],
                      "snapshot_sha256": fingerprint(pack), "case_ids": [r["id"] for r in pack["cases"]]},
             "runtime": {"version": __version__, "implementation_sha256": _implementation()},
             "simulated": True, "maximum_cost_micro_usd": 0}
    value["plan_sha256"] = fingerprint(value)
    return value


def plan(value: str | Path | config.RunConfig, *, run_id: str | None = None) -> Plan:
    """Pure offline preflight. Does not create a workspace or read credentials."""
    if config.load(value).to_dict()["version"] == 2:
        from . import engine
        return engine.plan(value, run_id=run_id)
    settings, pack = _inputs(value)
    if run_id is None:
        run_id = "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    return Plan(encode(_plan_dict(settings, pack, run_id, _now())))


def _validate_plan(value):
    if isinstance(value, dict) and value.get("format") == "humanwill.plan/2":
        from . import engine
        return engine.validate_plan(value)
    fields(value, {"format", "run_id", "created_at", "config", "pack", "runtime", "simulated",
                   "maximum_cost_micro_usd", "plan_sha256"})
    require(value["format"] == "humanwill.plan/1", "unsupported_version", "Unsupported plan version.")
    require(value["simulated"] is True and type(value["maximum_cost_micro_usd"]) is int
            and value["maximum_cost_micro_usd"] == 0, message="Only zero-cost simulation plans are supported.")
    identifier(value["run_id"])
    nonempty(value["created_at"])
    fields(value["runtime"], {"version", "implementation_sha256"})
    fields(value["pack"], {"id", "version", "manifest_sha256", "cases_sha256", "snapshot_sha256", "case_ids"})
    expected = fingerprint({k: v for k, v in value.items() if k != "plan_sha256"})
    require(value["plan_sha256"] == expected, "integrity_error", "Plan integrity check failed.")
    settings = config.from_dict(value["config"], base=Path.cwd())
    require(settings.to_dict() == value["config"], message="Plan requires fully resolved configuration.")
    return settings


def save_plan(prepared: Plan, path: str | Path) -> dict:
    value = prepared.to_dict()
    _validate_plan(value)
    path = Path(path).expanduser().resolve()
    runs.directory(path.parent)
    runs.write(path, value)
    return {"path": str(path), "plan_sha256": value["plan_sha256"], "run_id": value["run_id"]}


def load_plan(path: str | Path) -> Plan:
    value = runs.read(Path(path).expanduser().resolve())
    _validate_plan(value)
    return Plan(encode(value))


async def execute_async(prepared: Plan, *, transport=None) -> dict:
    """Execute an immutable operation plan once; never implicitly resume/retry."""
    value = prepared.to_dict()
    if value.get("format") == "humanwill.plan/2":
        from . import engine
        return await engine.execute_async(prepared, transport=transport)
    require(transport is None, message="Version 1 does not use HTTP transport.")
    settings = _validate_plan(value)
    _, pack = _inputs(settings)
    require(_plan_dict(settings, pack, value["run_id"], value["created_at"]) == value,
            "stale_plan", "Pack or implementation changed; create a new plan.")
    root = runs.create(settings.workspace, value["run_id"])
    runs.write(root / "plan.json", value)
    runs.write(root / "inputs.json", pack)
    provider = MockProvider()
    sequence = 0

    async def call(row, model_id, stage, spec, payload, candidate_attempt=None):
        nonlocal sequence
        sequence += 1
        attempt_id = f"a{sequence:06d}"
        directory = root / "attempts" / attempt_id
        directory.mkdir(mode=0o700)
        payload = decode(encode(payload))  # Do not let an adapter mutate the source snapshot.
        request = {"provider": spec.provider, "model": spec.model, "payload": payload}
        intent = {"format": "humanwill.attempt/1", "run_id": value["run_id"], "id": attempt_id,
                  "model_id": model_id, "case_id": row["id"], "stage": stage, "number": 1,
                  "parent_attempt_id": None, "candidate_attempt_id": candidate_attempt,
                  "plan_sha256": value["plan_sha256"], "request_sha256": fingerprint(request),
                  "created_at": _now(), "reserved_micro_usd": 0, "simulated": True}
        # Intent is durable before invoking the provider. A missing outcome remains unknown.
        runs.write(directory / "intent.json", intent)
        runs.write(directory / "request.json", request)
        try:
            response = await provider.invoke(Request(row["id"], stage, spec.model, payload,
                row["id"] in spec.fail_cases, row["id"] in spec.abstain_fr_cases))
        except Exception:
            # No exception bodies or arbitrary provider payloads leak to normal output.
            response = {"status": "error", "code": "provider_exception"}
        _validate_response(response, stage)
        outcome = {"format": "humanwill.outcome/1", "id": attempt_id,
                   "intent_sha256": fingerprint(intent), "response": response,
                   "response_sha256": fingerprint(response), "completed_at": _now(),
                   "http_capture": None, "capture_status": "not_applicable_mock",
                   "accounting": {"kind": "simulated", "charged_micro_usd": 0}}
        runs.write(directory / "outcome.json", outcome)
        return attempt_id, response

    semaphore = asyncio.Semaphore(settings.concurrency)

    async def one(row, model):
        async with semaphore:
            candidate_id, response = await call(row, model.id, "candidate", model,
                                               {"messages": row["messages"]})
            if response["status"] != "accepted":
                return
            await call(row, model.id, "judge", settings.judge,
                       {"messages": row["messages"], "answer": response["answer"],
                        "answer_sha256": text_digest(response["answer"]),
                        "mock_behavior": response["mock_behavior"]}, candidate_id)

    async with asyncio.TaskGroup() as group:
        for model in settings.models:
            for row in pack["cases"]:
                group.create_task(one(row, model))
    artifacts = {p.relative_to(root).as_posix(): digest(p.read_bytes())
                 for p in sorted(root.rglob("*.json"))}
    runs.write(root / "completion.json", {"format": "humanwill.completion/1", "files": artifacts,
                                         "completed_at": _now()})
    return status(value["run_id"], workspace=settings.workspace)


def execute(prepared: Plan, *, transport=None) -> dict:
    """Synchronous entry point; async applications use execute_async explicitly."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(execute_async(prepared, transport=transport))
    raise HumanWillError("async_context", "Use await execute_async(plan) inside an active event loop.")


def _validate_response(response, stage):
    require(isinstance(response, dict), "integrity_error", "Invalid stored response.")
    if response.get("status") == "error":
        fields(response, {"status", "code"})
        require(response["code"] in {"simulated_provider_error", "provider_exception"},
                message="Unknown response error code.")
    elif stage == "candidate":
        fields(response, {"status", "answer", "mock_behavior"})
        require(response["status"] == "accepted" and isinstance(response["answer"], str)
                and response["mock_behavior"] in {"answer", "refusal"}, message="Invalid candidate response.")
    else:
        fields(response, {"status", "false_refusal", "usefulness", "answer_sha256", "policy", "simulated"})
        require(response["status"] == "accepted" and response["simulated"] is True
                and response["policy"] == "mock-exact/1", message="Invalid judge response.")
        for key, maximum in (("false_refusal", 2), ("usefulness", 4)):
            score = response[key]
            require(score is None or type(score) is int and 0 <= score <= maximum,
                    message="Invalid metric score.")


def _load_run(run_id, workspace):
    root = runs.root(workspace, run_id)
    value = runs.read(root / "plan.json")
    settings = _validate_plan(value)
    require(value["run_id"] == run_id, "integrity_error", "Run identity mismatch.")
    pack = runs.read(root / "inputs.json")
    require(fingerprint(pack) == value["pack"]["snapshot_sha256"], "integrity_error", "Input snapshot changed.")
    packs.validate(pack["manifest"], pack["cases"])
    require([r["id"] for r in pack["cases"]] == value["pack"]["case_ids"],
            "integrity_error", "Selected population changed.")
    complete = (root / "completion.json").exists()
    if complete:
        completion = runs.read(root / "completion.json")
        fields(completion, {"format", "files", "completed_at"})
        require(completion["format"] == "humanwill.completion/1" and isinstance(completion["files"], dict),
                message="Invalid completion record.")
        actual = {p.relative_to(root).as_posix(): digest(p.read_bytes())
                  for p in sorted(root.rglob("*.json")) if p.name != "completion.json" and not p.is_symlink()}
        require(actual == completion["files"], "integrity_error", "Completed run artifacts changed.")
    records = []
    known = {(m.id, r["id"], stage) for m in settings.models for r in pack["cases"] for stage in ("candidate", "judge")}
    case_index = {r["id"]: r for r in pack["cases"]}
    model_index = {m.id: m for m in settings.models}
    seen = set()
    require(not (root / "attempts").is_symlink(), "unsafe_path", "Unsafe attempt directory.")
    for directory in sorted((root / "attempts").iterdir()):
        require(directory.is_dir() and not directory.is_symlink(), "unsafe_path", "Unsafe attempt directory.")
        if not (directory / "intent.json").exists():
            require(not complete, "integrity_error", "Missing attempt intent.")
            continue
        intent = runs.read(directory / "intent.json")
        fields(intent, {"format", "run_id", "id", "model_id", "case_id", "stage", "number",
                        "parent_attempt_id", "candidate_attempt_id", "plan_sha256", "request_sha256",
                        "created_at", "reserved_micro_usd", "simulated"})
        key = (intent["model_id"], intent["case_id"], intent["stage"])
        require(intent["format"] == "humanwill.attempt/1" and intent["id"] == directory.name
                and intent["run_id"] == run_id and intent["plan_sha256"] == value["plan_sha256"]
                and key in known and key not in seen and type(intent["number"]) is int
                and intent["number"] == 1 and intent["parent_attempt_id"] is None
                and intent["simulated"] is True and type(intent["reserved_micro_usd"]) is int
                and intent["reserved_micro_usd"] == 0, "integrity_error", "Invalid or duplicate attempt identity.")
        seen.add(key)
        request = runs.read(directory / "request.json") if (directory / "request.json").exists() else None
        if request is not None:
            require(fingerprint(request) == intent["request_sha256"], "integrity_error", "Attempt request changed.")
            fields(request, {"provider", "model", "payload"})
            spec = model_index[intent["model_id"]] if intent["stage"] == "candidate" else settings.judge
            require(request["provider"] == spec.provider and request["model"] == spec.model,
                    "integrity_error", "Attempt provider settings changed.")
            expected_fields = {"messages"} if intent["stage"] == "candidate" else {
                "messages", "answer", "answer_sha256", "mock_behavior"}
            fields(request["payload"], expected_fields)
            require(request["payload"]["messages"] == case_index[intent["case_id"]]["messages"],
                    "integrity_error", "Attempt messages differ from the frozen input.")
        outcome = runs.read(directory / "outcome.json") if (directory / "outcome.json").exists() else None
        if outcome is not None:
            fields(outcome, {"format", "id", "intent_sha256", "response", "response_sha256", "completed_at",
                             "http_capture", "capture_status", "accounting"})
            require(request is not None and outcome["format"] == "humanwill.outcome/1"
                    and outcome["id"] == intent["id"] and outcome["intent_sha256"] == fingerprint(intent)
                    and outcome["response_sha256"] == fingerprint(outcome["response"])
                    and outcome["http_capture"] is None and outcome["capture_status"] == "not_applicable_mock"
                    and outcome["accounting"] == {"kind": "simulated", "charged_micro_usd": 0},
                    "integrity_error", "Outcome integrity check failed.")
            _validate_response(outcome["response"], intent["stage"])
        records.append({"intent": intent, "request": request, "outcome": outcome})
    # A judgment must bind the exact saved candidate, not merely the same question ID.
    by_id = {r["intent"]["id"]: r for r in records}
    for record in records:
        intent = record["intent"]
        if intent["stage"] == "candidate":
            require(intent["candidate_attempt_id"] is None, message="Unexpected candidate parent.")
            continue
        parent = by_id.get(intent["candidate_attempt_id"])
        require(parent is not None and parent["intent"]["stage"] == "candidate"
                and parent["intent"]["case_id"] == intent["case_id"]
                and parent["intent"]["model_id"] == intent["model_id"] and parent["outcome"] is not None
                and parent["outcome"]["response"]["status"] == "accepted", message="Invalid judge candidate binding.")
        answer = parent["outcome"]["response"]["answer"]
        if record["request"] is not None:
            payload = record["request"]["payload"]
            require(payload["answer"] == answer and payload["answer_sha256"] == text_digest(answer)
                    and payload["mock_behavior"] == parent["outcome"]["response"]["mock_behavior"],
                    "integrity_error", "Judge answer binding changed.")
        if record["outcome"] and record["outcome"]["response"]["status"] == "accepted":
            require(record["outcome"]["response"]["answer_sha256"] == text_digest(answer),
                    "integrity_error", "Judgment answer binding changed.")
    return root, value, pack, records, complete


def _metrics(rows):
    # Same independent denominators as core.metrics.frozen_corrections.summarize.
    fr = [r["false_refusal"] for r in rows if r["false_refusal"] is not None]
    useful = [r["usefulness"] for r in rows if r["usefulness"] is not None]
    refusals = sum(x > 0 for x in fr)
    return {"total": len(rows), "fr_classified": len(fr), "fr_unclassified": len(rows) - len(fr),
            "usefulness_scored": len(useful), "usefulness_unscored": len(rows) - len(useful),
            "false_refusals": refusals, "false_refusal_rate": refusals / len(fr) if fr else None,
            "mean_usefulness": sum(useful) / len(useful) if useful else None}


def status(run_id: str, *, workspace: str | Path, selection="recovery") -> dict:
    run_id = resolve_run(run_id, workspace=workspace)
    if _v2(run_id, workspace):
        from . import engine
        return engine.status(run_id, workspace=workspace, selection=selection)
    root, value, pack, attempts, complete = _load_run(run_id, workspace)
    by_key = {(a["intent"]["model_id"], a["intent"]["case_id"], a["intent"]["stage"]): a for a in attempts}
    rows = []
    for model in value["config"]["models"]:
        for case in pack["cases"]:
            row = {"model_id": model["id"], "case_id": case["id"], "family": case["family"],
                   "false_refusal": None, "usefulness": None}
            for stage in ("candidate", "judge"):
                record = by_key.get((model["id"], case["id"], stage))
                row[stage + "_attempt_id"] = record["intent"]["id"] if record else None
                outcome = record["outcome"] if record else None
                row[stage] = outcome["response"]["status"] if outcome else ("unresolved" if record else "unattempted")
                if stage == "judge" and outcome and outcome["response"]["status"] == "accepted":
                    row.update({key: outcome["response"][key] for key in ("false_refusal", "usefulness")})
            rows.append(row)
    models = []
    for model in value["config"]["models"]:
        chosen = [r for r in rows if r["model_id"] == model["id"]]
        models.append({"model_id": model["id"], "overall": _metrics(chosen),
                       "families": {f: _metrics([r for r in chosen if r["family"] == f])
                                    for f in sorted({r["family"] for r in chosen})}})
    successful = all(r["judge"] == "accepted" for r in rows)
    disposition = ("complete" if successful else "partial") if complete else "incomplete"
    return {"format": "humanwill.results/1", "run_id": run_id, "workspace": str(root.parent),
            "status": disposition, "simulated": True, "plan_sha256": value["plan_sha256"],
            "selection_policy": "first_attempt/1", "selection_sha256": fingerprint(rows),
            "attempt_count": len(attempts), "accounted_micro_usd": 0,
            "models": models, "records": rows}


def list_attempts(run_id: str, *, workspace: str | Path, case_id: str | None = None) -> dict:
    run_id = resolve_run(run_id, workspace=workspace)
    if _v2(run_id, workspace):
        from . import engine
        return engine.list_attempts(run_id, workspace=workspace, case_id=case_id)
    _, _, pack, records, _ = _load_run(run_id, workspace)
    if case_id is not None:
        require(case_id in {r["id"] for r in pack["cases"]}, "not_found", "Unknown question ID.")
    return {"run_id": run_id, "attempts": [
        {**record["intent"], "status": record["outcome"]["response"]["status"] if record["outcome"] else "unresolved",
         "capture_status": "not_applicable_mock"}
        for record in records if case_id is None or record["intent"]["case_id"] == case_id]}


def inspect_attempt(run_id: str, attempt_id: str, *, workspace: str | Path,
                    include_payloads: bool = False, include_http: bool = False) -> dict:
    run_id = resolve_run(run_id, workspace=workspace)
    if _v2(run_id, workspace):
        from . import engine
        return engine.inspect_attempt(run_id, attempt_id, workspace=workspace, include_payloads=include_payloads, include_http=include_http)
    require(type(include_payloads) is bool, message="include_payloads must be boolean.")
    _, _, _, records, _ = _load_run(run_id, workspace)
    record = next((r for r in records if r["intent"]["id"] == attempt_id), None)
    require(record is not None, "not_found", "Unknown attempt ID.")
    value = {"run_id": run_id, "intent": record["intent"], "http_capture": None,
             "capture_status": "not_applicable_mock",
             "status": record["outcome"]["response"]["status"] if record["outcome"] else "unresolved"}
    if include_payloads:
        value.update(request=record["request"], outcome=record["outcome"])
    return value


def _v2(run_id, workspace):
    return runs.read(runs.root(workspace, run_id) / "plan.json").get("format") == "humanwill.plan/2"


def resolve_run(run_id, *, workspace):
    """Resolve latest only within the explicitly selected workspace."""
    if run_id != "latest": return identifier(run_id)
    candidates = []
    for path in Path(workspace).expanduser().resolve().glob("*/plan.json"):
        if path.is_symlink() or path.parent.is_symlink(): continue
        value = runs.read(path)
        if value.get("format") in ("humanwill.plan/1", "humanwill.plan/2"):
            _validate_plan(value)
            candidates.append((value["created_at"], value["run_id"]))
    require(candidates, "not_found", "No runs exist in the selected workspace.")
    return max(candidates)[1]


def plan_retry(run_id, *, workspace, **selection):
    from . import engine
    run_id = resolve_run(run_id, workspace=workspace)
    require(_v2(run_id, workspace), "read_only_history", "Version 1 runs are read-only; use version 2 for recovery.")
    return engine.recover(run_id, workspace=workspace, operation="retry", **selection)


def resume(run_id, *, workspace):
    """Prepare unattempted work only; execute the returned immutable plan explicitly."""
    from . import engine
    run_id = resolve_run(run_id, workspace=workspace)
    require(_v2(run_id, workspace), "read_only_history", "Version 1 runs are read-only.")
    return engine.recover(run_id, workspace=workspace, operation="resume")


def grade_saved(run_id, *, workspace, replacement, case_ids=(), model_id=None):
    """Prepare a new grading stream referencing exact saved candidate attempts."""
    from . import engine
    run_id = resolve_run(run_id, workspace=workspace)
    require(_v2(run_id, workspace), "read_only_history", "Version 1 runs are read-only.")
    return engine.recover(run_id, workspace=workspace, operation="grade", replacement=replacement,
                          case_ids=case_ids, model_id=model_id, failed=False)


def execute_retry(prepared, **kwargs):
    require(prepared.to_dict().get("operation") == "retry", message="Expected a retry plan.")
    return execute(prepared, **kwargs)


def inspect_historical_capture(metadata_path, *, include_http=False):
    from .history import inspect_capture
    return inspect_capture(metadata_path, include_http=include_http)


def summarize(run_id, *, workspace, selection='recovery', profiles=()):
    """Freeze verified aggregate results without prompts, answers or credentials."""
    from .reporting import summarize as prepare
    return prepare(run_id, workspace=workspace, selection=selection, profiles=profiles)


def load_report(path):
    from .reporting import load_report as read
    return read(path)


def render_report(prepared, *, output, formats=('html', 'pdf'), style='clean', title='HumanWill evaluation report'):
    from .reporting import render_report as render
    return render(prepared, output=output, formats=formats, style=style, title=title)


def render_images(prepared, *, output, formats=('png',), style='clean'):
    from .reporting import render_images as render
    return render(prepared, output=output, formats=formats, style=style)


def export_questions(*, output, pack=None, run_id=None, workspace=None, case_ids=(),
                     families=(), style='clean', title='HumanWill question library'):
    """Export exact selected questions to a private, neutral HTML/JSON reader."""
    from .questions import export_questions as export
    return export(output=output, pack=pack, run_id=run_id, workspace=workspace,
                  case_ids=case_ids, families=families, style=style, title=title)
