# Reports, images and question readers

Phase 5, package `0.1.0a3`, implements the same operations for CLI users and agents.
Exports read saved data; they never generate answers, call a judge, resolve
credentials or upload anything. Historical publication builders and editions
remain unchanged.

Version `0.1.0a7` adds automatic reference/customized configuration labels across
every result-report format and both image styles. No extra CLI flags are needed.

## Install and export

From the source checkout, install the visual dependencies in a separate environment:

```sh
python -m pip install '.[reports]'
# Use '.[live,reports]' when this environment also executes live runs.
```

The base package supports JSON/CSV results and HTML question readers without
optional dependencies. HTML/PDF result reports and PNG/SVG charts need the
`reports` extra: Matplotlib, ReportLab and Pillow. Neither Inspect nor a browser
is required to generate them. Poppler is used for development PDF validation,
not by the installed renderer.

For the run created by the [quickstart](../humanwill/README.md):

```sh
humanwill report demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/report-01 --style both
humanwill images demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/images-01 --style both --format png,svg
humanwill questions demo-01 --workspace demo/.local/humanwill-runs --output .local/exports/questions-01 --style both
```

Use `--style clean` for the light presentation, `--style spotlight` for the navy,
teal and gold presentation, or `--style both`. Clean is the default. Reports default
to `--format html,pdf`; images default to PNG. Reports also accept `json,csv`.
Every report bundle includes `results.json` and `results.csv` as audit sidecars,
even when only HTML, PDF, JSON or CSV is requested. Images include `results.json`
and `chart-data.json` with every plotted value and its denominator.
Both report and image bundles include `result-context.json`, with the overall
label, question/selection provenance and each profile's policy classification.

## Reference and customized configuration labels

Labels are derived from immutable saved inputs, not a pack's display name or a
user-supplied claim. Current reference recognition pins the original initial424
snapshot and its owner-selected public-material rc2, plus the exact bundled
`POLICY.md`. Hash pins contain no question text. Unrecognized pack versions need
an explicit reviewed registry update before they can receive a reference label.

| Label | Meaning |
| --- | --- |
| Reference configuration | Pinned reference question pack, its full selected population, and exact bundled reference policy. |
| Customized configuration | Different/unrecognized pack, selected subset, different policy, or a combination; reasons are shown per profile. |
| Simulation | A candidate or judge uses the deterministic mock provider; no model-performance claim. |
| Unverified configuration | A legacy aggregate snapshot lacks sufficient saved pack provenance to verify reference status. |
| Mixed configurations | The report contains profiles with different classifications; each profile keeps its own label and policy hash. |

Question provenance, full/subset selection and judging policy are separate axes.
For example, reference questions with a company topic override receive
**Customized configuration / Custom policy**, while still identifying the
questions as reference questions. An extension remains a customized question pack,
even when it preserves all 424 inherited questions. A familiar pack name alone
cannot earn a reference label. The new named-rule `humanwill-fr-u/1` policy base
has different instructions from the historical bundled text, so it is a custom
policy relative to this reference configuration, even without overrides.

Reference labels describe configuration, not official certification, judge
calibration, reproduction of historical corrections or comparability across
different model/judge settings. Incomplete runs keep their status and coverage;
reference configuration does not mean completed execution. No metric, selected
population, denominator or historical result is changed by labeling. Aggregates
over an extension remain aggregates over that combined custom population; labels
do not manufacture a separate reference-subset score.

HTML reports show an explanation panel and labels beside each profile. Every PDF
page and standalone PNG/SVG chart carries a configuration banner; mixed charts
also label each plotted profile. CSV repeats classification, question/selection
status and policy/pack hashes on every row. JSON and chart audit data retain the
same machine-readable context. Export manifests and CLI/API export results expose
that context too. Custom titles cannot remove these labels. Question readers
contain no model results and remain neutral exact-content exports.

New summaries use `humanwill.report-data/2`, with context and per-profile
assessment fields bound by the report hash. `humanwill.chart-data/2` adds the same
classification to image audits. Existing `report-data/1` snapshots remain readable
and their authoritative `results.json` bytes/hash stay unchanged when re-exported.
Their new rendered views, CSV and `result-context.json` explicitly show unverified
configuration (or simulation); missing provenance is never guessed from a name.
Previously generated files and frozen historical publication editions are not
rewritten. Regenerate exports to see the new labels.

All destinations must be **new directories**. Existing paths, symlinks and exports
inside a run directory are rejected. A manifest records each file's hash and size;
files/directories use POSIX modes 0600/0700. The manifest is written last. A disk
failure can leave an incomplete directory without a completion manifest; select
a new destination after investigating it. Nothing is overwritten automatically.

## Freeze a selection, render it repeatedly

```sh
humanwill report demo-01 --workspace demo/.local/humanwill-runs --selection first --format json,csv --output .local/exports/first-results
humanwill report --results .local/exports/first-results/results.json --output .local/exports/first-report --style both
humanwill images --results .local/exports/first-results/results.json --output .local/exports/first-images --style spotlight
```

`--selection recovery` is the default and uses the same chronological selection
as `status`. `first` retains first-attempt results. Repeat `--profile HASH` to
restrict a run report to explicit candidate/judge configuration profiles. These
filters retain the original question population. A snapshot already fixes its
selection: `--results` cannot be combined with a run, workspace, profile filters
or a different selection. `latest` requires an explicit workspace as elsewhere.

`humanwill.report-data/1` is an immutable aggregate snapshot with a report digest,
source run/plan/result/selection digests, pack identity and source licensing,
separate profile settings, family/overall metrics and interpretation caveats.
Loading verifies its digest, shape and denominator arithmetic. The digest detects
changes; it is not a signature or a claim of independent audit. Rendering a saved
snapshot needs neither its original run nor its private question pack.

FR and usefulness retain independent scored populations; missing scores are null,
never zero or passes. Tables and figures show scored/selected coverage. Per-profile
settings also retain selected candidate/judge state counts and service signals,
so scored partial answers remain visible without exposing their text. Signals
are transport evidence, not semantic FR labels. Candidate
or judge setting changes remain separate profiles. Mock candidates or judges are
visibly marked as simulation. There is no combined willingness/safety score,
invented harmful-compliance denominator, inferred calibration or generated narrative.
The current report schema covers the assistance-focused FR/U execution contract.

Both themes consume the same numbers and fixed metric scales. Charts paginate at
eight profiles and six families, keeping one-model and larger comparisons usable.
CSV has explicit overall/family scopes and empty cells for undefined metrics.
Report data contains no prompt text, answers, raw HTTP bodies or credential
references. Investigate those separately through `attempts` and `inspect --http`.

Version 1 and 2 HumanWill runs are supported. Older campaign publication JSON is
not this snapshot schema: keep using its existing frozen publication builder.
No legacy correction overlay or campaign is silently imported or rejudged.

## Export the questions as HTML

```sh
humanwill questions --pack .local/packs/cybersecurity-initial-0.1.0/manifest.json --output .local/reviews/questions-01 --style both
humanwill questions --pack path/to/manifest.json --family C --case C01 --output .local/reviews/question-C01
```

Choose a pack manifest or a saved run. A run uses its frozen selected questions,
even if the original pack file has disappeared. Repeat `--case` and `--family` to
select subsets; together they intersect. Unknown IDs, duplicates and empty
selections fail explicitly. Question exports must remain inside a `.local`
directory because export does not grant question redistribution rights.

The self-contained reader works offline with family tabs, full-pack search,
exact-ID lookup, keyboard navigation and question links such as `#question-C01`.
It preserves Unicode, original wording, system instructions, source identifiers
and full provenance. Structured supplied evidence expands separately from the
question, with the exact original user JSON also available. `questions.json`
preserves the complete original selected records and remains authoritative for
control characters browsers cannot display. With JavaScript disabled, all
questions are readable. No model-result annotations, remote fonts or telemetry
are included. Source licensing and review status remain explicit.

## Agent/Python operations

```python
from humanwill import api

report = api.summarize("demo-01", workspace="demo/.local/humanwill-runs",
                       selection="recovery")
report.to_dict()  # independent copy; inspect metrics and selection before rendering
api.render_report(report, output=".local/exports/agent-report", style="both")
api.render_images(report, output=".local/exports/agent-images",
                  style="spotlight", formats=("png", "svg"))
saved = api.load_report(".local/exports/agent-report/results.json")
api.export_questions(run_id="demo-01", workspace="demo/.local/humanwill-runs",
                     case_ids=("D01",), output=".local/exports/agent-questions")
```

`render_report` and `export_questions` also accept `title=`; the CLI exposes
`--title`. API functions return structured file inventories without printing.
CLI `--json` uses the existing `humanwill.cli/1` envelope and exit codes. An export
can succeed for an incomplete run: its source status and missing coverage remain
visible, and successful file generation is not a claim that execution completed.

## Validation and release boundary

Harmless automated fixtures cover CLI/API equality, snapshot replay, version 1
compatibility, first/recovery/profile selection, independent denominators, nulls,
invalid schemas, duplicates, safe destinations, exact question messages and
provenance, HTML escaping, both themes and actual PDF/PNG/SVG output. Visual tests
need the reports extra; optional pypdf adds extracted PDF text assertions.
Local browser checks also verify search, tabs, deep links, responsive layouts and
exact delivered messages for all 424 private questions without printing them.

Report generation leaves historical results unchanged and performs no uploads or
paid model calls. See [release tooling and validation](CLI_RELEASE.md) for
exact-commit hosted checks. Software/demo licensing and internal
owner review of the separately distributed question pack are complete. Distribution is through
GitHub releases. Model responses and local diagnostics remain private to the user.
