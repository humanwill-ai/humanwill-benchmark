# Product alpha release validation

## Release and access

[HumanWill Benchmark v0.1.0a11](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11)
is the first release in the separate product repository. It provides a framework
wheel, curated software source archive, unchanged approved 424-question ZIP,
SHA256SUMS.txt and VALIDATION.json. Repository access is required while private.
The CLI is `humanwill`; the distribution is `humanwill-evals`.

The release's VALIDATION.json records the exact commit, hosted run URLs and
artifact hashes. Check that evidence rather than treating earlier research CI
as proof of this release. The repository and release remain private; no public
visibility change, PyPI upload or new paid model execution is part of this work.

Software uses Apache 2.0; demo and approved reference content use CC BY 4.0.
See [license scope](../LICENSING.md). The pack retains its internal owner review
with self-declared expertise, without an independently verified external audit.
All question, policy, attribution and review-summary bytes are preserved.

## Hosted validation

The standalone workflow builds and verifies wheel/sdist, runs the full synthetic
product suite without skips and exercises installed base/report CLI/API behavior
on macOS and Ubuntu with CPython 3.11–3.14. No provider credentials or paid requests
are used. The reference-pack workflow verifies the exact approved checksum
inventory, pack schema/provenance/count, pinned reference identity and policy,
and checks that the shipped reference template resolves against the real pack.
It emits only metadata, never question text or personal review details.

## Reproduce locally

Use a dedicated environment with `.[live,reports]`, `pypdf` and `build` installed:

```sh
python tools/release_check.py test --require-extras
python tools/check_reference_pack.py
python tools/release_check.py stage --output .local/release-candidate
cd .local/release-candidate
python -m build --outdir dist
python tools/release_check.py archive dist/*
python -m venv .local/base
.local/base/bin/python -m pip install --no-deps dist/*.whl
.local/base/bin/python -I tools/smoke_installed.py
```

The reference-pack check runs from the Git checkout; the pack is deliberately
excluded from the software wheel and curated sdist. The pack ZIP is a separate
asset. `release/files.txt` is the explicit software inventory. Its staged root
README comes from release/README.md with adjusted relative links. The stage receipt
records `publication_authorized: false`: building is not authorization to publish.
New stage destinations must be under `.local`, with no symlink components.
Archive checks reject unexpected/missing files, changed bytes or licenses, unsafe
paths and limited recognizable credential patterns. They are not comprehensive
secret detection or an independent security audit.

## Support and interpretation limits

Supported: local filesystems on macOS/Linux, Python 3.11–3.14, OpenAI/Anthropic/
OpenRouter through explicit configuration. Native Windows, shared/network run
storage and distributed/account-wide provider budgets are outside alpha scope.
Model availability and pricing are user-configured, not fixed promises.

Earlier bounded live checks exercised selected provider/judge pairs, including
judge-only recovery of fenced JSON. This release changes distribution/docs and
keeps the engine semantics; it makes no claim of newly retesting every route.
Synthetic checks cover native blocks, partial responses, failures, recovery,
accounting and independent score denominators. They do not establish judge
calibration, overall model safety or provider invoice accuracy.

## Public launch and subsequent work

The clean destination is prepared and validated while private. A later owner
instruction can authorize making only this product repository public; the
research repository remains private. At that point update access wording and
verify unauthenticated installation/download links. PyPI can follow separately.

Recommended: a small external-user onboarding pilot and a representative
human-versus-judge comparison. Deferred: full company-policy compliance, separate
reference/custom-question subgroup metrics, arbitrary third-party imports,
native Windows, automatic legacy migration, provider invoice reconciliation and
automatic release of unknown billing holds. None is implied by a green CI run.
