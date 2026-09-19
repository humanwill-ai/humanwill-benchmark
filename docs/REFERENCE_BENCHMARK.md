# Run the HumanWill reference benchmark

The reference pack contains 424 cybersecurity questions. False refusal and
usefulness are scored separately. These are selected challenge questions, not
a random sample of everyday usage or a measure of overall model safety.

## Start with three questions

Install the CLI using [the first-run guide](FIRST_RUN.md). From the Git checkout:

```sh
humanwill pack validate packs/cybersecurity/0.1.0/manifest.json --json
mkdir -p .local
cp examples/reference.toml .local/reference.toml
```

For a wheel or curated source archive, download the question-pack ZIP from the
[same release](https://github.com/humanwill-ai/humanwill-benchmark/releases/tag/v0.1.0a11),
verify `SHA256SUMS.txt`, unzip it, and set `pack` and `judge_policy` in the copied
configuration to the extracted manifest and POLICY.md. Paths are relative to the
configuration file, not your shell directory. The ZIP's original README preserves
historical delivery instructions; this guide supplies the current repository links.

Edit `.local/reference.toml`: choose exact candidate and judge model IDs, verified
prices and a positive budget. Check both models' input limits against the question
and answer sizes. Supply keys through the configured environment references;
never write API keys in TOML. The starter uses `env:OPENAI_API_KEY` for both stages.
Other providers and separate judge credentials are supported; see
[provider templates](FIRST_RUN.md#choose-a-provider-template).

```sh
humanwill check --config .local/reference.toml --json
humanwill run --config .local/reference.toml --run-id reference-smoke --save-plan .local/reference-smoke-plan.json
humanwill run --plan .local/reference-smoke-plan.json --execute
humanwill report reference-smoke --workspace .local/runs --output .local/reference-report --style both
```

Check and planning are offline. Execution sends questions to the candidate
provider and answers/evidence to the judge provider and may incur charges.
The shared budget covers both stages. A three-question selection is labeled
customized because it uses a subset of the reference pack.

## Run all 424

Remove `case_ids`, review model limits and total budget, and create a new run/plan
with a new run ID. All questions with the exact bundled policy have a reference
configuration label. This label identifies inputs; it does not reproduce previous
model results, prove judge calibration or guarantee complete judged coverage.
Native block scoring is optional and creates a distinct policy profile.

## Inspect, retry, customize and export

Human CLI users and agents use the same operations and structured `--json`
outputs. See [agent workflow](FIRST_RUN.md#use-the-same-workflow-from-an-agent),
[selective retries and raw HTTP](CLI_TROUBLESHOOTING.md),
[question extensions](PACK_ACCESS.md#local-question-authoring-and-extensions),
and [domain/topic judging policies](POLICY_OVERRIDES.md).

```sh
humanwill questions --pack packs/cybersecurity/0.1.0/manifest.json --output .local/question-reader --style both
humanwill images reference-smoke --workspace .local/runs --output .local/reference-images --style both
```

Reports and images support clean and spotlight styles; the HTML reader is for
local question inspection. Saved inputs, failed attempts, raw responses and old
judging profiles remain inspectable. No automatic model retries or uploads occur.

## License and review

Question/policy content uses CC BY 4.0 for HumanWill's licensable rights, with
HumanWill / https://humanwill.ai attribution. The approved pack and its checksum
inventory are unchanged from delivery 0.1.0. Internal owner review used
self-declared expertise; no independent external audit is claimed. Personal review
records and historical model answers are excluded. See [pack access](PACK_ACCESS.md).
