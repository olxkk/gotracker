# Commands, without the guesswork

In Discord, type `/` and pick a command from the menu. If a title field offers autocomplete, choose the exact title from the list — that helps avoid selecting the wrong series. This guide covers what each command does and when to use it.

## Getting started

1. Use `/track add` to find an anime or manga, then pick the right result.
2. Run `/notify guide` for a quick walkthrough.
3. Use `/notify show` to choose where that title posts. Add a role if you want people pinged; leave it blank if you don’t.
4. Try `/notify test-title` to check the setup. It sends a real test message, and it may ping the configured role or user, so run it somewhere that’s okay.
5. Check `/track list` and `/notify routes` to make sure everything saved.

The notification setup commands `/notify show`, `/notify test-title`, `/notify title`, `/notify types`, and `/notify quiet-hours` require **Manage Server** permission. Everyone can use the usual browse and info commands, such as search, release info, news, `/random`, `/help`, and status.

## Finding and tracking shows: `/track`

| Command | Options | What it does |
|---|---|---|
| `/track add` | `title`, `media_format`, `source` | Searches catalogues and opens a selection menu. Select the exact result to add it; a search result is never auto-added. Sources: default catalogues (AniList, Kitsu, MyAnimeList), AniList, Kitsu, MyAnimeList, or MangaDex (manga only). Choose MangaDex with `media_format:Manga`. |
| `/track remove` | `title` | Removes one matching title from this server's watchlist. It does not delete the title globally or from other servers. Use autocomplete to avoid ambiguity. |
| `/track list` | none | Lists this server's tracked titles and known schedule/catalogue information. Large lists are shortened in the display. |
| `/track search` | `title`, `media_format`, `source` | Searches without adding anything. Choose `media_format:Manga` and `source:MangaDex (manga only)` to search MangaDex directly. |
| `/track info` | `title` | Shows catalogue metadata for a tracked title; exact catalogue matches may also be looked up when untracked. |

Examples: `/track add title:Cyberpunk media_format:Anime source:AniList` or `/track add title:One Piece media_format:Manga source:MangaDex (manga only)`. The source choice is required so MangaDex is visible in the command form. The default source option searches AniList, Kitsu and MyAnimeList; MangaDex is selected directly.

## Release dates and history: `/release`

| Command | Options | What it does |
|---|---|---|
| `/release next` | `title` | Shows the next known anime airing schedule when available. For manga, it explains what reliable chapter timing is or is not available. A scheduled airing is not proof that an episode is streaming. |
| `/release latest` | `title` | Shows the latest recorded release event for a title tracked in this server. Catalogue episode/chapter totals are not treated as a latest release. |
| `/release check` | `title` | Refreshes one tracked title now. This calls the provider and may be rate-limited. It reports whether schedule changes were detected; it cannot guarantee that an episode is streamable. |
| `/release upcoming` | none | Lists scheduled upcoming anime episodes for this server's tracked titles. It does not invent missing manga release dates. |
| `/release history` | `title` | Shows recorded releases and schedule changes for a tracked title. Empty history means the bot has not recorded events, not necessarily that no release occurred. |

## Anime news: `/news`

| Command | Options | What it does |
|---|---|---|
| `/news title` | `title` | Searches configured RSS/Atom news sources for recent matching items. No match does not prove no announcement exists. |
| `/news upcoming` | none | Combines this server's upcoming tracked anime schedule with relevant recent announcements from configured feeds. |

RSS/Atom feeds must be configured in `.env` using `RSS_FEEDS`. The bot does not bypass logins, paywalls, CAPTCHAs, or anti-bot controls.

## Notifications: `/notify`

### The commands you'll actually need

| Command | Options | What it does |
|---|---|---|
| `/notify guide` | none | Shows the short setup steps. Start here if you're new to notifications. |
| `/notify show` | `title`, `channel`, optional `role` | Picks where one tracked anime or manga sends its episode/chapter alerts. Leave `role` empty for no ping. Requires Manage Server. |
| `/notify test-title` | `title` | Sends a real test message through that title's saved route. A configured role may be pinged. Requires Manage Server. |
| `/notify routes` | none | Shows saved destinations, including older routes already stored in the database. |
| `/notify settings` | none | Shows the server's current defaults and quiet hours. |
| `/notify title` | `title`, `enabled` | Turns all notifications for one tracked title on or off. Requires Manage Server. |
| `/notify types` | `title`, optional alert switches | Shows or changes episode, chapter, schedule, delay, hiatus and announcement alerts. Only switches you provide are changed. Requires Manage Server. |
| `/notify quiet-hours` | `start`, `end`, optional `timezone` | Optional quiet period using 24-hour times, e.g. `22:00` to `07:00` and `Europe/London`. Enter `OFF` for both times to disable. Requires Manage Server. |

`/notify test-title` sends a real Discord message, not a fake release. If the title has a role configured, the role may be pinged. Run the test in a channel where that ping is expected.

The old advanced commands (`route`, `title-route`, `route-clear`, `channel`, `target`, `role`, `user`, `everyone`, and `preview`) are no longer registered, to keep the slash-command menu tidy. Existing route settings in the database are not deleted; `/notify routes` can still display them, and the notification service continues to respect existing saved routes.

If a test says alerts are disabled, use `/notify title` and `/notify types` to check the title's settings. If no destination is configured, use `/notify show`. If sending fails, check the bot's `View Channel`, `Send Messages`, and `Embed Links` permissions and confirm the selected role still exists.

## Other useful commands

| Command | Options | What it does |
|---|---|---|
| `/random` | `category`, optional `minimum_score`, `genre`, `max_episodes`, `year` | Picks an AniList anime that matches Currently releasing, Fully released, or Highly rated. The minimum score applies to Highly rated (default 75/100). Optional filters let you choose a genre, cap the episode count, or choose a starting year. |
| `/status` | none | Shows uptime, Discord latency, database responsiveness, tracked entry count, the latest monitoring run, recent notification delivery counts, and recorded provider health. |
| `/settings` | none | Shows provider availability, monitoring configuration, and this server's basic notification defaults. |
| `/help` | none | Displays a compact command overview. |

## If something isn’t working

- **A title isn't in autocomplete:** add it with `/track add` first, or use `/track search` to find the correct catalogue entry.
- **No route is configured:** use `/notify show` to set a destination for that title.
- **The test says notifications are disabled:** check `/notify title` and `/notify types` for that title.
- **A test message cannot be delivered:** check the selected channel and the bot's `View Channel`, `Send Messages`, and (for embeds) `Embed Links` permissions. Check the logs for provider/database errors.
- **No episode is detected:** check `/release check` and `/status`. Data sources may be delayed or may not provide reliable schedules. MangaDex monitoring is limited to English whole-number chapters in this version.
- **A slash command is missing:** check startup logs for command-sync errors, then wait for Discord to propagate registered commands.


## Finding something to watch

`/random` can do more than pick from a release category. Choose a genre, limit the number of episodes, or set a starting year if you have something specific in mind. These filters are optional, so you can leave them blank for a surprise. The score threshold is only used for **Highly rated** picks. If the filters are too restrictive, remove one and try again.

`/status` is the quick health check. It shows whether the database responds, the bot's Discord latency, the last monitoring run, provider check health, and notification outcomes from the last 24 hours.
