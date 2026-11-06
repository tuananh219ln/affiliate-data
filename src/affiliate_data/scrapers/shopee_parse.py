"""Turns JSON captured from Shopee pages into product, link and conversion rows."""

from decimal import Decimal
from typing import Any

from .. import config
from .parse import dedupe, has_any, pick, text, to_datetime, to_decimal, to_int, to_rate, walk_dicts

# shopee.vn search responses store prices multiplied by 100 000.
SEARCH_PRICE_SCALE = Decimal(100_000)


def image_url(value: Any) -> str | None:
    value = text(value)
    if value is None or value.startswith("http"):
        return value
    return f"{config.SHOPEE_IMAGE_BASE}/{value}"


def product_url(shop_id: Any, item_id: Any) -> str:
    return f"{config.SHOPEE_BASE}/product/{shop_id}/{item_id}"


_MALL_KEYS = ("is_official_shop", "isOfficialShop", "is_mall", "isMall")
_PREFERRED_PLUS_KEYS = ("is_preferred_plus_seller", "isPreferredPlusSeller", "is_preferred_plus", "isPreferredPlus")
_PREFERRED_KEYS = ("shopee_verified", "shopeeVerified", "is_preferred", "isPreferred", "is_preferred_seller")
_TYPE_LABELS = {
    "mall": "mall",
    "official": "mall",
    "preferred_plus": "preferred_plus",
    "preferredplus": "preferred_plus",
    "preferred": "preferred",
    "normal": "other",
}


def shop_type(d: dict[str, Any]) -> str | None:
    """mall | preferred_plus | preferred | other, from the shop's badge flags.

    None when the record carries none of the flags: "unknown" must not read as an ordinary shop,
    or a later save would downgrade a Mall seen elsewhere.
    """
    label = pick(d, "shop_type", "shopType")
    if isinstance(label, str) and label.strip().lower().replace(" ", "_") in _TYPE_LABELS:
        return _TYPE_LABELS[label.strip().lower().replace(" ", "_")]
    flags = [(keys, pick(d, *keys)) for keys in (_MALL_KEYS, _PREFERRED_PLUS_KEYS, _PREFERRED_KEYS)]
    if all(value is None for _, value in flags):
        return None
    for (_, value), kind in zip(flags, ("mall", "preferred_plus", "preferred"), strict=True):
        if value is True or value == 1:
            return kind
    return "other"


def _scaled_price(value: Any) -> Decimal | None:
    number = to_decimal(value)
    return None if number is None else (number / SEARCH_PRICE_SCALE).quantize(Decimal("0.01"))


def search_products(responses: list[Any], keyword: str | None = None) -> list[dict[str, Any]]:
    """Items from shopee.vn search responses (`/api/v4/search/search_items`)."""
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        if not (has_any(d, "itemid") and has_any(d, "shopid") and has_any(d, "name")):
            continue
        item_id, shop_id = str(d["itemid"]), str(d["shopid"])
        rows.append(
            {
                "external_id": item_id,
                "shop_id": shop_id,
                "shop_name": text(pick(d, "shop_name", "shopName")),
                "shop_type": shop_type(d),
                "name": text(d["name"]),
                "price": _scaled_price(pick(d, "price", "price_min")),
                "original_price": _scaled_price(pick(d, "price_before_discount", "price_min_before_discount")),
                "image_url": image_url(pick(d, "image")),
                "url": product_url(shop_id, item_id),
                "sold": to_int(pick(d, "historical_sold", "sold", "global_sold_count")),
                "rating": float(r) if (r := to_decimal(pick(d, "item_rating.rating_star"))) is not None else None,
                "keyword": keyword,
                "raw": d,
            }
        )
    return dedupe(rows, "external_id")


def offer_products(responses: list[Any], keyword: str | None = None) -> list[dict[str, Any]]:
    """Product offers from the affiliate dashboard, which carry the commission rate.

    The dashboard's prices are plain numbers (no 100 000 scale) and its keys are camelCase or
    snake_case depending on the endpoint, so both are read.
    """
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        item_id = pick(d, "itemId", "item_id")
        rate = pick(d, "commissionRate", "commission_rate", "defaultCommissionRate", "default_commission_rate")
        name = pick(d, "productName", "product_name", "itemName", "item_name", "name")
        if item_id is None or rate is None or name is None:
            continue
        shop_id = pick(d, "shopId", "shop_id")
        price = to_decimal(pick(d, "priceMin", "price_min", "price"))
        commission = to_decimal(pick(d, "commission", "commissionAmount", "commission_amount"))
        rows.append(
            {
                "external_id": str(item_id),
                "shop_id": str(shop_id) if shop_id is not None else None,
                "shop_name": text(pick(d, "shopName", "shop_name")),
                "shop_type": shop_type(d),
                "name": text(name),
                "price": price,
                "image_url": image_url(pick(d, "imageUrl", "image_url", "image")),
                "url": text(pick(d, "productLink", "product_link"))
                or (product_url(shop_id, item_id) if shop_id is not None else None),
                "sold": to_int(pick(d, "sales", "sold", "historicalSold", "historical_sold")),
                "rating": float(r) if (r := to_decimal(pick(d, "ratingStar", "rating_star", "rating"))) else None,
                "commission_rate": to_rate(rate),
                "commission_amount": commission,
                "affiliate_link": text(pick(d, "offerLink", "offer_link")),
                "keyword": keyword,
                "raw": d,
            }
        )
    return dedupe(rows, "external_id")


def short_links(responses: list[Any]) -> dict[str, str]:
    """original URL -> affiliate short link, from the custom-link tool's responses."""
    links = {}
    for d in (d for response in responses for d in walk_dicts(response)):
        short = pick(d, "shortLink", "short_link", "affiliateLink", "affiliate_link")
        original = pick(d, "originalLink", "original_link", "originUrl", "origin_url", "longLink", "long_link")
        if short and original:
            links[str(original)] = str(short)
    return links


def conversions(responses: list[Any]) -> list[dict[str, Any]]:
    """Order lines from the conversion report."""
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        order_id = pick(d, "orderId", "order_id", "checkoutId", "checkout_id", "orderSn", "order_sn")
        commission = pick(
            d, "totalCommission", "total_commission", "itemTotalCommission", "item_commission", "commission"
        )
        if order_id is None or commission is None:
            continue
        rows.append(
            {
                "order_id": str(order_id),
                "item_id": str(pick(d, "itemId", "item_id") or ""),
                "item_name": text(pick(d, "itemName", "item_name", "productName", "product_name")),
                "order_amount": to_decimal(pick(d, "actualAmount", "actual_amount", "orderAmount", "order_amount")),
                "commission": to_decimal(commission),
                "status": text(pick(d, "orderStatus", "order_status", "conversionStatus", "status")),
                "ordered_at": to_datetime(pick(d, "purchaseTime", "purchase_time", "orderTime", "order_time")),
                "raw": d,
            }
        )
    by_key = {(r["order_id"], r["item_id"]): r for r in rows}
    return list(by_key.values())
