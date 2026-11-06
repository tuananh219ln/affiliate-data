from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from affiliate_data import crypto, jobs, tasks, worker
from affiliate_data.models import Job, PlatformSession, Product, Watch
from affiliate_data.scrapers.browser import Blocked


def _session(db, platform="shopee"):
    db.add(PlatformSession(platform=platform, storage_state=crypto.encrypt('{"cookies": []}'), status="ok"))
    db.commit()


def test_claim_takes_the_oldest_queued_job(db):
    first = jobs.enqueue(db, "shopee.report", {})
    jobs.enqueue(db, "tiktok.report", {})
    assert worker.claim() == first.id
    db.refresh(first)
    assert first.status == "running"


def test_a_captcha_fails_the_job_and_marks_the_session(db, monkeypatch):
    _session(db)
    job = jobs.enqueue(db, "shopee.report", {})

    def blocked(db, job):
        raise Blocked("captcha")

    monkeypatch.setattr(tasks, "run", blocked)
    worker.run_job(worker.claim())

    db.expire_all()
    assert (db.get(Job, job.id).status, db.get(Job, job.id).error) == ("failed", "captcha")
    assert db.get(PlatformSession, "shopee").status == "blocked"


def test_a_done_job_keeps_its_result_and_clears_the_session_warning(db, monkeypatch):
    _session(db)
    db.get(PlatformSession, "shopee").status = "blocked"
    db.commit()
    job = jobs.enqueue(db, "shopee.report", {})
    monkeypatch.setattr(tasks, "run", lambda db, job: {"conversions": 3})
    worker.run_job(worker.claim())

    db.expire_all()
    assert db.get(Job, job.id).result == {"conversions": 3}
    assert db.get(PlatformSession, "shopee").status == "ok"


def test_a_job_without_a_session_asks_to_log_in(db):
    job = jobs.enqueue(db, "tiktok.report", {})
    worker.run_job(worker.claim())
    db.expire_all()
    assert db.get(Job, job.id).status == "failed"
    assert "đăng nhập" in db.get(Job, job.id).error


def test_due_watches_are_enqueued_once(db):
    db.add(Watch(kind="shopee.report", params={"dump": False}, every_hours=24, enabled=True))
    db.add(
        Watch(kind="tiktok.report", params={"dump": False}, every_hours=24, enabled=True, last_enqueued_at=worker.now())
    )
    db.add(
        Watch(
            kind="tiktok.trending",
            params={"keyword": "son", "pages": 1, "dump": False},
            every_hours=6,
            enabled=True,
            last_enqueued_at=worker.now() - timedelta(hours=7),
        )
    )
    db.commit()
    assert worker.enqueue_due_watches() == 2
    assert worker.enqueue_due_watches() == 0
    assert sorted(j.kind for j in db.query(Job).all()) == ["shopee.report", "tiktok.trending"]


def test_interrupted_jobs_are_failed_on_start(db):
    job = jobs.enqueue(db, "shopee.report", {})
    worker.claim()
    worker.fail_interrupted()
    db.expire_all()
    assert db.get(Job, job.id).status == "failed"


GOOD_SHOP = {"shop_type": "mall", "rating": 4.9, "sold": 500}
# keyword -> (id, price, commission rate, affiliate link from the offers page)
OFFERS = {
    "nồi": [(19, 50_000, 0.20, "https://s.shopee.vn/old"), (11, 100_000, 0.10, None), (12, 300_000, 0.02, None)],
    "máy xay": [(21, 100_000, 0.10, None), (22, 200_000, 0.05, None), (23, 300_000, 0.01, None)],
    "quạt": [],
}


def test_picks_job_searches_each_keyword_and_links_only_the_picks(db, monkeypatch):
    def offers(page, keyword, pages, captures):
        return [
            {
                "external_id": str(n),
                "name": f"{keyword} {n}",
                "url": f"https://shopee.vn/product/1/{n}",
                "price": Decimal(price),
                "commission_rate": rate,
                "affiliate_link": link,
                "keyword": keyword,
                **GOOD_SHOP,
            }
            for n, price, rate, link in OFFERS[keyword]
        ]

    asked = []

    def make_links(page, urls, captures):
        asked.extend(urls)
        # The tool answers for all but the last URL.
        return {url: url.replace("shopee.vn/product/1/", "s.shopee.vn/") for url in urls[:-1]}

    monkeypatch.setattr(tasks.shopee, "offers", offers)
    monkeypatch.setattr(tasks.shopee, "make_links", make_links)
    params = jobs.validate("shopee.picks", {"keywords": ["nồi", "máy xay", "quạt"], "top": 2})

    result = tasks.HANDLERS["shopee.picks"](db, None, params, [])

    assert result == {"products": 6, "picked": 4, "links": 2, "without_link": 1, "no_pick": ["quạt"]}
    # The picks are 19, 11 and 21, 22; 19 already had a link, so only three go to the tool.
    assert asked == [f"https://shopee.vn/product/1/{n}" for n in (11, 21, 22)]
    linked = dict(
        db.execute(select(Product.external_id, Product.affiliate_link).where(Product.affiliate_link.is_not(None))).all()
    )
    assert linked == {"19": "https://s.shopee.vn/old", "11": "https://s.shopee.vn/11", "21": "https://s.shopee.vn/21"}


def test_tiktok_picks_job_only_picks(db, monkeypatch):
    def products(page, keyword, pages, captures):
        return [
            {"external_id": str(n), "name": f"{keyword} {n}", "keyword": keyword, "price": Decimal(price)}
            | {"commission_rate": rate, "rating": 4.9, "sold": 500}
            for n, price, rate in ((1, 100_000, 0.10), (2, 300_000, 0.02))
            if keyword == "son"
        ]

    monkeypatch.setattr(tasks.tiktok, "products", products)
    params = jobs.validate("tiktok.picks", {"keywords": ["son", "kem"], "top": 1})

    result = tasks.HANDLERS["tiktok.picks"](db, None, params, [])

    assert result == {"products": 2, "picked": 1, "no_pick": ["kem"]}
    assert db.scalars(select(Product.platform)).all() == ["tiktok", "tiktok"]
