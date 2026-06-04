---
name: Bug report
about: Create a report to help us improve
title: "[BUG] "
labels: ["bug", "needs-triage"]
assignees: []
---

## Describe the bug

A clear and concise description of what the bug is.

## To reproduce

Steps to reproduce the behaviour:

1. Go to '…'
2. Click on '…'
3. Scroll down to '…'
4. See error

## Expected behaviour

A clear and concise description of what you expected to happen.

## Screenshots / recordings

If applicable, add screenshots or a screen recording to help explain
the problem. Use https://github.com/nibaldox/conciliacion-geo-v02/issues
to attach files.

## Environment

- **Browser**: [e.g. Chrome 119, Firefox 121, Safari 17]
- **OS**: [e.g. macOS 14.2, Windows 11, Ubuntu 22.04]
- **App version**: [e.g. v2.0 — see footer of the page]
- **Mode**: [ ] React frontend (web/)  [ ] Streamlit (app.py)
- **Backend reachable?**: [ ] Yes (Render)  [ ] Local only
- **Demo mode repros?**: [ ] Yes  [ ] No  [ ] N/A

## Console / log output

```
Paste the relevant error messages here. For the web frontend open
DevTools → Console and copy the red lines. For the backend paste the
output of `uvicorn api.main:app` or Render's log stream.
```

## Sample data

If you can share a small STL/DXF that triggers the issue, attach it
or link to a public download. Strip any confidential geometry first
— the geometry itself doesn't usually matter for diagnosing bugs.

## Severity

How broken is this for you?

- [ ] Critical — can't use the app at all
- [ ] Major — workaround exists but I lose time
- [ ] Minor — cosmetic, edge case, or "nice to fix"
- [ ] Question — not sure if this is a bug
