# P0 failing-first receipt

- Command: `node --test scripts/run-node-tests.test.mjs`
- CWD: `music-bot/`
- Exit status: `1`
- Assertion: failed with `ERR_MODULE_NOT_FOUND` for `scripts/run-node-tests.mjs`, proving the enumerator contract preceded its implementation.
- Command: `node --test test/qa/qa-task.test.mjs`
- CWD: `music-bot/`
- Exit status: `1`
- Assertion: failed with `ERR_MODULE_NOT_FOUND` for `scripts/qa-manifest.mjs`, proving the manifest/runner contract preceded its implementation.
- Artifacts: this receipt and the two test files named above.
- Cleanup: no child process, browser, profile, database, port, or temporary project remained after either Node process exited.
- Resource tuple: `port=none`, `database=none`, `browserProfile=none`, `composeProject=none`.

## Unsupported-runtime extension

- Command: `node --test scripts/run-node-tests.test.mjs`
- CWD: `music-bot/`
- Exit status: `1`
- Assertion: failed because `assertSupportedNodeVersion` was not exported, proving the unsupported-Node rejection test preceded that implementation.

## Review-hardening extension

- Command: `node --test test/qa/qa-task.test.mjs`
- CWD: `music-bot/`
- Exit status: `1`
- Assertion: failed because `createChildEnvironment` was not exported, proving environment filtering, output redaction, symlink rejection, empty-case parity, and timeout-race tests preceded the review hardening implementation.

## Atomic evidence-write extension

- Command: `node --test test/qa/qa-task.test.mjs`
- CWD: `music-bot/`
- Exit status: `1`
- Assertion: failed because `writeExclusiveFile` was not exported, proving the no-follow exclusive-write regression test preceded its implementation.
