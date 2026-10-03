# Scout by gamedai — ChatGPT App connection

This app uses the Apps SDK over MCP. Connect the app to the hosted MCP URL:

`https://gamedai-mcp.fly.dev/mcp`

There is no OpenAPI upload. The MCP server advertises its tools directly:

- `get_game_scores(date?, event_id?)`
- `get_wire_news(page?, page_size?)`
- `get_player_grade(player, season?, week?)`
- `get_start_sit_recommendation(player_a, player_b, week, season?)`
- `get_scout_rankings(position?, scoring?, week?)`

An omitted `season` defaults to the latest complete stats season for grades, and to the current league year for start/sit
for player grades and start/sit, using the calendar rule documented in
`README.md`. Rankings derive their source season in the backend. It sends the
optional Scout key only on Scout API calls.

The server sends `X-Scout-API-Key` only when `GAMEDAI_SCOUT_API_KEY` is set in
its host environment. It isn't currently configured, and the backend facade
doesn't enforce keys on the preview backend today. If key enforcement is
turned on, the Fly secret must be set before enforcement or `/readyz` flips to
503 and deploy smoke fails.

The existing `/.well-known/openai-apps-challenge` route remains available for
domain verification. Product information is at [gamedai.app](https://gamedai.app).
