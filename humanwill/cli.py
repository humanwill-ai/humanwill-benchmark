"""Thin CLI: all evaluation behavior lives in humanwill.api."""
import argparse
import sys

from . import __version__, api
from .contracts import HumanWillError, encode, envelope, require


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can include user input; keep machine errors bounded.
        raise HumanWillError("invalid_arguments", "Invalid arguments; use humanwill COMMAND --help.")


def parser():
    root = Parser(description="HumanWill local evaluation operations for humans and agents.")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                      help="Emit one versioned JSON envelope on stdout.")
    sub = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    commands = {}
    for name, help_text in {
        "init": "Create a harmless demo and configuration without replacing files.",
        "check": "Validate local configuration and pack; no model calls or writes.",
        "run": "Prepare a plan, or explicitly execute its bounded operation.",
        "status": "Read verified run status and separate metric summaries.",
        "attempts": "List attempts without displaying prompt/response payloads.",
        "inspect": "Inspect one attempt; payload disclosure is explicit.",
        "retry": "Prepare selected new attempts; default is failed-only and read-only.",
        "resume": "Prepare unattempted work under the original configuration.",
        "grade": "Prepare a separate judge stream over saved answers.",
        "history": "Read and verify one historical HTTP capture; no migration or execution.",
        "report": "Export verified aggregates to HTML/PDF and JSON/CSV without model calls.",
        "images": "Export charts in clean and spotlight styles without model calls.",
        "questions": "Export a private searchable HTML question library.",
        "pack": "Author, validate and build local question packs and extensions.",
        "policy": "Create, preview and inspect explicit judge-policy resolution.",
    }.items():
        cmd = sub.add_parser(name, help=help_text, description=help_text)
        cmd.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        commands[name] = cmd
    commands["init"].add_argument("directory", nargs="?", default=".")
    policy = commands['policy'].add_subparsers(dest='policy_operation', required=True, parser_class=Parser)
    for name in ('init','preview','inspect'):
        item = policy.add_parser(name)
        item.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
        item.add_argument('source')
        if name=='preview': item.add_argument('--pack',required=True)
        if name=='inspect':
            item.add_argument('--workspace',required=True)
            item.add_argument('--operation',dest='operation_id')
        if name!='init': item.add_argument('--case',action='append',default=[],dest='case_ids')
    pack = commands['pack'].add_subparsers(dest='pack_operation', required=True, parser_class=Parser)
    for name in ('init', 'validate', 'build'):
        item = pack.add_parser(name)
        item.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
        item.add_argument('source')
        if name == 'init': item.add_argument('--extends')
        if name == 'build': item.add_argument('--output', required=True)
    commands["init"].add_argument("--engine-version", type=int, choices=(1, 2), default=2)
    commands["check"].add_argument("--config", default="benchmark.toml")
    commands["history"].add_argument("metadata_path")
    commands["history"].add_argument("--http", action="store_true")
    run = commands["run"]
    source = run.add_mutually_exclusive_group()
    source.add_argument("--config", help="TOML file; defaults to benchmark.toml.")
    source.add_argument("--plan", help="Previously saved plan; revalidate inputs before execution.")
    run.add_argument("--run-id")
    run.add_argument("--save-plan", metavar="PATH")
    run.add_argument("--execute", action="store_true", help="Execute; default is a read-only preview.")
    for name in ("status", "attempts", "inspect", "retry", "resume", "grade"):
        commands[name].add_argument("run_id")
        commands[name].add_argument("--workspace", required=True, help="Explicit local run workspace.")
    commands["status"].add_argument("--selection", choices=("first", "recovery"), default="recovery")
    commands["inspect"].add_argument("--http", action="store_true", help="Return exact saved body as base64, with metadata/path.")
    for name in ("retry", "resume", "grade"):
        commands[name].add_argument("--execute", action="store_true")
        commands[name].add_argument("--save-plan")
    for name in ("retry", "grade"):
        commands[name].add_argument("--case", action="append", default=[], dest="case_ids")
        commands[name].add_argument("--model", dest="model_id")
        commands[name].add_argument("--config", required=name=="grade", help="Complete replacement configuration; changes remain separately labeled.")
    commands["retry"].add_argument("--profile", dest="profile_id", help="Explicit source profile; default is the latest operation.")
    commands["retry"].add_argument("--stage", choices=("candidate", "judge"), default="judge")
    commands["retry"].add_argument("--failed", action="store_true", help="Limit selection to failed/latest incomplete attempts.")
    commands["retry"].add_argument("--acknowledge-unknown-billing", action="store_true")
    commands["attempts"].add_argument("--case", dest="case_id")
    commands["inspect"].add_argument("--attempt", required=True, dest="attempt_id")
    commands["inspect"].add_argument("--payloads", action="store_true",
                                      help="Explicitly display saved requests and responses.")
    for name in ("report", "images", "questions"):
        commands[name].add_argument("run_id", nargs="?")
        commands[name].add_argument("--workspace")
        commands[name].add_argument("--output", required=True, help="New export directory; never overwrite.")
        commands[name].add_argument("--style", choices=("clean", "spotlight", "both"), default="clean")
    for name in ("report", "images"):
        commands[name].add_argument("--results", help="Previously exported, verified results.json snapshot.")
        commands[name].add_argument("--selection", choices=("first", "recovery"), default="recovery")
        commands[name].add_argument("--profile", action="append", default=[], dest="profiles")
        commands[name].add_argument("--format", default="html,pdf" if name=="report" else "png", dest="formats")
    commands["report"].add_argument("--title", default="HumanWill evaluation report")
    commands["questions"].add_argument("--pack", help="Explicit original pack manifest; alternative to a run ID.")
    commands["questions"].add_argument("--case", action="append", default=[], dest="case_ids")
    commands["questions"].add_argument("--family", action="append", default=[], dest="families")
    commands["questions"].add_argument("--title", default="HumanWill question library")
    return root


def dispatch(args):
    if args.command == 'policy':
        if args.policy_operation=='init': return api.init_policy(args.source)
        if args.policy_operation=='preview': return api.preview_policy(args.source,pack=args.pack,case_ids=args.case_ids)
        return api.inspect_policy(args.source,workspace=args.workspace,operation_id=args.operation_id,case_ids=args.case_ids)
    if args.command == 'pack':
        if args.pack_operation == 'init': return api.init_pack(args.source, extends=args.extends)
        if args.pack_operation == 'validate': return api.validate_pack(args.source)
        return api.build_pack(args.source, output=args.output)
    if args.command in ("report", "images"):
        require(bool(args.results) != bool(args.run_id), message="Select a run or a saved results snapshot.")
        if args.results:
            require(args.workspace is None and not args.profiles and args.selection=="recovery", message="Saved snapshots already bind profiles and selection.")
            prepared = api.load_report(args.results)
        else:
            require(args.workspace is not None, message="A run export requires a workspace.")
            prepared = api.summarize(args.run_id, workspace=args.workspace, selection=args.selection, profiles=args.profiles)
        if args.command == "report":
            return api.render_report(prepared, output=args.output, formats=args.formats, style=args.style, title=args.title)
        return api.render_images(prepared, output=args.output, formats=args.formats, style=args.style)
    if args.command == "questions":
        return api.export_questions(pack=args.pack, run_id=args.run_id, workspace=args.workspace,
            output=args.output, style=args.style, title=args.title, case_ids=args.case_ids, families=args.families)
    if args.command == "init":
        return api.init(args.directory, version=args.engine_version)
    if args.command == "history":
        return api.inspect_historical_capture(args.metadata_path, include_http=args.http)
    if args.command == "check":
        return api.check(args.config)
    if args.command == "run":
        require(not (args.plan and args.run_id), message="Saved plans already bind a run ID.")
        prepared = api.load_plan(args.plan) if args.plan else api.plan(args.config or "benchmark.toml", run_id=args.run_id)
        if args.save_plan:
            api.save_plan(prepared, args.save_plan)
        return api.execute(prepared) if args.execute else prepared.to_dict()
    if args.command in ("retry", "resume", "grade"):
        if args.command == "resume": prepared = api.resume(args.run_id, workspace=args.workspace)
        elif args.command == "grade":
            prepared = api.grade_saved(args.run_id, workspace=args.workspace, replacement=args.config,
                                       case_ids=args.case_ids, model_id=args.model_id)
        else:
            prepared = api.plan_retry(args.run_id, workspace=args.workspace, replacement=args.config,
                    case_ids=args.case_ids, model_id=args.model_id, stage=args.stage,
                    failed=args.failed or not args.case_ids, acknowledge_unknown=args.acknowledge_unknown_billing, profile_id=args.profile_id)
        if args.save_plan: api.save_plan(prepared, args.save_plan)
        return api.execute(prepared) if args.execute else prepared.to_dict()
    if args.command == "status":
        return api.status(args.run_id, workspace=args.workspace, selection=args.selection)
    if args.command == "attempts":
        return api.list_attempts(args.run_id, workspace=args.workspace, case_id=args.case_id)
    return api.inspect_attempt(args.run_id, args.attempt_id, workspace=args.workspace,
                               include_payloads=args.payloads, include_http=args.http)


def display(operation, data):
    if data.get('format')=='humanwill.policy-preview/1':
        print(f"Policy {data['policy_id']} ({data['version']}): {data['selected_questions']} questions in {data['pack_id']}.")
        print(f"Policy snapshot SHA-256: {data['policy_sha256']}")
        if 'operation_id' in data: print(f"Saved operation: {data['operation_id']}")
        for row in data['resolutions']:
            print(f"\nDomain {row['domain']}; topic {row['topic'] or 'all'}; {len(row['case_ids'])} question(s).")
            print('Cases: '+', '.join(row['case_ids']))
            print('Rule resolution:')
            for entry in row['trace']:
                prior = ' (previously '+entry['previous_source']+')' if 'previous_source' in entry else ''
                print(f"  {entry['action']} {entry['rule']} from {entry['source']}{prior}")
            print('Exact judge system instructions:\n'+(row['judge_system_text'] or 'Mock fixture; no semantic judge instructions.'))
        for note in data['limitations']: print(note)
    elif operation == "init":
        print(f"Created offline demo: {data['config']}")
        print("Simulation only; no API keys or model calls.")
    elif operation == "check":
        print(f"Valid configuration: {data['questions']} questions, {len(data['models'])} model(s).")
        print("Simulation; no credentials required." if data["simulated"] else "Live configuration; inspect --json for credential references and budget.")
        if 'native_block_scoring' in data:
            print('Local scoring: '+data['native_block_scoring']['text'])
    elif data.get("format") == "humanwill.export-result/1":
        print(f"Created {data['kind']} export: {data['directory']}")
        for path in data['files']:
            print(f"  {path}")
        print(f"File hashes: {data['manifest']}")
    elif data.get("format") == "humanwill.plan/2":
        print(f"{data['operation']} plan for {data['run_id']}: {len(data['tasks'])} selected tasks.")
        print(f"Run budget: ${data['config']['budget_micro_usd']/1e6:.2f}; maximum operation reservations: ${data['maximum_reservation_micro_usd']/1e6:.2f}.")
        for job in data['tasks']:
            print(f"  {job['model']['id']} {job['case_id']} {job['stage']}: {job['reason']}; parent={job['parent_attempt_id']}; profile={job['profile'][:12]}")
        if data["configuration_changes"]: print("Configuration changes: " + encode(data["configuration_changes"]).decode())
        print("No execution performed. Add --execute or execute the saved plan.")
    elif data.get("format") == "humanwill.plan/1":
        print(f"Plan for {data['run_id']}: {len(data['pack']['case_ids'])} questions, "
              f"{len(data['config']['models'])} simulated model(s).")
        print(f"Workspace: {data['config']['workspace']}")
        print(f"Plan SHA-256: {data['plan_sha256']}")
        print("No execution performed. Add --execute to run this simulation.")
    elif data.get("format") in ("humanwill.results/1", "humanwill.results/2"):
        print(f"Run {data['run_id']}: {data['status']}; {data['attempt_count']} attempts; accounted ${data['accounted_micro_usd']/1e6:.6f}.")
        for model in data["models"]:
            metrics = model["overall"]
            fr, usefulness = metrics["false_refusal_rate"], metrics["mean_usefulness"]
            fr_text = "undefined" if fr is None else f"{100 * fr:.1f}%"
            u_text = "undefined" if usefulness is None else f"{usefulness:.2f}/4"
            print(f"  {model['model_id']} {model.get('profile', '')[:12]}: FR {fr_text} (n={metrics['fr_classified']}/{metrics['total']}); "
                  f"U {u_text} (n={metrics['usefulness_scored']}/{metrics['total']})")
        if data["simulated"]: print("Fixture scores demonstrate the workflow, not model performance.")
    else:
        print(encode(data).decode(), end="")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    operation = "parse"
    try:
        args = parser().parse_args(argv)
        json_mode = getattr(args, "json", False)
        operation = args.command
        data = dispatch(args)
        if json_mode:
            print(encode(envelope(operation, data)).decode(), end="")
        else:
            display(operation, data)
        # A partial result is still valid data; callers use both the exit code and status.
        return 3 if data.get("status") in ("partial", "incomplete") else 0
    except KeyboardInterrupt:
        error = HumanWillError("interrupted", "Interrupted; inspect saved intents before any recovery.", 130)
    except HumanWillError as exc:
        error = exc
    except OSError:
        error = HumanWillError("filesystem_error", "Local file operation failed; inspect paths and permissions.", 4)
    except Exception:
        error = HumanWillError("internal_error", "Operation failed; no exception payload was printed.", 70)
    if json_mode:
        print(encode(envelope(operation, error=error)).decode(), end="")
    else:
        print(f"{error.code}: {error}", file=sys.stderr)
    return error.exit_code
