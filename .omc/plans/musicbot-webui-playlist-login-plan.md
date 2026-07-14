# RALPLAN-DR Plan — music-bot Web UI + プレイリスト連携 + ログイン機能

- Plan ID: musicbot-webui-playlist-login-plan
- Mode: **RALPLAN-DR / DELIBERATE** (trigger: authentication / OAuth / encrypted token storage = high-risk category)
- Source spec: `.omc/specs/deep-interview-musicbot-webui-playlist-login.md` (authoritative; not re-litigated here)
- Target: brownfield `music-bot/` (discord.js v14, Node >= 20, ESM)
- Generated: 2026-07-14
- Status: **pending approval** (consensus reached after 2 review rounds — Architect: APPROVE WITH CHANGES x2, Critic: REVISE x2, all required changes applied; no unresolved blocking items)

---

## PART 1 — RALPLAN-DR SUMMARY

### Principles (guiding constraints)

1. **Secrets stay in `.env`, never in source or DB in plaintext.** Extends the existing `DISCORD_TOKEN` / `CLIENT_ID` convention (`music-bot/.env.example`, `music-bot/CLAUDE.md` "シークレット管理"). New secrets (`SPOTIFY_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET`, `DISCORD_CLIENT_SECRET`, token encryption key, internal API shared secret) all live in `.env` only. OAuth tokens stored in SQLite are always AES-256-GCM encrypted at rest.
2. **Reuse the existing VC-presence permission pattern; do not invent a parallel one — but adapt it deliberately for the web context.** `src/permissions.js#checkSameVoiceChannel` and `src/queueEditorInteractions.js` already encode "same VC as the bot = may operate". The Web permission model (VC-presence for basic ops, Admin role for unconditional extended ops) must be enforced by the **Bot process**, which is the only process with live Discord voice state — not re-implemented blindly in the web tier. **Two deliberate divergences from `checkSameVoiceChannel` are documented and required (see item 6 of the revision changelog):** (a) the web resolver checks **only the voice-channel match (`inVoice`)**, not the original `inVoice && inChat` text-channel condition — the web UI has no originating Discord text channel, so `inChat` is inapplicable; this is an intentional behavior change, not an accidental drop. (b) `permissions.js:7` returns `true` when there is **no session** (an interaction-context convenience); the web resolver instead **denies `basic` when there is no session** — only an Admin-role bypass may succeed with no active session. Default-allow is forbidden in the web context.
3. **The Bot process NEVER touches `better-sqlite3`; the Web process owns ALL DB writes.** `src/sessions.js` (the `sessions` Map), `GuildPlayer` (`src/player.js`), and `GuildQueue` (`src/queue.js`) are in-memory objects living only in the Bot process. The web container physically cannot call `session.player.pause()`; any control action is delegated to the Bot process over its internal HTTP API. Conversely, the Bot process opens **no** SQLite connection at all — the Web process is the sole owner of every read and write to `data/musicbot.db` (auth, tokens, import jobs, import-track match results, session/OAuth-state rows). When the bot resolves/enqueues an import batch it **reports progress back to the Web process over the internal HTTP API** (or the web polls `GET /import/:jobId/progress`), and the **Web process** persists `import_jobs`/`import_tracks` counts. This keeps synchronous `better-sqlite3` writes entirely off the Discord voice/Opus event loop. SQLite is durable-facts-only; the Bot API is the sole channel for imperative live actions. This resolves the earlier contradiction where the bot was said to "write import-job counts" — it does not; the web does.
4. **Prefer already-declared, unused dependencies; add no new infra unless forced.** `fastify@5.6.2`, `@fastify/cookie@11.0.2`, `@fastify/static@8.3.0`, `better-sqlite3@12.4.1`, `react-router-dom@7.9.5`, `react@19`, `zod@4` are already in `package.json` but unused. `node:crypto` covers encryption with zero new deps. Single-host homelab (GTX 980 Ti box) — no Redis/broker unless the design truly requires it.
5. **Reuse existing music resolution, do not duplicate it.** `src/search.js#searchYoutube` and `createTrack` (`src/queue.js`) already resolve YouTube tracks via yt-dlp. Spotify→YouTube matching and the final enqueue must funnel through the exact same track shape (`{ title, webpageUrl, duration, requestedBy, thumbnail }`) so imported tracks are indistinguishable from slash-command tracks.

### Decision Drivers (top 3)

1. **In-memory runtime state vs. separate process** — the single hardest constraint. Playback control (pause/resume/skip/stop/volume) and queue mutation are live method calls in the Bot process; the web tier is a different container. The IPC choice is dominated by this.
2. **Security of OAuth tokens** — access/refresh tokens for Spotify + Google must be encrypted at rest, refreshed safely (Spotify rotates refresh tokens), and degrade gracefully to a "再連携" (re-link) button on failure. This is the reason we are in DELIBERATE mode.
3. **Homelab operational simplicity** — one machine, Docker Compose, Cloudflare Tunnel. Minimize moving parts, avoid new stateful infrastructure, keep `network_mode: host` compatibility (required by the bot per `music-bot/CLAUDE.md`).

### Viable Options — Bot ⇄ Web IPC mechanism (the decision the spec deferred to Architect)

The spec (Constraints line 43, Technical Context line 89) explicitly leaves the Bot↔Web communication mechanism to this planning pass. Three viable options:

#### Option A — Shared SQLite as single source of truth, both processes poll
Both the bot and web open the same `better-sqlite3` file (WAL mode). Web writes a "command" row (e.g. `pause guild=G`); the bot polls a `control_commands` table and applies it against its in-memory `sessions` Map; current playback state is mirrored bot→DB continuously so the web can render it.

- **Pros:** One transport, one store. No network coupling between containers. Trivially survives container restarts (durable). Reuses only `better-sqlite3`.
- **Cons:** Imperative live control over a polled table is awkward and laggy (poll interval = perceived button latency). Runtime state (`GuildPlayer` internals, voice connection status) is **not** naturally representable in SQLite — the bot would have to continuously serialize live state to the DB purely for the web to read it, which is duplicated bookkeeping and can drift. Permission checks need live voice state that also isn't in SQLite. Concurrency: multiple writers to a command table need careful claiming. Poor fit for real-time control.

#### Option B — Bot process exposes a small internal HTTP/REST API; web calls it (RECOMMENDED, hybrid)
The Bot process starts a tiny fastify (or `node:http`) server bound to the internal/loopback interface, guarded by a shared-secret bearer token (`BOT_API_TOKEN` from `.env`). It exposes imperative endpoints (`POST /control/:guildId/pause`, `.../skip`, `POST /import/:guildId/enqueue`, `GET /state/:guildId`, `GET /permission?userId=&guildId=`). These operate directly on the in-memory `sessions` Map and reuse the VC-presence/Admin logic. **In parallel**, SQLite (WAL) is the persistent store for auth: `service_links` (encrypted tokens), `import_jobs`, `web_sessions`. Crucially, **only the Web process opens `better-sqlite3`** — the bot process holds no DB handle; it reports import progress back to the web over the internal API and the web persists all counts (Principle 3). The web tier owns OAuth flows and every DB write; the bot owns live control and authoritative permission decisions.

- **Pros:** Natural, low-latency imperative control. The bot stays the single owner of its live state — no serialization/drift. Permission checks run where the voice state actually lives (Principle 2). Clean separation: DB = durable facts, API = live actions. No new infrastructure — fastify is already a dependency. Both concerns use the right tool.
- **Cons:** Two mechanisms to reason about (HTTP for live, SQLite for durable). Requires a shared secret and network reachability between containers (straightforward with `network_mode: host` + loopback, or a compose bridge). Bot process now has an inbound surface (mitigated: loopback-bound, token-gated, never exposed via the tunnel).

#### Option C — Lightweight message bus (Redis pub/sub or embedded broker)
Introduce Redis (or similar); web publishes commands, bot subscribes and applies; bot publishes state snapshots.

- **Pros:** Decoupled, supports fan-out and future multi-instance. Good real-time semantics.
- **Cons:** **New stateful infrastructure** on a single-host homelab — violates Principle 4. Overkill for one bot + one web process. Still needs SQLite for durable encrypted tokens anyway, so it does not remove the DB, it only adds a third moving part. Operational cost (another container, persistence/eviction config) unjustified at this scale.

#### Recommendation: **Option B (hybrid: internal Bot HTTP API + shared encrypted SQLite)**

Option B is recommended because Decision Driver #1 (in-memory runtime state in a separate process) makes imperative HTTP the natural fit for live control, while Decision Driver #2 (token security) is served by encrypted SQLite as the durable store — each concern uses the correct tool. Option A is not invalidated (it works) but is rejected for real-time control: representing live `GuildPlayer`/voice state in a polled table is duplicated bookkeeping that drifts, and button latency equals poll interval. Option C is rejected under Principle 4: it adds stateful infrastructure without removing the DB requirement, unjustifiable for a single-host deployment. If a future requirement adds multiple bot shards or horizontal web scaling, revisit Option C.

### Pre-mortem (3 concrete failure scenarios — DELIBERATE requirement)

1. **Spotify refresh-token rotation race → user silently logged out of Spotify.**
   Two concurrent imports both read the same near-expired `service_link`, both POST `/api/token` to refresh. Spotify may rotate (invalidate) the old refresh token; the second refresh fails, and whichever writes last may persist a dead token. User sees repeated "再連携" prompts.
   *Mitigation:* Single-flight refresh per `(discord_user_id, service)` — an in-process async mutex in the web tier plus an optimistic-concurrency guard on `service_links.updated_at` (write only if row version unchanged). Refresh is centralized in one `tokenStore.getValidAccessToken()` path; callers never refresh ad-hoc. On refresh failure, mark link `status='needs_relink'` exactly once.

2. **Cloudflare Tunnel + OAuth redirect_uri mismatch → login/link loop.**
   Behind the tunnel the app sees an internal host/scheme (`http://localhost:PORT`), so it builds `redirect_uri` that does not match what is registered at Discord/Spotify/Google (`https://music.example.com/...`), and providers reject with `redirect_uri_mismatch`. Separately, session cookies set without `Secure`/`SameSite`/proxy-trust fail over the proxied HTTPS origin, so login never sticks.
   *Mitigation:* A single `PUBLIC_BASE_URL` env var is the sole source for every `redirect_uri` and cookie domain — never derive from request host. Register exactly those callback URLs at each provider. **fastify `trustProxy` is scoped to the actual proxy hop, not a blanket `true`.** Because `docker-compose` uses `network_mode: host`, the web port is directly LAN-reachable (not only via the tunnel), so a blanket `trustProxy: true` would let any LAN peer spoof `X-Forwarded-For`. `cloudflared` runs on the same host and forwards to `localhost`, so trust is scoped to loopback: `trustProxy: ['127.0.0.1', '::1']` (or Cloudflare's documented IP ranges if the tunnel is ever fronted by a non-loopback hop). Cookies `Secure; HttpOnly; SameSite=Lax`. Document the exact provider console redirect URIs in `.env.example` comments and a README section.

3. **Encryption-key loss / no rotation path → all stored tokens unrecoverable or a crash loop.**
   The AES key in `.env` is lost/changed, or `libsodium`/`crypto` throws on decrypt for a legacy row. If decrypt errors bubble up uncaught, the whole playlists route (or web boot) crashes for every user, not just the affected link.
   *Mitigation:* Encryption is fail-soft: a decrypt/auth-tag failure is caught per-row and surfaced as `status='needs_relink'` (show 再連携), never a 500. Store a `key_id` column alongside ciphertext so a future key rotation can decrypt-old/encrypt-new without a flag day. Key generation + backup documented; startup logs a fingerprint (not the key) so a key change is observable. Tokens are worthless without the key, satisfying the "encrypted at rest" acceptance criterion even if the DB file leaks.

### Expanded Test Plan (unit / integration / e2e / observability — DELIBERATE requirement)

- **Unit** (extend existing `scripts/run-node-tests.mjs --suite server`, node:test): AES-256-GCM encrypt→decrypt roundtrip + tamper (auth-tag failure) → `needs_relink`; migration runner idempotency; Spotify→YouTube matching query builder (`"title artist"` → `searchYoutube`) and `createTrack` shape parity; permission resolver truth table (VC-present member / non-present member / Admin non-present / non-Admin non-present / **no-session non-Admin → deny** / **no-session Admin → extended**, `inVoice`-only — item 6); `GuildPlayer.get status()` + `setVolume` clamp/apply (item 1/2); import-with-no-session join-vs-`409` branch (item 3); TTL sweep DELETE of expired rows (minor note); single-flight token refresh (concurrent callers → one network refresh); `redirect_uri` builder always uses `PUBLIC_BASE_URL`.
- **Integration**: two-process SQLite WAL access (bot + web open same file, concurrent read/write, no lock errors); Bot internal API endpoints against a stubbed `sessions` Map (pause/skip/enqueue/state/permission), including auth-token rejection; OAuth callback handlers with a mocked provider token endpoint (happy path, error, expired→refresh); full import job lifecycle row transitions (`running → completed` / `partial`), `matched_count`/`failed_count` correctness.
- **E2E** (extend `scripts/run-browser-tests.mjs` / Playwright `test/browser/`): unauthenticated dashboard access is gated (redirect to Discord login); logged-in VC-present user sees and successfully clicks pause/skip/queue-reorder; import flow — select a playlist, one-shot enqueue, verify tracks land and post-import re-search/replace works; expired-token surface renders the 再連携 button. Use mocked provider + a stubbed bot API to keep e2e deterministic (aligns with the existing deterministic QA harness, commit 596be65).
- **Observability**: structured JSON logs on every OAuth event, token refresh, and control action (userId, guildId, service, outcome — never token values); `import_jobs` table doubles as an audit trail (queryable via `npm run db:inspect`); `GET /healthz` on both bot API and web server; startup logs encryption-key fingerprint + `PUBLIC_BASE_URL` + resolved redirect URIs; counters for refresh-success/refresh-fail/needs-relink.

---

## PART 2 — PLAN BODY

### Requirements Summary

Add to `music-bot/` three coupled capabilities (spec Goal, lines 33-39):

1. **Web UI dashboard** (single screen): playback controls, queue view/edit, external-playlist browse + one-shot import to the Discord queue. Runs as a **separate process/container** (spec line 43).
2. **Playlist integration**: Spotify and YouTube (Google OAuth + YouTube Data API for the user's *private* playlist list — distinct from the existing yt-dlp public-playlist path, spec line 85). User picks a playlist in the UI; each track is auto-matched (Spotify tracks → `"title artist"` YouTube search) and **one-shot** bulk-enqueued regardless of match confidence; post-import per-track re-search/replace editing. Apple Music deferred (spec Non-Goals).
3. **Login/auth**: Discord OAuth gates Web UI access; after login, per-user Spotify/Google OAuth linking. Long-lived cookie session; auto-refresh OAuth tokens; 再連携 button on failure; tokens encrypted at rest in `better-sqlite3`.

Permission model (spec Constraints line 41): same-VC-as-bot users get basic ops (play control + queue edit); Admin-role users get unconditional extended ops. Exposure via Cloudflare Tunnel + custom domain; access control is the permission model, not network location.

### DB Schema Proposal (`better-sqlite3`, WAL mode)

Grounded in the spec Ontology (lines 94-105). File: `data/musicbot.db` (existing `./data` volume, currently empty). All tables created by an idempotent migration runner.

```sql
-- DiscordUser (Ontology: discordId, username, role). Role is authoritative at
-- runtime from Discord; this is a cache for display only.
CREATE TABLE discord_users (
  discord_id   TEXT PRIMARY KEY,
  username     TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL
);

-- WebUISession (Ontology: sessionId, discordUserId, cookie, expiresAt).
-- DB-backed so sessions are revocable; cookie carries only the opaque session_id.
CREATE TABLE web_sessions (
  session_id      TEXT PRIMARY KEY,      -- opaque random, stored in signed cookie
  discord_user_id TEXT NOT NULL REFERENCES discord_users(discord_id),
  created_at      INTEGER NOT NULL,
  expires_at      INTEGER NOT NULL       -- long-lived per spec line 46
);
CREATE INDEX idx_web_sessions_user ON web_sessions(discord_user_id);

-- ServiceLink (Ontology: id, discordUserId, service, accessToken(enc),
-- refreshToken(enc), expiresAt). Tokens AES-256-GCM encrypted (spec line 47).
CREATE TABLE service_links (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_user_id     TEXT NOT NULL REFERENCES discord_users(discord_id),
  service             TEXT NOT NULL CHECK (service IN ('spotify','youtube')),
  access_token_enc    BLOB NOT NULL,     -- iv || authTag || ciphertext
  refresh_token_enc   BLOB,              -- some flows omit; nullable
  key_id              TEXT NOT NULL,     -- for future key rotation (pre-mortem #3)
  scope               TEXT,
  token_expires_at    INTEGER,
  status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','needs_relink')),
  created_at          INTEGER NOT NULL,
  updated_at          INTEGER NOT NULL,  -- optimistic-concurrency guard (pre-mortem #1)
  UNIQUE (discord_user_id, service)
);

-- OAuth transaction state (CSRF + PKCE code_verifier). Short-lived.
CREATE TABLE oauth_states (
  state           TEXT PRIMARY KEY,
  discord_user_id TEXT,                  -- null for the Discord-login flow itself
  service         TEXT NOT NULL,         -- 'discord' | 'spotify' | 'youtube'
  code_verifier   TEXT,                  -- PKCE where supported
  redirect_after  TEXT,
  created_at      INTEGER NOT NULL,
  expires_at      INTEGER NOT NULL
);

-- ImportJob (Ontology: id, playlistId, status, matchedCount, failedCount).
CREATE TABLE import_jobs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_user_id TEXT NOT NULL REFERENCES discord_users(discord_id),
  guild_id        TEXT NOT NULL,         -- target GuildQueue (Ontology: Guild)
  service         TEXT NOT NULL,
  playlist_id     TEXT NOT NULL,         -- ExternalPlaylist.id
  playlist_name   TEXT,
  total_count     INTEGER NOT NULL DEFAULT 0,
  matched_count   INTEGER NOT NULL DEFAULT 0,
  failed_count    INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','completed','partial','failed')),
  created_at      INTEGER NOT NULL,
  completed_at    INTEGER
);
CREATE INDEX idx_import_jobs_user ON import_jobs(discord_user_id, created_at);

-- ExternalTrack → QueueTrack matching results (Ontology: ExternalTrack).
-- Backs the post-import verification/re-search UI (spec AC line 63).
CREATE TABLE import_tracks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id        INTEGER NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
  position      INTEGER NOT NULL,
  source_title  TEXT NOT NULL,           -- ExternalTrack.title
  source_artist TEXT,                    -- ExternalTrack.artist
  source_url    TEXT,                    -- ExternalTrack.sourceUrl
  matched_url   TEXT,                    -- resolved YouTube webpageUrl (nullable = failed)
  matched_title TEXT,
  match_status  TEXT NOT NULL DEFAULT 'matched'
                  CHECK (match_status IN ('matched','failed','replaced'))
);
CREATE INDEX idx_import_tracks_job ON import_tracks(job_id, position);
```

`Permission` (Ontology) is not a table — it is computed at request time by the Bot API from live voice state + guild roles (Principle 2). `ExternalPlaylist`/`ExternalTrack` browse data is fetched live from provider APIs and not persisted except as `import_tracks` snapshots.

### Implementation Steps (with concrete file references)

Deployment shape: **one Docker image, two Compose services** (`music-bot` = existing bot, `music-web` = new web server), different `CMD`. Shared code lives under `src/` so both services import it from the same image. This avoids a second build pipeline.

**Step 1 — Shared persistence + crypto foundation.**
New: `src/db/index.js` (better-sqlite3 connection, WAL pragma, exports prepared-statement helpers), `src/db/migrate.js` + `src/db/migrations/001_init.sql` (schema above), `src/db/crypto.js` (`encrypt(plaintext)`/`decrypt(blob)` via `node:crypto` AES-256-GCM, key from `MUSICBOT_TOKEN_ENC_KEY`, fail-soft on auth-tag error), `src/db/tokenStore.js` (`getValidAccessToken(userId, service)` with single-flight refresh + optimistic `updated_at` guard — pre-mortem #1). Wire `src/db/inspect.js` (referenced by existing `npm run db:inspect`, currently missing — create it). Reuse: none broken; `src/settings.js` JSON store stays as-is.
*Acceptance:* migrations create all tables idempotently; crypto roundtrip + tamper unit tests pass; `npm run db:inspect` prints table row counts.

**Step 2 — Bot internal control API (Option B), including prerequisite `GuildPlayer` capabilities.**

*Step 2a — extend `GuildPlayer` (`src/player.js`) with the accessors/mutators the API requires (these do not exist today and are hard prerequisites):*
- **`get status()` accessor (item 2).** `#audioPlayer` is private with no getter (`player.js:29`), so `GET /state` cannot currently report player status. Add `get status()` (returning `this.#audioPlayer.state.status`, e.g. `playing`/`paused`/`idle`) — or an equivalent `getState()` — to `GuildPlayer`, and have `GET /state/:guildId` read it. No other consumer breaks (additive).
- **`setVolume(level)` + inline volume, both resource paths (item 1, closed in full).** `player.js` has no `setVolume`/`inlineVolume` support today. Crucially there are **two** resource-creation call sites, and both must be fixed or the fix silently no-ops for any guild with normalize enabled:
  - `#createFallbackResource` (`player.js:158-163`) — change to `createAudioResource(stream, { inputType: StreamType.Arbitrary, inlineVolume: true })`.
  - `createNormalizedResource` (`normalize.js:93-120`) — this is the path used whenever `getGuildSettings(guildId).normalize` is true (`player.js:168-182`) and today returns `createAudioResource(proc.stdout, { inputType: StreamType.Raw })` with **no** `inlineVolume`, so `resource.volume` is `undefined` on that path. Add `inlineVolume: true` to this call too (`normalize.js:117-119`), and thread an optional `initialVolume` param through `createNormalizedResource(filePath, measured, { inlineVolume: true })` if a non-default starting level is desired.
  - In `GuildPlayer`, keep a `#volume` field (default `1`) applied to whichever resource is currently playing (`resource.volume.setVolume(this.#volume)` immediately after either resource-creation call returns, not just at request time), and add `setVolume(level)` that clamps `level` to `[0, 2]`, updates `#volume`, and calls `resource.volume.setVolume(level)` if a resource is currently playing. Because both paths now return `inlineVolume:true` resources, `setVolume` works identically regardless of which path produced the current resource, and the level persists correctly across the fallback/normalize boundary when a track is skipped or normalize prefetch fails over to fallback (`player.js:184-185`). Wire `POST /control/:guildId/volume` to call `player.setVolume(level)`.

*Step 2b — the API itself:*
New: `src/botApi.js` — a fastify server bound to loopback, `BOT_API_TOKEN` bearer guard, endpoints: `GET /healthz`, `GET /state/:guildId` (serialize `sessions.get(guildId)` → current track + `queue.upcoming()` + **`player.status`** + loop mode), `GET /permission?userId=&guildId=` (authoritative VC-presence + Admin check), `POST /control/:guildId/{pause,resume,skip,stop,volume}`, `POST /queue/:guildId/{remove,move}`, `POST /import/:guildId/enqueue`. Reuse: `sessions` (`src/sessions.js`), `GuildPlayer` methods (`pause/resume/skip/stop` + new `setVolume`/`status`, `src/player.js`), `GuildQueue.moveUpcoming/removeUpcoming/add` (`src/queue.js`). Update: `src/index.js` to `import { startBotApi } from './botApi.js'` and start it after `ClientReady`, passing `client` + `sessions`. **The bot process opens no DB (Principle 3):** import progress is returned in the `POST /import/.../enqueue` response and/or exposed via `GET /import/:guildId/status`, and the **web process** writes the counts.

*Permission helper (item 6).* Extract the channel-match check from `src/permissions.js#checkSameVoiceChannel` into a **pure helper** `resolveWebPermission({ member, session, adminRoleId })` (no `interaction` dependency) callable by the API. Two documented divergences from the original are **required** and enforced by tests: (1) check **only `inVoice`** (member's live voice `channelId === session.connection.joinConfig.channelId` — note the real shape is nested under `session.connection`, per `permissions.js:5` / `index.js:74`, **not** `session.joinConfig.channelId`), **dropping the original `inChat` text-channel half** — the web UI has no originating text channel, so `inChat` is inapplicable (intentional divergence, per Principle 2). (2) When there is **no session for the guild**, return `basic=false` (deny) — do **not** port `permissions.js:7`'s no-session `return true`; only the Admin-role check may still grant `extended=true` (and thus operations) with no active session.

*Import-with-no-session behavior (item 3).* When the queue drains or all humans leave VC, `sessions.js`/`index.js:80-85` destroys the session, so `POST /import/:guildId/enqueue` may arrive when the guild has **no session at all** (bot not in any VC) and there is **no channel-selection UI in scope**. **Resolution (chosen, testable):** `POST /import/:guildId/enqueue` first checks for an existing session; if none, it **joins the voice channel that the initiating user is currently in** — the request carries the acting `userId`, the bot looks up that member's live voice state, and if the member is in a VC in that guild it creates a session/joins that channel, then enqueues. If the initiating user is **not** in any VC of the target guild, the endpoint **rejects with `409 { error: 'user_not_in_voice' }`** and the UI shows "先にVCに参加してください" (join a VC first). No silent default channel is ever picked. **Signature refactor required (minor item 2):** `getOrCreateSession(interaction, channel)` in `sessions.js:10,19` reads `interaction.guildId` and `interaction.guild.voiceAdapterCreator`, but the bot API path has no Discord `interaction` object — only `guildId` and a resolved voice `channel` from the member's live voice state. Refactor `getOrCreateSession` to accept `{ guildId, guild, channel }` (a plain object carrying exactly the fields it actually reads) instead of `interaction`, and update its one existing call site (the `/play` command path) to pass `{ guildId: interaction.guildId, guild: interaction.guild, channel }` — behavior-preserving for slash commands, and usable from `botApi.js` without a synthetic interaction.

*Note:* reading member roles for the Admin check requires `GatewayIntentBits.GuildMembers` (currently only `Guilds`+`GuildVoiceStates` in `src/index.js` line 19). Add it and enable Server Members Intent (the repo already did this for vc-disconnect-bot, commit 4b47cc3).
*Acceptance:* `get status()` and `setVolume()` exist on `GuildPlayer`; `POST /control/.../volume` audibly changes level and is observable via `GET /state`; endpoints operate the live session; unauthorized calls 401; permission resolver matches the truth table (no-session non-Admin → deny); import with no session joins the acting user's VC or returns 409 if they are not in one.

**Step 3 — Web server: auth + session (Discord login).**
New under `src/web/`: `server/index.js` (fastify entry, `@fastify/cookie`, `@fastify/static` serving the built React app from `web/dist`, **`trustProxy: ['127.0.0.1', '::1']`** — scoped to the same-host `cloudflared` loopback hop, **not** a blanket `true`, because `network_mode: host` makes the web port directly LAN-reachable and blanket trust would let LAN peers spoof `X-Forwarded-For` — item 5 / pre-mortem #2), `server/auth/discord.js` (Discord OAuth2 authorize + callback → upsert `discord_users`, create `web_sessions`, set signed cookie), `server/middleware/requireAuth.js` (resolve session cookie → user or 401/redirect), `server/config.js` (reads `PUBLIC_BASE_URL`, all redirect URIs derived here — pre-mortem #2), `server/botClient.js` (HTTP client to the bot API using `BOT_API_TOKEN`), `server/cleanup.js` (**TTL sweep, minor Critic note**: a `setInterval` job — e.g. every 10 min — run only by the web process that `DELETE`s `oauth_states` and `web_sessions` rows where `expires_at < now`; idempotent, logs a count). Reuse: `src/db/*`.
*Acceptance:* unauthenticated requests to protected routes redirect to Discord OAuth; successful callback establishes a long-lived session; logout revokes the `web_sessions` row; the TTL sweep removes an artificially-expired `oauth_states`/`web_sessions` row on its next tick.

**Step 4 — Web server: per-service OAuth + provider clients.**
New: `server/auth/spotify.js`, `server/auth/youtube.js` (authorize/callback → `tokenStore` encrypt+store into `service_links`), `server/services/spotify.js` (list user playlists + tracks via Web API), `server/services/youtube.js` (list private playlists + items via YouTube Data API), `server/routes/links.js` (link status + 再連携 trigger). Reuse: `src/db/tokenStore.js` (Step 1) for all token reads/refresh.
*Acceptance:* logged-in user links Spotify and YouTube; tokens land encrypted; a forced-expiry link surfaces `needs_relink`.

**Step 5 — Import pipeline + matching + control proxy.**
New: `server/matching.js` (Spotify track `{title, artist}` → `"title artist"` query → `searchYoutube` → first result → `createTrack` shape; YouTube playlist items already carry a watch URL → resolve directly), `server/routes/import.js` (create `import_jobs`, resolve tracks, write `import_tracks`, POST batch to bot `POST /import/:guildId/enqueue`, then **the web process writes all `matched_count`/`failed_count`/`status` from the bot's response** — the bot never writes the DB, Principle 3/item 4), `server/routes/import-edit.js` (per-track re-search/replace → update `import_tracks` + enqueue replacement), `server/routes/control.js` + `server/routes/queue.js` (thin proxies to the bot API, enforcing session→permission first). **No-session import (item 3):** if the bot's enqueue call returns `409 user_not_in_voice`, `import.js` marks the job `failed` and returns a clear "先にVCに参加してください" error to the UI; it never picks a channel itself. Reuse: `src/search.js#searchYoutube`, `createTrack` (`src/queue.js`) — imported tracks are byte-identical to slash-command tracks (Principle 5).
*Acceptance:* one-shot import enqueues all matchable tracks regardless of confidence; failed matches recorded; post-import replace works; job status reflects matched/failed counts (written by the web process, not the bot); importing when the acting user is not in a VC yields a `409`-derived job-`failed` + join-VC prompt.

**Step 6 — React dashboard UI.**
New under `web/src/`: `App.jsx` (react-router-dom routes: `/` dashboard, `/login`, `/callback/*`), `pages/Dashboard.jsx` (single-screen: NowPlaying + transport controls, queue list w/ reorder/remove, playlist browser + import panel, post-import match-review panel), `components/*`, `api/client.js` (fetch wrapper, credentials include). Update: `web/src/main.jsx` to mount `<App/>` (keep `p0-smoke.jsx` + its test for the existing QA harness — do not delete). Update `web/index.html`/`web/vite.config.js` if a second entry is needed; prefer keeping `main.jsx` as the single app entry and routing internally.
*Acceptance:* controls and queue edits reflect within one poll of live state; Apple Music shown only as "準備中" (spec AC line 68); unauthenticated UI is gated.

**Step 7 — Deployment: Compose, Cloudflare Tunnel, env, Docker.**
Update `docker-compose.yml`: add `music-web` service (same `build: .`, `command` overriding CMD to run `node src/web/server/index.js`, `network_mode: "host"` to reach the bot API on loopback and keep bot compatibility, shares `./data` volume for the SQLite file, `env_file: .env`), and a `cloudflared` service (tunnel → `localhost:${WEB_PORT}`; the bot API port is **never** tunneled). Update `Dockerfile` to `COPY web/ ./web/` and add a web build stage (`npm run build:web` → `web/dist`) — the current Dockerfile copies only `src/`. Update `.env.example` with: `DISCORD_CLIENT_SECRET`, `DISCORD_OAUTH_REDIRECT`, `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MUSICBOT_TOKEN_ENC_KEY` (32-byte base64), `WEB_SESSION_SECRET`, `BOT_API_TOKEN`, `BOT_API_URL` (default `http://127.0.0.1:${BOT_API_PORT}`), `BOT_API_PORT`, `WEB_PORT`, `PUBLIC_BASE_URL`, `ADMIN_ROLE_ID` — each with a comment noting the exact provider-console redirect URI to register (pre-mortem #2). Update `music-bot/CLAUDE.md` and `README.md` with the new architecture + setup.
*Acceptance:* `docker compose up --build` starts both services + tunnel; web reachable via `PUBLIC_BASE_URL`; bot API not reachable through the tunnel.

**Step 8 — Tests + observability (per Expanded Test Plan).**
New tests alongside sources (repo convention: `*.test.js` run by `scripts/run-node-tests.mjs`): `src/db/crypto.test.js`, `src/db/tokenStore.test.js`, `src/player.test.js` (**new** — `get status()` reflects audioPlayer state; `setVolume` clamps and applies to the inline-volume resource; item 1/2), `src/botApi.test.js` (stubbed sessions — includes import-with-no-session → join acting user's VC vs. `409 user_not_in_voice`, item 3), `src/web/server/matching.test.js`, `src/web/server/auth/*.test.js` (mocked providers), permission-resolver test (**extended** truth table: no-session non-Admin → `basic=false` deny, no-session Admin → `extended=true`; `inVoice`-only, item 6), `src/web/server/cleanup.test.js` (**new** — TTL sweep deletes expired `oauth_states`/`web_sessions`, minor note). Extend `test/browser/` for the e2e flows. Add `GET /healthz` to both servers and structured logging.
*Acceptance:* `npm run check` (existing aggregate: server + web + typecheck + build + e2e) passes with the new suites.

### Testable Acceptance Criteria (refined from spec lines 55-68; ≥90% concrete)

1. A request to any dashboard data/control route without a valid `web_sessions` cookie returns 401 or redirects to Discord OAuth; after successful Discord callback the same route returns 200. *(spec AC1)*
2. `GET /permission?userId&guildId` returns `basic=true` for a user whose live voice `channelId` equals the bot's `joinConfig.channelId`, and control endpoints succeed for that user; a user not in the bot's VC and without the Admin role gets `basic=false` and control returns 403. **When there is no active session for the guild, a non-Admin user gets `basic=false` (deny — no default-allow), and only `ADMIN_ROLE_ID` holders get `extended=true` (item 6).** The resolver checks voice-channel presence only (`inVoice`), not the legacy `inChat` text-channel condition (documented divergence). *(spec AC2)*
3. A user holding `ADMIN_ROLE_ID` who is **not** in the VC gets `extended=true` and all control/queue endpoints succeed, including when there is no active session. *(spec AC3)*
4. `GuildPlayer` exposes `get status()` and `setVolume(level)`; clicking pause/resume/skip/stop/volume in the UI changes the live `GuildPlayer` state — volume via `setVolume` on an `inlineVolume: true` resource, verified for tracks on **both** the fallback path (`#createFallbackResource`) and the `normalize: true` path (`createNormalizedResource`) — via `GET /state/:guildId` (which reads `player.status`) before/after. *(spec AC2)*
5. Queue reorder/remove in the UI mutates `GuildQueue.upcoming()` order/length identically to the Discord queue editor. *(spec AC2)*
6. A logged-in user completes Spotify OAuth and a `service_links` row with `service='spotify'`, `status='active'` exists. *(spec AC4)*
7. Same for YouTube/Google. *(spec AC5)*
8. `GET /links/:service/playlists` returns the linked account's own playlists (including private, for YouTube via Data API). *(spec AC6)*
9. Selecting a playlist creates an `import_jobs` row; every Spotify track is enqueued as a `createTrack`-shaped YouTube match (`"title artist"` search) regardless of confidence; `total_count`/`matched_count`/`failed_count` are populated **by the web process from the bot's enqueue response** (the bot writes no DB — item 4); enqueued tracks appear in `GET /state/:guildId`. *(spec AC7)*
9b. Importing to a guild with **no active session** while the acting user **is** in one of that guild's voice channels causes the bot to join that channel and enqueue; importing while the acting user is **not** in any VC of that guild returns `409 user_not_in_voice`, marks the job `failed`, and the UI shows a "先にVCに参加してください" prompt — no channel is ever auto-selected. *(item 3)*
10. After import, `GET /jobs/:id/tracks` lists per-track match results; a re-search/replace request updates the `import_tracks` row and swaps the enqueued track. *(spec AC8)*
11. Forcing a `service_links` token to expired/invalid flips it to `status='needs_relink'`; the UI renders a 再連携 button; re-authorizing restores `status='active'`. *(spec AC9)*
12. Inspecting the raw `service_links` rows shows `access_token_enc`/`refresh_token_enc` as ciphertext (no plaintext token substring); decryption succeeds only with the correct `MUSICBOT_TOKEN_ENC_KEY`. *(spec AC10)*
13. `docker compose up` starts `music-bot` and `music-web` as distinct containers/processes sharing `./data`. *(spec AC11)*
14. The dashboard is reachable at `PUBLIC_BASE_URL` through Cloudflare Tunnel from an external network; the bot API port returns no response through the tunnel. *(spec AC12)*
15. No functional Apple Music link exists; any Apple Music affordance is a disabled "準備中" element. *(spec AC13)*

### Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Spotify refresh-token rotation race (pre-mortem #1) | Single-flight refresh in `tokenStore` + optimistic `updated_at` guard; one-time `needs_relink`. |
| Tunnel/redirect_uri + cookie mismatch (pre-mortem #2) | All URIs from `PUBLIC_BASE_URL`; `trustProxy`; `Secure/HttpOnly/SameSite` cookies; documented provider redirect URIs. |
| Encryption-key loss / no rotation (pre-mortem #3) | Fail-soft decrypt → `needs_relink`; `key_id` column for rotation; key fingerprint at startup; key in `.env` only. |
| Bot API accidentally exposed publicly | Bind to loopback; `BOT_API_TOKEN` bearer; never routed through the tunnel (Compose comment + Step 7 AC14). |
| `network_mode: host` port collisions (bot + web + tunnel on same host) | Explicit distinct `BOT_API_PORT`/`WEB_PORT` in `.env`; documented; `/healthz` verifies binding. |
| better-sqlite3 contention / sync writes on the voice event loop | **Resolved by design (Principle 3, item 4): the bot process opens no DB connection at all.** The web process is the sole reader/writer of `data/musicbot.db`; the bot reports import progress over the internal HTTP API and the web persists counts. This keeps synchronous `better-sqlite3` writes entirely off the Discord voice/Opus event loop and removes the two-writer contention scenario. WAL mode still enabled for the web's own concurrent request handling. |
| GuildMembers intent adds privacy surface / requires portal toggle | Enable Server Members Intent (already precedented, commit 4b47cc3); document; used only for Admin-role resolution. |
| YouTube Data API quota exhaustion | Cache the playlist list per session; batch playlist-items calls; surface quota errors as retryable UI state, not a crash. |
| Spotify→YouTube mis-match on ambiguous titles | Accepted per spec (confidence-agnostic auto-match); post-import re-search/replace is the corrective path (AC10). |

### Verification Steps

1. `cd music-bot && npm run check` — full aggregate suite (server unit, web unit, typecheck, web build, e2e) green including new suites.
2. `npm run db:inspect` after migration — all tables present, zero rows initially; re-run migration → no error (idempotent).
3. Unit: crypto roundtrip + tamper; token single-flight; permission truth table (Step 8).
4. Integration: launch bot API against a stubbed `sessions` Map; drive pause/skip/enqueue; assert live-state changes and 401 on bad token.
5. `docker compose up --build`: confirm two running containers, shared `data/musicbot.db`, both `/healthz` OK; confirm bot API unreachable via tunnel, web reachable via `PUBLIC_BASE_URL` from an off-LAN device (phone).
6. Manual OAuth E2E: Discord login → link Spotify → link YouTube → import a playlist → verify tracks enqueued and playing → force token expiry → confirm 再連携 → re-link.
7. Security check: dump `service_links`; grep for any known plaintext token substring → must be absent.

### ADR (Architecture Decision Record — DELIBERATE final requirement)

- **Decision:** Bot↔Web communication uses **Option B — a loopback-bound, token-guarded internal HTTP API on the Bot process for imperative live control, paired with a shared WAL-mode `better-sqlite3` store for durable encrypted auth/token/import data.**
- **Drivers:** (1) live runtime state (`sessions`/`GuildPlayer`/`GuildQueue`) exists only in the Bot process memory; (2) OAuth token security demands an encrypted durable store; (3) single-host homelab simplicity.
- **Alternatives considered:** Option A (shared SQLite + polling for everything) — rejected for real-time control (poll-interval latency, live-state serialization drift, permission state absent from DB). Option C (message bus/Redis) — rejected as new stateful infrastructure unjustified at single-host scale that still would not remove the DB requirement.
- **Why chosen:** each concern uses the correct tool — HTTP for imperative low-latency actions where the state lives, SQLite for durable secrets — with zero new infrastructure (fastify + better-sqlite3 already declared dependencies).
- **Consequences:** two mechanisms to operate; a shared secret + loopback reachability must be managed; the Bot process gains a guarded inbound surface (never tunneled). **Strict ownership boundary (revised this round): the Bot process opens no `better-sqlite3` connection at all — the Web process is the sole DB reader/writer, including import-job/track counts, which the bot reports back over the internal API.** This keeps synchronous SQLite writes off the Discord voice/Opus event loop. DB = durable facts (web-owned); Bot API = live actions and authoritative permission decisions.
- **Follow-ups / open questions:** multi-guild guild-switching UI in the web (spec line 92, unconfirmed in interview); horizontal scaling would revisit Option C; encryption-key rotation runbook; YouTube Data API quota budgeting; Apple Music phase-2 (MusicKit JS + paid Developer Program).

---

## Open Questions (persisted separately to `.omc/plans/open-questions.md`)

- Multi-guild: does the Web UI need a guild-switcher, or is single-guild assumed? (spec line 92 — unconfirmed in interview)
- Concrete `WEB_PORT`/`BOT_API_PORT` values and Cloudflare Tunnel hostname to register at providers.
- Encryption-key rotation operational runbook (who holds the backup, rotation cadence).

---

## Revision Changelog

### Round 1 revision — Architect (APPROVE WITH CHANGES) + Critic (REVISE), 2026-07-14

Targeted revision closing the six gaps both reviewers independently confirmed against the actual codebase, plus one minor Critic note. No rewrite: the Option-B IPC decision, DB schema shape, spec-derived requirements, pre-mortem, and test-plan structure are all retained; only the flagged items changed.

1. **BLOCKING — Volume unimplementable (item 1).** Added Step 2a: `GuildPlayer.setVolume(level)` backed by `createAudioResource(..., { inlineVolume: true })`, level persisted and re-applied per track; `POST /control/:guildId/volume` wired to it. Refined AC4; added `src/player.test.js`. *Why:* `player.js` had no `setVolume`/`inlineVolume` yet AC4 + the endpoint required it.
2. **BLOCKING — No player-status accessor (item 2).** Added `get status()` to `GuildPlayer` (Step 2a); `GET /state/:guildId` now reads `player.status`. *Why:* `#audioPlayer` was private (`player.js:29`) with no getter.
3. **BLOCKING — Import-with-no-session unspecified (item 3).** Specified: `POST /import/:guildId/enqueue` joins the acting user's current VC when no session exists, else returns `409 user_not_in_voice` with a join-VC prompt; never auto-picks a channel. Added AC9b; wired into Step 5 and botApi tests. *Why:* session is destroyed on drain/empty-VC (`index.js:80-85`) with no channel-selection mechanism in the plan.
4. **MAJOR — Bot-DB self-contradiction (item 4).** Resolved decisively: **the Bot process opens no `better-sqlite3` connection at all**; the Web process owns every DB write including import-job/track counts, which the bot reports back over the internal HTTP API. Rewrote Principle 3, Option B, the risk-table contention row, AC9, ADR consequences, and unit/step-8 test notes. *Why:* the risk table had claimed the bot writes counts synchronously on the voice/Opus event loop — now removed by design.
5. **MAJOR — `trustProxy: true` over-trusts (item 5).** Scoped to `trustProxy: ['127.0.0.1', '::1']` (same-host `cloudflared` loopback hop) in Step 3 and pre-mortem #2. *Why:* `network_mode: host` makes the web port directly LAN-reachable, so blanket trust would let LAN peers spoof `X-Forwarded-For`.
6. **MAJOR — Permission helper drops `inChat` + no-session default-allow bug (item 6).** Documented two deliberate divergences in Principle 2 and the Step 2 helper spec: (a) web resolver checks `inVoice` only — `inChat` is inapplicable to a web UI (intentional, not an accidental drop); (b) no-session case **denies** `basic` (only Admin bypass works), never ports `permissions.js:7`'s `return true`. Refined AC2/AC3 and the permission truth-table tests. *Why:* naive porting would grant everyone `basic=true` when the bot has no session.
- **Minor — TTL sweep (Critic note).** Added `server/cleanup.js`: a web-process `setInterval` that `DELETE`s expired `oauth_states`/`web_sessions` rows; added an AC and `cleanup.test.js`. *Why:* no cleanup was specified for rows carrying `expires_at`.

### Round 2 revision — Architect re-review (APPROVE WITH CHANGES) + Critic re-review (REVISE), 2026-07-14

Both reviewers independently re-confirmed the same three narrow gaps in the round-1 revision. Applied directly (mechanical, precisely-scoped fixes) rather than looping through another full Planner pass, per Critic's own note that the plan is "ACCEPT-ready" once these three close. No other content changed.

1. **Required — Volume fix covered only one of two resource-creation paths.** `GuildPlayer.setVolume`/`inlineVolume` (round-1 fix) only touched `#createFallbackResource` (`player.js:158-163`). The `normalize: true` path (`createNormalizedResource`, `normalize.js:93-120`, invoked from `player.js:168-182`) returns a resource with no `inlineVolume`, so `resource.volume` is `undefined` and AC4 silently failed for any guild with normalize enabled. Fixed: Step 2a now specifies `inlineVolume: true` on **both** `createAudioResource` call sites (`player.js` fallback and `normalize.js:117-119`), plus a `#volume` field applied to whichever resource is current so the level survives a normalize→fallback failover (`player.js:184-185`). *Why:* two independent code paths produce the playing resource; a single-path fix leaves half of production traffic unfixed.
2. **Minor — `getOrCreateSession` interaction-coupling unstated.** `sessions.js:10,19` reads `interaction.guildId`/`interaction.guild.voiceAdapterCreator`, but the bot-API import-with-no-session flow (round-1 fix item 3) has no interaction object. Step 2's permission/import-no-session paragraph now specifies the required refactor: `getOrCreateSession({ guildId, guild, channel })` replacing the `interaction` parameter, with the existing `/play` call site updated to pass the equivalent fields. *Why:* the round-1 fix specified the *behavior* (join the user's VC) without specifying the *signature change* needed to invoke it from a non-interaction caller.
3. **Minor — wrong property path for session's join config.** The permission-helper spec wrote `session.joinConfig.channelId`; the real shape (verified against `permissions.js:5` and `index.js:74`) is `session.connection.joinConfig.channelId`. A literal implementation of the former would make `inVoice` always false, denying every non-Admin user regardless of actual VC presence. Fixed in the Step 2 permission-helper paragraph. *Why:* silent property-path errors are a common source of "always-false" permission bugs; caught here before implementation rather than after.
