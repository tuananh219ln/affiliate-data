"""Job kinds, their parameters, and enqueueing. The worker (worker.py) runs them."""

from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Job


class KeywordParams(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    pages: int = Field(default=1, ge=1, le=config.MAX_PAGES)
    # Saves every captured response under DATA_DIR/dumps, to see a site's current shapes.
    dump: bool = False


class LinkParams(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=50)
    dump: bool = False


class ReportParams(BaseModel):
    dump: bool = False


KINDS: dict[str, type[BaseModel]] = {
    "shopee.search": KeywordParams,
    "shopee.offers": KeywordParams,
    "shopee.links": LinkParams,
    "shopee.report": ReportParams,
    "tiktok.trending": KeywordParams,
    "tiktok.products": KeywordParams,
    "tiktok.report": ReportParams,
}

KIND_LABELS = {
    "shopee.search": "Tìm sản phẩm Shopee",
    "shopee.offers": "Sản phẩm + hoa hồng Shopee Affiliate",
    "shopee.links": "Tạo link affiliate Shopee",
    "shopee.report": "Báo cáo đơn/hoa hồng Shopee",
    "tiktok.trending": "Video TikTok đang hot",
    "tiktok.products": "Sản phẩm + hoa hồng TikTok Shop",
    "tiktok.report": "Báo cáo đơn/hoa hồng TikTok",
}


class InvalidJob(ValueError):
    pass


def platform_of(kind: str) -> str:
    return kind.split(".", 1)[0]


def validate(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    model = KINDS.get(kind)
    if model is None:
        raise InvalidJob(f"Loại việc không hợp lệ: {kind}")
    try:
        return model.model_validate(params).model_dump()
    except ValidationError as error:
        raise InvalidJob(f"Tham số không hợp lệ cho {kind}: {error.errors()[0]['msg']}") from error


def same_job_open(db: Session, kind: str, params: dict[str, Any]) -> Job | None:
    """An identical job still queued or running; enqueueing it again would scrape twice."""
    return db.scalars(
        select(Job).where(Job.kind == kind, Job.params == params, Job.status.in_(("queued", "running"))).limit(1)
    ).first()


def enqueue(db: Session, kind: str, params: dict[str, Any]) -> Job:
    params = validate(kind, params)
    existing = same_job_open(db, kind, params)
    if existing is not None:
        return existing
    job = Job(kind=kind, params=params, status="queued")
    db.add(job)
    db.commit()
    return job
