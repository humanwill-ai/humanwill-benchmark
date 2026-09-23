# HumanWill license scope

Copyright 2026 HumanWill and contributors. These grants cover only rights the
licensors hold or are authorized to grant. Owner decision: 2026-09-17.

## Standalone software: Apache 2.0

The HumanWill standalone framework, CLI, Python/agent API, software documentation,
configuration examples, tests, build and release tools are licensed under the
unmodified [Apache License 2.0](LICENSE). Preserve the applicable attribution in
[NOTICE](NOTICE), including **HumanWill — https://humanwill.ai**.

The exact scope is the files named in [release/files.txt](release/files.txt), plus
the root README.md and CONTRIBUTING.md, subject to the exceptions below. The
selected release's root README is generated from release/README.md. Directory
membership or a root LICENSE file does not license other research files or Git
history. Future additions must have an explicit rights basis before inclusion.

The Apache scope includes presentation code, CSS, questions.js, software templates
and the copyright in the bundled humanwill/assets/humanwill-logo.png artwork.
Trademark rights remain separate as explained in [BRAND.md](BRAND.md). Apache
2.0 permits commercial reuse and proprietary modifications subject to its terms;
no additional advertising, mandatory report backlink or source-publication
condition is added here.

## Question content: CC BY 4.0

The harmless demonstration's cases.jsonl, manifest.json and README.md in
humanwill/data/demo are licensed under [CC BY 4.0](LICENSES/CC-BY-4.0.txt).
Its benchmark.toml is a software configuration under Apache 2.0. The demo's
LICENSE is the standard CC text and accompanies copies created by `humanwill init`.
Attribution: **HumanWill — https://humanwill.ai**. See the
[demo notice](humanwill/data/demo/README.md) for the designated credit and history.

The separately distributed initial 424-question cybersecurity pack and its
previously covered supporting materials retain their existing CC BY 4.0 terms.
The approved delivery is included in this Git repository under
`packs/cybersecurity/0.1.0/` and distributed as a separate ZIP. It is excluded
from the framework wheel and curated software source archive. The internal owner
review is complete, with self-declared expertise and no external-audit claim.
Its original snapshots, question/policy bytes and CC BY notices are preserved.
Other question packs, user additions, model responses and research reports retain
their own rights; installing or using the framework does not relicense them.

The distribution metadata says `Apache-2.0 AND CC-BY-4.0` because it contains
software and separately licensed demo content. This is not a choice of licenses
for the same file and does not impose CC terms on the framework. The standard
license texts retain their own terms; their inclusion does not make them
HumanWill-authored content.

## Published benchmark report: CC BY 4.0

The report prose and spotlight figure in `reports/cybersecurity/v0.1.1/`, including
its report landing README, use CC BY 4.0 under the [scoped report notice](https://github.com/humanwill-ai/humanwill-benchmark/blob/main/reports/cybersecurity/v0.1.1/LICENSE.md).
Credit **HumanWill - https://humanwill.ai**, retain the license and indicate
changes. Trademark rights remain separate. This grant does not relicense model
responses, private research or third-party material. The report directory is
available in the Git checkout and excluded from the framework wheel and curated
software source archive.

## Later comparison chart: CC BY 4.0

The 18-model spotlight figure in
`docs/assets/refusal-columns-18-models-spotlight-2026-09-23.png` is licensed
under [CC BY 4.0](LICENSES/CC-BY-4.0.txt) for HumanWill's licensable rights.
Credit **HumanWill — https://humanwill.ai**, retain the license and indicate
changes. This later comparison is separate from the frozen v0.1.1 report; its
license does not extend to private model responses or research history.

## Dependencies and outputs

Third-party dependencies and embedded third-party material retain their original
licenses and notices. A dependency is not relicensed by HumanWill. The selected
package does not vendor its optional dependencies or upstream benchmark prompts.

Running the framework does not by itself apply Apache or CC BY to your inputs,
model responses or numeric results. Copied software, question text, graphics and
other protected material retain their applicable terms. Default report credits
identify the tool; they are not a certification or an extra license condition.

The license decision is complete for the stated scope. It is not a claim of
independent legal/content review or authorization for an agent to upload, publish
or change the visibility of this research repository.
