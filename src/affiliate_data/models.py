from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

PLATFORMS = ("shopee", "tiktok")


class PlatformSession(Base):
    """A logged-in browser state (cookies) for one platform, encrypted."""

    __tablename__ = "platform_sessions"

    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    storage_state: Mapped[str] = mapped_column(Text)
    # ok | needs_login | blocked: set by the worker when a page asks to log in or shows a captcha.
    status: Mapped[str] = mapped_column(String(20), default="ok")
    message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("platform", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(64))
    shop_id: Mapped[str | None] = mapped_column(String(64))
    shop_name: Mapped[str | None] = mapped_column(Text)
    # Shopee: mall | preferred_plus | preferred | other (the same values Reels Studio uses). None when unknown.
    shop_type: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    image_url: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    sold: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[float | None] = mapped_column(Float)
    # A fraction: 0.1 means 10 %.
    commission_rate: Mapped[float | None] = mapped_column(Float)
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    affiliate_link: Mapped[str | None] = mapped_column(Text)
    keyword: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrendingVideo(Base):
    __tablename__ = "trending_videos"
    __table_args__ = (UniqueConstraint("platform", "external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(64))
    author: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    keyword: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversion(Base):
    """One order line credited to our affiliate account."""

    __tablename__ = "conversions"
    __table_args__ = (UniqueConstraint("platform", "order_id", "item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    order_id: Mapped[str] = mapped_column(String(64))
    # "" when the report has no per-item lines, so the unique key still works.
    item_id: Mapped[str] = mapped_column(String(64), default="")
    item_name: Mapped[str | None] = mapped_column(Text)
    order_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    commission: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str | None] = mapped_column(String(40))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Watch(Base):
    """A job the worker enqueues again every `every_hours` (e.g. a daily keyword search or report)."""

    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    every_hours: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
