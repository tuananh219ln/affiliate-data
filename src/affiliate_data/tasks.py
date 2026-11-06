"""What each job kind does: open the platform with its saved login, scrape, save."""

import json
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, crypto, store
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
    links = shopee.make_links(page, [product.url for product in products if product.url], caps)
    made = 0
    for product in products:
        link = links.get(product.url or "")
        if link:
            product.affiliate_link = link
            made += 1
    db.commit()
    if made == 0:
        raise TaskError("Không đọc được link affiliate nào từ trang tạo link. Thử lại với dump=true để xem phản hồi.")
    return {"links": made, "missing": len(products) - made}


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
    "tiktok.trending": _tiktok_trending,
    "tiktok.products": _tiktok_products,
    "tiktok.report": _tiktok_report,
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
