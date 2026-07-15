# P0 manual Chromium receipt

- Command/surface: Playwright MCP `browser_navigate` to a deterministic `data:text/html` page, then `browser_run_code_unsafe` with `page.getByTestId('p0-manual-status')`, then `browser_close`.
- CWD: Playwright-managed browser process; no repository server required.
- Exit status: all three operations succeeded.
- Assertion: selector `[data-testid="p0-manual-status"]` had exact text `P0 manual Chromium ready`; context contained one page before close; close returned `No open tabs`.
- Artifact path: this receipt. The MCP-generated transient snapshot was deleted immediately and was not staged.
- Cleanup: page closed; no tabs, browser profile, process, or repository snapshot remained.
- Resource tuple: `port=none`, `database=none`, `browserProfile=Playwright-MCP-ephemeral`, `composeProject=none`.
