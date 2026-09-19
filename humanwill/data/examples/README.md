# Live configuration starters

Copy one TOML file into your working `.local` directory as `benchmark.toml`.
Fill every blank model/pricing/route field and choose a positive total budget.
Unfilled templates deliberately fail validation; copying never authorizes a paid run.

- `openai.toml`: OpenAI candidate and judge.
- `anthropic.toml`: Anthropic candidate and judge.
- `openrouter.toml`: explicit OpenRouter routes for candidate and judge.
- `compare.toml`: OpenAI and Anthropic candidates with a shared OpenAI judge.

Default paths match the first-run guide: `my-pack-built/manifest.json`,
`my-policy/policy.toml`, `runs`, and case `CUSTOM01`. Paths resolve relative to the
copied TOML file. Change them for your own questions or reference-pack selection.
The configuration contains credential references, never key values. Inspect is
not required. Model availability, supported settings and rates must be checked by
the operator; these templates do not assert any current model or price.

After editing, run `humanwill check --config .local/benchmark.toml --json`, then
`humanwill run --config .local/benchmark.toml` to preview. Add `--execute` only when
you intend to send questions/answers to the configured providers and incur charges.
See `docs/FIRST_RUN.md` in the matching source archive for the full walkthrough.
