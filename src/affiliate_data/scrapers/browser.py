"""A real Chromium (Playwright) that loads pages with our saved login and records the JSON they fetch.

Rules: go slowly (SCRAPE_DELAY_SECONDS between pages), and when a site shows a captcha or a login
wall, stop and report it; a person logs in again by hand. Nothing here tries to get past a captcha
or hide that it is automated.
"""

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Response, sync_playwright

from .. import config

log = logging.getLogger(__name__)

PAGE_TIMEOUT_MS = 60_000
SCROLL_PAUSE_MS = 1_500
SETTLE_MS = 2_500

_CAPTCHA_MARKERS = ("/verify/", "captcha", "/verify?", "security-check")
_LOGIN_MARKERS = ("/buyer/login", "/login", "/signin")


class ScrapeStop(Exception):
    """The site refused to go on; `status` is what the platform session becomes."""

    status = "blocked"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class Blocked(ScrapeStop):
    status = "blocked"


class NeedsLogin(ScrapeStop):
    status = "needs_login"


@contextmanager
def open_page(storage_state: dict[str, Any] | None) -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.HEADLESS)
        try:
            context = browser.new_context(
                storage_state=storage_state,  # type: ignore[arg-type]
                locale="vi-VN",
                timezone_id=config.TIME_ZONE,
                viewport={"width": 1366, "height": 900},
            )
            yield context.new_page()
        finally:
            browser.close()


class Capture:
    """Collects JSON bodies of responses whose URL contains one of `patterns`."""

    def __init__(self, page: Page, patterns: tuple[str, ...]):
        self.patterns = patterns
        self.bodies: list[Any] = []
        self.urls: list[str] = []
        page.on("response", self._on_response)

    def _on_response(self, response: Response) -> None:
        if not any(p in response.url for p in self.patterns):
            return
        if "json" not in (response.headers.get("content-type") or ""):
            return
        try:
            self.bodies.append(response.json())
            self.urls.append(response.url)
        except Exception:  # a body that is not JSON after all, or one the page already discarded
            log.debug("could not read %s", response.url)

    def dump(self, path: Path) -> None:
        """Debug aid: writes what was captured so a person can see a site's current response shapes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"url": u, "body": b} for u, b in zip(self.urls, self.bodies, strict=True)]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def check_page(page: Page) -> None:
    url = page.url.lower()
    if any(m in url for m in _CAPTCHA_MARKERS):
        raise Blocked("Sàn đang yêu cầu xác minh (captcha). Hãy đăng nhập lại bằng tay rồi chạy lại sau.")
    if any(m in url for m in _LOGIN_MARKERS):
        raise NeedsLogin("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại (lệnh login) rồi tải phiên mới lên.")


def visit(page: Page, url: str, scrolls: int = 3) -> None:
    """Opens `url`, scrolls so lazy lists load, and waits for the page to settle."""
    log.info("visit %s", url)
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    check_page(page)
    for _ in range(scrolls):
        page.mouse.wheel(0, 2_500)
        page.wait_for_timeout(SCROLL_PAUSE_MS)
    page.wait_for_timeout(SETTLE_MS)
    check_page(page)


def pause() -> None:
    time.sleep(config.SCRAPE_DELAY_SECONDS)
