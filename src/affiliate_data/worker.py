"""The job worker: one job at a time (one browser), plus re-enqueueing watches that are due.

Run it with `python -m affiliate_data worker`. Jobs are claimed with SELECT ... FOR UPDATE SKIP
LOCKED, so a second worker would be safe, but one is enough: scraping slowly is the point.
"""

import logging
import time
import traceback
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from . import jobs, tasks
from .db import SessionLocal
from .models import Job, PlatformSession, Watch
from .scrapers.browser import ScrapeStop

log = logging.getLogger(__name__)

IDLE_SECONDS = 5


def now() -> datetime:
    return datetime.now(UTC)


def fail_interrupted() -> None:
    """Jobs left running by a worker that died will never finish; say so instead of leaving them."""
    with SessionLocal() as db:
        db.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="failed", error="Worker đã dừng giữa chừng. Hãy chạy lại việc này.", finished_at=now())
        )
        db.commit()


def enqueue_due_watches() -> int:
    enqueued = 0
    with SessionLocal() as db:
        for watch in db.scalars(select(Watch).where(Watch.enabled)).all():
            due = watch.last_enqueued_at is None or watch.last_enqueued_at + timedelta(hours=watch.every_hours) <= now()
            if not due:
                continue
            try:
                jobs.enqueue(db, watch.kind, watch.params)
                enqueued += 1
            except jobs.InvalidJob as error:
                log.warning("watch %s is invalid: %s", watch.id, error)
                watch.enabled = False
            watch.last_enqueued_at = now()
            db.commit()
    return enqueued


def claim() -> int | None:
    with SessionLocal() as db:
        job = db.scalars(
            select(Job).where(Job.status == "queued").order_by(Job.id).limit(1).with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.status = "running"
        job.started_at = now()
        db.commit()
        return job.id


def _mark_session(platform: str, status: str, message: str) -> None:
    with SessionLocal() as db:
        session = db.get(PlatformSession, platform)
        if session is not None:
            session.status = status
            session.message = message
            db.commit()


def run_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        try:
            job.result = tasks.run(db, job)
            job.status = "done"
            _mark_session(jobs.platform_of(job.kind), "ok", "")
        except ScrapeStop as stop:
            db.rollback()
            job.status, job.error = "failed", stop.message
            _mark_session(jobs.platform_of(job.kind), stop.status, stop.message)
        except tasks.TaskError as error:
            db.rollback()
            job.status, job.error = "failed", str(error)
        except Exception:
            db.rollback()
            log.exception("job %s failed", job_id)
            job.status = "failed"
            job.error = "Lỗi không mong đợi khi lấy dữ liệu.\n" + traceback.format_exc(limit=5)
        job.finished_at = now()
        db.commit()


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    fail_interrupted()
    log.info("worker started")
    while True:
        enqueue_due_watches()
        job_id = claim()
        if job_id is None:
            time.sleep(IDLE_SECONDS)
            continue
        log.info("job %s started", job_id)
        run_job(job_id)
        log.info("job %s finished", job_id)
