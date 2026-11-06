"""API routes. Long work (anything that opens a browser) is enqueued as a job, never done in a request."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, cast, desc, func, nulls_last, select
from sqlalchemy.orm import Session

from . import config, crypto, jobs, ranking
from .db import get_db
from .models import PLATFORMS, Conversion, Job, PlatformSession, Product, TrendingVideo, Watch

VN = ZoneInfo(config.TIME_ZONE)

Platform = Literal["shopee", "tiktok"]
ShopType = Literal["mall", "preferred_plus", "preferred", "other"]


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Không tìm thấy {what}.")


# --- Login sessions ---------------------------------------------------------------------------

sessions = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    platform: str
    status: str
    message: str | None
    updated_at: datetime | None


@sessions.get("")
def list_sessions(db: Session = Depends(get_db)) -> list[SessionOut]:
    """Every platform, with "missing" for one nobody has logged in to yet. Cookies are never returned."""
    saved = {s.platform: s for s in db.scalars(select(PlatformSession)).all()}
    out = []
    for platform in PLATFORMS:
        s = saved.get(platform)
        if s is None:
            out.append(SessionOut(platform=platform, status="missing", message="Chưa đăng nhập.", updated_at=None))
        else:
            out.append(SessionOut(platform=platform, status=s.status, message=s.message, updated_at=s.updated_at))
    return out


@sessions.put("/{platform}")
def save_session(platform: Platform, storage_state: dict[str, Any], db: Session = Depends(get_db)) -> SessionOut:
    """Body: the JSON file `python -m affiliate_data login <platform>` writes (Playwright storage state)."""
    if not isinstance(storage_state.get("cookies"), list) or not storage_state["cookies"]:
        raise HTTPException(status_code=422, detail="Phiên đăng nhập không có cookie nào.")
    session = db.get(PlatformSession, platform) or PlatformSession(platform=platform)
    session.storage_state = crypto.encrypt(json.dumps(storage_state))
    session.status, session.message, session.updated_at = "ok", None, datetime.now(VN)
    db.add(session)
    db.commit()
    return SessionOut(platform=platform, status="ok", message=None, updated_at=session.updated_at)


@sessions.delete("/{platform}", status_code=204)
def delete_session(platform: Platform, db: Session = Depends(get_db)) -> None:
    session = db.get(PlatformSession, platform)
    if session is not None:
        db.delete(session)
        db.commit()


# --- Jobs -------------------------------------------------------------------------------------

jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobIn(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    params: dict[str, Any]
    status: str
    error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@jobs_router.get("/kinds")
def job_kinds() -> list[dict[str, Any]]:
    return [
        {"kind": kind, "label": jobs.KIND_LABELS[kind], "params": model.model_json_schema()}
        for kind, model in jobs.KINDS.items()
    ]


@jobs_router.post("", status_code=202)
def create_job(body: JobIn, db: Session = Depends(get_db)) -> JobOut:
    try:
        job = jobs.enqueue(db, body.kind, body.params)
    except jobs.InvalidJob as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JobOut.model_validate(job)


@jobs_router.get("")
def list_jobs(
    status: str | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[JobOut]:
    query = select(Job).order_by(desc(Job.id)).limit(limit)
    if status:
        query = query.where(Job.status == status)
    return [JobOut.model_validate(j) for j in db.scalars(query).all()]


@jobs_router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise _not_found("việc")
    return JobOut.model_validate(job)


# --- Products ---------------------------------------------------------------------------------

products = APIRouter(prefix="/products", tags=["products"])


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    external_id: str
    name: str
    shop_name: str | None
    shop_type: str | None
    price: Decimal | None
    original_price: Decimal | None
    image_url: str | None
    url: str | None
    sold: int | None
    rating: float | None
    commission_rate: float | None
    commission_amount: Decimal | None
    affiliate_link: str | None
    keyword: str | None
    updated_at: datetime


PRODUCT_SORTS = {
    "sold": nulls_last(desc(Product.sold)),
    "commission": nulls_last(desc(Product.commission_rate)),
    "commission_amount": nulls_last(
        desc(func.coalesce(Product.commission_amount, Product.price * Product.commission_rate))
    ),
    "updated": desc(Product.updated_at),
}


@products.get("")
def list_products(
    platform: Platform | None = None,
    q: str | None = Query(None, max_length=100),
    min_commission: float | None = Query(None, ge=0, le=1, description="Tỉ lệ tối thiểu, 0.1 = 10 %"),
    has_link: bool | None = None,
    shop_type: list[ShopType] | None = Query(
        None, description="Lặp lại để lấy nhiều loại: shop_type=mall&shop_type=preferred"
    ),
    min_rating: float | None = Query(None, ge=0, le=5),
    min_sold: int | None = Query(None, ge=0),
    sort: Literal["sold", "commission", "commission_amount", "updated"] = "updated",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    query = select(Product)
    if platform:
        query = query.where(Product.platform == platform)
    if q:
        query = query.where(Product.name.ilike(f"%{q}%"))
    if min_commission is not None:
        query = query.where(Product.commission_rate >= min_commission)
    if shop_type:
        query = query.where(Product.shop_type.in_(shop_type))
    if min_rating is not None:
        query = query.where(Product.rating >= min_rating)
    if min_sold is not None:
        query = query.where(Product.sold >= min_sold)
    if has_link is not None:
        query = query.where(Product.affiliate_link.is_not(None) if has_link else Product.affiliate_link.is_(None))
    query = query.order_by(PRODUCT_SORTS[sort], desc(Product.id)).limit(limit).offset(offset)
    return [ProductOut.model_validate(p) for p in db.scalars(query).all()]


class PickOut(ProductOut):
    score: float


class KeywordPicks(BaseModel):
    keyword: str
    products: list[PickOut]


# Before /{product_id}, which would otherwise take "picks" for an id.
@products.get("/picks")
def list_picks(
    platform: Platform = "shopee",
    keyword: list[str] = Query(description="Lặp lại cho nhiều từ khoá: keyword=nồi chiên&keyword=máy xay"),
    top: int = Query(3, ge=1, le=20),
    price_weight: float = Query(0.5, ge=0, le=1, description="1 = chỉ xét giá rẻ, 0 = chỉ xét hoa hồng cao"),
    approved_only: bool = Query(
        True, description="Chỉ sản phẩm từ 4.7 sao, từ 100 lượt bán; với Shopee thêm shop Mall/Yêu thích"
    ),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
) -> list[KeywordPicks]:
    """The best products already saved for each keyword (run a `shopee.picks` or `tiktok.picks` job first)."""
    keywords = list(dict.fromkeys(k.strip() for k in keyword if k.strip()))
    if not keywords or len(keywords) > 20:
        raise HTTPException(status_code=422, detail="Cần từ 1 đến 20 từ khoá.")
    out = []
    for kw in keywords:
        ranked = ranking.picks(db, platform, kw, top, price_weight, approved_only, min_price, max_price)
        out.append(
            KeywordPicks(
                keyword=kw,
                products=[PickOut(**ProductOut.model_validate(p).model_dump(), score=score) for p, score in ranked],
            )
        )
    return out


@products.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise _not_found("sản phẩm")
    return ProductOut.model_validate(product)


class LinksIn(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=50)


@products.post("/links", status_code=202)
def make_links(body: LinksIn, db: Session = Depends(get_db)) -> JobOut:
    """Enqueues affiliate-link creation for Shopee products. TikTok links are not supported yet."""
    found = db.scalars(select(Product.id).where(Product.id.in_(body.product_ids), Product.platform == "shopee")).all()
    if not found:
        raise HTTPException(status_code=422, detail="Chỉ tạo được link cho sản phẩm Shopee đã lưu.")
    return JobOut.model_validate(jobs.enqueue(db, "shopee.links", {"product_ids": sorted(found)}))


# --- Trending videos --------------------------------------------------------------------------

videos = APIRouter(prefix="/videos", tags=["videos"])


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    external_id: str
    author: str | None
    description: str | None
    cover_url: str | None
    url: str | None
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    keyword: str | None
    posted_at: datetime | None
    updated_at: datetime


VIDEO_SORTS = {
    "views": nulls_last(desc(TrendingVideo.views)),
    "likes": nulls_last(desc(TrendingVideo.likes)),
    "recent": nulls_last(desc(TrendingVideo.posted_at)),
}


@videos.get("")
def list_videos(
    keyword: str | None = Query(None, max_length=100),
    posted_within_days: int | None = Query(None, ge=1, le=365),
    sort: Literal["views", "likes", "recent"] = "views",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[VideoOut]:
    query = select(TrendingVideo)
    if keyword:
        query = query.where(TrendingVideo.keyword == keyword)
    if posted_within_days:
        query = query.where(TrendingVideo.posted_at >= datetime.now(VN) - timedelta(days=posted_within_days))
    query = query.order_by(VIDEO_SORTS[sort], desc(TrendingVideo.id)).limit(limit).offset(offset)
    return [VideoOut.model_validate(v) for v in db.scalars(query).all()]


# --- Conversions (orders and commission) ------------------------------------------------------

conversions = APIRouter(prefix="/conversions", tags=["conversions"])


class ConversionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    order_id: str
    item_id: str
    item_name: str | None
    order_amount: Decimal | None
    commission: Decimal | None
    status: str | None
    ordered_at: datetime | None


@conversions.get("")
def list_conversions(
    platform: Platform | None = None,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ConversionOut]:
    query = select(Conversion).where(Conversion.ordered_at >= datetime.now(VN) - timedelta(days=days))
    if platform:
        query = query.where(Conversion.platform == platform)
    query = query.order_by(nulls_last(desc(Conversion.ordered_at)), desc(Conversion.id)).limit(limit).offset(offset)
    return [ConversionOut.model_validate(c) for c in db.scalars(query).all()]


class DaySummary(BaseModel):
    day: str
    platform: str
    orders: int
    order_amount: Decimal
    commission: Decimal


@conversions.get("/summary")
def summary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)) -> list[DaySummary]:
    """Totals per Vietnam calendar day and platform."""
    day = cast(func.timezone(config.TIME_ZONE, Conversion.ordered_at), Date)
    rows = db.execute(
        select(
            day.label("day"),
            Conversion.platform,
            func.count(func.distinct(Conversion.order_id)),
            func.coalesce(func.sum(Conversion.order_amount), 0),
            func.coalesce(func.sum(Conversion.commission), 0),
        )
        .where(Conversion.ordered_at >= datetime.now(VN) - timedelta(days=days))
        .group_by(day, Conversion.platform)
        .order_by(desc(day), Conversion.platform)
    ).all()
    return [
        DaySummary(day=d.isoformat(), platform=p, orders=n, order_amount=amount, commission=commission)
        for d, p, n, amount, commission in rows
    ]


# --- Watches (repeat a job every N hours) -----------------------------------------------------

watches = APIRouter(prefix="/watches", tags=["watches"])


class WatchIn(BaseModel):
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    # At least 6 h: scraping the same pages more often gets accounts blocked.
    every_hours: int = Field(ge=6, le=24 * 30)


class WatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    params: dict[str, Any]
    every_hours: int
    enabled: bool
    last_enqueued_at: datetime | None


@watches.get("")
def list_watches(db: Session = Depends(get_db)) -> list[WatchOut]:
    return [WatchOut.model_validate(w) for w in db.scalars(select(Watch).order_by(Watch.id)).all()]


@watches.post("", status_code=201)
def create_watch(body: WatchIn, db: Session = Depends(get_db)) -> WatchOut:
    if body.kind == "shopee.links":
        raise HTTPException(status_code=422, detail="Không thể lên lịch tạo link; hãy tạo link khi cần.")
    try:
        params = jobs.validate(body.kind, body.params)
    except jobs.InvalidJob as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    watch = Watch(kind=body.kind, params=params, every_hours=body.every_hours, enabled=True)
    db.add(watch)
    db.commit()
    return WatchOut.model_validate(watch)


class WatchPatch(BaseModel):
    enabled: bool | None = None
    every_hours: int | None = Field(None, ge=6, le=24 * 30)


@watches.patch("/{watch_id}")
def update_watch(watch_id: int, body: WatchPatch, db: Session = Depends(get_db)) -> WatchOut:
    watch = db.get(Watch, watch_id)
    if watch is None:
        raise _not_found("lịch chạy")
    if body.enabled is not None:
        watch.enabled = body.enabled
    if body.every_hours is not None:
        watch.every_hours = body.every_hours
    db.commit()
    return WatchOut.model_validate(watch)


@watches.delete("/{watch_id}", status_code=204)
def delete_watch(watch_id: int, db: Session = Depends(get_db)) -> None:
    watch = db.get(Watch, watch_id)
    if watch is not None:
        db.delete(watch)
        db.commit()


ROUTERS = [sessions, jobs_router, products, videos, conversions, watches]
