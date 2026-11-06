from datetime import UTC, datetime
from decimal import Decimal

import pytest

from affiliate_data.scrapers import shopee_parse, tiktok_parse
from affiliate_data.scrapers.parse import pick, to_datetime, to_decimal, to_rate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (12000, Decimal(12000)),
        ("12.000", Decimal(12000)),
        ("1.234.567", Decimal(1234567)),
        ("₫99.000", Decimal(99000)),
        ("1,2k", Decimal(1200)),
        ("3.5M", Decimal(3500000)),
        ("12.5", Decimal("12.5")),
        ("abc", None),
        (None, None),
        (True, None),
    ],
)
def test_to_decimal(raw, expected):
    assert to_decimal(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("10%", 0.1), (10, 0.1), (0.07, 0.07), (1000, 0.1), ("12.5%", 0.125), (None, None)]
)
def test_to_rate(raw, expected):
    if expected is None:
        assert to_rate(raw) is None
    else:
        assert to_rate(raw) == pytest.approx(expected)


def test_to_datetime_accepts_seconds_millis_and_iso():
    expected = datetime(2026, 11, 1, tzinfo=UTC)
    assert to_datetime(1793491200) == expected
    assert to_datetime(1793491200000) == expected
    assert to_datetime("2026-11-01T00:00:00Z") == expected


def test_pick_follows_dotted_paths_and_list_indexes():
    d = {"a": {"b": [{"c": 1}]}, "empty": ""}
    assert pick(d, "missing", "a.b.0.c") == 1
    assert pick(d, "empty", "a.b.5.c") is None


SHOPEE_SEARCH = {
    "items": [
        {
            "itemid": 111,
            "shopid": 222,
            "item_basic": {
                "itemid": 111,
                "shopid": 222,
                "name": "Áo thun nam",
                "price": 15900000000,
                "price_before_discount": 25000000000,
                "image": "vn-abc",
                "historical_sold": 1520,
                "item_rating": {"rating_star": 4.8},
                "shop_name": "Coolmate Official",
                "is_official_shop": True,
                "shopee_verified": True,
            },
        }
    ]
}


def test_shopee_search_reads_items_and_unscales_prices():
    [row] = shopee_parse.search_products([SHOPEE_SEARCH], "áo thun")
    assert row["external_id"] == "111"
    assert row["name"] == "Áo thun nam"
    assert row["price"] == Decimal("159000.00")
    assert row["original_price"] == Decimal("250000.00")
    assert row["sold"] == 1520
    assert row["rating"] == 4.8
    assert row["url"].endswith("/product/222/111")
    assert row["image_url"].endswith("/vn-abc")
    assert row["keyword"] == "áo thun"
    assert (row["shop_name"], row["shop_type"]) == ("Coolmate Official", "mall")


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"is_official_shop": True, "shopee_verified": True}, "mall"),
        ({"is_official_shop": False, "is_preferred_plus_seller": True}, "preferred_plus"),
        ({"is_official_shop": False, "shopee_verified": True}, "preferred"),
        ({"isOfficialShop": False, "shopeeVerified": False}, "other"),
        ({"shopType": "Preferred Plus"}, "preferred_plus"),
        ({"shopType": "Mall"}, "mall"),
        # No badge information at all is unknown, not an ordinary shop.
        ({"name": "x"}, None),
        ({"shopType": "something new"}, None),
    ],
)
def test_shopee_shop_type(record, expected):
    assert shopee_parse.shop_type(record) == expected


def test_shopee_offers_read_commission_from_camel_or_snake_case():
    response = {
        "data": {
            "list": [
                {"itemId": 1, "shopId": 9, "productName": "Nồi chiên", "priceMin": "990000", "commissionRate": "8%"},
                {"item_id": 2, "item_name": "Quạt", "price": 300000, "default_commission_rate": 12},
                {"item_id": 3, "item_name": "No rate"},
            ]
        }
    }
    rows = {r["external_id"]: r for r in shopee_parse.offer_products([response])}
    assert set(rows) == {"1", "2"}
    assert rows["1"]["commission_rate"] == pytest.approx(0.08)
    assert rows["1"]["price"] == Decimal(990000)
    assert rows["1"]["url"].endswith("/product/9/1")
    assert rows["2"]["commission_rate"] == pytest.approx(0.12)
    assert rows["2"]["url"] is None


def test_shopee_short_links_map_original_to_short():
    response = {
        "data": {"batchCustomLink": [{"originalLink": "https://shopee.vn/p/1", "shortLink": "https://s.shopee.vn/x"}]}
    }
    assert shopee_parse.short_links([response]) == {"https://shopee.vn/p/1": "https://s.shopee.vn/x"}


def test_shopee_conversions_keep_one_row_per_order_item():
    response = {
        "data": {
            "list": [
                {
                    "checkoutId": 5,
                    "itemId": 1,
                    "totalCommission": "12.000",
                    "actualAmount": 150000,
                    "purchaseTime": 1793491200,
                },
                {
                    "checkoutId": 5,
                    "itemId": 1,
                    "totalCommission": "13.000",
                    "actualAmount": 150000,
                    "purchaseTime": 1793491200,
                },
                {"checkoutId": 5, "itemId": 2, "totalCommission": 500},
            ]
        }
    }
    rows = shopee_parse.conversions([response])
    assert len(rows) == 2
    first = next(r for r in rows if r["item_id"] == "1")
    assert first["commission"] == Decimal(13000)
    assert first["ordered_at"] == datetime(2026, 11, 1, tzinfo=UTC)


def test_tiktok_videos_read_stats_and_build_url():
    response = {
        "item_list": [
            {
                "id": "7300",
                "desc": "review nồi chiên",
                "createTime": 1793491200,
                "author": {"uniqueId": "shop.ab", "id": "1"},
                "video": {"cover": "https://p16/cover.jpg"},
                "stats": {"playCount": 120000, "diggCount": 5000, "commentCount": 30, "shareCount": 12},
                "statsV2": {"playCount": "125000"},
            }
        ]
    }
    [row] = tiktok_parse.videos([response], "nồi chiên")
    assert row["url"].endswith("/@shop.ab/video/7300")
    assert row["views"] == 125000  # statsV2 is fresher and wins
    assert row["likes"] == 5000
    assert row["posted_at"] == datetime(2026, 11, 1, tzinfo=UTC)


def test_tiktok_products_read_money_objects_and_basis_point_rates():
    response = {
        "data": {
            "products": [
                {
                    "product_id": "17",
                    "title": "Son kem",
                    "price": {"amount": "129000", "currency": "VND"},
                    "commission_rate": 1500,
                    "sold_count": 2300,
                }
            ]
        }
    }
    [row] = tiktok_parse.products([response])
    assert row["price"] == Decimal(129000)
    assert row["commission_rate"] == pytest.approx(0.15)
    assert row["sold"] == 2300


def test_tiktok_conversions():
    response = {"orders": [{"order_id": "9", "product_id": "17", "estimated_commission": {"amount": "19350"}}]}
    [row] = tiktok_parse.conversions([response])
    assert (row["order_id"], row["item_id"], row["commission"]) == ("9", "17", Decimal(19350))
