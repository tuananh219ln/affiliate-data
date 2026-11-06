"""Picks the products to promote for a keyword: cheap and well paid first.

A product's score mixes two things, each scaled to 0..1 among the keyword's candidates:
how cheap it is (the cheapest scores 1) and how high its commission rate is (the highest
scores 1). `price_weight` sets the mix: 1 ranks by price only, 0 by commission only.
"""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product

# Reels Studio approves a product only from these shops, with this rating and these sales.
APPROVED_SHOP_TYPES = ("mall", "preferred_plus", "preferred")
APPROVED_MIN_RATING = 4.7
APPROVED_MIN_SOLD = 100


def _scaled(value: float, low: float, high: float) -> float:
    return 1.0 if high == low else (value - low) / (high - low)


def rank(products: Sequence[Product], top: int, price_weight: float = 0.5) -> list[tuple[Product, float]]:
    """The best `top` products with their scores, best first. Products lacking a price or rate are left out."""
    candidates = [p for p in products if p.price is not None and p.price > 0 and p.commission_rate is not None]
    if not candidates:
        return []
    prices = [float(p.price) for p in candidates if p.price is not None]
    rates = [p.commission_rate for p in candidates if p.commission_rate is not None]
    low_price, high_price, low_rate, high_rate = min(prices), max(prices), min(rates), max(rates)

    def score(p: Product) -> float:
        cheap = _scaled(-float(p.price or 0), -high_price, -low_price)
        paid = _scaled(p.commission_rate or 0.0, low_rate, high_rate)
        return round(price_weight * cheap + (1 - price_weight) * paid, 4)

    scored = [(p, score(p)) for p in candidates]
    # Equal scores: the better seller first, then the older row, so the order is stable.
    scored.sort(key=lambda pair: (-pair[1], -(pair[0].sold or 0), pair[0].id or 0))
    return scored[:top]


def candidates(
    db: Session,
    keyword: str,
    approved_only: bool = True,
    min_price: Decimal | int | None = None,
    max_price: Decimal | int | None = None,
) -> list[Product]:
    """Saved Shopee products found for `keyword` that carry a price and a commission rate."""
    query = select(Product).where(
        Product.platform == "shopee",
        Product.keyword == keyword,
        Product.price.is_not(None),
        Product.commission_rate.is_not(None),
    )
    if approved_only:
        query = query.where(
            Product.shop_type.in_(APPROVED_SHOP_TYPES),
            Product.rating >= APPROVED_MIN_RATING,
            Product.sold >= APPROVED_MIN_SOLD,
        )
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    return list(db.scalars(query).all())


def picks(
    db: Session,
    keyword: str,
    top: int,
    price_weight: float = 0.5,
    approved_only: bool = True,
    min_price: Decimal | int | None = None,
    max_price: Decimal | int | None = None,
) -> list[tuple[Product, float]]:
    return rank(candidates(db, keyword, approved_only, min_price, max_price), top, price_weight)
