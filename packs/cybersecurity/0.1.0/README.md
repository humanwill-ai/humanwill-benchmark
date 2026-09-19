# HumanWill Cybersecurity Benchmark — initial424

Question version **0.1.0** · delivery **0.1.0** · 424 questions.

This assistance-focused challenge set covers vulnerability validation (81),
source-code security (84), binary investigation (80), network investigation (89),
and filesystem/artifact investigation (90). All original question IDs, messages,
supplied evidence and provenance are preserved. False refusal and usefulness are
scored separately; this pack does not measure harmful compliance or overall safety.

## Install and run

Download the framework wheel and this pack from the same GitHub release. The
repository and its release assets currently require authorized private access:
https://github.com/humanwill-ai/humanwill-evals/releases/tag/v0.1.0a10

Use Python 3.11–3.14 on macOS or Linux. From your download directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './humanwill_evals-0.1.0a10-py3-none-any.whl[live,reports]'
unzip humanwill-cybersecurity-initial424-0.1.0.zip
cd humanwill-cybersecurity-initial424-0.1.0
humanwill pack validate manifest.json
cp benchmark.example.toml benchmark.toml
```

Edit `benchmark.toml`: fill exact candidate/judge model IDs, current verified
prices, credential references and budget. Supply API keys through the referenced
environment variables or supported Keychain integration; never put keys in TOML.
The example selects three questions initially; remove `case_ids` for all 424.

```sh
humanwill check --config benchmark.toml
humanwill run --config benchmark.toml --save-plan .local/run-plan.json
humanwill run --plan .local/run-plan.json --execute
```

Execution sends selected questions to your candidate provider and evidence to
your judge provider. Planning and validation make no model calls. Use the source
archive's `docs/FIRST_RUN.md` for provider templates, retry and raw-response
inspection, reports, both image styles and HTML question export. Human CLI users
and agents use the same operation API.

To extend this pack, run `humanwill pack init .local/my-extension --extends
manifest.json`, edit the generated questions, then use `humanwill pack build`.
The extension pins its parent and preserves retained records and attribution.
Use `humanwill policy init` for explicit domain/topic judging-policy overrides.

## Review and interpretation

The owner completed and accepted the internal review on 2026-09-19: all 424
questions passed rights, privacy, cybersecurity release and evaluation-scope
checks, and the exact bundled POLICY.md was approved. Expertise is self-declared;
this is not an independently verified external audit or certification. The
private completed review is represented by its hash in REVIEW_STATUS.json.

REVIEWED_MANIFEST.json preserves the approved candidate's manifest. Delivery
changes update its version/review status and supporting instructions only;
cases.jsonl and POLICY.md are byte-identical to those reviewed. Original frozen
provenance retains its historical metadata, including earlier license status.
CHECKSUMS.json binds every delivery file; hashes provide integrity, not identity
authentication. Personal review details and model responses are not included.

POLICY.md is the reference FR/U policy, not a promise to reproduce historical
judge requests or model results. Native-block scoring is optional and explicitly
versioned in the framework; enabling it creates a distinct policy profile.
Missing answers and uncertainty retain separate coverage and denominators.
Authorization and justified limits require contextual assessment. This is a
selected challenge set, including 324 cases discovered through one model's
blocking behavior, rather than a random sample of everyday requests. No
contamination-free, unrestricted-compliance or overall-safety claim is made.

## License and attribution

HumanWill's licensable rights in these questions, policy and pack-specific
supporting materials use **CC BY 4.0**. Credit **HumanWill — https://humanwill.ai**,
retain notices and identify modifications. See LICENSE.md and ATTRIBUTION.md.
No additional rights in third-party or unprotected material are created. The
framework is separately licensed; see its LICENSE and LICENSING.md.

Suggested citation: HumanWill Cybersecurity Benchmark, initial424, question and
delivery version 0.1.0, HumanWill, https://humanwill.ai, CC BY 4.0.
