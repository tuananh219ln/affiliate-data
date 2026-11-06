"""TikTok pages: trending videos by keyword, affiliate marketplace products and the order report."""

from typing import Any
from urllib.parse import quote

from playwright.sync_api import Page

from .. import config
from . import tiktok_parse
from .browser import Capture, pause, visit

VIDEO_API = ("/api/search/", "/api/challenge/item_list", "/api/recommend/item_list")
AFFILIATE_API = ("/api/",)


def trending(page: Page, keyword: str, pages: int, captures: list[Capture]) -> list[dict[str, Any]]:
    """Videos for a keyword; each extra "page" is another round of scrolling, which loads more."""
    capture = Capture(page, VIDEO_API)
    captures.append(capture)
    path = config.PATHS["TIKTOK_SEARCH_VIDEO"].format(keyword=quote(keyword))
    visit(page, config.TIKTOK_BASE + path, scrolls=3 * pages)
    pause()
    return tiktok_parse.videos(capture.bodies, keyword)


def products(page: Page, keyword: str, pages: int, captures: list[Capture]) -> list[dict[str, Any]]:
    capture = Capture(page, AFFILIATE_API)
    captures.append(capture)
    path = config.PATHS["TIKTOK_PRODUCTS"].format(keyword=quote(keyword))
    visit(page, config.TIKTOK_AFFILIATE_BASE + path, scrolls=3 * pages)
    pause()
    return tiktok_parse.products(capture.bodies, keyword)


def report(page: Page, captures: list[Capture]) -> list[dict[str, Any]]:
    capture = Capture(page, AFFILIATE_API)
    captures.append(capture)
    visit(page, config.TIKTOK_AFFILIATE_BASE + config.PATHS["TIKTOK_REPORT"], scrolls=2)
    return tiktok_parse.conversions(capture.bodies)
