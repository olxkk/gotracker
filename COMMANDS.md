# Commands, without the guesswork

In Discord, type `/` and pick a command from the menu. If a title field offers autocomplete, choose the exact title from the list — that helps avoid selecting the wrong series. This guide covers what each command does and when to use it.

## Getting started

1. Use `/track add` to find an anime or manga, then pick the right result.
2. Run `/notify guide` for a quick walkthrough.
3. Use `/notify show` to choose where that title posts. Add a role if you want people pinged; leave it blank if you don’t.
4. Try `/notify test-title` to check the setup. It sends a real test message, and it may ping the configured role or user, so run it somewhere that’s okay.
5. Check `/track list` and `/notify routes` to make sure everything saved.

Most settings commands need the **Manage Server** permission. `/notify everyone` needs **Administrator**. Everyone can use the usual browse and info commands, such as search, release info, news, `/random`, `/help`, and status.

## Finding and tracking shows: `/track`

| Command | Options | What it does |
|---|---|---|
| `/track add` | `title`, `media_format`, optional `source` | Searches catalogues and opens a selection menu. Select the exact result to add it; a search result is never auto-added. Sources: all, AniList, Kitsu, MyAnimeList, or MangaDex (manga only). |
| `/track remove` | `title` | Removes one matching title from this server's watchlist. It does not delete the title globally or from other servers. Use autocomplete to avoid ambiguity. |
| `/track list` | none | Lists this server's tracked titles and known schedule/catalogue information. Large lists are shortened in the display. |
| `/track search` | `title`, `media_format`, optional `source` | Searches without adding anything. MangaDex is available for manga. |
| `/track info` | `title` | Shows catalogue metadata for a tracked title; exact catalogue matches may also be looked up when untracked. |

Example: `/track add title:Cyberpunk media_format:Anime source:AniList`.

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

### The handy everyday commands

| Command | Options | What it does |
|---|---|---|
| `/notify guide` | none | Displays the recommended setup steps. |
| `/notify show` | `title`, `channel`, optional `role` | Sets the channel and optional role for one tracked title. Anime routes episode alerts; manga routes chapter alerts. Leaving `role` empty means no ping. Requires Manage Server. |
| `/notify test-title` | `title` | Sends a real test through the title's effective episode/chapter route. It checks settings and delivery route, but does not create a fake release or mark a release as delivered. A configured role/user may be pinged. Requires Manage Server. |
| `/notify settings` | none | Shows the server's fallback notification channel/target, quiet hours, and `@everyone` safety state. |
| `/notify routes` | none | Lists saved category defaults and title-specific routes. |
| `/notify preview` | none | Sends a server-default test notification. The configured target may be pinged. Requires Manage Server. |

### Default settings for the server

| Command | Options | What it does |
|---|---|---|
| `/notify channel` | `channel` | Sets the fallback channel for notifications that have no matching specific route. Requires Manage Server. |
| `/notify target` | `target` | Chooses the fallback mention mode: none, role, user, or everyone. The selected role/member must already be configured. Requires Manage Server. |
| `/notify role` | `role` | Sets the fallback role and selects role mentions as the server-wide default. Requires Manage Server. |
| `/notify user` | `member` | Sets the fallback member and selects user mentions as the server-wide default. Requires Manage Server. |
| `/notify everyone` | `enabled`, `confirmation` | Explicitly enables/disables `@everyone`. Requires Administrator and exact confirmation `ENABLE` or `DISABLE`. Enabling it also sets it as the server-wide default target; disabling it resets that default to `none` if needed. Use sparingly. |

### More detailed settings

| Command | Options | What it does |
|---|---|---|
| `/notify route` | `category`, `channel`, `target`, optional `role`, `member`, `confirmation` | Sets a fallback route for one category: anime episodes, manga chapters, news/announcements, or schedules/delays. For `target:Role`, select `role`; for `target:User`, select `member`; for everyone, an administrator must enter `ENABLE`. Requires Manage Server. |
| `/notify title-route` | `title`, `category`, `channel`, `target`, optional `role`, `member`, `confirmation` | Sets a route override for one tracked title and one category. Same target rules as `/notify route`. Requires Manage Server. |
| `/notify route-clear` | `category`, optional `title` | Without `title`, removes that category's fallback route. With a tracked `title`, removes only that title/category override. Requires Manage Server. |
| `/notify title` | `title`, `enabled` | Turns all notifications for one tracked title on/off. This is the master switch for that title. Requires Manage Server. |
| `/notify types` | `title`, optional `episodes`, `chapters`, `schedule_changes`, `delays`, `hiatus`, `announcements` | View current alert types when no switches are supplied, or change only the switches you specify. Omitted switches remain unchanged. Requires Manage Server. |
| `/notify quiet-hours` | `start`, `end`, optional `timezone` | Sets quiet hours using `HH:MM` 24-hour times and an IANA timezone such as `Europe/London`. Use a window such as `22:00` to `07:00`. Enter `OFF` for both start and end to disable quiet hours. Ordinary alerts are held; official announcements, delays, and hiatus notices may still be sent. Requires Manage Server. |

### If more than one route is set

For a particular show and type of update, the bot uses the show’s own route first. If there isn’t one, it tries the category default, then the older server-wide channel/mention settings. A title route for anime episodes does not automatically configure its news or schedule alerts. Use `/notify routes` to inspect saved routes.

For `@everyone`, Discord's server and channel permissions still apply. The bot must have permission to view/send in the selected channel, and roles/users must still exist. A successful test confirms a message was sent through the selected route; it cannot guarantee every future external release will be detected.

## Other useful commands

| Command | Options | What it does |
|---|---|---|
| `/random` | `category`, optional `minimum_score`, `genre`, `max_episodes`, `year` | Picks an AniList anime that matches Currently releasing, Fully released, or Highly rated. The minimum score applies to Highly rated (default 75/100). Optional filters let you choose a genre, cap the episode count, or choose a starting year. |
| `/status` | none | Shows uptime, Discord latency, database responsiveness, tracked entry count, the latest monitoring run, recent notification delivery counts, and recorded provider health. |
| `/settings` | none | Shows provider availability, monitoring configuration, and this server's basic notification defaults. |
| `/help` | none | Displays a compact command overview. |

## If something isn’t working

- **A title isn't in autocomplete:** add it with `/track add` first, or use `/track search` to find the correct catalogue entry.
- **No route is configured:** use `/notify show` for a specific title or `/notify channel` for a server-wide fallback.
- **The test says notifications are disabled:** check `/notify title` and `/notify types` for that title.
- **A test message cannot be delivered:** check the selected channel and the bot's `View Channel`, `Send Messages`, and (for embeds) `Embed Links` permissions. Check the logs for provider/database errors.
- **No episode is detected:** check `/release check` and `/status`. Data sources may be delayed or may not provide reliable schedules. MangaDex monitoring is limited to English whole-number chapters in this version.
- **A slash command is missing:** check startup logs for command-sync errors, then wait for Discord to propagate registered commands.


## Finding something to watch

`/random` can do more than pick from a release category. Choose a genre, limit the number of episodes, or set a starting year if you have something specific in mind. These filters are optional, so you can leave them blank for a surprise. The score threshold is only used for **Highly rated** picks. If the filters are too restrictive, remove one and try again.

`/status` is the quick health check. It shows whether the database responds, the bot's Discord latency, the last monitoring run, provider check health, and notification outcomes from the last 24 hours.
