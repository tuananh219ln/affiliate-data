from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from affiliate_data import accounts, jobs, store
from affiliate_data.main import app
from affiliate_data.models import Job

PASSWORD = "mat-khau-dai-du"


@pytest.fixture
def web():
    return TestClient(app, follow_redirects=False)


def _member(db, email="an@example.com", admin=False):
    return accounts.create(db, email, email.split("@")[0], PASSWORD, is_admin=admin)


def _sign_in(web, email="an@example.com", password=PASSWORD):
    return web.post("/login", data={"email": email, "password": password})


def test_pages_need_signing_in_and_the_api_still_takes_the_key(web, client):
    for path in ("/", "/picks", "/picks/1", "/jobs", "/revenue", "/sessions", "/members", "/account"):
        response = web.get(path)
        assert (response.status_code, response.headers["location"]) == (303, "/login"), path
    assert web.get("/login").status_code == 200
    assert client.get("/api/jobs").status_code == 200
    assert web.get("/api/jobs").status_code == 401


def test_signing_in(web, db):
    _member(db, "An@Example.com")
    assert _sign_in(web, password="sai-mat-khau").status_code == 401
    assert _sign_in(web, email="khong-co@example.com").status_code == 401
    assert "Sai email hoặc mật khẩu" in _sign_in(web, email="khong-co@example.com").text

    response = _sign_in(web, email=" AN@example.com ")
    assert (response.status_code, response.headers["location"]) == (303, "/")
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=1209600" in cookie
    assert web.get("/picks").status_code == 200

    web.post("/logout")
    assert web.get("/picks").status_code == 303


def test_a_changed_cookie_or_a_turned_off_member_is_signed_out(web, db):
    member = _member(db)
    _sign_in(web)
    token = web.cookies[accounts.COOKIE]

    web.cookies.set(accounts.COOKIE, token[:-4] + "AAAA")
    assert web.get("/picks").status_code == 303

    web.cookies.set(accounts.COOKIE, token)
    assert web.get("/picks").status_code == 200
    member.active = False
    db.commit()
    assert web.get("/picks").status_code == 303
    assert _sign_in(web).status_code == 401


def test_a_new_password_signs_out_other_devices_but_not_this_one(web, db):
    _member(db)
    other = TestClient(app, follow_redirects=False)
    _sign_in(web)
    _sign_in(other)

    wrong = web.post("/account/password", data={"current": "sai-mat-khau", "new": "mat-khau-moi-123"})
    assert wrong.status_code == 422 and "không đúng" in wrong.text
    assert web.post("/account/password", data={"current": PASSWORD, "new": "ngan"}).status_code == 422

    changed = web.post("/account/password", data={"current": PASSWORD, "new": "mat-khau-moi-123"})
    assert changed.status_code == 303
    assert web.get("/account").status_code == 200
    assert other.get("/account").status_code == 303
    assert _sign_in(other, password="mat-khau-moi-123").status_code == 303


def test_a_form_from_another_site_is_refused(web, db):
    _member(db)
    _sign_in(web)
    response = web.post(
        "/picks", data={"platform": "shopee", "keywords": "nồi"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert db.query(Job).count() == 0


def test_picking_from_the_page_enqueues_a_job_and_shows_its_picks(web, db):
    member = _member(db)
    _sign_in(web)

    refused = web.post("/picks", data={"platform": "shopee", "keywords": " \n "})
    assert refused.status_code == 422 and "Tham số không hợp lệ" in refused.text

    response = web.post(
        "/picks",
        data={
            "platform": "shopee",
            "keywords": "nồi chiên\nmáy xay\n",
            "top": "2",
            "price_weight": "0.5",
            "min_price": "",
            "max_price": "500000",
            "approved_only": "true",
        },
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 303
    job = db.get(Job, int(response.headers["location"].rsplit("/", 1)[1]))
    assert (job.kind, job.created_by) == ("shopee.picks", member.id)
    assert job.params == jobs.validate(
        "shopee.picks", {"keywords": ["nồi chiên", "máy xay"], "top": 2, "max_price": 500000}
    )

    page = web.get(f"/picks/{job.id}")
    assert page.status_code == 200
    assert 'http-equiv="refresh"' in page.text and "Đang chờ" in page.text

    good = {"shop_type": "mall", "rating": 4.9, "sold": 1234, "keyword": "nồi chiên"}
    store.save_products(
        db,
        "shopee",
        [
            {
                "external_id": "1",
                "name": "Nồi tốt",
                "price": Decimal(200_000),
                "commission_rate": 0.1,
                "url": "https://shopee.vn/product/1/1",
                "affiliate_link": "https://s.shopee.vn/abc",
                **good,
            },
            {
                "external_id": "2",
                "name": "Nồi lạ",
                "price": Decimal(300_000),
                "commission_rate": 0.05,
                "url": "javascript:alert(1)",
                "image_url": "javascript:alert(2)",
                **good,
            },
        ],
    )
    job.status = "done"
    job.result = {"products": 2, "picked": 2, "links": 1, "without_link": 1, "no_pick": ["máy xay"]}
    db.commit()

    page = web.get(f"/picks/{job.id}").text
    assert "http-equiv" not in page
    assert "Nồi tốt" in page and "200.000 ₫" in page and "20.000 ₫" in page and "10 %" in page and "1.234" in page
    assert 'data-copy="https://s.shopee.vn/abc"' in page
    assert 'href="https://shopee.vn/product/1/1"' in page
    assert "javascript:" not in page
    assert "Không có sản phẩm nào đạt điều kiện" in page  # máy xay
    assert "an" in web.get("/picks").text


def test_pages_for_jobs_revenue_and_logins_show(web, db):
    _member(db)
    _sign_in(web)
    jobs.enqueue(db, "shopee.report", {})
    assert "Báo cáo đơn/hoa hồng Shopee" in web.get("/jobs").text
    assert "Doanh thu 30 ngày" in web.get("/revenue").text
    assert "Chưa đăng nhập" in web.get("/sessions").text
    assert web.get("/picks/999").status_code == 404


def test_only_admins_manage_members(web, db):
    admin = _member(db, "chu@example.com", admin=True)
    _member(db, "an@example.com")

    _sign_in(web, "an@example.com")
    assert web.get("/members").status_code == 403
    assert web.post("/members", data={"email": "x@example.com", "name": "X", "password": PASSWORD}).status_code == 403

    web.cookies.clear()
    _sign_in(web, "chu@example.com")
    assert "an@example.com" in web.get("/members").text

    added = web.post("/members", data={"email": "Binh@Example.com", "name": "Bình", "password": PASSWORD})
    assert added.status_code == 303
    assert accounts.find(db, "binh@example.com").name == "Bình"
    taken = web.post("/members", data={"email": "binh@example.com", "name": "B", "password": PASSWORD})
    assert taken.status_code == 422 and "đã có tài khoản" in taken.text
    assert web.post("/members", data={"email": "c@example.com", "name": "C", "password": "ngan"}).status_code == 422

    an = accounts.find(db, "an@example.com")
    assert web.post(f"/members/{an.id}/active", data={}).status_code == 303
    db.refresh(an)
    assert an.active is False
    assert web.post(f"/members/{an.id}/active", data={"active": "true"}).status_code == 303
    db.refresh(an)
    assert an.active is True

    turn_self_off = web.post(f"/members/{admin.id}/active", data={})
    assert turn_self_off.status_code == 422 and "Không thể tự tắt" in turn_self_off.text


def test_passwords_are_hashed_with_a_salt():
    one, two = accounts.hash_password("giong-nhau-123"), accounts.hash_password("giong-nhau-123")
    assert one != two and "giong-nhau" not in one
    assert accounts.check_password("giong-nhau-123", one)
    assert not accounts.check_password("khac-123456", one)
    assert not accounts.check_password("x", "not-a-hash")
