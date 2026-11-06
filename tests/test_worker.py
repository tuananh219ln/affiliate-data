from datetime import timedelta

from affiliate_data import crypto, jobs, tasks, worker
from affiliate_data.models import Job, PlatformSession, Watch
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
