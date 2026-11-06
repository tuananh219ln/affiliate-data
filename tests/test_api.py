import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from affiliate_data import crypto, store
from affiliate_data.main import app
from affiliate_data.models import PlatformSession

STATE = {"cookies": [{"name": "SPC_EC", "value": "secret", "domain": ".shopee.vn", "path": "/"}], "origins": []}


def test_api_needs_the_key():
    assert TestClient(app).get("/api/jobs").status_code == 401
    assert TestClient(app, headers={"X-API-Key": "wrong"}).get("/api/jobs").status_code == 401
    assert TestClient(app).get("/health").status_code == 200


def test_session_is_stored_encrypted_and_never_returned(client, db):
    response = client.put("/api/sessions/shopee", json=STATE)
    assert response.status_code == 200
    assert "secret" not in response.text

    saved = db.get(PlatformSession, "shopee")
    assert "secret" not in saved.storage_state
    assert json.loads(crypto.decrypt(saved.storage_state)) == STATE

    listed = client.get("/api/sessions").json()
    assert {s["platform"]: s["status"] for s in listed} == {"shopee": "ok", "tiktok": "missing"}
    assert "secret" not in json.dumps(listed)


def test_session_without_cookies_is_refused(client):
    assert client.put("/api/sessions/shopee", json={"cookies": []}).status_code == 422
    assert client.put("/api/sessions/lazada", json=STATE).status_code == 422


def test_job_is_validated_and_not_enqueued_twice(client):
    assert client.post("/api/jobs", json={"kind": "shopee.nope"}).status_code == 422
    assert client.post("/api/jobs", json={"kind": "shopee.search", "params": {"keyword": ""}}).status_code == 422
    assert (
        client.post("/api/jobs", json={"kind": "shopee.search", "params": {"keyword": "a", "pages": 99}}).status_code
        == 422
    )

    first = client.post("/api/jobs", json={"kind": "shopee.search", "params": {"keyword": "nồi chiên"}})
    again = client.post("/api/jobs", json={"kind": "shopee.search", "params": {"keyword": "nồi chiên", "pages": 1}})
    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["params"] == {"keyword": "nồi chiên", "pages": 1, "dump": False}


def test_a_search_refresh_keeps_the_commission_an_offer_found(client, db):
    store.save_products(
        db, "shopee", [{"external_id": "1", "name": "Nồi", "price": Decimal(100), "commission_rate": 0.1}]
    )
    store.save_products(db, "shopee", [{"external_id": "1", "name": "Nồi chiên", "price": Decimal(90), "sold": 7}])
    store.save_products(db, "shopee", [{"external_id": "2", "name": "Quạt", "commission_rate": 0.2}])

    products = client.get("/api/products", params={"sort": "commission"}).json()
    assert [p["external_id"] for p in products] == ["2", "1"]
    pot = products[1]
    assert (pot["name"], Decimal(pot["price"]), pot["sold"], pot["commission_rate"]) == ("Nồi chiên", 90, 7, 0.1)

    assert len(client.get("/api/products", params={"min_commission": 0.15}).json()) == 1
    assert len(client.get("/api/products", params={"q": "nồi"}).json()) == 1


def test_products_filter_like_the_reels_studio_approval_rules(client, db):
    store.save_products(
        db,
        "shopee",
        [
            {"external_id": "1", "name": "Mall tốt", "shop_type": "mall", "rating": 4.9, "sold": 500},
            {"external_id": "2", "name": "Shop thường", "shop_type": "other", "rating": 4.9, "sold": 500},
            {"external_id": "3", "name": "Ít bán", "shop_type": "preferred", "rating": 4.8, "sold": 20},
            {"external_id": "4", "name": "Sao thấp", "shop_type": "preferred_plus", "rating": 4.5, "sold": 900},
        ],
    )
    # A later search row without badge information keeps the shop type already known.
    store.save_products(db, "shopee", [{"external_id": "1", "name": "Mall tốt", "shop_type": None}])

    params = {
        "shop_type": ["mall", "preferred_plus", "preferred"],
        "min_rating": 4.7,
        "min_sold": 100,
    }
    products = client.get("/api/products", params=params).json()
    assert [(p["external_id"], p["shop_type"]) for p in products] == [("1", "mall")]
    assert client.get("/api/products", params={"shop_type": "vip"}).status_code == 422


def test_links_only_for_shopee_products(client, db):
    store.save_products(db, "tiktok", [{"external_id": "1", "name": "Son", "url": "https://x"}])
    store.save_products(db, "shopee", [{"external_id": "1", "name": "Nồi", "url": "https://shopee.vn/product/1/1"}])
    ids = [p["id"] for p in client.get("/api/products").json()]
    tiktok_id = next(p["id"] for p in client.get("/api/products", params={"platform": "tiktok"}).json())

    assert client.post("/api/products/links", json={"product_ids": [tiktok_id]}).status_code == 422
    job = client.post("/api/products/links", json={"product_ids": ids}).json()
    assert job["kind"] == "shopee.links"
    assert job["params"]["product_ids"] == [i for i in ids if i != tiktok_id]


def test_summary_groups_by_vietnam_day(client, db):
    # 23:30 UTC on 1 Nov is 06:30 on 2 Nov in Vietnam.
    late = datetime.now(UTC).replace(hour=23, minute=30, second=0, microsecond=0)
    store.save_conversions(
        db,
        "shopee",
        [
            {
                "order_id": "A",
                "item_id": "1",
                "commission": Decimal(1000),
                "order_amount": Decimal(10000),
                "ordered_at": late,
            },
            {
                "order_id": "A",
                "item_id": "2",
                "commission": Decimal(500),
                "order_amount": Decimal(5000),
                "ordered_at": late,
            },
        ],
    )
    [day] = client.get("/api/conversions/summary", params={"days": 3}).json()
    assert day["day"] == (late + timedelta(hours=7)).date().isoformat()
    assert (day["orders"], Decimal(day["commission"]), Decimal(day["order_amount"])) == (1, 1500, 15000)


def test_watch_needs_a_valid_job_and_a_slow_schedule(client):
    assert client.post("/api/watches", json={"kind": "shopee.report", "every_hours": 1}).status_code == 422
    assert (
        client.post(
            "/api/watches", json={"kind": "shopee.links", "params": {"product_ids": [1]}, "every_hours": 24}
        ).status_code
        == 422
    )
    created = client.post("/api/watches", json={"kind": "shopee.report", "every_hours": 24})
    assert created.status_code == 201
    assert client.patch(f"/api/watches/{created.json()['id']}", json={"enabled": False}).json()["enabled"] is False


def _offer(n, keyword, price, rate, **extra):
    """A saved offer from a shop Reels Studio would approve, unless `extra` says otherwise."""
    row = {
        "external_id": str(n),
        "name": f"SP {n}",
        "keyword": keyword,
        "price": Decimal(price),
        "commission_rate": rate,
    }
    return row | {"shop_type": "mall", "rating": 4.9, "sold": 500} | extra


def test_picks_rank_each_keyword_and_keep_reels_studio_rules_by_default(client, db):
    store.save_products(
        db,
        "shopee",
        [
            _offer(1, "nồi chiên", 200_000, 0.03),
            _offer(2, "nồi chiên", 100_000, 0.05, affiliate_link="https://s.shopee.vn/a"),
            _offer(3, "nồi chiên", 150_000, 0.10),
            _offer(4, "nồi chiên", 50_000, 0.20, shop_type="other"),
            _offer(5, "nồi chiên", 60_000, 0.20, rating=4.5),
            _offer(6, "nồi chiên", 70_000, 0.20, sold=10),
            _offer(7, "máy xay", 300_000, 0.07),
            _offer(8, "quạt", 300_000, None),
        ],
    )

    picks = client.get("/api/products/picks", params={"keyword": ["nồi chiên", "máy xay", "quạt"], "top": 2}).json()
    assert [(p["keyword"], [x["external_id"] for x in p["products"]]) for p in picks] == [
        ("nồi chiên", ["3", "2"]),
        ("máy xay", ["7"]),
        ("quạt", []),
    ]
    best = picks[0]["products"][1]
    assert (best["score"], best["affiliate_link"], Decimal(best["price"])) == (0.6429, "https://s.shopee.vn/a", 100_000)

    anyone = client.get("/api/products/picks", params={"keyword": "nồi chiên", "approved_only": False, "top": 1})
    assert anyone.json()[0]["products"][0]["external_id"] == "4"

    cheap = client.get("/api/products/picks", params={"keyword": "nồi chiên", "price_weight": 1, "max_price": 150_000})
    assert [x["external_id"] for x in cheap.json()[0]["products"]] == ["2", "3"]


def test_picks_need_a_keyword(client):
    assert client.get("/api/products/picks").status_code == 422
    assert client.get("/api/products/picks", params={"keyword": "  "}).status_code == 422
    assert client.get("/api/products/picks", params={"keyword": "a", "price_weight": 2}).status_code == 422


def test_picks_job_params_are_cleaned(client):
    job = client.post(
        "/api/jobs", json={"kind": "shopee.picks", "params": {"keywords": [" nồi chiên ", "nồi chiên", "máy xay"]}}
    )
    assert job.status_code == 202
    assert job.json()["params"] == {
        "keywords": ["nồi chiên", "máy xay"],
        "pages": 1,
        "top": 3,
        "price_weight": 0.5,
        "approved_only": True,
        "min_price": None,
        "max_price": None,
        "dump": False,
    }
    for bad in ({"keywords": []}, {"keywords": [""]}, {"keywords": ["a"] * 11}, {"keywords": ["a"], "top": 6}):
        assert client.post("/api/jobs", json={"kind": "shopee.picks", "params": bad}).status_code == 422
