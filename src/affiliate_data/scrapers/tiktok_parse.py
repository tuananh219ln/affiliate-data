"""Turns JSON captured from TikTok pages into video, product and conversion rows."""

from typing import Any

from .. import config
from .parse import dedupe, has_any, pick, text, to_datetime, to_decimal, to_int, to_rate, walk_dicts


def videos(responses: list[Any], keyword: str | None = None) -> list[dict[str, Any]]:
    """Videos from tiktok.com search and tag responses (`item_list` / `data[].item`)."""
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        if not (has_any(d, "id") and "desc" in d and has_any(d, "stats", "statsV2")):
            continue
        author = pick(d, "author.uniqueId", "author.unique_id", "author")
        author = author if isinstance(author, str) else None
        video_id = str(d["id"])
        rows.append(
            {
                "external_id": video_id,
                "author": author,
                "description": text(d.get("desc")),
                "cover_url": text(pick(d, "video.cover", "video.originCover", "video.dynamicCover")),
                "url": f"{config.TIKTOK_BASE}/@{author}/video/{video_id}" if author else None,
                "views": to_int(pick(d, "statsV2.playCount", "stats.playCount")),
                "likes": to_int(pick(d, "statsV2.diggCount", "stats.diggCount")),
                "comments": to_int(pick(d, "statsV2.commentCount", "stats.commentCount")),
                "shares": to_int(pick(d, "statsV2.shareCount", "stats.shareCount")),
                "posted_at": to_datetime(pick(d, "createTime", "create_time")),
                "keyword": keyword,
                "raw": d,
            }
        )
    return dedupe(rows, "external_id")


def _money(value: Any) -> Any:
    """TikTok Shop prices come as {"amount": "...", "currency": "VND"} or as a plain number."""
    if isinstance(value, dict):
        return pick(value, "amount", "price", "min_price", "sale_price")
    return value


def products(responses: list[Any], keyword: str | None = None) -> list[dict[str, Any]]:
    """Products from the TikTok Shop affiliate marketplace, with their commission rate."""
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        product_id = pick(d, "product_id", "productId")
        name = pick(d, "title", "product_name", "productName", "name")
        rate = pick(d, "commission_rate", "commissionRate", "commission.rate", "commission_rate_info.rate")
        if product_id is None or name is None or rate is None:
            continue
        rows.append(
            {
                "external_id": str(product_id),
                "shop_id": text(pick(d, "shop_id", "shopId", "seller_id", "shop.shop_id")),
                "shop_name": text(pick(d, "shop_name", "shopName", "seller_name", "shop.shop_name", "shop.name")),
                "name": text(name),
                "price": to_decimal(_money(pick(d, "price", "sale_price", "min_price", "price_info.sale_price"))),
                "original_price": to_decimal(_money(pick(d, "original_price", "origin_price"))),
                "image_url": text(pick(d, "cover", "image.url_list.0", "main_image", "image_url", "cover_url")),
                "url": text(pick(d, "product_url", "detail_url", "pdp_url")),
                "sold": to_int(pick(d, "sold_count", "sale_count", "sales", "sold")),
                "rating": float(r) if (r := to_decimal(pick(d, "rating", "product_rating", "star"))) else None,
                "commission_rate": to_rate(rate),
                "commission_amount": to_decimal(_money(pick(d, "commission_amount", "commission.amount"))),
                "keyword": keyword,
                "raw": d,
            }
        )
    return dedupe(rows, "external_id")


def conversions(responses: list[Any]) -> list[dict[str, Any]]:
    """Order lines from the creator's affiliate order page."""
    rows = []
    for d in (d for response in responses for d in walk_dicts(response)):
        order_id = pick(d, "order_id", "orderId", "main_order_id")
        commission = pick(
            d, "estimated_commission", "estimatedCommission", "actual_commission", "commission_amount", "commission"
        )
        if order_id is None or commission is None:
            continue
        rows.append(
            {
                "order_id": str(order_id),
                "item_id": str(pick(d, "product_id", "productId", "sku_id") or ""),
                "item_name": text(pick(d, "product_name", "productName", "title")),
                "order_amount": to_decimal(_money(pick(d, "payment_amount", "order_amount", "gmv", "price"))),
                "commission": to_decimal(_money(commission)),
                "status": text(pick(d, "order_status", "status", "settlement_status")),
                "ordered_at": to_datetime(pick(d, "create_time", "order_create_time", "createTime")),
                "raw": d,
            }
        )
    by_key = {(r["order_id"], r["item_id"]): r for r in rows}
    return list(by_key.values())
