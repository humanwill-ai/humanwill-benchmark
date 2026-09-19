# Deferred PyPI distribution plan

Status: deferred by the owner in favor of GitHub-only distribution. This plan
is retained for future work; it does not authorize implementation or uploads.

Keep distribution name `humanwill-evals`, executable/import `humanwill`, and the
subtitle **Measuring harmful refusals in AI models**. Keep the 424-question pack
in the Git checkout and separate versioned ZIP, outside the wheel/curated sdist.

1. Check package-name availability/ownership and prepare the next alpha metadata.
   Provide a PyPI-facing description with working absolute documentation links.
2. Add an explicit release workflow: build once, validate archive contents,
   metadata and installed behavior, then publish those same verified artifacts.
   Use GitHub Actions Trusted Publishing rather than long-lived upload tokens.
   Ordinary code pushes must not publish packages.
3. Update onboarding for PyPI plus demo, PyPI plus reference ZIP, and Git checkout.
   Cover model/price/budget configuration, API keys, upgrades, exact version pins,
   reports and the shared agent/Python API. A verified pack-download command is
   a possible later improvement, not an existing command or initial requirement.
4. Establish owner-controlled PyPI and TestPyPI accounts with 2FA and configure
   trusted publishers for the exact repository/workflow/environment. A pending
   publisher does not reserve the project name before its first publication.
5. After separate public-upload authorization, rehearse on TestPyPI. TestPyPI is
   publicly accessible, not private staging. Obtain dependencies from normal
   PyPI separately, install the exact candidate, and verify CLI/API, reports,
   both styles, reference-pack setup and downloaded artifact hashes.
6. Publish the validated release to PyPI after authorization. Verify installation
   without GitHub credentials and document version pinning, release withdrawal
   and corrected releases. Keep the research repository private.

Target install command, after publication and inside an activated environment:

```sh
python -m pip install --pre "humanwill-evals[live,reports]"
```

Completion: a new user can install the tool, obtain questions and follow the
benchmark workflow without maintainer assistance. Agent/CLI flexibility remains
unchanged; PyPI hosts packages, not evaluation execution or user responses.

Sources checked 2026-09-19:
[official publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/),
[pending publishers and name ownership](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/).
