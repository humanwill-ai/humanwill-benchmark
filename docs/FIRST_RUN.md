# Your first HumanWill evaluation

This guide takes you from installation to a report, then to a small live run.
HumanWill measures false refusal and answer usefulness on legitimate cybersecurity
tasks, keeping the two scores separate. The CLI and agent/Python API perform the
same operations. You do not need Inspect, Docker, a database server or a hosted
HumanWill account.

The framework uses Apache 2.0; the bundled demo questions use CC BY 4.0 with
HumanWill attribution. See [license scope](../LICENSING.md). Your own questions
and model responses retain their applicable rights.

Choose a starting point:

| Path | What you need | Model calls |
| --- | --- | --- |
| Offline demo | Python and the software | None; simulated scores. |
| One-question live run | Your local pack, API key(s), model/judge choices, prices and budget | Candidate generation and judging are paid provider requests. |
| Full reference benchmark | The separate 424-question pack plus live configuration | Paid candidate/judge requests; pack download requires private repository access. |

## Install

Use CPython 3.11–3.14 on macOS or Linux and a local filesystem. The commands below
work in Bash or zsh. Native Windows and shared/network run storage are outside
the alpha support scope.

**Distribution status:** the [private GitHub release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11)
provides `humanwill_evals-0.1.0a11-py3-none-any.whl`, the curated
`humanwill_evals-0.1.0a11.tar.gz` source archive, and
`humanwill-cybersecurity-initial424-0.1.0.zip`. Sign in with an account that has
repository access. Download the software and, for reference runs, the separate
question pack. Check downloaded files against `SHA256SUMS.txt` from that release.
No PyPI publication is part of this alpha.

For a source checkout:

```sh
git clone https://github.com/humanwill-ai/humanwill-benchmark.git
cd humanwill-benchmark
```

Then, from the directory containing `pyproject.toml`:

```sh
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[live,reports]'
humanwill --version
```

Expect version `0.1.0a11`. Keep this environment active for the rest of the guide.
In a new terminal, activate it again. If the command is not found, use
`python -m humanwill` in place of `humanwill` with the same activated Python.
Installation may download build/runtime dependencies; the demo itself is offline.

If you were supplied a wheel instead, create/activate an environment in a working
directory of your choice and replace the install command with the following,
substituting the actual wheel path:

```sh
python -m pip install '/absolute/path/humanwill_evals-0.1.0a11-py3-none-any.whl[live,reports]'
```

The starter templates used below are included in the wheel as well as the source.
A source archive includes the complete linked documentation; keep it alongside a
wheel installation if you want the guides offline.

For a smaller source installation, use `python -m pip install .`: it supports the
demo, JSON/CSV exports and HTML question readers without runtime dependencies.
Add `.[live]` for HTTP execution or `.[reports]` for HTML/PDF result reports and
PNG/SVG images. This guide uses both extras.

## Run the free offline demo

Keep using the same working directory throughout this guide; paths below are
relative to it. Use a fresh `demo` destination. If it exists from a previous try,
choose a new name and update the commands; initialization never overwrites it.

```sh
humanwill init demo
humanwill check --config demo/benchmark.toml
humanwill run --config demo/benchmark.toml --run-id demo-01 --save-plan demo/plan.json
humanwill run --plan demo/plan.json --execute
humanwill status demo-01 --workspace demo/.local/humanwill-runs
humanwill report demo-01 --workspace demo/.local/humanwill-runs --output .local/demo-report --style both
```

Expected outcome: **3 selected questions, 6 attempts (3 candidate + 3 judge),
complete status, $0 accounted, and Simulation labels**. The fixture answers score
FR 0% and usefulness 4/4; those numbers demonstrate the workflow, not a real model.
The planning command makes no requests; executing this particular demo is also
offline because both providers are `mock`.

Open `.local/demo-report/report-clean.html` in your browser or the corresponding
PDF in a PDF viewer. `report-spotlight.html` and `.pdf` provide the dark navy/teal/gold
style. The folder also contains `results.json`, `results.csv`,
`result-context.json` and an inventory `manifest.json`.

Only want images, or a searchable question reader?

```sh
humanwill images demo-01 --workspace demo/.local/humanwill-runs --output .local/demo-images --style both --format png,svg
humanwill questions demo-01 --workspace demo/.local/humanwill-runs --output .local/demo-questions --style both
```

Look for `refusal-overall-01-clean.png`, `usefulness-overall-01-spotlight.png` and
`questions-clean.html` in their respective directories. Export destinations must
be new; choose another output name when repeating a command. Question readers
stay under `.local` and retain exact question text and provenance.

## From the demo to a live evaluation

### Create a small question pack and judging policy

The following creates a harmless one-question cybersecurity pack with ID
`CUSTOM01`, suitable for checking your live setup:

```sh
humanwill pack init .local/my-pack
humanwill pack validate .local/my-pack/pack.toml
humanwill pack build .local/my-pack/pack.toml --output .local/my-pack-built
humanwill policy init .local/my-policy
humanwill policy preview .local/my-policy/policy.toml --pack .local/my-pack-built/manifest.json --case CUSTOM01
```

These operations are offline. Read the generated question and policy before using
them. The example question asks about a supplied synthetic `debug=false` setting;
it is an installation exercise, not substantive benchmark coverage. Before using
your own cases, edit `questions.jsonl` and the TOML metadata, replace the example
authorship/attribution, and build to a new destination. Follow
[pack authoring](PACK_ACCESS.md#local-question-authoring-and-extensions).

The generated policy is a versioned starting rubric, not a calibrated judge.
Domain/topic customization changes judging criteria; arbitrary company rules that
change when refusal is required are not implemented. This run will be labeled
**Customized configuration**. See [policy overrides](POLICY_OVERRIDES.md).

### Choose a provider template

All four are complete TOML files; each includes candidate(s), judge, prices,
credential references, budget, selection and paths:

| Template | Candidates | Judge | Environment variables |
| --- | --- | --- | --- |
| `openai.toml` | One OpenAI model | OpenAI | `OPENAI_API_KEY` |
| `anthropic.toml` | One Anthropic model | Anthropic | `ANTHROPIC_API_KEY` |
| `openrouter.toml` | One OpenRouter model on an explicit route | OpenRouter on an explicit route | `OPENROUTER_API_KEY` |
| `compare.toml` | One OpenAI and one Anthropic model | One shared OpenAI judge | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` |

Copy one template from the installed package. This works for both wheel and source
installs and refuses to replace an existing configuration. Change `openai.toml`
below to the template you want:

```sh
python - <<'PY'
from importlib.resources import files
from pathlib import Path
template = "openai.toml"
target = Path(".local/benchmark.toml")
with target.open("xb") as output:
    output.write(files("humanwill").joinpath("data", "examples", template).read_bytes())
print(target)
PY
```

The templates also live at `humanwill/data/examples/` in a source checkout.
Open `.local/benchmark.toml` in a text editor and fill:

1. `model` for every candidate and the judge: exact IDs available to your account.
2. Both price bounds, their source and `verified_at` date for each model. Use
   verified rates covering the applicable provider/route/context tiers.
3. A positive `budget_micro_usd` for the entire run, including the judge and retries.
4. For OpenRouter, each `route` and `returned_providers` list. The route selector
   and returned provider name can differ; use the exact service identities.
5. Input/output limits and optional settings supported by your chosen model.

Blank model/pricing fields and zero budgets deliberately fail validation. No model
IDs or prices are silently chosen. `1_000_000` micro-USD is **USD 1**. Price fields
are micro-USD per **million tokens**: a hypothetical USD 2 per million tokens is
`2_000_000`, not `2`. These conversions are examples, not current prices. The
engine's byte-based reservations can be conservative; inspect the plan's maximum
reservation. A cap that cannot cover the next request produces a partial run.

The default paths resolve relative to `.local/benchmark.toml`: `my-pack-built/`
means `.local/my-pack-built/`, `my-policy/` means `.local/my-policy/`, and `runs`
means `.local/runs`. Do not add another `.local/` prefix inside that config.
`case_ids = ["CUSTOM01"]` keeps the first run to one question.

For a comparison, use `compare.toml` and fill both candidate sections plus the
shared judge. One question then requires two candidate calls and two judge calls.
You may add further `[[models]]` blocks with unique `id` labels before `[judge]`.
The judge provider can differ from candidate providers. Each model gets a separate
profile. OpenRouter requires explicit routes and does not silently fall back;
optional reasoning/temperature settings are never silently removed on failure.

### Supply API keys in your terminal

For the OpenAI template, enter the key at the hidden prompt below. The key itself
is not part of your shell command history or the TOML file:

```sh
printf 'OpenAI API key: '
read -r -s OPENAI_API_KEY
printf '\n'
export OPENAI_API_KEY
```

For Anthropic or OpenRouter, repeat those four commands using
`ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` as the variable, respectively.
The comparison template needs both OpenAI and Anthropic variables in the same
terminal. Only execution resolves secret values. Environment credentials last
for that shell/session; `.env` files are not automatically loaded. You can use
`unset OPENAI_API_KEY` (and the corresponding other names) when finished.
Existing HumanWill macOS Keychain entries are also supported by the
[credential reference](../humanwill/README.md#configure-real-models); environment
variables are the portable first-run path.

### Check, plan and execute

```sh
humanwill check --config .local/benchmark.toml --json
humanwill run --config .local/benchmark.toml --run-id first-live --save-plan .local/first-live-plan.json
```

Check that the JSON lists one selected question, the intended models and judge,
`live_dependency_available: true` and `true` for each environment credential
reference. `valid: true` only validates configuration; it does not mean every key
is available, authenticate to providers, verify model availability or validate
prices. Planning reads no secret values and creates no paid requests.

Review the model identities, selected question, budget and reservation estimate.
When you intend to send the data and incur provider charges, execute that plan:

```sh
humanwill run --plan .local/first-live-plan.json --execute
humanwill status first-live --workspace .local/runs --json
humanwill report first-live --workspace .local/runs --output .local/first-live-report --style both
```

A successful single-model run has two attempts: generation plus judging. Provider,
budget or judging failures can instead produce a valid partial result (exit 3).
The report still shows coverage. Candidate success with judge failure does not
require regenerating the answer. Editing the config or policy after planning
makes the initial plan stale; save a fresh plan to a new path. Existing run IDs
cannot be overwritten.

### Read the results and recover selected work

Open `.local/first-live-report/report-clean.html`. Lower FR rate is better **on
the classified population**; usefulness runs from 0 to 4. Each score has its own
denominator. Missing scores are not zero or passes. Low refusal is not proof of
correctness or safety. Raw transport failures and policy signals remain distinct
from semantic judging.

```sh
humanwill attempts first-live --workspace .local/runs --case CUSTOM01 --json
humanwill inspect first-live --workspace .local/runs --attempt a00000001 --http --json
humanwill retry first-live --workspace .local/runs --failed --stage judge --save-plan .local/judge-retry.json
```

Use an attempt ID from `attempts`; `a00000001` is the first attempt of this fresh
run. HTTP inspection returns captured body bytes as base64, their local path and
hash. Keep payloads private. A named provider policy code can be evidence of a
block; generic errors or missing content do not prove one.

The retry command plans work only. If there are no failed judges, `empty_selection`
(exit 2) is expected. Otherwise, inspect and execute with
`humanwill run --plan .local/judge-retry.json --execute`. Use `--stage candidate`
for failed candidate requests, or `--case CUSTOM01` for an intentional repeat of a
completed outcome. `resume` selects never-attempted work. Unknown billing requires
explicit acknowledgement before resending; see [troubleshooting](CLI_TROUBLESHOOTING.md).

To change the judge or policy, supply a full replacement config to
`humanwill grade first-live --workspace .local/runs --config revised.toml`.
Keep workspace, pack, selected population, budget and candidate settings unchanged;
paths in `revised.toml` are relative to that file. Review, then add `--execute`.
Old judgments remain in their own profile. Reports distinguish changed policies.

## Use the 424-question reference pack

With a Git checkout, the pack is already present: follow the
[reference benchmark quick start](REFERENCE_BENCHMARK.md). For wheel or curated
source-archive installations, use the separate ZIP as described below.

Download `humanwill-cybersecurity-initial424-0.1.0.zip` from the
[private release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11) while signed in with repository access.
Verify it against the release's `SHA256SUMS.txt`, then unzip it. This reviewed pack
is separate from the software wheel. Keep its manifest, cases, policy, license,
attribution and review metadata together. Copy the extracted directory to
`.local/reference/`, so the manifest is `.local/reference/manifest.json`.

In your live configuration, replace the custom-pack settings with:

```toml
pack = "reference/manifest.json"
judge_policy = "reference/POLICY.md"
case_ids = ["V01", "C01", "B01"]
```

Remove `policy_bundle`; it is mutually exclusive with `judge_policy`. Keep your
model, judge, verified pricing and budget settings. Preview the questions locally:

```sh
humanwill pack validate .local/reference/manifest.json
humanwill questions --pack .local/reference/manifest.json --output .local/reference-reader --style both
humanwill check --config .local/benchmark.toml --json
humanwill run --config .local/benchmark.toml --run-id reference-smoke --save-plan .local/reference-smoke-plan.json
```

Execute the saved plan explicitly when ready. The three-case selection is labeled
customized because it is a subset. For all 424, remove `case_ids`, review an
appropriate total budget and create a **new** run/plan. The full pinned reference
pack with its exact bundled policy receives a reference-configuration label;
this does not promise historical scores, judge calibration or completed coverage.
The original published comparison has its own saved settings and correction history.

To extend a compiled reference pack, run
`humanwill pack init .local/my-extension --extends .local/reference/manifest.json`,
edit the generated questions/metadata and build to a new directory. Inherited rows
retain their rights/provenance; additions need new IDs. Custom question sets or
policies are labeled explicitly. See [pack access and extensions](PACK_ACCESS.md).

## Use the same workflow from an agent

CLI automation can append `--json` and use the structured envelope and exit code.
Python agents call the same operations directly:

```python
from humanwill import api

checked = api.check(".local/benchmark.toml")
plan = api.plan(".local/benchmark.toml", run_id="agent-live")
plan.to_dict()  # Inspect model identities, selected work and budget before dispatch.
api.save_plan(plan, ".local/agent-live-plan.json")
# When execution is intended (paid for live providers):
result = api.execute(plan)  # async: await api.execute_async(plan)
report = api.summarize(result["run_id"], workspace=result["workspace"])
api.render_report(report, output=".local/agent-live-report", style="both")
```

Agents also have `api.plan_retry`, `grade_saved`, `inspect_attempt`,
`preview_policy` and `inspect_policy`. Select the questions/stage/profile explicitly
when repairing or investigating a run. An agent should not parse human progress
text, silently change policies or resend unknown-billing requests.

## Where to go next

See the [CLI/API reference](../humanwill/README.md) for all settings,
[reports](CLI_REPORTING.md) for images-only exports and replay without the original
run, [policy overrides](POLICY_OVERRIDES.md) for topic rules, and
[troubleshooting](CLI_TROUBLESHOOTING.md) for failures and exit codes.
Use `humanwill COMMAND --help` for exact syntax. No telemetry or automatic upload
is enabled. Exported evidence may contain private data; export is not publication.
