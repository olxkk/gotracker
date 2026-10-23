# What has and hasn’t been tested

This file describes the current source package. Syntax checks are useful, but they do not prove that Discord commands or live provider requests will work in production.

## Checks completed for this update

- `python -m compileall -q .` — passed for all Python files.
- `bash -n deploy/setup_ubuntu.sh` — passed.
- ZIP integrity check — passed when the release archive was created.
- Targeted local check of the `/random` provider query — verifies that random discovery uses compact fields and does not request long descriptions in a 25-title response.
- Static source inspection — `/track add` and `/track search` expose a required source choice including `MangaDex (manga only)`; the old advanced `/notify` commands are no longer registered.

## What still needs a real environment

The full automated test suite could not be run here because `aiosqlite` and `discord.py` are not installed, and package downloads are unavailable in this environment. No live Discord server or live AniList/MangaDex integration test was performed. Do not treat static checks as proof of zero bugs.

After installing dependencies in a normal Python 3.11+ environment, run:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q bot.py config.py bot tests
pytest -q
```

Then restart the bot and check the startup log for command-sync errors. Global Discord slash-command updates can take time to appear. For quick testing, configure `DEV_GUILD_ID` for a private test server and sync there first.

## Current behavior notes

- `/random` requests compact fields for its candidate page to avoid hitting `MAX_RESPONSE_BYTES` because of long synopsis text. After choosing a result, it makes a separate detail request to load the synopsis; if that detail request fails, the pick still works and shows a fallback description.
- `/track add` and `/track search` require a source choice so MangaDex is visible in the command form. Choose `Manga` and `MangaDex (manga only)` to search MangaDex. MangaDex is not an anime source.
- The simplified `/notify` group keeps `guide`, `show`, `test-title`, `routes`, `settings`, `title`, `types`, and `quiet-hours`. The old advanced commands are removed from the registered command menu. Existing saved route settings are not deleted and the notification service can still use them as fallbacks.
- `/notify test-title` sends a real message to the configured route and may ping its role. Run it only where that test is expected.
- The project has not been deployed to Kerit from this environment.
