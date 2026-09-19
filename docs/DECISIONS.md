# Product decisions

## P001 — Separate product repository, 2026-09-19

The owner selected `humanwill-ai/humanwill-benchmark`, product name HumanWill
Benchmark and subtitle **Measuring harmful refusals in AI models**. CLI executable
and Python import remain `humanwill`; distribution remains `humanwill-evals`.
The first product release is 0.1.0a11. This changes distribution and onboarding,
not model execution, scoring, saved-run contracts or reference question content.

Start with fresh Git history from the explicit standalone software selection,
plus the approved immutable 424-question delivery. Preserve Apache 2.0 software
and CC BY 4.0 question attribution. Private research history, personal reviews,
historical model responses and experiments are not copied. The research repo
remains private; this product repo also remains private pending explicit public
launch authorization. No PyPI publication or new paid model requests.

Software development now belongs here. Private research can install a pinned
released framework version in an isolated environment; historical research code
and frozen results remain intact. Avoid maintaining two competing engine copies.
CLI and agent API parity, inspectable raw evidence and selective retries remain
core design requirements. The wheel/curated sdist exclude the reference pack;
the Git checkout and separate unchanged ZIP provide it explicitly.
