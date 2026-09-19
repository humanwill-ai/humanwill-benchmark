# Working on HumanWill Benchmark

Human CLI usage and agent-driven execution are equal design pillars. Keep the
CLI thin over the shared Python operation API, structured outputs, selective
retries, saved policies and exact raw-response inspection.

Before changes, inspect Git status and read docs/DECISIONS.md, docs/HANDOFF.md
and the relevant CLI execution/reporting/pack contract. Preserve user work.
Keep false refusal and usefulness independent. Harmful-compliance scoring is
not implemented here; never describe FR as overall safety or an uncensored score.
Do not use keyword matching as the primary semantic refusal judge.

The approved packs/cybersecurity/0.1.0 delivery is immutable. Preserve IDs,
provenance, question/policy bytes, checksums and review boundaries. New versions
need explicit review; never fabricate expert approval. Cybersecurity contributions
need appropriate expert review; biosecurity needs stricter handling.

Software/docs use Apache 2.0; demo and reference content use CC BY 4.0 within
LICENSING.md's scope. Preserve HumanWill / https://humanwill.ai attribution.
Keep credentials, private submissions, model answers and runs under ignored local
paths. No automatic telemetry or uploads. Add meaningful tests for contracts,
adapters, scoring, provenance, duplicate handling and metric denominators.

Run the offline release gate and reference-pack check as documented in
docs/CLI_RELEASE.md. Record decisions and substantial handoffs. Never commit,
push, upload, publish or change visibility without the user's explicit permission.
The owner selected GitHub-only public distribution, with explicit final
confirmation required before changing this product repository from private to
public. Preparation and private commit/push are authorized; do not infer that
confirmation from passing tests. Research stays private. PyPI/TestPyPI are deferred.
See docs/HANDOFF.md for the current launch state.
