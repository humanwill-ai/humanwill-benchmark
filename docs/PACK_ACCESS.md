# Question packs and judge policies

For a complete installation-to-report walkthrough, including authoring a small
pack and configuring the separately downloaded reference pack, see
[Your first evaluation](FIRST_RUN.md).

The installable wheel includes three harmless demonstration questions. The
approved 424-question pack is also available in this Git repository under
`packs/cybersecurity/0.1.0/`, and as a separate ZIP in the
[product release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11).
Follow the
[reference benchmark quick start](REFERENCE_BENCHMARK.md).

The pack's accepted 0.1.0 delivery is preserved byte-for-byte, including its
historical README and review summary. Use the current quick start for this
repository's installation links. Model responses, personal review records and
the private research history are not distributed. Installing the software alone
does not reproduce a historical model comparison.

## Existing authorized local users

Point `pack` in TOML at your existing permitted `manifest.json`. The read-only
adapter recognizes `humanwill.frozen-message-pack/0.1.0`, checks source identities,
original message hashes, case and manifest digests, duplicate content and counts,
and retains provenance/licensing. Keep its entire directory tree together.
The adapter does not grant access, download data, convert licenses, rewrite the
frozen original or automatically apply historical scoring corrections.

Supply a reviewed `judge_policy` text file or explicit `policy_bundle` when using
a live judge; see [domain/topic overrides](POLICY_OVERRIDES.md). The engine
snapshots its bytes and appends the strict structured FR/U output contract. An
arbitrary policy or a reused model name does not establish the calibration of
the historical study. The policy, exact judge/model settings and dataset version
must accompany any benchmark claim. `grade` creates a separately identified
grading stream; it does not replace old judgments.

Start with a permitted small selection (`case_ids` in TOML), declared price bounds
and budget. Planning is offline; actual execution sends the selected messages to
the configured provider and sends answers/evidence to the configured judge.
Run only within the data permissions and execution scope you have established.

## Harmless fixtures and additional pack formats

The portable `humanwill.message-pack/1` contract is restricted to harmless
`domain=demonstration` fixtures and is exemplified by
`humanwill/data/demo/manifest.json` and `cases.jsonl`. For new harmless test fixtures, use original or properly licensed data, unique
source IDs, exact system/user messages and accurate source provenance. The manifest binds the JSONL bytes; each case binds the exact messages.
Use the validator, rather than removing or inventing provenance to satisfy it.
The demo's `domain=demonstration` is for simulations; do not relabel real benchmark
content as demonstration to bypass live semantic judging requirements.

See `humanwill/packs.py` for the strict field contract and `humanwill/sources.py`
for adapter dispatch. The v1/v2 engine currently measures assistance-focused FR/U;
new metrics and restricted domains require explicit adapters/contracts and review.
Local assistance-focused cybersecurity authoring and composition now use
`humanwill.question-pack/1`, described below. Arbitrary CSV, other domains and
third-party framework formats still require explicit adapters.
Imported benchmark questions keep their applicable rights and attribution.

## Review, licensing and delivery

On 2026-09-17 the owner selected the complete 424-question cybersecurity pack as
the intended public reference release, under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) for HumanWill's
licensable rights, with attribution to **HumanWill — https://humanwill.ai**.
The separate software decision is now Apache 2.0, with CC BY 4.0 for demo content
and distinct trademark boundaries; see [license scope](../LICENSING.md).

The approved delivery contains all 424 exact question messages, source provenance,
CC BY attribution, file hashes and a redacted review summary. The owner approved
all four review dimensions for all 424 questions,
the exact bundled policy, and the overall release recommendation on 2026-09-19.
This is an internal review with self-declared expertise, not an independently
verified external audit or a legal certification. Review acceptance is separate
from publication authorization. The
candidate preserves the frozen research pack and its historical
`unselected` metadata under each original record, while recording the current
question license separately. The same CC BY 4.0 terms now cover the HumanWill-authored
policy and supporting documents supplied in the question-pack bundle; framework
documentation and code remain outside that scope. The owner explicitly retained
the expert-review requirement. The local rc2 archive includes an exact-version
review template, review guide and example configuration. The completed record and
owner acceptance are retained privately with exact artifact hashes. The accepted delivery updates version/review metadata only, with exact cases and
policy preserved; REVIEW_STATUS.json and REVIEWED_MANIFEST.json record the binding.
Only the approved pack and redacted review summary are attached to the GitHub release. This is a disclosed challenge set, with no clean
held-out or contamination-free claim.

Suggested attribution: “Contains questions from the HumanWill Cybersecurity
Benchmark, version 0.1.0, by HumanWill (https://humanwill.ai), licensed under
CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Changes: [describe, or
none].” Citation in aggregate-only benchmark results is requested, not an added
license condition. The license permits commercial adaptation and does not ban
training or guarantee attribution for every use or resulting model.

`humanwill questions` produces a private, neutral HTML/JSON reader for local
review. It is not a publishing or licensing command. Historical aggregate-report
terms do not apply automatically to its underlying questions or model responses.


## Local question authoring and extensions

CLI users and agents share the same operations; none makes a model call:

| CLI | Python API |
| --- | --- |
| `humanwill pack init .local/my-pack` | `api.init_pack(".local/my-pack")` |
| `humanwill pack init .local/my-extension --extends PATH/manifest.json` | `api.init_pack(".local/my-extension", extends="PATH/manifest.json")` |
| `humanwill pack validate .local/my-pack/pack.toml` | `api.validate_pack(".local/my-pack/pack.toml")` |
| `humanwill pack build .local/my-pack/pack.toml --output .local/my-built-pack` | `api.build_pack(".local/my-pack/pack.toml", output=".local/my-built-pack")` |
| `humanwill pack validate .local/my-built-pack/manifest.json` | `api.validate_pack(".local/my-built-pack/manifest.json")` |

Add `--json` for a versioned, metadata-only response. Validation of a draft does
not create output. Init writes a harmless example: replace its authorship,
attribution and question before treating it as your evaluation. Both source and
build output creation require a new directory under `.local`; no overwrite,
symlink paths, traversal escape or writes inside immutable run directories.
An interrupted build may leave an incomplete directory without a final manifest;
use a new destination after inspecting it.

The source consists of `pack.toml` and `questions.jsonl`. TOML identifies the
pack/version, cybersecurity domain, attribution, review status and rights. Each
JSONL line supplies one question, for example:

```json
{"id":"ACME01","family":"C","messages":[{"role":"system","content":"Review only this synthetic configuration."},{"role":"user","content":"debug=false. Is debug enabled?"}],"provenance":{"source":"Acme internal scenarios","source_id":"ACME01","authorship":"Acme","license":"private; no redistribution grant","attribution":"Acme"},"evaluation":{"expected_behavior":"assist_within_supplied_scope","criteria":"State that debug is disabled, citing debug=false. Do not invent execution."}}
```

Evidence available to the tested model belongs in the messages, inline as text or
JSON. No external evidence files are silently loaded. Evaluation criteria go only
to the judge, inside the quoted evidence; they do not alter candidate instructions
or replace the configured judge policy. The first contract supports assistance
cases and FR/usefulness only. Refusal-required or ambiguous expected behaviors,
and harmful-compliance scoring are not implemented by these authoring commands.
Domain/topic judging-policy overrides are configured separately through
[policy bundles](POLICY_OVERRIDES.md), preserving question records and eligibility.
Case-specific criteria require appropriate judge
validation before performance claims.

For an extension, init records the parent manifest path and exact snapshot hash
in `[extends]`. Build refuses a changed parent until the author reviews and
explicitly updates that pin. It copies inherited records unchanged, appends the
local questions and applies the explicit `exclude = ["CASE_ID"]` list. Additions
cannot reuse a parent ID, including excluded IDs. Modified tasks need new IDs and
accurate source attribution; there is no implicit replacement or relabeling.
Unique IDs alone do not prove statistical independence.

The compiled manifest records the parent identity/hash, parent case hashes,
excluded IDs and added IDs. Cases retain their own rights and attribution;
setting a new top-level license never relicenses inherited questions. The
`ATTRIBUTION.md` companion collects per-question credit and license statements.
Exact message and source duplicates fail validation; normalized text overlap
produces a review warning without silently deleting cases. Broader semantic
near-duplicate detection remains a review task.

A compiled pack is self-contained: source drafts and parent directories may be
removed or moved without breaking execution, retries or saved-run inspection.
Use its `manifest.json` as `pack` in a version-2 run config. Cybersecurity packs
require real provider configurations and a semantic judge, even for harmless
custom questions; synthetic transport is a test seam, not a model score.
Planning remains offline and execution remains explicit.

The existing status/report records bind the new pack identity and selected
population. An extended pack measures that combined custom population; it is not
the unchanged HumanWill reference benchmark. Reports now label reference/customized
configurations and separately identify question provenance, selection and policy;
see [report labels](CLI_REPORTING.md#reference-and-customized-configuration-labels).
Separate reference/custom subgroup metrics remain subsequent work. To compare a reference subset today,
run it as a separately selected population with the same model/judge settings.
