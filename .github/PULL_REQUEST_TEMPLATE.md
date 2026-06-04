## Summary

<!-- One or two sentences. What does this PR change and why? -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing
      functionality to change)
- [ ] Refactor (no functional change, code quality)
- [ ] Docs (README, AGENTS.md, ARCHITECTURE.md, comments)
- [ ] Tests (adding or fixing tests)
- [ ] CI / build / tooling

## Affected areas

- [ ] Backend (`core/`, `api/`)
- [ ] Frontend (`web/`)
- [ ] Streamlit (`app.py`, `ui/`, `cli.py`) — confirm in the PR
      description that you did NOT modify these
- [ ] Demo data (`scripts/generate_demo_data.py`, `web/public/demo/`)
- [ ] CI / deploy (`.github/workflows/`, `render.yaml`, `Dockerfile*`)
- [ ] Docs only

## How to test

<!-- Concrete steps a reviewer can follow. Include any commands,
     files to upload, env vars to set, etc. -->

```bash
pytest tests/ -v                          # backend
cd web && npm run build                   # frontend
cd web && npm run lint                    # frontend linting
# Manual check:
#   1. Open http://localhost:5173
#   2. Click "Try with sample data"
#   3. ...
```

## Screenshots / recordings

If the change is visual, attach before/after. For UI changes,
include both light and dark mode if relevant.

## Checklist

- [ ] I read [AGENTS.md](AGENTS.md) and the [architecture](ARCHITECTURE.md) docs
- [ ] My change is **additive** — no modifications to `app.py`,
      `ui/`, `core/` (other than the file I'm explicitly fixing),
      or `cli.py`
- [ ] I added or updated tests in `tests/` for backend changes
- [ ] I added the new string to BOTH `web/src/locales/es.json` and
      `en.json` for any new user-facing text
- [ ] I ran `pytest tests/ -v` and the count is still 97+ (or my
      changes added new tests)
- [ ] I ran `cd web && npm run build` and it succeeded
- [ ] I followed conventional commits
      (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`)
- [ ] I did NOT add `Co-Authored-By:` or AI attribution
- [ ] No secrets, API keys, or PII are included in the diff
- [ ] If a new dependency was added, it was added to
      `requirements.txt` (Python) or `web/package.json` (Node)

## Related issues

<!-- Link related issues with `Closes #123` or `Refs #456` -->
