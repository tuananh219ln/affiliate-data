"""Settings, read from the environment once at import."""

import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DATABASE_URL = _env("DATABASE_URL", "postgresql+psycopg://affiliate:affiliate@localhost:5432/affiliate")
API_KEY = _env("API_KEY")
SECRET_KEY = _env("SECRET_KEY")
DATA_DIR = Path(_env("DATA_DIR", "data"))
SCRAPE_DELAY_SECONDS = float(_env("SCRAPE_DELAY_SECONDS", "5"))
MAX_PAGES = int(_env("MAX_PAGES", "5"))
HEADLESS = _env("HEADLESS", "1") != "0"
# The web sign-in cookie goes over HTTPS only. Browsers still accept it on http://localhost.
COOKIE_SECURE = _env("COOKIE_SECURE", "1") != "0"
TIME_ZONE = "Asia/Ho_Chi_Minh"

SHOPEE_BASE = _env("SHOPEE_BASE_URL", "https://shopee.vn").rstrip("/")
SHOPEE_AFFILIATE_BASE = _env("SHOPEE_AFFILIATE_BASE_URL", "https://affiliate.shopee.vn").rstrip("/")
SHOPEE_IMAGE_BASE = _env("SHOPEE_IMAGE_BASE_URL", "https://down-vn.img.susercontent.com/file").rstrip("/")
TIKTOK_BASE = _env("TIKTOK_BASE_URL", "https://www.tiktok.com").rstrip("/")
TIKTOK_AFFILIATE_BASE = _env("TIKTOK_AFFILIATE_BASE_URL", "https://affiliate.tiktok.com").rstrip("/")

# Pages the scrapers open. The sites move these now and then; override one with PATH_<NAME>.
_DEFAULT_PATHS = {
    "SHOPEE_SEARCH": "/search?keyword={keyword}&page={page}",
    "SHOPEE_OFFERS": "/offer/product_offer?keyword={keyword}&page={page}",
    "SHOPEE_CUSTOM_LINK": "/offer/custom_link",
    "SHOPEE_REPORT": "/report/conversion_report",
    "TIKTOK_SEARCH_VIDEO": "/search/video?q={keyword}",
    "TIKTOK_PRODUCTS": "/product/marketplace?keyword={keyword}",
    "TIKTOK_REPORT": "/data/order",
}
PATHS = {name: _env(f"PATH_{name}", default) for name, default in _DEFAULT_PATHS.items()}
