"""Job kinds, their parameters, and enqueueing. The worker (worker.py) runs them."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, ValidationError, field_validator
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


Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PickParams(BaseModel):
    """Search offers for each keyword and keep the best `top` of each (on Shopee, with affiliate links)."""

    # At most 10 x 5 = 50 links, what one custom-link job takes.
    keywords: list[Keyword] = Field(min_length=1, max_length=10)
    pages: int = Field(default=1, ge=1, le=config.MAX_PAGES)
    top: int = Field(default=3, ge=1, le=5)
    # 1 ranks by price only, 0 by commission rate only.
    price_weight: float = Field(default=0.5, ge=0, le=1)
    # Only products Reels Studio would approve: 4.7 stars or more, 100 sales or more, and on Shopee a trusted shop.
    approved_only: bool = True
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    dump: bool = False

    @field_validator("keywords")
    @classmethod
    def _distinct(cls, keywords: list[str]) -> list[str]:
        return list(dict.fromkeys(keywords))


KINDS: dict[str, type[BaseModel]] = {
    "shopee.search": KeywordParams,
    "shopee.offers": KeywordParams,
    "shopee.links": LinkParams,
    "shopee.report": ReportParams,
    "shopee.picks": PickParams,
    "tiktok.trending": KeywordParams,
    "tiktok.products": KeywordParams,
    "tiktok.report": ReportParams,
    "tiktok.picks": PickParams,
}

KIND_LABELS = {
    "shopee.search": "Tìm sản phẩm Shopee",
    "shopee.offers": "Sản phẩm + hoa hồng Shopee Affiliate",
    "shopee.links": "Tạo link affiliate Shopee",
    "shopee.report": "Báo cáo đơn/hoa hồng Shopee",
    "shopee.picks": "Chọn sản phẩm Shopee rẻ, hoa hồng cao theo danh sách từ khoá",
    "tiktok.trending": "Video TikTok đang hot",
    "tiktok.products": "Sản phẩm + hoa hồng TikTok Shop",
    "tiktok.report": "Báo cáo đơn/hoa hồng TikTok",
    "tiktok.picks": "Chọn sản phẩm TikTok Shop rẻ, hoa hồng cao theo danh sách từ khoá",
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
