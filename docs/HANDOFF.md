# Product handoff

## GitHub public launch completed — 2026-09-19

Owner explicitly confirmed the visibility change. HumanWill Benchmark is now
public at https://github.com/humanwill-ai/humanwill-benchmark.
The research repository humanwill-ai/humanwill-evals remains private. PyPI and
TestPyPI are deferred; the saved plan remains docs/PYPI_PLAN.md in the product.

Switched the exact approved product repository (ID 1377161784) at preparation
commit c53924abd367bfcd6e14a59609aa7b89f18c0672 after rechecking refs, successful
CI, release identity/body and every asset digest. The approved preparation passed
all eight standalone matrix jobs (35451242825) and the reference-pack job
(35451242879). Preflight inspected 106 reachable blobs and eight Actions runs.

Post-switch verification used no authentication: repository/release pages,
a fresh Git clone with credential helpers disabled, GitHub's source ZIP and all
five release asset downloads succeeded. Both clone and source ZIP include all
10 unchanged reference-pack files. Every release download matches its SHA-256
and size; the installed CLI validated all 424 questions from the clone and ZIP.
Anonymous research-repository API access returns 404; authenticated metadata
confirms it is still private. No paid model requests or PyPI uploads occurred.

Release v0.1.0a11, its tag and five artifact bytes remain unchanged. Its embedded
private-access language and private_repository metadata describe its original
issuance; maintained guides and the release page describe current GitHub access.
The CLI, engine, approved questions, judging policy and licenses are unchanged.
Local confirmation, switch and anonymous-download receipts live under the
product checkout's ignored .local/github-launch/. This status commit records
completion; use Actions for validation of later commits.

Next optional work: external-user onboarding pilot and human-versus-judge
calibration. Keep future private research, model responses and submissions out
of the public product repo. GitHub is the only current distribution channel.

## GitHub-only public launch prepared — awaiting owner confirmation

The owner selected GitHub-only distribution, deferred PyPI and explicitly asked
for confirmation immediately before the visibility switch. Product repository
humanwill-ai/humanwill-benchmark remains private. Do not change visibility until
that confirmation arrives; research humanwill-ai/humanwill-evals stays private.

Updated current README, installation/reference/pack/release guides, CLI docs and
rights notice for GitHub distribution. Retained the six-step future PyPI plan in
docs/PYPI_PLAN.md. The CLI, engine, 424-question pack, policy and licenses are
unchanged. Existing release/tag v0.1.0a11 and its five assets stay immutable;
embedded private-access wording records their original issuance. Current release
page links to maintained guides instead of requiring old research-repo access.

Preflight passed: the approved 424-question pack and policy hashes match; all
121 current local documentation links resolve. Reviewed all 90 reachable blobs
from the existing two-commit product history, the five release asset hashes and
all six existing Actions runs' downloadable logs. No unexpected repository paths,
recognized credential patterns or full reference-question messages were found
in logs. There are no issues, PRs, Pages site or uploaded Actions artifacts.
This is a scoped content/integrity check, not comprehensive security certification.
The preparation commit must pass both hosted workflows before confirmation.
Receipts remain under ignored .local/github-launch.
After confirmation: recheck the approved commit/refs and release assets, change
only this product repository to public, then verify anonymous source/release
access and downloads; record completion. No PyPI/TestPyPI upload or paid model run.

## Product private alpha v0.1.0a11 complete — 2026-09-19

Owner approved steps 1–4 and selected HumanWill Benchmark with subtitle
“Measuring harmful refusals in AI models”. Created and pushed a fresh private
repository: https://github.com/humanwill-ai/humanwill-benchmark
Release:
https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11
Source/tag commit: 9c07432302c153108e48799d7dd582a4909fcaeb.

The initial commit contains 79 selected software/docs files and the unchanged
10-file approved reference delivery under packs/cybersecurity/0.1.0. No research
Git history, personal reviewer records, historical model responses, credentials
or private experiments were copied. Approved questions, policy, provenance,
review hashes and all delivery bytes remain unchanged. Framework Apache 2.0 and
question CC BY 4.0 scope/attribution are preserved. CLI/import remain humanwill;
distribution remains humanwill-evals. No engine/scoring behavior changes.

Updated product README, download/install links, package URLs, reference-run guide
and example config. The immutable pack's historical README remains intact;
current instructions live in docs/REFERENCE_BENCHMARK.md. New checksum/provenance
CI also verifies the reference template without credentials or provider calls.

Validation: 144 local tests, zero skips; all eight macOS/Linux × Python 3.11–3.14
hosted jobs passed (35444589299), plus reference-pack job (35444589220). Local
wheel/sdist source checks, base and report installed smoke, both styles, CLI/API
parity, 117 local Markdown links and fresh GitHub-clone reference validation pass.
All five release assets were downloaded and checked byte-for-byte; installed CLI
validated 424 questions from the downloaded ZIP. Source/tag and released archives
stay immutable; this handoff records completion after validation.

Both GitHub repositories remain private. No PyPI, public launch or paid model
calls. Next: public visibility only after an explicit owner instruction, followed
by checking unauthenticated links and updating access wording. External-user
onboarding and human-versus-judge calibration remain recommended follow-ups;
company-policy compliance, subgroup metrics and Windows remain deferred.

## Initial product release preparation — 2026-09-19

Prepared HumanWill Benchmark with the owner-selected subtitle, fresh product
history, updated installation/download links, version 0.1.0a11, and unchanged
approved 424-question delivery. Agent and CLI execution semantics are unchanged.
The current validation evidence belongs to the exact release commit and is saved
as VALIDATION.json with the release. Check GitHub Actions for subsequent commits.

The repository stays private. Public launch requires a later explicit owner
instruction. PyPI is optional and not configured. External-user onboarding and
representative human-versus-judge calibration remain recommended follow-up work.
Company-policy compliance, reference/custom subgroup metrics, broader imports,
native Windows and invoice reconciliation remain outside this alpha.
