# What has and hasn’t been tested

These notes explain which checks were run on this project and which ones still need to be done.

## Checks that passed

- `python -m compileall -q bot.py config.py bot tests` — passed.
- `bash -n deploy/setup_ubuntu.sh` — passed.
- `PYTHONPATH=/tmp/anime-tracker-test-stubs:$PWD pytest -q` — **21 tests passed** using temporary, test-only compatibility shims for `discord.py`, `aiosqlite`, and `feedparser`. The shims were kept outside the project and are not included in the release archive.

## What those checks don’t prove

The environment could not reach the Python package index (DNS/network resolution failed), so the real dependencies could not be installed here. Those tests check the database, service, and provider logic against mock versions of the libraries. They do **not** prove the bot works with the real installed `discord.py`, `aiosqlite`, and `feedparser` packages. No Discord credentials, Oracle Cloud account, live Discord guild, or live API integration was available, and no cloud deployment was performed.

After installing the requirements in a normal networked Python 3.11+ environment, run:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q bot.py config.py bot tests
pytest -q
```

Then test command registration and notification delivery in a private Discord test server before inviting the bot to other servers.


## Channel routing update (15 October 2026)

Added configurable category routes (`episodes`, `chapters`, `news`, `schedule`) and per-title overrides, each with an independent channel and mention target. Resolution order is title override → category default → legacy server-wide channel/target. Added `/notify route`, `/notify title-route`, `/notify routes`, and `/notify route-clear`. Per-route `@everyone` requires administrator permission and the exact `ENABLE` confirmation. Added tests for route precedence, server isolation, removal/fallback, and explicit everyone enablement.

The updated Python source passed `compileall`. The pytest suite was not executed in this pass because `aiosqlite` is not installed in the current environment and package downloads are unavailable.

## Extra archive checks (15 October 2026)

A follow-up static audit of the release archive passed ZIP integrity, Python AST/compile checks, and shell syntax checks. The environment did not contain the real `discord.py`, `aiosqlite`, or `feedparser` packages, so the full dependency-backed tests and a vulnerability scan could not be performed. See `SECURITY_AUDIT.md` for scope, limitations, and production recommendations. This is not a guarantee of zero bugs or leaks.


## Making notification setup easier (20 October 2026)

Added `/notify guide` for in-Discord instructions, `/notify show` as a quick per-title channel plus optional role setup, and `/notify test-title` to check a tracked title's effective episode/chapter route and send a real test message using the configured mention policy. The test command refuses to send when all-title notifications or the relevant episode/chapter preference is disabled; it does not create a release event or write notification history. Test messages can produce a real role/user ping.

- `python -m compileall -q bot.py bot tests`: passed after the notification changes.
- `python -m pytest -q`: not run to completion because `aiosqlite` is not installed in this environment (`ModuleNotFoundError`).
- Added tests for title-specific channel/role test delivery and disabled-title behavior; these tests still need to be executed in an environment with the actual project dependencies installed.
- No live Discord command sync, permission check, or delivery test was possible. Do not treat this static validation as proof of live behavior.


## Making the commands easier to understand (20 October 2026)

Added `COMMANDS.md` covering every registered command, options, examples, permissions, notification route precedence, and test-message behavior. Updated `/help` to include all notification commands and explain the recommended workflow; improved Discord option descriptions without renaming commands or changing their signatures. Corrected the README API endpoint attribution. Python syntax compilation and static command-inventory checks passed. The test suite could not run because required packages (`aiosqlite`, `discord.py`) are absent in this environment, and package installation is unavailable; live Discord sync/delivery is not verified.


## Additional discovery and health checks

The `/random` command now passes optional genre, maximum episode count, and starting year filters to AniList and re-checks returned results locally. `/status` checks database responsiveness and reports the most recent scheduler result and notification counts. These changes have static checks and targeted unit tests added; live API and Discord delivery still need a real deployment test.
