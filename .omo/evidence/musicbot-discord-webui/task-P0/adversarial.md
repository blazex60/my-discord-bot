# P0 adversarial QA receipt

- Dirty worktree: baseline and post-QA fingerprints stayed `.omc/project-memory.json=4ddf75a1876fa80bde1105409593d4624752c7173583b7a9b6cd95b8af7d9096` and `DiscordVoiceVox=219e765543898def4ed8f17deba08f5ff89545db269da09f88e8e326965337bd`; exit `0`; assertion: unrelated changes preserved.
- Misleading success output: `invalid-fake-success.json` printed a success token but exited `7`; isolated runner test passed only because the runner rejected `exit code 7`.
- Stale generated state: a second `npm run qa:task -- P0 happy` exited nonzero with `Stale evidence collision`; existing happy evidence was not overwritten.
- Malformed manifest: `invalid-malformed.json` exited nonzero on JSON parsing before evidence execution.
- Manifest collision: `invalid-collision.json` was rejected for shared port `46110` before execution.
- Missing assertion: `invalid-missing-assertion.json` was rejected by the schema before execution.
- Path escape: `invalid-path-escape.json` exited nonzero with `Step cwd escapes project root: ..`.
- Directory argv: `invalid-directory-argv.json` exited nonzero with `Directory argv is forbidden for node --test: src`.
- Unknown selector: `node scripts/qa-task.mjs P0 missing test/qa/manifests/task-P0.json` exited nonzero with `Unknown case: missing`; unit coverage also rejects an unknown task.
- Unsupported runtime: the failing-first unit contract rejects Node `19.9.0` and accepts Node `20.0.0`; all CLI entry points invoke the same guard.
- Leaked resource: `invalid-leaked-resource.json` was run in a temporary evidence sandbox; the runner rejected `.qa-p0-leak`, and test cleanup removed it.
- Hung browser-command class: `invalid-hung-browser.json` was killed at its 100ms deadline and rejected as timed out; no matching process remained.
- Command: `node --test test/qa/invalid-fixtures.test.mjs`; cwd `music-bot/`; exit `0`; assertion: all six isolated failure-fixture tests passed; artifact: this receipt; cleanup: sandbox evidence and leak probes removed.
- Resource tuple: per-fixture ports `46110-46116`, temporary database/profile/compose labels only; none were opened or left active.
