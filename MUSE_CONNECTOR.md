# Scout by gamedai, Meta Muse connection

Muse (muse.ai) has no downloadable connector SDK. There are two ways a Muse
agent reaches this server, and both use the same hosted MCP URL:

`https://gamedai-mcp.fly.dev/mcp`

Nothing is uploaded to Meta. Muse builds its bridge with the official MCP SDK
over streamable HTTP and calls the advertised tools directly.

## 1. Custom integration (works today, no review)

Any Muse user can connect gamedai with one message:

> Build a custom integration to gamedai. Its MCP server URL is
> https://gamedai-mcp.fly.dev/mcp. It gives me live NFL scores, Wire news,
> Scout player grades, start/sit calls, and fantasy rankings. No login needed.

Meta does not review custom integrations. Users trust the endpoint directly.

## 2. Directory connector (submitted at muse.ai/platform)

The form has three steps. These are the values to enter.

### Overview

| Field | Value |
| --- | --- |
| Connector name | Scout by gamedai |
| Company / developer | gamedai (omniviewai) |
| Product website | https://gamedai.app |
| Icon (512x512 PNG) | https://gamedai.app/icon.png |
| Accepts payments | No |
| Work email | hello@gamedai.app |
| Support | hello@gamedai.app |
| Privacy policy | https://gamedai.app/privacy |
| Terms of service | https://gamedai.app/terms |

Example prompts:

- "What's the score of the Bills game right now?"
- "Give me the latest NFL news from the Wire."
- "What's Josh Allen's Scout grade this season?"
- "Start Josh Allen or Lamar Jackson in week 4?"
- "Show me the top PPR running backs this week."

Description: Scout by gamedai gives agents read-only NFL intelligence. Live
game scores, the Wire news feed, Scout player grades, head-to-head start/sit
recommendations, and positional fantasy rankings. All tools are read-only and
non-destructive. Grades cite their data source and license in every response.

### Technical specs

| Field | Value |
| --- | --- |
| Connection type | Existing MCP |
| Hosted MCP endpoint | https://gamedai-mcp.fly.dev/mcp |
| Documentation | https://github.com/omniviewai/gamedai-nfl-mcp |
| Authentication | None. Public, unauthenticated. |
| Access requirements | No account needed. No regional limits. Backend errors return structured `code` / `http_status` / `message` objects, never stack traces. Scout tools return `tier: public_degraded`, the name of the free tier; it is the only tier these routes serve and is unrelated to auth. |

### Review

Confirm authorization to submit, acknowledge that submission does not
guarantee approval, and accept the Muse Connector Terms. Meta then runs
functional, security, and legal review plus end-to-end testing against the
live endpoint above.

## Tools advertised

- `get_game_scores(date?, event_id?)`
- `get_wire_news(page?, page_size?)`
- `get_player_grade(player, season?, week?)`
- `get_start_sit_recommendation(player_a, player_b, week, season?)`
- `get_scout_rankings(position?, scoring?, week?)`

All five carry `readOnlyHint: true` and `destructiveHint: false`. Season
defaulting follows the rule in `README.md`.

## Requested vs verified context in responses

An agent must not report a requested week as the week the data is for. The
responses keep the two apart:

- Start/sit: `requested_season` and `requested_week` are the query, added by
  this server. The backend does not report a source week; the projection row
  it read is for exactly that season and week or the answer is ungrounded.
- Rankings: `requested_week` is the query. `source_season`, `source_week`,
  and `source_status` come from the backend, which reads them from the
  FantasyPros body. Null means the body did not say; it is never copied from
  the request. `source_status` other than `ok` explains an empty list
  (`disabled`, `upstream_error`, `empty`, `rate_limited`).
- Player grade: `stats_season` and `attribution` say which completed season
  the grade was computed from and credit nflverse.

Fields that are null are unknown, not zero and not "current".

## Data freshness, verified 2026-09-27

- Projection rows (Sleeper, ESPN, FantasyPros) are written by a daily
  `projection_refresh` cron at 04:00 UTC, gated by
  `PROJECTION_REFRESH_ENABLED`, plus the manual
  `backend/scripts/backfill_sleeper_projections.py`. The backend's `/healthz`
  reports `projection_refresh_freshness`, which is a record of the cron's
  last run, not a census of the table. On 2026-09-27 it showed the last
  cron run at 2026-09-06 covering 2026 weeks 1 and 2. Rows written by the
  manual script would not appear there, so this does not prove weeks 3 to 5
  are absent; it proves the cron has not written them. Actual coverage
  needs a DB query. Sleeper's free feed had usable PPR points for weeks 3
  to 5 when checked.
- Rankings are fetched live from FantasyPros for the current calendar-year
  season. `source_week` is what the FantasyPros body reports. With no week
  requested it returned `0`, which is not a week number and does not
  establish that the board is current-week; treat it as "the source's
  default board, week unspecified". With `week=4` requested it returned `4`.
- The start/sit "tie" for 2026 weeks with `grounded: true` has two causes.
  The first, rows with null points comparing as 0.0 to 0.0, is fixed and
  deployed. The second is the start/sit confidence engine
  (`startsit_confidence/serving_pipeline.py`): it marked a player as found
  once the name resolved, then filled every missing feature with the
  training median, so two players with no current-season history got the
  identical projection. A follow-up fix makes such a player unsupported
  (no observed rolling-history feature at all), which sends the sources
  layer to its stored-projection-row fallback. With rows, the rows decide;
  with none, the public answer is unavailable. Legitimate all-zero
  histories and genuine ties are unchanged. So a projection backfill does
  affect the answer once that fix is deployed, through the fallback, even
  though it does not change what the engine itself predicts.

## Verification status

Two kinds of checks, kept separate.

### Checks run from this repo (generic MCP client, not Muse)

Exercised end to end with a raw streamable HTTP client, no credentials, on
2026-09-27:

- `initialize` negotiated protocol 2025-03-26, server `Scout by gamedai 1.28.1`.
- `get_game_scores` returned the live Sunday slate with in-progress clocks.
- `get_wire_news(page_size=3)` returned three current articles with sources.
- `get_player_grade("Josh Allen")` returned an A+ with nflverse attribution.
- `get_scout_rankings(QB, PPR)` returned 50 rows; week 20 returned an empty
  list rather than stale rows.
- `get_start_sit_recommendation` returned the null "tie" described above for
  2026 weeks and real picks for 2025 week 4.

These prove the endpoint works for a generic MCP client. They do not prove
Muse used it.

Repeated after omniviewai/gamedai#1964 deployed (2026-09-27 21:35 UTC, both
Fly apps green, server still reports 1.28.1):

- Scores: 14 games, 4 live. News: 3 articles. Grade: Josh Allen A+,
  `stats_season: 2025`, nflverse attribution.
- Start/sit 2025 week 4: `requested_season: 2025`, `requested_week: 4`,
  grounded pick crediting Sleeper.
- Start/sit 2026 week 4: `requested_season: 2026`, `requested_week: 4`,
  still `recommendation: null`, `grounded: true`, tie rationale. The engine
  median-imputation cause above is why; the null-row fix alone did not
  change this response. One call during the deploy restart returned
  `backend_unavailable`; two retries succeeded.
- Rankings QB PPR: `requested_week: null`, `source_status: ok`,
  `source_season: 2026`, `source_week: 0`, 50 rows. With `week=4`:
  `requested_week: 4`, `source_week: 4`, 35 rows.

### Checks run inside Muse

User-reported, 2026-09-27, against the server as deployed before the fixes
in omniviewai/gamedai#1964. Not reproduced from this repo.

- Muse first failed on its SSE client, corrected it, then called all five
  tools successfully.
- `get_wire_news` returned 10 articles.
- `get_player_grade` for Josh Allen showed `stats_season: 2025`.
- `get_start_sit_recommendation` returned a null recommendation with
  `tier: public_degraded` (the null-projection "tie" described above).
- `get_scout_rankings` returned 50 QBs with `tier: public_degraded` and no
  source week (the field did not exist yet).

This demonstrates connectivity from Muse. It does not validate the fixes.

User-reported, 2026-09-27 20:46 local, after omniviewai/gamedai#1964 and
#1966 deployed. `get_start_sit_recommendation` for Josh Allen vs Lamar
Jackson, season 2026 passed explicitly, week 4:

- `requested_season: 2026`, `requested_week: 4`, `tier: public_degraded`
- `recommendation: null`, `grounded: false`, `isError: false`
- rationale: "We can't compare these two right now, so we're not going to
  guess. Projection data is unavailable."

That is the expected post-fix answer: an explicit unavailable instead of an
invented tie. The earlier Muse call, made before the fixes, returned
`grounded: true` with the "no edge either way" line. The difference is the
backend fix deployed between the two calls, not the explicit `season`; this
pair of results does not establish any difference between explicit and
default season handling.

Still unverified through Muse after the fixes: rankings `requested_*` and
`source_*` fields, and behaviour when a projection exists for one player
but not the other.

No Scout key is ever sent to the MCP client. The same considerations in
`CHATGPT_APP.md` about key enforcement and `/readyz` apply here.
