# Anime & Manga Tracker Discord Bot

A Discord bot for keeping track of anime and manga, checking release schedules, and getting updates in the channels you choose. It runs on Python 3.11+ with `discord.py`, SQLite, and a few data-source APIs. The deployment instructions below cover Ubuntu with `systemd`; you can use another host if it supports the same Python setup.

**A quick note about release info:** catalogue episode and chapter counts don’t prove that something just came out, and an airing time doesn’t guarantee an episode is available to stream. When the bot can’t confirm something, it should say so rather than guess.

## Want to keep the code on GitHub?

You don’t need GitHub to run the bot. It’s just a handy place to keep the code and track changes. GitHub won’t keep the bot online for you; you’ll still need to run it on a hosting service.

**New to GitHub?** GitHub Desktop is usually the easiest option on Windows or Mac.

1. Download and extract the project ZIP. Open the extracted `anime-manga-tracker` folder.
2. Go to <https://github.com/> and sign in. Click **New repository**, name it `anime-manga-tracker`, choose **Private** if desired, and create an empty repository. Do not add a README or `.gitignore` during creation because this project already contains them.
3. Install GitHub Desktop from <https://desktop.github.com/> and sign in.
4. In GitHub Desktop, choose **File → Add Local Repository** and select the extracted project folder. If prompted, create a local repository in that folder.
5. Review the changed-file list before committing. `.env`, database files, backups, logs, and private keys must not be included. The supplied `.gitignore` excludes common local/private files, but you must still inspect the list.
6. Enter `Initial project import`, click **Commit to main**, then click **Publish repository** and choose the repository you created.
7. Open the repository on GitHub.com and confirm you can see `README.md`, `bot.py`, `bot/`, `tests/`, `deploy/`, the requirements files, `.env.example`, `.gitignore`, and the audit documents. Confirm `.env` and database files are absent.

For detailed GitHub Desktop, terminal/Git, and browser-upload instructions, see [`GITHUB_UPLOAD_GUIDE.md`](GITHUB_UPLOAD_GUIDE.md).

### Which files can I upload?

Include the Python source files and folders, tests, deployment templates/scripts, `README.md`, `COMMANDS.md`, `GITHUB_UPLOAD_GUIDE.md`, `SECURITY_AUDIT.md`, `VERIFICATION.md`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, and `.env.example` (placeholders only).

Never publish `.env`, a real Discord token/API key/password, private SSH keys, production database files (`*.db`, `*.sqlite*`), backups, logs, `.venv/`, or generated `__pycache__/` and `*.pyc` files. A private GitHub repository is not a safe place for secrets either. If a token is exposed, reset it immediately; deleting it later is not enough.

---

## What the bot can do

- Slash-command groups: `/track`, `/release`, `/news`, `/notify`, plus `/help`, `/status`, `/settings`.
- Search with an explicit selection menu before adding a title; supports anime and manga and avoids accidental duplicate entries within one server.
- Independent guild watchlists, channels, mention policies, quiet hours, and per-title/per-update-type preferences. Notification setup includes `/notify guide`, quick per-title routing via `/notify show`, and a real delivery/mention test via `/notify test-title`.
- MyAnimeList is the primary catalogue. Its weekly broadcast day/time is used to estimate the next airing when available; AniList and Kitsu are fallback catalogue sources.
- RSS/Atom feeds for current news and announcement matching. The default feed is Crunchyroll News RSS, conservatively classified as third-party reporting because articles in a news feed are not necessarily first-party announcements about each series.
- Persistent SQLite records for titles, schedules, feed items, events, source health, and notification deduplication.
- Background scheduler starts once after Discord becomes ready; it is not tied to reconnect events. `systemd` restarts the process after an exit/reboot. The default monitoring interval is 60 seconds (`POLL_INTERVAL_SECONDS=60`). Each cycle checks tracked titles sequentially, so a large list or a slow provider can make a cycle take longer than a minute; frequent checks may also encounter upstream API rate limits.
- Role/user/everyone/no-mention modes; all outgoing messages use explicit `AllowedMentions`. External feed text cannot request an arbitrary ping.

## Need help with commands?

See [`COMMANDS.md`](COMMANDS.md) for a complete guide to every slash command, examples, permission requirements, notification routing, and test behavior. In Discord, `/help` gives a compact overview and `/notify guide` gives the recommended notification setup.

## Where the bot gets its information (and what to expect)

### MyAnimeList (primary catalogue and estimated broadcast schedule)

- API reference: <https://myanimelist.net/apiconfig/references/api/v2>
- Supplies catalogue metadata and, when available, a regular broadcast day/time. The bot estimates the next weekly airing from that schedule using Japan time if MAL does not provide a timezone. This is an estimate, not a confirmed episode date or streaming availability.
- API rate limits can change or temporarily degrade. Requests are paced conservatively and bounded retries respect rate-limit responses.

### AniList (fallback catalogue and airing-time source)

- GraphQL endpoint: <https://graphql.anilist.co>
- Documentation: <https://docs.anilist.co/guide/graphql/>
- Rate limiting: <https://docs.anilist.co/guide/rate-limiting>
- Used as a secondary catalogue when MAL returns too few search results. Its `nextAiringEpisode` may provide a more precise airing time for AniList-sourced entries, but MAL-sourced tracks are not silently enriched from AniList.

### MangaDex (manga chapter monitoring)

- Manga search can use the explicit MangaDex source in `/track add` or `/track search`; a MangaDex title URL is accepted too.
- The bot checks MangaDex’s chapter feed for the newest English **whole-number** chapter and emits a chapter notification when that value advances after the initial snapshot.
- Decimal/special chapter labels and non-English releases are not converted into guessed numbers. This version monitors English whole-number chapters only; availability can differ by translation group.
- Source: <https://api.mangadex.org> and <https://mangadex.org>.

### `/random` anime picker

- `/random` lets members choose currently releasing, finished airing, or highly rated anime. The highly-rated category defaults to a minimum AniList average score of 75/100 and can be adjusted. Optional genre, episode-count, and starting-year filters help narrow the pick.
- Picks come from AniList catalogue results; the command returns title, status, synopsis when available, episode count, cover, and source link. A scheduled airing time is not proof of streaming availability.

### Kitsu

- JSON:API base: <https://kitsu.io/api/edge>
- Documentation: <https://kitsu.docs.apiary.io/>
- Supplies fallback anime/manga title searches and catalogue fields. It is not treated as a universal live release feed.

### MyAnimeList API

- API reference: <https://myanimelist.net/apiconfig/references/api/v2>
- Set `MAL_CLIENT_ID` in `.env`. Obtain the key from the MyAnimeList developer/API settings yourself. Search is disabled when the value is empty. This integration uses a client ID, not your personal password or browser cookies.
- MAL `num_chapters` is shown as the catalogue chapter count when present. It is not assumed to prove that a chapter was just released. A weekly broadcast estimate cannot determine the next episode number.

### RSS and official news

The bot reads only explicitly configured RSS/Atom URLs; it does not scrape websites or bypass logins, paywalls, CAPTCHAs, or anti-bot rules. Default feed: Crunchyroll News RSS, `https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss`. Crunchyroll describes its news RSS feeds on its [official About page](https://www.crunchyroll.com/hi/news/about). The default feed is classified as third-party reporting for series-specific claims; the fact that a feed is operated by a news site does not automatically make every reported announcement a first-party publisher announcement.

Override the feed list in `.env` with a semicolon-separated value:

```dotenv
RSS_FEEDS="Crunchyroll News|https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss|third-party;Publisher Press Room|https://publisher.example/feed.xml|official"
```

Only mark a feed `official` when its entries are published directly by the studio, manga publisher, rights holder, or platform responsible for the actual announcement. RSS entries are seeded on first successful fetch, so the bot doesn't dump an existing feed archive into Discord. Later new entries are matched conservatively against tracked title names. RSS matching is approximate text matching, not a guarantee of perfect title attribution. Confirm articles at their source.

Many publishers/platforms do not offer a public RSS feed. Add only URLs you are permitted to use and respect their terms and request limits. The bot does not crawl arbitrary websites for chapter numbers. Manga chapter availability/upcoming dates remain unknown unless a provider or a permitted source supplies reliable information.

## Project layout

```text
anime-manga-tracker/
├── bot.py
├── config.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── README.md
├── GITHUB_UPLOAD_GUIDE.md
├── SECURITY_AUDIT.md
├── VERIFICATION.md
├── deploy/
│   ├── anime-tracker.service
│   └── setup_ubuntu.sh
├── bot/
│   ├── commands/{tracking,releases,news,notifications,general,helpers}.py
│   ├── providers/{base,anilist,myanimelist,kitsu,mangadex,official_sources}.py
│   ├── services/{scheduler,release_service,news_service,notification_service}.py
│   ├── database/{session,repositories}.py
│   └── utils/{embeds,permissions,logging}.py
└── tests/
    ├── conftest.py
    ├── test_tracking.py
    ├── test_releases.py
    ├── test_notifications.py
    ├── test_permissions.py
    ├── test_providers.py
    ├── test_news.py
    └── test_rate_limits.py
```

## Running it and checking that it works

Python 3.11 or later is recommended. These commands work from the project directory.

```bash
python3 --version
python3 -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` and set `DISCORD_TOKEN`. Do not share the token. Start the bot with:

```bash
python bot.py
```

The database is created at `DATABASE_PATH` (default: `data/tracker.sqlite3`, inside the project folder). This SQLite file stores tracked titles and the bot’s saved settings. If your hosting environment sets `DATABASE_PATH`, that configured path takes precedence. Keep the same database file when updating the bot, or it may appear that your tracked shows have disappeared. You do not need to create it manually. To run offline tests without Discord credentials or live API calls:

```bash
pytest -q
```

The automated tests use fake providers/Discord clients and temporary SQLite databases. The production `requirements.txt` omits pytest to keep the VM environment lean; the local `requirements-dev.txt` includes test tools. See [VERIFICATION.md](VERIFICATION.md) for the precise checks run during the build.

## Create the Discord application

1. Open <https://discord.com/developers/applications>, create an application, and add a **Bot** user.
2. Copy/reset the bot token and store it only in `.env` as `DISCORD_TOKEN=...`. Never commit `.env`.
3. Under OAuth2 URL Generator, select scopes `bot` and `applications.commands`.
4. Grant only the permissions needed for your community: View Channels, Send Messages, Embed Links, and (optionally) Read Message History. The bot does not need Administrator. Role mentions may require the role to be mentionable or the bot to have the appropriate role-mention permission. Do not give it Manage Server or Administrator.
5. Invite the bot to your test server with the generated URL.
6. Start the bot and use `/help`. Slash-command global registration can take time to appear. For faster testing, set `DEV_GUILD_ID` to your test server ID; the project copies/syncs commands to that guild. Remove/blank it for global registration once ready.
7. Use `/notify channel` to choose a channel. Set a role/user target or keep `/notify target` at `none`. `@everyone` requires Administrator permission, setting a target explicitly, and typing the exact confirmation `ENABLE`; disabling requires `DISABLE`.

## Hosting the bot on an Ubuntu server

Oracle's Always Free resources can run this small persistent process, but the provider controls capacity and may reclaim idle Always Free compute under its policy. **Do not assume a free instance will always be available or that this service has a permanent uptime guarantee.** Current eligibility/limits: [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) and [Free Tier FAQ](https://www.oracle.com/cloud/free/faq/).

### A. Create an account and VM

1. Sign up at <https://www.oracle.com/cloud/free/>. Oracle normally asks for valid contact information and a payment card for identity verification; policies vary. You are not charged for properly designated Always Free resources while usage remains within their free limits. Do not create multiple accounts to work around limits.
2. Select your **home region carefully**. Always Free compute allocation is limited to the home region. Keep track of your account's free usage and avoid creating paid resources accidentally.
3. In the OCI Console, open **Compute → Instances → Create instance**.
4. Name the VM `anime-tracker`. Select an Ubuntu 24.04 LTS image and an Always Free eligible shape. An eligible Ampere A1 Flex VM around **1 OCPU / 6 GB RAM** is suitable if available; the current Always Free monthly allowance is equivalent to 2 OCPUs and 12 GB memory (check the Console's eligibility label and current official limits). AMD `VM.Standard.E2.1.Micro` is another Always Free eligible option but has only 1 GB RAM and limited CPU.
5. Configure a public subnet with a public IPv4 address if you want to SSH from your computer. Generate an SSH key pair in the Console or locally; **download/save the private key securely**. Never share or upload it. Use an ingress rule for TCP port 22 restricted to your current public IP when practical. The bot does not need inbound web ports. Outbound HTTPS (TCP 443) is required to reach Discord/API services.
6. Create the VM. If OCI says **Out of host capacity**, try another availability domain when offered, or try later. This is a real capacity constraint, not a bot configuration problem.
7. Copy the VM public IP from the instance details page.

### B. Connect over SSH

On macOS/Linux, set the key permission then connect:

```bash
chmod 600 ~/Downloads/oci-ssh-key.key
ssh -i ~/Downloads/oci-ssh-key.key ubuntu@YOUR_VM_PUBLIC_IP
```

On Windows use Windows Terminal/PowerShell with OpenSSH or your preferred SSH client and the private key you saved. Replace `YOUR_VM_PUBLIC_IP` with the actual IP; do not type the placeholder literally.

### C. Upload the project

On your **local computer**, zip or copy the project folder, then transfer it to the VM. Example using `scp` from the directory containing `anime-manga-tracker/`:

```bash
scp -i ~/Downloads/oci-ssh-key.key -r anime-manga-tracker ubuntu@YOUR_VM_PUBLIC_IP:/home/ubuntu/
```

On the VM, move files to the fixed installation directory:

```bash
sudo mv /home/ubuntu/anime-manga-tracker /opt/anime-manga-tracker
sudo chown -R ubuntu:ubuntu /opt/anime-manga-tracker
cd /opt/anime-manga-tracker
sudo bash deploy/setup_ubuntu.sh
```

The setup script installs OS packages, makes a virtual environment, installs Python requirements, creates a dedicated `animebot` service account, installs the systemd unit, and enables it on boot. It does **not** start the process before you configure secrets.

If you are updating an existing installation, do not overwrite or delete `/opt/anime-manga-tracker/data/`. That directory contains the database.

### D. Configure the token and start

```bash
sudo nano /opt/anime-manga-tracker/.env
```

Set at minimum:

```dotenv
DISCORD_TOKEN=your_real_discord_bot_token
DATABASE_PATH=/opt/anime-manga-tracker/data/tracker.sqlite3
POLL_INTERVAL_SECONDS=60
```

Leave `MAL_CLIENT_ID` empty to disable MAL. Leave `DEV_GUILD_ID` empty for global slash commands, or enter a test guild ID while developing. The default Crunchyroll News RSS feed is used unless you replace it with `RSS_FEEDS=...`.

Save (`Ctrl+O`, Enter) and exit (`Ctrl+X`). Then:

```bash
sudo chown root:animebot /opt/anime-manga-tracker/.env
sudo chmod 640 /opt/anime-manga-tracker/.env
sudo systemctl start anime-tracker
sudo systemctl status anime-tracker --no-pager
sudo journalctl -u anime-tracker -f
```

In the logs, look for a ready message and successful slash-command registration. Press `Ctrl+C` to exit the log viewer; it does not stop the service. Verify commands appear in Discord and run `/track search`, `/track add`, `/notify guide`, `/notify show`, `/notify test-title`, and `/status` in your test server. Use a test role/channel because `/notify test-title` can generate a real role/user ping.

### E. Updating without losing data

1. Back up `data/tracker.sqlite3` before updating.
2. Replace source files but **do not remove the `data/` directory or `.env`**. Reapply root ownership to source and virtual-environment files after copying an update; the service account should not own executable code.
3. From `/opt/anime-manga-tracker` run:

```bash
sudo /opt/anime-manga-tracker/.venv/bin/python -m pip install -r /opt/anime-manga-tracker/requirements.txt
sudo systemctl restart anime-tracker
sudo systemctl status anime-tracker --no-pager
sudo journalctl -u anime-tracker -n 100 --no-pager
```

If the schema changes in a later upgrade, take a database backup first and follow that release's migration instructions; the current version initializes missing tables but does not drop existing tables.

### F. Backups and restore

Use SQLite's backup command for a consistent copy while the bot is running:

```bash
sudo -u animebot sqlite3 /opt/anime-manga-tracker/data/tracker.sqlite3 ".backup '/opt/anime-manga-tracker/data/backup-$(date -u +%Y%m%dT%H%M%SZ).sqlite3'"
```

Copy a backup off the VM as well; a backup on the same disk does not protect against VM/disk deletion. Example from your local terminal:

```bash
scp -i ~/Downloads/oci-ssh-key.key ubuntu@YOUR_VM_PUBLIC_IP:/opt/anime-manga-tracker/data/backup-YYYYMMDDTHHMMSSZ.sqlite3 .
```

To restore a saved backup, stop the service first and replace the live DB file:

```bash
sudo systemctl stop anime-tracker
sudo cp /opt/anime-manga-tracker/data/tracker.sqlite3 /opt/anime-manga-tracker/data/pre-restore.sqlite3
sudo cp /path/to/your/backup.sqlite3 /opt/anime-manga-tracker/data/tracker.sqlite3
sudo chown animebot:animebot /opt/anime-manga-tracker/data/tracker.sqlite3
sudo systemctl start anime-tracker
```

Replace `/path/to/your/backup.sqlite3` with the actual location. For a backup copied to your local computer, transfer it back with `scp` first.

### G. Monitor resources and troubleshoot

```bash
# Service state and last logs
sudo systemctl status anime-tracker --no-pager
sudo journalctl -u anime-tracker -n 100 --no-pager
sudo journalctl -u anime-tracker -f

# Memory, CPU, disk, uptime
free -h
top
df -h
uptime

# Check DB integrity
sudo -u animebot sqlite3 /opt/anime-manga-tracker/data/tracker.sqlite3 'PRAGMA integrity_check;'
```

Common issues:

- **Service fails immediately:** check `.env` syntax and `DISCORD_TOKEN`; look at `journalctl` and confirm Python is 3.11+.
- **Commands don't appear:** make sure the bot is invited with `applications.commands`; wait for global sync propagation or configure `DEV_GUILD_ID` for a test guild. Check logs for sync errors.
- **403/429/provider errors:** provider/API throttling or outage; the bot tracks source health and will retry on later cycles. Don't try to bypass the limit.
- **No upcoming chapter:** expected if no reliable source provides a schedule. Catalogue chapter count is not a latest chapter report.
- **Notifications don't send:** check `/notify settings`, that the bot can view/send/embed in the channel, and that selected roles/users still exist. @everyone is off by default.
- **SQLite locked or disk full:** verify only one bot process runs, inspect `df -h`, and check file ownership (`sudo chown -R animebot:animebot /opt/anime-manga-tracker/data`).
- **OCI cannot provision a VM:** attempt again later or in another available domain in the home region. Do not create paid resources unless you have explicitly decided to accept possible charges.
- **OCI VM goes away:** Always Free instance capacity, idle reclamation and account policies are outside this project. Keep off-instance backups. Do not generate fake traffic to evade the platform's idle policy.

## Oracle Always Free limitations and alternatives

- Oracle's current docs list up to two `VM.Standard.E2.1.Micro` instances (1 GB RAM each), and a monthly Ampere A1 allowance currently equivalent to 2 OCPUs/12 GB RAM for an Always Free tenancy. Always check the live console/documentation: free resources must be created in the home region and shapes can be out of capacity.
- OCI's idle compute policy states instances may be reclaimed when CPU and network utilization remain below its thresholds for seven days (and memory is also considered for A1). A mostly idle Discord bot can be at risk. Do not artificially keep utilization high; keep backups and plan for replacement/redeployment.
- Google Cloud has an Always Free Compute Engine allowance for one non-preemptible `e2-micro`, but only in three US regions, with 30 GB-months standard disk and 1 GB/month North America outbound transfer in the current published limit. A billing account is required and overages may be charged: <https://docs.cloud.google.com/free/docs/free-cloud-features>. This may be a useful alternative if your network usage and region meet the limits; configure billing alerts and verify current terms.
- AWS EC2's free usage benefit is time-limited for many newer accounts (the current program distinguishes accounts created before/after July 15, 2025), so it should not be represented as permanent free hosting: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html>.
- A device you already own that can run 24/7 (e.g. a Raspberry Pi or home server) avoids a hosting bill but still uses electricity and depends on your home internet/power.
- Free web application tiers often sleep, restrict long-running processes, or change plan terms; verify persistent websocket and always-on worker support before migrating. GitHub Actions and uptime-ping tricks are not a suitable always-on Discord gateway host.

## A few useful things to know

- `/track add` opens a selection menu and stores the chosen source ID per guild.
- `/release next` uses a provider schedule when one exists; dates are displayed with Discord's timestamp widget (localized for the person viewing it). The bot stores timestamps in UTC.
- `/release latest` shows recent recorded events, not the total episode/chapter count pretending to be a latest release.
- `/release check` serializes with scheduled checks. The scheduler is a single async task and de-duplicates the same media title across servers in each cycle.
- `/news title` searches configured RSS/Atom feed titles and summaries. It reports no match when a feed doesn't provide a trustworthy result.
- `/notify types` only changes fields you explicitly supply; omitted switches remain unchanged. `/notify show` is the quick per-title channel/optional-role setup; `/notify test-title` tests the effective route and sends a real test ping if one is configured; `/notify guide` shows the short instructions.
- Ordinary notifications respect configured quiet hours. Official announcement events, metadata delays, and hiatus notices bypass quiet hours; see the message displayed when configuring the setting.
- Historical events older than 48 hours are not automatically replayed. Recent undelivered event records can catch up after restart; notification rows are unique per guild/release key. A crash exactly between sending a message and confirming the DB write can never be made mathematically exactly-once across Discord + SQLite, but reservation records strongly reduce duplicates.

## The easiest way to set up notifications

The notification system keeps the advanced controls, but most servers can use three simple commands. Run these in the Discord server where the bot is installed; server setup commands require **Manage Server** permission.

1. **Set a server-wide fallback:** run `/notify channel` and choose the channel for ordinary release alerts. Optionally run `/notify role` to choose the default role to ping, or leave the target as `none` for no ping.
2. **Choose a channel for one title:** run `/notify show`, select a title that is already tracked, choose a channel, and optionally choose a role. Leaving `role` empty means the title sends without a ping. Anime titles route episode alerts; manga titles route chapter alerts. This overrides the matching category default for that title only.
3. **Test the title:** run `/notify test-title` and select the tracked title. The bot checks whether title and episode/chapter alerts are enabled, resolves the actual route, and sends a test message to that channel. **This is a real message and can ping the configured role/user**, so only run it when that ping is expected. It does not create a fake release event or mark a real release as delivered.
4. **Check settings:** `/notify routes` lists saved routes; `/notify settings` shows server defaults. `/notify guide` displays these steps inside Discord.

If the test says alerts are disabled, use `/notify title` to enable title notifications and `/notify types` to enable episode or chapter alerts. If it reports no channel, use `/notify show` or `/notify channel`. If sending fails, check the bot's `View Channel`, `Send Messages`, and `Embed Links` permissions and confirm the selected role still exists.

## Choosing where notifications go

The bot supports both server-wide category routes and title-specific overrides. Category routes are the defaults; a title-specific route for the same category takes precedence. Categories are `episodes`, `chapters`, `news`, and `schedule`.

Examples (run as a server administrator; the simpler `/notify show` command is recommended for a single title):

- `/notify route category:Anime episodes channel:#anime-releases target:Role role:@Anime Fans`
- `/notify route category:Manga chapters channel:#manga-releases target:Role role:@Manga Readers`
- `/notify route category:News and announcements channel:#anime-news target:None — no ping`
- `/notify title-route title:One Piece category:Anime episodes channel:#one-piece target:Role role:@One Piece`
- `/notify routes` to inspect all routes
- `/notify route-clear category:Anime episodes` to remove a category default
- `/notify route-clear category:Anime episodes title:One Piece` to remove just that title override

`/notify title-route` requires the title to already be tracked in this server. Each route stores its own channel and target, so choosing a role for one category does not affect other categories. Title-specific routes override category defaults, which override the legacy global notification channel/target. `@everyone` routing is accepted only for an administrator and requires the exact confirmation `ENABLE`; Discord mention permissions are explicitly restricted to the selected target.



### Fixes in this source build

- `/track add` and `/track search` accept a `source` choice, including **MangaDex (manga only)**. Leave it as all supported sources to search the existing catalogues.
- `/random` chooses an AniList anime from the selected category: currently releasing, finished, or highly rated (minimum score 1–100, default 75). Optional filters include genre, maximum episode count, and starting year. It displays the AniList link, available synopsis, score, status, episode count, and airing details when available.
- MangaDex chapter polling stores the initial latest whole-number English chapter as a baseline, then emits a new-chapter event only when a later check detects a higher chapter number. Decimal chapter numbers are intentionally ignored.

`/random` also supports optional genre, episode-count, and starting-year filters. `/status` includes database, recent notification, and provider health information.
