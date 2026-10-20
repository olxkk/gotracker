# Build verification notes

This artifact was generated and checked in the provided build environment on 2026-10-15.

## Checks actually executed

- `python -m compileall -q bot.py config.py bot tests` — passed.
- `bash -n deploy/setup_ubuntu.sh` — passed.
- `PYTHONPATH=/tmp/anime-tracker-test-stubs:$PWD pytest -q` — **21 tests passed** using temporary, test-only compatibility shims for `discord.py`, `aiosqlite`, and `feedparser`. The shims were kept outside the project and are not included in the release archive.

## Important limits of that verification

The environment could not reach the Python package index (DNS/network resolution failed), so the real dependencies could not be installed here. The tests therefore verify the local database/service/provider logic against the mocked interfaces; they do **not** prove that this project has been started with the genuine installed `discord.py`, `aiosqlite`, and `feedparser` packages. No Discord credentials, Oracle Cloud account, live Discord guild, or live API integration was available, and no cloud deployment was performed.

After installing the requirements in a normal networked Python 3.11+ environment, run:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q bot.py config.py bot tests
pytest -q
```

Then test command registration and notification delivery in a private Discord test server before inviting the bot to other servers.


## Channel routing update (2026-10-15)

Added configurable category routes (`episodes`, `chapters`, `news`, `schedule`) and per-title overrides, each with an independent channel and mention target. Resolution order is title override → category default → legacy server-wide channel/target. Added `/notify route`, `/notify title-route`, `/notify routes`, and `/notify route-clear`. Per-route `@everyone` requires administrator permission and the exact `ENABLE` confirmation. Added tests for route precedence, server isolation, removal/fallback, and explicit everyone enablement.

The updated Python source passed `compileall`. The pytest suite was not executed in this pass because `aiosqlite` is not installed in the current environment and package downloads are unavailable.

## Independent archive audit (2026-10-15)

A follow-up static audit of the release archive passed ZIP integrity, Python AST/compile checks, and shell syntax checks. The environment did not contain the real `discord.py`, `aiosqlite`, or `feedparser` packages, so the full dependency-backed tests and a vulnerability scan could not be performed. See `SECURITY_AUDIT.md` for scope, limitations, and production recommendations. This is not a guarantee of zero bugs or leaks.
