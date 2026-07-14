# P0 ultraqa applicability

- `native_abi`: applicable; `better-sqlite3` opened and queried an in-memory database after clean install.
- `dirty_worktree`: applicable; unrelated tracked and nested-worktree fingerprints were unchanged.
- `oauth_replay`: not applicable because P0 adds no OAuth flow or callback.
- `pkce_state`: not applicable because P0 adds no PKCE or authorization state.
- `csrf_origin`: not applicable because P0 adds no HTTP mutation routes.
- `cookie_flags`: not applicable because P0 creates no cookies.
- `key_rotation`: not applicable because P0 creates no cryptographic keyring.
- `token_plaintext`: not applicable because P0 handles no bearer, refresh, or session token.
- `snowflake_precision`: not applicable because P0 parses no Discord identifiers.
- `auth_epoch`: not applicable because P0 adds no authentication persistence.
- `vc_race`: not applicable because P0 does not edit voice/session production code.
- `stale_revision`: not applicable because P0 adds no queue snapshot or revision behavior.
- `serializer_external_await`: not applicable because P0 adds no guild serializer or external playback effect.
- `admin_bypass`: not applicable because P0 adds no admin API/UI.
- `readiness`: not applicable because P0 adds no production server lifecycle or readiness route.
