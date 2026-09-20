# HumanWill Benchmark

**Measuring harmful refusals in AI models**

HumanWill measures whether AI models provide useful assistance on legitimate
cybersecurity tasks. It measures **false refusal** and **answer usefulness**
separately: willingness to answer does not establish correctness, and an incomplete
answer is not automatically a refusal.

## Read the benchmark report

[**Download the full report: When security AI withholds help (PDF)**](https://raw.githubusercontent.com/humanwill-ai/humanwill-benchmark/main/reports/cybersecurity/v0.1.1/humanwill-cybersecurity-report-v0.1.1.pdf)

**13 model configurations, 424 selected cybersecurity scenarios.** Our first
report compares false refusals and answer usefulness, with methodology, coverage
gaps and tested settings. Results v0.1.1, frozen **15 September 2026**.

[**Explore the interactive chart on Hugging Face →**](https://huggingface.co/spaces/humanwill-ai/cybersecurity-benchmark)

Click the preview below to open the interactive chart, then hover over a model's
bar to see its false-refusal rates across the five cybersecurity topics.

[![False-refusal rates across 13 model configurations on 424 selected cybersecurity scenarios; lower is better. Frozen 15 September 2026.](https://raw.githubusercontent.com/humanwill-ai/humanwill-benchmark/main/reports/cybersecurity/v0.1.1/refusal-columns-spotlight.png)](https://huggingface.co/spaces/humanwill-ai/cybersecurity-benchmark)

These are challenge-set results, not everyday refusal rates or an overall safety
score. Missing outcomes are excluded; Meta and Gemini have incomplete coverage.
[Report details, current question access and CC BY 4.0 attribution](https://github.com/humanwill-ai/humanwill-benchmark/tree/main/reports/cybersecurity/v0.1.1).

## Use HumanWill

Use it to compare model/provider configurations, investigate failed or blocked
responses, and evaluate questions specific to your work. Humans use a command-line
interface; agents and Python applications use the same operation API. Runs retain
their inputs, attempts and judging policies so you can investigate a result or
regrade saved answers without rerunning the candidate model.

The reference benchmark contains **424 cybersecurity questions** covering
vulnerability validation, source-code security, binary investigation, network
investigation, and filesystem/artifact investigation. It is a selected challenge
set, not an estimate of everyday refusal rates. You can also author your own pack,
extend an existing compiled pack, and customize judging criteria by topic.

**GitHub alpha `0.1.0a11`.** Download the framework wheel, curated source archive
and approved 424-question pack from the [GitHub release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11)
or clone this repository, which includes the full reference pack. Distribution
is through GitHub; PyPI is deferred. Questions and bundled policy/materials use
CC BY 4.0; their internal owner review is complete. The framework uses Apache 2.0 and the demo
questions use CC BY 4.0; see [license scope](LICENSING.md). See
[pack access](docs/PACK_ACCESS.md) and [release status](docs/CLI_RELEASE.md).

Cloning the repository or downloading GitHub's **Code → Download ZIP** includes
all 424 questions. The wheel and curated `humanwill_evals-…tar.gz` software archive
require the separate question-pack ZIP. See the
[reference quick start](docs/REFERENCE_BENCHMARK.md).

## Try the offline demo

Use Python 3.11–3.14 on macOS or Linux. Clone the repository, then install the CLI plus live/report extras:

```sh
git clone https://github.com/humanwill-ai/humanwill-benchmark.git
cd humanwill-benchmark
```

From the checkout, or the extracted curated source archive:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[live,reports]'
humanwill --version
humanwill init demo
humanwill check --config demo/benchmark.toml
humanwill run --config demo/benchmark.toml --run-id demo-01 --execute
humanwill report demo-01 --workspace demo/.local/humanwill-runs --output .local/demo-report --style both
```

The demo needs no API key and makes no model calls. Installation may download
dependencies. Expect **3 questions, 6 attempts, complete status and $0 accounted**.
Its scores are simulated, not model-performance results. Open
`.local/demo-report/report-clean.html` or `report-spotlight.html` in your browser;
the same folder contains PDFs, JSON/CSV results and configuration labels.

For wheel installation, a smaller base install, or help with an existing `demo`
directory, follow [Your first evaluation](docs/FIRST_RUN.md).

## Run the reference benchmark

The Git checkout includes the approved questions under `packs/cybersecurity/0.1.0/`.
The wheel and curated software source archive use the separate question-pack ZIP.
See the [reference benchmark quick start](docs/REFERENCE_BENCHMARK.md) for the
three-question first run, API keys, model/pricing/budget settings, and all 424 questions.
The questions and policy are unchanged from the accepted release.

## Run a real evaluation

Follow the [first-run guide](docs/FIRST_RUN.md#from-the-demo-to-a-live-evaluation)
to create a one-question pack, copy a complete provider template, configure API
keys, choose model IDs/prices/budget, and run your first live evaluation. It covers
OpenAI, Anthropic, OpenRouter and a two-model comparison with one shared judge.
No current model IDs or prices are assumed by the templates.

The workflow is a short command with a TOML configuration:

```sh
humanwill check --config .local/benchmark.toml --json
humanwill run --config .local/benchmark.toml --run-id first-live --save-plan .local/first-live-plan.json
humanwill run --plan .local/first-live-plan.json --execute
humanwill report first-live --workspace .local/runs --output .local/first-live-report --style both
```

`check` and planning make no provider calls. `--execute` sends questions to the
candidate provider and answers/evidence to the judge, and may incur charges.
The budget covers both stages. Inspect is not a dependency.

## Common workflows

| I want to… | Entry point |
| --- | --- |
| Compare models or provider routes | [Provider templates and comparison recipe](docs/FIRST_RUN.md#choose-a-provider-template); multiple `[[models]]` entries and one judge. |
| Retry only failed questions or judgments | `humanwill retry latest --workspace .local/runs --failed --stage judge`; add `--execute` after inspecting the plan. [Recovery guide](docs/CLI_TROUBLESHOOTING.md#recover-selected-work). |
| Continue work never attempted | `humanwill resume latest --workspace .local/runs`; explicit execution. |
| Investigate a possible policy block | `humanwill attempts` then `humanwill inspect ... --http --json`. [Raw evidence](humanwill/README.md#recover-and-investigate). |
| Rejudge saved answers under a new policy | `humanwill grade ... --config revised.toml`; old judgments remain separate. [Policy guide](docs/POLICY_OVERRIDES.md). |
| Add my own questions or extend a pack | `humanwill pack init`, `validate`, `build`. [Pack authoring](docs/PACK_ACCESS.md#local-question-authoring-and-extensions). |
| Adjust judging rules for a topic | `humanwill policy init`, `preview`, `inspect`. [Policy overrides](docs/POLICY_OVERRIDES.md). |
| Export a report, only images, or a question reader | `humanwill report`, `images`, `questions`. [Formats and both styles](docs/CLI_REPORTING.md). |
| Automate with an agent or Python | Structured CLI `--json` or the shared `humanwill.api`. [Agent workflow](docs/FIRST_RUN.md#use-the-same-workflow-from-an-agent). |

Reports distinguish reference, customized, simulated and unverified configurations.
Reference questions judged under a custom policy remain visibly customized. Missing
scores and independent FR/usefulness denominators stay visible in both styles.

## Scope and limitations

The current engine supports assistance-focused cybersecurity FR/usefulness and
the harmless demonstration. General company-policy compliance, additional domains,
harmful-compliance scoring and separate extension-subgroup metrics are future work.
No universal safety or “uncensored” score is produced. Usefulness is judged, not
verified by executing generated code. The engine makes tool-free model requests.

OpenAI, Anthropic and OpenRouter are supported through explicit configurations.
There are no hidden retries, provider fallbacks, automatic uploads or telemetry.
Local files retain private request/response evidence; only live execution transmits
evaluation data to configured providers. Budget reservations are conservative
estimates, not provider invoices or account-wide spending controls. Native Windows
and network/shared run storage are outside the supported alpha scope.

## Documentation and release readiness

- [First-run guide](docs/FIRST_RUN.md): installation through your first report.
- [CLI/API reference](humanwill/README.md): configuration and all operation examples.
- [Troubleshooting](docs/CLI_TROUBLESHOOTING.md): errors, recovery and private diagnostics.
- [Execution contracts](docs/CLI_EXECUTION.md): saved evidence, budgets and reproducibility.
- [Release validation](docs/CLI_RELEASE.md): support matrix and remaining gates.
- [Rights notice](release/NOTICE.md): separate software, question and asset rights.

The release's `VALIDATION.json` records the exact product commit, hosted checks
and artifact hashes. The internal question/policy review is complete; historical model
responses and personal review records are not part of this repository.

Contributors can run `python tools/release_check.py test` in a source checkout.
Install `.[live,reports]` plus test-only `pypdf` and use `--require-extras` for the
complete gate. Keep private questions, model responses and credentials out of
public issues. See [contribution guidance](release/CONTRIBUTING.md) for software
and question licensing requirements.
