"""Shopee pages: product search, affiliate offers, custom links and the conversion report."""

import re
from typing import Any
from urllib.parse import quote

from playwright.sync_api import Page

from .. import config
from . import shopee_parse
from .browser import Capture, pause, visit

SEARCH_API = ("/api/v4/search/search_items",)
# The affiliate dashboard's endpoints change names often; take every JSON it loads and let the
# parser pick records by their keys.
AFFILIATE_API = ("/api/",)


def search(page: Page, keyword: str, pages: int, captures: list[Capture]) -> list[dict[str, Any]]:
    capture = Capture(page, SEARCH_API)
    captures.append(capture)
    for n in range(pages):
        path = config.PATHS["SHOPEE_SEARCH"].format(keyword=quote(keyword), page=n)
        visit(page, config.SHOPEE_BASE + path)
        pause()
    return shopee_parse.search_products(capture.bodies, keyword)


def offers(page: Page, keyword: str, pages: int, captures: list[Capture]) -> list[dict[str, Any]]:
    capture = Capture(page, AFFILIATE_API)
    captures.append(capture)
    for n in range(1, pages + 1):
        path = config.PATHS["SHOPEE_OFFERS"].format(keyword=quote(keyword), page=n)
        visit(page, config.SHOPEE_AFFILIATE_BASE + path)
        pause()
    return shopee_parse.offer_products(capture.bodies, keyword)


def make_links(page: Page, urls: list[str], captures: list[Capture]) -> dict[str, str]:
    """Pastes product URLs into the dashboard's custom-link tool and reads back the short links."""
    capture = Capture(page, AFFILIATE_API)
    captures.append(capture)
    visit(page, config.SHOPEE_AFFILIATE_BASE + config.PATHS["SHOPEE_CUSTOM_LINK"], scrolls=0)
    page.locator("textarea").first.fill("\n".join(urls))
    page.get_by_role("button", name=re.compile(r"lấy link|get link", re.IGNORECASE)).first.click()
    page.wait_for_timeout(5_000)
    return shopee_parse.short_links(capture.bodies)


def report(page: Page, captures: list[Capture]) -> list[dict[str, Any]]:
    """The conversion report as the dashboard first shows it (its default date range)."""
    capture = Capture(page, AFFILIATE_API)
    captures.append(capture)
    visit(page, config.SHOPEE_AFFILIATE_BASE + config.PATHS["SHOPEE_REPORT"], scrolls=2)
    return shopee_parse.conversions(capture.bodies)
