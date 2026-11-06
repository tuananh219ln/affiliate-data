# Affiliate Data: rules for every AI agent

Collects Shopee and TikTok affiliate data (products, commission, links, orders, trending videos)
by driving a real browser, and serves it over an API. See [README.md](README.md).

- **Talk to the user in Vietnamese.** Code, comments, docs and commit messages are in English;
  messages the API returns to people are in Vietnamese.
- **Scraping happens only in the worker**, one job at a time, slowly. Routes enqueue and return.
- **Never try to get past a captcha, hide automation or rotate accounts/proxies.** On a captcha or
  login wall the job stops and the session is marked for a person to log in again.
- **Do not hit the real sites from tests.** Parsers are tested with sample responses; base URLs
  are env vars so a test can point a browser at a local fake page.
- **Sessions are secrets.** Stored encrypted, never returned by the API, never committed
  (`*-session.json` is ignored). Agents do not read `.env` or session files.
- **Never edit a migration that is on `main`.** Add a new one.
- **Bug fixes start with a failing test.** A parser fix starts with a test built from a dump.
- **Never make a check pass by weakening it.**
- Done means: `ruff check` and `ruff format --check` pass and tests for the change exist and pass.
- Git: branch from `main`, Conventional Commits, PRs reviewed before merging; no force-push.
