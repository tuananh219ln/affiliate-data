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
| `shopee.picks` | For a list of keywords: offers, the best few per keyword (cheap, high commission), their links | Shopee Affiliate |
| `tiktok.trending` | Videos for a keyword, with views, likes, comments, shares | TikTok |
| `tiktok.products` | TikTok Shop affiliate marketplace products, with commission rate | TikTok Shop creator |
| `tiktok.report` | Affiliate orders and commission | TikTok Shop creator |
| `tiktok.picks` | Like `shopee.picks` on the TikTok Shop marketplace, without links | TikTok Shop creator |

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
# Only products Reels Studio would approve: trusted shop, 4.7 stars or more, 100 sales or more.
curl "localhost:8000/api/products?shop_type=mall&shop_type=preferred_plus&shop_type=preferred&min_rating=4.7&min_sold=100" \
  -H "X-API-Key: $API_KEY"
```

### Best products for a list of keywords

```bash
# 1. Find them: search offers for each keyword, keep the best 3, make their affiliate links.
curl -X POST localhost:8000/api/jobs -H "X-API-Key: $API_KEY" -H "Content-Type: application/json"   -d '{"kind": "shopee.picks", "params": {"keywords": ["nồi chiên không dầu", "máy xay sinh tố"], "top": 3}}'
# 2. When the job is done, read them (any time later too):
curl "localhost:8000/api/products/picks?keyword=nồi%20chiên%20không%20dầu&keyword=máy%20xay%20sinh%20tố&top=3"   -H "X-API-Key: $API_KEY"
```

Each keyword's saved offers are scored 0..1: `price_weight × cheapness + (1 − price_weight) ×
commission`, where the cheapest offer has cheapness 1 and the highest commission rate has
commission 1 (default `price_weight` 0.5; 1 ranks by price alone, 0 by commission alone). By
default only offers Reels Studio would approve count (Mall or Preferred shop, 4.7 stars, 100
sales); `approved_only=false` drops that. `min_price` / `max_price` keep accessories out of a
search for the main product. Up to 10 keywords and `top` 5 per job (50 links, one custom-link
run). A product belongs to the keyword it was last found with.

`tiktok.picks` and `GET /api/products/picks?platform=tiktok&keyword=...` do the same on TikTok
Shop. TikTok has no shop badges, so its approval rule is the rating and sales only, and it makes
no links: add the picked products to the showcase in the TikTok app.

Shopee products carry `shop_name` and `shop_type` (`mall`, `preferred_plus`, `preferred`,
`other`: the values Reels Studio uses), read from the shop's badge flags. `shop_type` is empty
when a page did not say; a later save never turns a known type back into empty.

See [docs/PLAN.md](docs/PLAN.md) for where this service fits in the whole affiliate workflow.

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
