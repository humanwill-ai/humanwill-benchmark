# HumanWill local API and CLI

HumanWill evaluates false refusal and answer usefulness on legitimate cybersecurity
questions, reporting them separately. CLI users, agents and Python applications
share one operation API. For installation through your first real report, start
with [Your first evaluation](../docs/FIRST_RUN.md); this document is the detailed
command/configuration reference.
The installable engine supports offline simulation, bounded OpenAI/Anthropic/
OpenRouter requests, separate candidate/judge attempts, selective recovery, saved
answer grading, private HTTP inspection, saved-result reports and charts in clean
and spotlight styles, and searchable HTML question readers. Historical builders
remain available in the research checkout.

Alpha targets CPython 3.11–3.14 on macOS/Linux. The product release is v0.1.0a11. Exact release
commit, installed-package checks and support boundaries are recorded in
[release validation](../docs/CLI_RELEASE.md).
Native Windows is not a supported alpha target. The demo, JSON/CSV result exports
and HTML question readers use the standard library. HTTP execution adds HTTPX;
visual reports and charts use the optional `reports` extra. Install into a separate environment from the historical research setup:

```sh
python -m pip install .                 # local source, offline engine
python -m pip install '.[live]'         # add HTTP execution
python -m pip install '.[reports]'      # add HTML/PDF reports and PNG/SVG charts
python -m pip install '.[live,reports]' # usual installation for a live evaluation
# Or use python -m humanwill directly from the checkout.
```

The build uses setuptools and installation may download dependencies. A prepared
wheel installs with `pip install --no-index --no-deps /path/to/wheel.whl`; HTTPX
must already be present for live execution. Inspect is not a dependency.

## Start with the harmless demo

```sh
humanwill init demo
humanwill check --config demo/benchmark.toml
humanwill run --config demo/benchmark.toml --run-id demo-01 --save-plan demo/plan.json
humanwill run --plan demo/plan.json --execute --json
humanwill status demo-01 --workspace demo/.local/humanwill-runs --json
humanwill attempts demo-01 --workspace demo/.local/humanwill-runs --case D01 --json
humanwill inspect demo-01 --workspace demo/.local/humanwill-runs --attempt a00000001 --payloads --json
```

The default demo uses config/run version 2 and makes no network requests. Scores
are synthetic fixture checks, not model performance. `init --engine-version 1`
retains the earlier offline demonstration. Version 1 runs remain readable but are
not migrated into writable recovery runs.

Plans are read-only previews unless `--save-plan` or `--execute` is specified.
They bind exact pack data, settings, implementation, selected IDs and price inputs.
Later TOML edits do not silently modify a saved plan. Initial execution needs the
original pack/policy files; later inspection and same-policy recovery use frozen
snapshots. Regenerate a plan after code changes. Resume additionally requires the
original implementation; an explicit retry can record a newer implementation.

## Configure real models

Use a complete version-2 template from the installed package or source:

| Template | Candidate(s) / judge |
| --- | --- |
| [OpenAI](data/examples/openai.toml) | OpenAI / OpenAI |
| [Anthropic](data/examples/anthropic.toml) | Anthropic / Anthropic |
| [OpenRouter](data/examples/openrouter.toml) | Explicit route for each OpenRouter model |
| [Compare two models](data/examples/compare.toml) | OpenAI + Anthropic / shared OpenAI judge |

The [first-run guide](../docs/FIRST_RUN.md#choose-a-provider-template) shows how to
copy them from either a source or wheel installation. Fill exact model IDs,
verified price bounds and dates, and a positive total budget. Empty/zero values
deliberately fail validation. Optional settings must be supported by the selected
model; the examples do not promise current model availability or prices.

| Run setting | Meaning |
| --- | --- |
| `version = 2` | Current live/recovery configuration contract. |
| `pack` | Local manifest for a compiled or frozen question pack. |
| `workspace` | Local directory containing immutable runs. |
| `models` / `judge` | One or more candidate configurations and a separate semantic judge. |
| `judge_policy` or `policy_bundle` | Exact text policy or explicit domain/topic bundle; mutually exclusive. |
| `case_ids` | Optional explicit question IDs; omitted or empty selects the full pack. |
| `budget_micro_usd` | Total run cap in integer micro-USD; 1,000,000 = USD 1. Includes judging and retries. |
| `concurrency` | Concurrent work limit, 1–16; default 1. |
| `minimum_interval_ms` | Request pacing, 0–60,000 milliseconds; default 0. |
| `native_block_scoring` | Optional `native-block-fr-u/1`: deterministic FR2/U0 for qualifying empty native blocks; see [the rule](../docs/CLI_EXECUTION.md#optional-deterministic-native-block-scoring-010a10). |

Paths are relative to the TOML file. Each candidate has a unique `id`;
`provider` selects the adapter and `model` is the actual service model ID.
Each live model/judge needs a credential reference and its own verified price
snapshot. `max_input_tokens`, `max_output_tokens`, optional model settings and
explicit returned-identity allowlists belong to each model configuration.

Compiled assistance-focused cybersecurity and exact frozen-message packs are
supported. The 424-question reference pack and exact bundled policy have completed
internal owner review and are distributed separately in the private GitHub release
under CC BY 4.0 for HumanWill's licensable rights. The software wheel includes only
the harmless demo. [Pack access](../docs/PACK_ACCESS.md) explains the approved
reference delivery and its unchanged historical provenance.

Credentials are references: `env:VARIABLE` or `keychain:openai`,
`keychain:anthropic`, `keychain:openrouter`. The latter read the existing HumanWill
macOS Keychain service/account entries in memory. Planning never reads secrets;
`check` checks environment presence without displaying values and reports Keychain
availability as unknown rather than triggering its UI. The
[first-run credential instructions](../docs/FIRST_RUN.md#supply-api-keys-in-your-terminal)
show hidden terminal entry; .env files are not automatically loaded. There are no
secret-valued CLI arguments. Judge-only execution resolves only the judge credential.

Supported tool-free providers/settings:

| Provider | Request / settings |
| --- | --- |
| `openai` | Responses API, `store=false`; `reasoning_effort`, `temperature`. |
| `anthropic` | Messages API; original system text in the top-level `system`; `thinking=adaptive/disabled`, `effort`, `temperature`. |
| `openrouter` | Streaming Chat Completions; required single `route` and explicit `returned_providers` array; `reasoning_effort`, `temperature`. |

Provider/model combinations may reject parameters they do not support; nothing
is silently removed or substituted. Returned model IDs must match the requested
ID or an explicitly configured `returned_models` allowlist. OpenRouter disables
fallbacks and requires the named route to support parameters. No tools, automatic
retries, batch execution, proxy environment or redirects are enabled. Both read
and total request deadlines use `timeout_seconds` (default 240).

## Recover and investigate

```sh
humanwill retry RUN --workspace DIR --failed --stage judge
humanwill retry RUN --workspace DIR --failed --stage judge --execute
humanwill retry RUN --workspace DIR --case D01 --stage candidate --save-plan retry.json
humanwill run --plan retry.json --execute
humanwill resume RUN --workspace DIR --execute
humanwill grade RUN --workspace DIR --config revised-judge.toml --execute
humanwill inspect RUN --workspace DIR --attempt a00000001 --http --json
humanwill history /private/run/http/response-001.json --http --json
```

Retry defaults to failed-only selection in the latest operation's configuration.
`--case` explicitly selects completed outcomes too unless `--failed` is supplied.
Completed refusals/policy blocks are excluded from failed-only candidate retries.
`--profile HASH` selects an older profile, and `--model ID` narrows a comparison.
A replacement `--config` records a visible configuration diff and creates a separate
result profile. Candidate settings cannot change in a judge-only repair. Changed
pack/population/budget requires a new run. `grade` creates a distinct judge/policy
stream bound to the exact saved candidate answers.

Resume selects only never-attempted work, including an unattempted judge whose
candidate answer exists. It never resends an unresolved intent. A retry with
uncertain billing requires `--acknowledge-unknown-billing`; the previous hold
remains and the new request gets a separate reservation. Preview materializes
exact question/stage/parent IDs, accounting before execution and maximum operation
reservations. Execution rejects a stale selection if another operation changed
the run. A run is exclusively created; a SQLite writer lock excludes concurrent
execution/recovery processes within that run while allowing bounded async calls.

`latest` resolves only inside an explicit workspace and the result reports the
concrete run ID. Separate run IDs have separate budgets: creating multiple runs is
not an account-wide spend limit. Budget accounting is conservative, not an invoice:
input bytes plus a framing allowance bound reservations; known final usage uses
configured upper rates without claiming cache discounts or counting reasoning twice.
Missing/unfinished usage retains the full hold. A detected price-bound overrun is
recorded and stops further dispatch; it cannot undo the charge. An exhausted
budget leaves unattempted work visible. There is no automatic hold release or cap
increase command in this milestone.

Inspection omits payloads by default. `--payloads` returns saved request/outcome;
`--http` additionally returns the observed body as base64 and its local path/hash.
These are HTTPX content-decoded body bytes, not TLS/wire captures. Partial bytes
survive transport errors/cancellation. Response headers use a documented allowlist;
request headers/credentials are never recorded. Missing captures are unavailable,
never reconstructed. Historical inspection accepts the pinned ordinary and SSE
HTTPX capture schemas, checks hashes, and does not import old runners or migrate
campaign results. Native exact `cyber_policy` evidence remains distinct from a
generic filter, prose refusal and unknown failure. Service signals are evidence to
the judge, not automatic semantic FR scores or a universal safety score.

## Reports, images and question readers

```sh
humanwill report demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/report-01 --style both
humanwill images demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/images-01 --style spotlight --format png,svg
humanwill questions demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/questions-01 --style both
```

Reports default to HTML and PDF, with JSON/CSV audit sidecars. Images have exact
chart-data sidecars. Use `--style clean`, `spotlight` or `both`; both styles retain
the same values, profile identities and independent denominators. Each output
must be a new directory. Exports never call models or resolve credentials.
`--selection first` preserves first attempts; recovery is the default. Use
`--results path/to/results.json` instead of a run to render a frozen aggregate
snapshot again, including after its original private run is unavailable.

Question readers support family tabs, search, exact messages and expandable
supplied evidence/provenance without model-result annotations. Export either a
run's selected questions or `--pack path/to/manifest.json`, optionally filtering
with `--case` / `--family`. Question exports stay under `.local`; exporting does
not grant redistribution rights. Base installation supports JSON/CSV and question
HTML; visual result reports and charts require the `reports` extra.
See [complete reporting contracts](../docs/CLI_REPORTING.md) in the source checkout.

## Agents and reproducible results

```python
from humanwill import api

prepared = api.plan("benchmark.toml", run_id="comparison-01")
result = api.execute(prepared)  # async applications: await api.execute_async(prepared)
repair = api.plan_retry(result["run_id"], workspace=result["workspace"], stage="judge")
# Inspect repair.to_dict(); persist it with api.save_plan if desired.
repaired = api.execute_retry(repair)
evidence = api.inspect_attempt(result["run_id"], "a00000001",
                              workspace=result["workspace"], include_http=True)
```

All operations live in `humanwill.api`; CLI commands only parse/display. `Plan` and
`humanwill.settings.Settings` use immutable serialized values; `to_dict()` returns
a copy. `humanwill.config.load()` loads typed version 1 or 2 settings. API calls do
not print. `--json` emits one `humanwill.cli/1` envelope with `operation`, `ok`,
`data`, `error`. Synchronous execution refuses nested event loops. HTTP tests can
inject `httpx.MockTransport` through the API without authenticating or networking.

`status --selection first` preserves first-attempt votes per configuration;
`--selection recovery` chooses the latest usable candidate and latest valid judge
bound to that exact candidate/profile. An empty/error retry retains an earlier
usable partial. Selection is chronological, never best-score selection. The
selected and latest attempt IDs are both shown, and every selection has a hash.
Every profile keeps the original selected question population, including missing
rows, and its own model/judge/policy settings. FR and usefulness denominators are
independent, with null for no classified/scored population. No harmful-compliance
denominator is invented for the assistance-focused cybersecurity pack.

Exit codes: 0 successful operation; 2 validation/stale plan/empty selection/conflict;
3 valid partial/incomplete result (including budget/provider stop); 4 filesystem
failure; 70 unexpected internal failure; 130 interruption. Provider exception
messages are suppressed. Private files/directories use POSIX modes 0600/0700;
Windows ACLs remain separate work; see the tested release matrix. Use a local filesystem
for the writer lock, not a shared/network drive. No telemetry, uploads or public
publication are performed. Framework software uses Apache 2.0; the bundled
demo content uses CC BY 4.0. See [license scope](../LICENSING.md).

## Release validation and support

Package `0.1.0a11` is a private alpha. The [GitHub release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11)
provides the wheel, curated source archive and separate approved question pack
to authorized repository users. See the source checkout's
[release matrix and publication gates](../docs/CLI_RELEASE.md),
[troubleshooting](../docs/CLI_TROUBLESHOOTING.md) and
[pack access](../docs/PACK_ACCESS.md). Harmless demo, frozen cybersecurity and compiled assistance-focused cybersecurity
question packs are supported. Local authoring/extensions are available; arbitrary
third-party formats are not supported. Software and reference-pack downloads
require repository access; public distribution is a separate future launch.

The selected software is Apache 2.0, with [HumanWill attribution](../NOTICE).
The demo content uses CC BY 4.0; trademark rights remain separate under
[brand guidance](../BRAND.md). The broader research repository
and its Git history are outside the selected standalone candidate. A successful
local test or package build does not authorize publication.


## Author and extend local question packs

```sh
humanwill pack init .local/my-pack
# Edit .local/my-pack/pack.toml and questions.jsonl.
humanwill pack validate .local/my-pack/pack.toml --json
humanwill pack build .local/my-pack/pack.toml --output .local/my-built-pack
```

Use `.local/my-built-pack/manifest.json` as `pack` in a version-2 run configuration.
To extend an existing compiled pack, add `--extends PATH/manifest.json` to `pack init`.
The base is pinned by hash; inherited questions/rights remain unchanged. The
compiled extension works without the original source directory. `exclude` in TOML
removes explicitly named base cases. New questions need distinct IDs and accurate
provenance; assessment criteria are sent only to the judge.

Agents use `api.init_pack`, `api.validate_pack` and `api.build_pack`; the CLI calls
these same operations. No authoring operation reads API keys or contacts models.
Current custom packs are cybersecurity assistance cases with independent FR/U
scores; broader metric contracts remain separate work.
See [pack access and authoring](../docs/PACK_ACCESS.md) for the JSONL example,
privacy boundaries and validation limitations. Builds never overwrite files.

## Customize and inspect judging policies

```sh
humanwill policy init .local/company-policy
# Edit the named rules and explicit domain/topic overrides in policy.toml.
humanwill policy preview .local/company-policy/policy.toml --pack PATH/manifest.json --json
humanwill policy inspect latest --workspace .local/runs --json
```

Set `policy_bundle = "PATH/policy.toml"` instead of `judge_policy` in a version-2
run configuration. Resolution applies base, then domain, then exact topic/family;
preview shows the rule-edit trace and exact judge system instructions offline.
Saved inspection works without the original policy file. Use `grade` with a
replacement config to judge saved answers under a changed policy, retaining the
old profile and results. Candidate messages and assistance eligibility stay fixed.
Agents use `api.init_policy`, `api.preview_policy` and `api.inspect_policy`.
See [policy overrides](../docs/POLICY_OVERRIDES.md) for examples and limitations.

Reports and images automatically label reference/customized configurations,
including each profile in mixed reports. Reference questions with custom judging
remain visibly customized; subsets and extensions are identified. JSON/CSV and
the `result-context.json` sidecar expose the same classification for agents.
Legacy aggregate snapshots retain their hashes and show unverified provenance
where needed. See [report labels](../docs/CLI_REPORTING.md#reference-and-customized-configuration-labels).
