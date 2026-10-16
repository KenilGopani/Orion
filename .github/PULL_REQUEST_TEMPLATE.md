## What and why

<!-- What does this change, and what problem does it solve? Link the issue: Closes #… -->

## How it was verified

<!-- Tests added or updated, and anything you ran by hand (make dev, orion up, make eval). -->

## Checklist

- [ ] `make test` and `make lint` pass
- [ ] New or changed tools have a deliberate safety level in `EXPECTED_SAFETY` (`tests/test_tool_surface.py`)
- [ ] Anything that touches approvals, the API or OpenClaw calls is reflected in `SECURITY.md`
- [ ] Docs updated (README / ARCHITECTURE.md / .env.example) where behaviour changed
