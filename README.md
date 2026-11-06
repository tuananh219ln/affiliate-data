# Affiliate Data

A small service that collects Shopee and TikTok data for affiliate work and serves it over an
HTTP API, so tools such as Reels Studio can pick products to make videos about.

What it collects:

| Job kind | What it does | Needs login |
| --- | --- | --- |
| `shopee.search` | Products from a shopee.vn keyword search (price, sold, rating) | Shopee |
| `shopee.offers` | Products from the Shopee Affiliate dashboard, with commission rate | Shopee Affiliate |
| `shopee.links` | Affiliate short links for saved Shopee products (custom-link tool) | Shopee Affiliate |
| `shopee.report` | Orders and commission from the conversion report | Shopee Affiliate |
| `tiktok.trending` | Videos for a keyword, with views, likes, comments, shares | TikTok |
| `tiktok.products` | TikTok Shop affiliate marketplace products, with commission rate | TikTok Shop creator |
| `tiktok.report` | Affiliate orders and commission | TikTok Shop creator |

## How it works

```text
client ──HTTP──> api (FastAPI) ──> Postgres <── worker ──> Chromium (Playwright) ──> shopee.vn / tiktok.com
```

- The API never scrapes inside a request. `POST /api/jobs` enqueues a job; the worker runs one job
  at a time in a real browser with the platform's saved login, reads the JSON the page itself
  loads, and saves the rows. Results are read with `GET /api/products`, `/api/videos`,
  `/api/conversions` and `/api/conversions/summary`.
- **Watches** (`/api/watches`) repeat a job every N hours (6 at the least), e.g. a daily report.
- **Logins are done by a person.** `python -m affiliate_data login shopee` opens a visible
  browser; you log in (captcha and OTP included), press Enter, and the session (cookies) is saved
  and can be uploaded with `--upload`. It is stored encrypted and never returned by the API.
- **When a site shows a captcha or asks to log in again, the job stops**, the session is marked
  `blocked` or `needs_login` (see `GET /api/sessions`), and a person logs in again. Nothing tries
  to get past a captcha. Pages are loaded slowly (`SCRAPE_DELAY_SECONDS`).

### When a site changes

The parsers find records by their keys anywhere in a response, not by a fixed path, so small
changes do not break them. When a job saves nothing:

1. Run it again with `"dump": true` in its params; every JSON response the page loaded is written
   to `DATA_DIR/dumps/job-<id>-<n>.json`.
2. Find the records there and adjust the key names in `scrapers/shopee_parse.py` or
   `scrapers/tiktok_parse.py`, with a test in `tests/test_parse.py` built from the dump.
3. If a page moved, override its path with a `PATH_<NAME>` env var (see `config.py`) or change
   the default.

## Setup

Python 3.12, Postgres 15+.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # macOS/Linux: .venv/bin/pip
.venv/Scripts/playwright install chromium
cp .env.example .env                       # then fill API_KEY and SECRET_KEY
.venv/Scripts/python -m affiliate_data migrate
.venv/Scripts/python -m affiliate_data api      # http://localhost:8000/docs
.venv/Scripts/python -m affiliate_data worker
```

Or everything in Docker: `docker compose up --build`. Log in on your own machine (it needs a
visible browser) and upload the session:

```bash
.venv/Scripts/python -m affiliate_data login shopee --upload http://localhost:8000 --api-key <API_KEY>
```

## Example

```bash
curl -X POST localhost:8000/api/jobs -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"kind": "shopee.offers", "params": {"keyword": "nồi chiên", "pages": 2}}'
curl "localhost:8000/api/products?platform=shopee&sort=commission&min_commission=0.1" -H "X-API-Key: $API_KEY"
```

## Commands

| What | Command |
| --- | --- |
| Lint + format | `.venv/Scripts/ruff check --fix . && .venv/Scripts/ruff format .` |
| Tests (need Postgres database `affiliate_test`) | `.venv/Scripts/python -m pytest -q` |
| New migration | `.venv/Scripts/alembic revision -m "..."`, then edit it |

## Environment

| Name | Meaning |
| --- | --- |
| `DATABASE_URL` | Postgres SQLAlchemy URL |
| `API_KEY` | Clients send it in `X-API-Key`; required |
| `SECRET_KEY` | Fernet key that encrypts saved sessions |
| `DATA_DIR` | Where debug dumps go |
| `SCRAPE_DELAY_SECONDS` | Wait between page loads (default 5) |
| `MAX_PAGES` | Most pages one search job may load (default 5) |
| `HEADLESS` | `0` shows the browser window |
| `SHOPEE_BASE_URL`, `SHOPEE_AFFILIATE_BASE_URL`, `TIKTOK_BASE_URL`, `TIKTOK_AFFILIATE_BASE_URL` | Site base URLs |
| `PATH_<NAME>` | Overrides a page path from `config.py` |

## Known limits

- Scraping goes against the sites' terms; accounts used here can be limited or banned. Use an
  account you can afford to lose, keep the pace slow, and switch to the official Shopee Affiliate
  Open API / TikTok Shop Affiliate API when the accounts are approved.
- Page paths and response keys for the affiliate dashboards (`shopee.offers`, `shopee.links`,
  `shopee.report`, `tiktok.products`, `tiktok.report`) have not yet been checked against a real
  logged-in account; check them with `dump` on the first run.
- TikTok affiliate links are not supported yet (TikTok creates them in the app's showcase).
- Reports read the date range the dashboard opens with (usually the last 7 to 30 days); run the
  report job daily (a watch) to keep history.
