"""What each job kind does: open the platform with its saved login, scrape, save."""

import json
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, crypto, ranking, store
from .jobs import platform_of
from .models import Job, PlatformSession, Product
from .scrapers import shopee, tiktok
from .scrapers.browser import Capture, NeedsLogin, open_page


class TaskError(Exception):
    """A failure to show the user as is (Vietnamese)."""


def load_session(db: Session, platform: str) -> dict[str, Any]:
    session = db.get(PlatformSession, platform)
    if session is None:
        raise NeedsLogin(f"Chưa có phiên đăng nhập {platform}. Hãy chạy lệnh login rồi tải phiên lên.")
    return json.loads(crypto.decrypt(session.storage_state))


def _shopee_search(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"products": store.save_products(db, "shopee", shopee.search(page, p["keyword"], p["pages"], caps))}


def _shopee_offers(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"products": store.save_products(db, "shopee", shopee.offers(page, p["keyword"], p["pages"], caps))}


def _shopee_links(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    products = db.scalars(
        select(Product).where(Product.id.in_(p["product_ids"]), Product.platform == "shopee", Product.url.is_not(None))
    ).all()
    if not products:
        raise TaskError("Không có sản phẩm Shopee nào (có link) trong danh sách đã chọn.")
    made = _attach_links(db, page, list(products), caps)
    if made == 0:
        raise TaskError("Không đọc được link affiliate nào từ trang tạo link. Thử lại với dump=true để xem phản hồi.")
    return {"links": made, "missing": len(products) - made}


def _attach_links(db: Session, page: Page, products: list[Product], caps: list[Capture]) -> int:
    """Makes affiliate links for `products` (each with a url) and saves them; returns how many were made."""
    links = shopee.make_links(page, [product.url for product in products if product.url], caps)
    made = 0
    for product in products:
        link = links.get(product.url or "")
        if link:
            product.affiliate_link = link
            made += 1
    db.commit()
    return made


Search = Callable[[Page, str, int, list[Capture]], list[dict[str, Any]]]


def _pick(
    db: Session, page: Page, p: dict[str, Any], caps: list[Capture], platform: str, search: Search
) -> tuple[int, dict[str, list[Product]]]:
    """Searches every keyword, saves what it finds, and returns the count saved and each keyword's picks."""
    saved = 0
    for keyword in p["keywords"]:
        saved += store.save_products(db, platform, search(page, keyword, p["pages"], caps))
    options = {k: p[k] for k in ("top", "price_weight", "approved_only", "min_price", "max_price")}
    chosen = {
        keyword: [product for product, _ in ranking.picks(db, platform, keyword, **options)]
        for keyword in p["keywords"]
    }
    return saved, chosen


def _shopee_picks(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    saved, chosen = _pick(db, page, p, caps, "shopee", shopee.offers)
    picked = [product for products in chosen.values() for product in products]
    # The offers page often gives a link already; only the rest go through the custom-link tool.
    unlinked = [product for product in picked if product.affiliate_link is None and product.url]
    links = _attach_links(db, page, unlinked, caps) if unlinked else 0
    return {
        "products": saved,
        "picked": len(picked),
        "links": links,
        "without_link": sum(1 for product in picked if product.affiliate_link is None),
        "no_pick": [keyword for keyword, products in chosen.items() if not products],
    }


def _tiktok_picks(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    """TikTok affiliate links are made in the app's showcase, so this only picks."""
    saved, chosen = _pick(db, page, p, caps, "tiktok", tiktok.products)
    return {
        "products": saved,
        "picked": sum(len(products) for products in chosen.values()),
        "no_pick": [keyword for keyword, products in chosen.items() if not products],
    }


def _shopee_report(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"conversions": store.save_conversions(db, "shopee", shopee.report(page, caps))}


def _tiktok_trending(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"videos": store.save_videos(db, "tiktok", tiktok.trending(page, p["keyword"], p["pages"], caps))}


def _tiktok_products(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"products": store.save_products(db, "tiktok", tiktok.products(page, p["keyword"], p["pages"], caps))}


def _tiktok_report(db: Session, page: Page, p: dict[str, Any], caps: list[Capture]) -> dict[str, Any]:
    return {"conversions": store.save_conversions(db, "tiktok", tiktok.report(page, caps))}


Handler = Callable[[Session, Page, dict[str, Any], list[Capture]], dict[str, Any]]

HANDLERS: dict[str, Handler] = {
    "shopee.search": _shopee_search,
    "shopee.offers": _shopee_offers,
    "shopee.links": _shopee_links,
    "shopee.report": _shopee_report,
    "shopee.picks": _shopee_picks,
    "tiktok.trending": _tiktok_trending,
    "tiktok.products": _tiktok_products,
    "tiktok.report": _tiktok_report,
    "tiktok.picks": _tiktok_picks,
}


def run(db: Session, job: Job) -> dict[str, Any]:
    storage_state = load_session(db, platform_of(job.kind))
    captures: list[Capture] = []
    try:
        with open_page(storage_state) as page:
            return HANDLERS[job.kind](db, page, job.params, captures)
    finally:
        if job.params.get("dump"):
            for n, capture in enumerate(captures):
                capture.dump(config.DATA_DIR / "dumps" / f"job-{job.id}-{n}.json")
