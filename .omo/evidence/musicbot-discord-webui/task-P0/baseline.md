# P0 baseline dirty-worktree receipt

- Command: `git status --short` from repository root before edits.
- Exit status: `0`.
- Baseline summary: `M .omc/project-memory.json`, dirty `DiscordVoiceVox` gitlink, untracked `.omo/`, and untracked `.omx/`.
- Scoped P0 diff before edits: empty for `music-bot/`, `.omo/evidence/musicbot-discord-webui/task-P0/`, and the two requested notepads.
- Tracked baseline hashes: `music-bot/package.json=807298c8e4927da5db7acdd6269b90ec0cffeddbae251a447076960a9acc6863`; `music-bot/package-lock.json=a926530ecad44f44c34b70445c741424941874573465d6af587f02e8ef2993a6`.
- Unrelated tracked diff fingerprint: `.omc/project-memory.json=4ddf75a1876fa80bde1105409593d4624752c7173583b7a9b6cd95b8af7d9096`.
- Unrelated nested-worktree status fingerprint: `DiscordVoiceVox=219e765543898def4ed8f17deba08f5ff89545db269da09f88e8e326965337bd`.
- Assertion: P0 edits must not change either unrelated fingerprint or stage `.omc`, `.omx`, `DiscordVoiceVox`, other bots, secrets, database files, or runtime state.
- Cleanup: observation-only commands created no resources.
- Resource tuple: `port=none`, `database=none`, `browserProfile=none`, `composeProject=none`.
