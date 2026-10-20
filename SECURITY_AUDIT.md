# Security and reliability audit

Audit date: 2026-10-15
Artifact audited: `anime-manga-tracker.zip` as supplied in this session

## Scope and result

This was a static review plus isolated syntax/archive checks in `/tmp/anime-audit`. It was not a live Discord integration test, a cloud deployment, or a full dynamic security assessment. **Do not interpret this report as a guarantee of zero bugs, zero leaks, or production certification.**

### Checks passed

- ZIP integrity check (`unzip -t`).
- Python syntax/AST parsing and `compileall` for all project Python files.
- Bash syntax check for `deploy/setup_ubuntu.sh`.
- Reviewed token/config handling, SQL parameterization, role/user/everyone mention construction, category/title route scoping, provider HTTP response size limits, and systemd service restrictions.
- No real Discord token, private key, or credential was found in the source/config files inspected. `.env` is excluded by `.gitignore`; `.env.example` contains only a placeholder.
- Project has no inbound web server; its main network activity is outbound HTTPS to Discord and configured metadata/feed sources.
- Cleaned release archive of generated `__pycache__` / `.pyc` files, which are unnecessary build artifacts.

### Important limitations / remaining checks

- `discord.py`, `aiosqlite`, and `feedparser` were not installed in the audit environment. Therefore the real dependency-backed test suite could not be run here. The earlier `VERIFICATION.md` records a prior run with test-only compatibility shims, but that does not substitute for tests against the actual packages. The latest category/title routing changes need a dependency-backed test run.
- No `pip-audit`/SBOM scan was possible in this offline environment. Dependency ranges are bounded by major version, but they are not pinned to hashes or exact versions. Install in a fresh virtual environment and run `python -m pip install -r requirements-dev.txt`, `pytest -q`, and `python -m pip install pip-audit && pip-audit` in a networked environment before production use.
- No live Discord guild, credentials, or Oracle VM was available. Command registration, channel permissions, mention behavior, API rate limits, service startup/restart, backups, and restore remain to be tested in a private test server/VM.
- RSS source classification depends on operator configuration. Only mark a feed `official` when it is genuinely first-party.
- Discord/API outages, changing provider schemas, schedule corrections, and imperfect RSS title matching remain operational/data-quality risks rather than things static checks can rule out.

## Security recommendations before production

1. Use a fresh, dedicated Discord bot token; never paste it into chat or commit `.env`. If it was ever exposed, reset it in the Discord Developer Portal.
2. Grant only `View Channels`, `Send Messages`, and `Embed Links` where needed; add `Read Message History` only if needed. Do not grant Administrator.
3. Keep SSH ingress restricted to your IP where practical. The bot needs outbound HTTPS, not inbound public web ports.
4. Keep `.env` mode `0600`, keep database/backups private, and store off-VM backups securely. Do not include the database or `.env` in project archives.
5. Before accepting real communities, install actual dependencies in a clean Python 3.11+ environment, run the complete test suite and dependency audit, then verify commands and notification routes in a private test server.
6. Review logs after startup and monitor `systemctl status anime-tracker` and `journalctl -u anime-tracker`; periodically test a database restore.

## Local results

- `python -m compileall -q bot.py config.py bot tests`: passed.
- `bash -n deploy/setup_ubuntu.sh`: passed.
- Python AST parse of all `.py` files: passed.
- `unzip -t`: passed on input archive.
- Full dependency-backed pytest and dependency vulnerability scan: not run (dependencies/tools unavailable in this environment).

### Hardening change included in the audited archive

The deployment setup script now keeps application source and the virtual environment owned by root, gives the `animebot` account write access only to the data directory, and stores `.env` as `root:animebot` mode `0640` so the service can read it without making it world-readable. The README update instructions were adjusted to match this ownership model. This reduces the chance that a compromised bot process can alter its own executable code for persistence.
