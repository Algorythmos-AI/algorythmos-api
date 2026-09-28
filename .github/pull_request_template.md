## What and why

<!-- One or two sentences: what this changes and the reason for it. Link the issue if there is one. -->

## How it was tested

<!-- Commands run, screenshots, or the CI jobs that cover it. -->

## Checklist

- [ ] One focused change; the branch targets the repository's default branch
- [ ] Tests added or updated for changed behaviour
- [ ] No secrets, credentials or personal data in the diff
- [ ] Docs / changelog updated if behaviour changed for users
- [ ] Local gate passed: `ruff` bug rules, `pytest` (no new failures), one Alembic head, `pip-audit`
- [ ] Migrations are expand-only (additive, nullable or defaulted; no drops or renames)
