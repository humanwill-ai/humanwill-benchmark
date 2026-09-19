# CLI and agent troubleshooting

For installation, hidden API-key entry and a complete first-run configuration,
start with [Your first evaluation](FIRST_RUN.md). Starter templates intentionally
fail validation until model IDs, price bounds/date and a positive budget are set.

Use `humanwill COMMAND --help` for the actual grammar and append `--json` for the
versioned result/error envelope. API calls raise `HumanWillError` with the same
safe error code and exit-code contract. Keep the envelope and concrete run ID
when diagnosing failures; do not parse human progress prose.

## Installation and configuration

| Symptom | Action |
| --- | --- |
| `humanwill` not found | Activate the environment used for installation, or run its `python -m humanwill`. |
| No source tree / `pip install .` fails | Download the curated source archive or wheel from the [GitHub release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11). Run `pip install .` from the extracted source directory containing `pyproject.toml`, or install the wheel by path. |
| `already_exists` during the demo or export | Choose a new demo/run/output name and update the commands. Init, run creation and exports do not overwrite previous work. |
| `missing_dependency` | Install `.[live]` for HTTP or `.[reports]` for visuals; base JSON/CSV and HTML question readers need neither. Use the wheel path with the same extra when installing a wheel. |
| Invalid configuration | Run `check --config FILE --json`; use TOML version 2 and documented fields. Paths are relative to the TOML file. Secrets belong in environment variables or Keychain, never TOML or CLI arguments. |
| `valid: true` but execution lacks credentials | Check every `credential_references` entry and `live_dependency_available`; configuration validity does not authenticate or guarantee a key is present. Set environment variables in the same terminal. `.env` is not loaded automatically. |
| Missing pack/policy | Supply the permitted original files for an initial run. The software package contains only the demo; use the reference pack from the Git checkout or release ZIP. Inspection/recovery of an existing run uses its verified frozen inputs where supported. |
| Provider rejects a parameter | Inspect the exact request/outcome locally. Correct the model-specific settings or returned-identity allowlist explicitly; there is no silent parameter removal or fallback. |
| `unsafe_path` | Use a real local path without symlinks. On macOS, `/tmp` and `/var` may be aliases; resolve the parent path before selecting a new export directory. |

The accepted configuration schema does not guarantee a model accepts a given
effort/temperature combination. Price fields must be verified upper bounds for
the actual route and context tier. A successful `check` validates local inputs;
it does not authenticate, verify model availability or validate current prices.

## Recover selected work

```sh
humanwill status RUN --workspace WORKSPACE --json
humanwill attempts RUN --workspace WORKSPACE --case V01 --json
humanwill inspect RUN --workspace WORKSPACE --attempt ATTEMPT --http --json
humanwill retry RUN --workspace WORKSPACE --failed --stage judge --save-plan .local/judge-retry.json --json
humanwill run --plan .local/judge-retry.json --execute --json
```

An agent can use `api.list_attempts`, `inspect_attempt`, `plan_retry`, `save_plan`
and `execute_retry` for the same workflow. Plans name exact questions, stages and
parent attempts; inspect them before execution. For candidates use
`--failed --stage candidate`, or explicitly select `--case ID` when intentionally
repeating a completed outcome. Changed settings remain separate report profiles.

| State or error | Meaning and next action |
| --- | --- |
| Candidate succeeded, judge failed | Retry only the judge. Saved answer identity remains bound; no candidate resend is needed. |
| `invalid_judgment` | Inspect the judge response privately. Version 0.1.0a9 accepts plain JSON and a single complete JSON code block, while rejecting extra prose, malformed JSON or invalid fields/scores. An older format failure remains in history; retry only the judge after upgrading. |
| Partial/empty stream | Inspect captured body bytes and normalized disposition. A partial may be retained after an empty retry and may receive a valid judgment. Never infer a policy block merely from missing text. |
| Explicit native policy signal | Inspect the recorded mechanism and raw evidence. A generic filter is distinct from a named cyber-policy code; neither automatically sets the semantic FR label. |
| Unresolved intent / unknown billing | The request may have reached the provider. Resume will not resend it. An explicitly chosen retry needs `--acknowledge-unknown-billing`; the old hold remains. |
| Budget exhausted | Inspect accounted amounts and unresolved holds. There is no automatic cap increase or hold release. A new run has its own budget and does not cancel the old spend. |
| `stale_plan` / `run_changed` | Re-read state and prepare a new plan; do not edit hashes. Initial/resume plans bind the implementation. An explicit retry can record an updated implementation. |
| `run_busy` | Another process holds the run's writer lock. Inspect that process before acting; do not delete the lock file or run concurrent recoveries. |
| `empty_selection` | No work matches the selected stage/profile/cases. Completed refusals are excluded from failed-only recovery. |
| `integrity_error` | Stop writing to that run and investigate the changed/missing artifact. Hash validation is not a repair command. |

HTTP inspection is private: it can include original prompts, answers and decoded
HTTP body bytes. Do not paste it into public issues. Safe initial diagnostics are
package/Python/OS versions, the error code, command shape with secrets/private paths
removed, synthetic reproductions and aggregate coverage. No private support inbox
or submission service is promised by this alpha.

## Reports and exits

Report/image generation can succeed for a partial run; the report still shows its
missing coverage. `results.json` is the reusable aggregate snapshot, not a raw
provider response or a historical publication JSON file. Re-render it with
`--results FILE`; choose a new output directory each time. Question exports must
remain under `.local`. Check the final manifest before treating a bundle as
complete after an interrupted filesystem write.

Exit codes: **0** operation succeeded; **2** invalid inputs, conflicts, stale plan
or empty selection; **3** valid partial/incomplete execution result; **4** local
filesystem failure; **70** unexpected internal failure; **130** interruption.
Read the structured envelope as well as the exit code. A successful export is not
proof of a completed benchmark or permission to publish its content.
