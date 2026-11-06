"""The team's web pages: sign in, pick products, follow jobs, revenue, members.

Pages are rendered on the server. Signing in sets an encrypted cookie (see accounts.py); the
JSON API under /api keeps using the API key. Like the API, a page never scrapes: it enqueues a
job and the worker runs it.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import accounts, config, jobs, ranking, routes
from .db import get_db
from .models import Job, Product, User

VN = ZoneInfo(config.TIME_ZONE)
PICK_KINDS = {"shopee": "shopee.picks", "tiktok": "tiktok.picks"}
STATUS_LABELS = {"queued": "Đang chờ", "running": "Đang chạy", "done": "Xong", "failed": "Lỗi"}
# Messages a redirect may ask a page to show: a code in the URL, never the text itself.
NOTICES = {
    "member_added": "Đã thêm thành viên.",
    "member_changed": "Đã cập nhật thành viên.",
    "password_changed": "Đã đổi mật khẩu.",
}

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _money(value: Decimal | float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", ".") + " ₫"


def _percent(rate: float | None) -> str:
    return "—" if rate is None else f"{rate * 100:.1f}".rstrip("0").rstrip(".") + " %"


def _when(moment: datetime | None) -> str:
    return "—" if moment is None else moment.astimezone(VN).strftime("%d/%m %H:%M")


def _number(value: int | None) -> str:
    return "—" if value is None else f"{value:,}".replace(",", ".")


def _per_order(product: Product) -> Decimal | None:
    """Commission on one sale: what the site said, or price x rate."""
    if product.commission_amount is not None:
        return product.commission_amount
    if product.price is None or product.commission_rate is None:
        return None
    return product.price * Decimal(str(product.commission_rate))


def _web_url(value: str | None) -> str | None:
    """Only http(s) links go into href/src: these come from scraped pages and could say javascript:."""
    return value if value and urlsplit(value).scheme in ("http", "https") else None


templates.env.filters.update(
    money=_money, percent=_percent, when=_when, number=_number, per_order=_per_order, web_url=_web_url
)
templates.env.globals.update(status_labels=STATUS_LABELS, kind_labels=jobs.KIND_LABELS)


class SignInRequired(Exception):
    pass


class Forbidden(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = accounts.user_from_token(db, request.cookies.get(accounts.COOKIE))
    if user is None:
        raise SignInRequired
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise Forbidden
    return user


def same_origin(request: Request) -> None:
    """Refuses a form posted from another site. The Lax cookie already stops most; this covers the rest."""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise Forbidden


def _page(request: Request, name: str, user: User | None, status_code: int = 200, **context: Any) -> HTMLResponse:
    notice = NOTICES.get(request.query_params.get("notice", ""))
    return templates.TemplateResponse(
        request, name, {"user": user, "notice": notice, **context}, status_code=status_code
    )


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]
Member = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(admin_user)]
Posted = [Depends(same_origin)]


# --- Signing in -------------------------------------------------------------------------------


@router.get("/login")
def login_page(request: Request, db: Db) -> Response:
    if accounts.user_from_token(db, request.cookies.get(accounts.COOKIE)):
        return _redirect("/")
    return _page(request, "login.html", None)


@router.post("/login", dependencies=Posted)
def login(request: Request, db: Db, email: Annotated[str, Form()], password: Annotated[str, Form()]) -> Response:
    user = accounts.authenticate(db, email, password)
    if user is None:
        return _page(request, "login.html", None, 401, error="Sai email hoặc mật khẩu.", email=email)
    return _signed_in(_redirect("/"), user)


def _signed_in(response: Response, user: User) -> Response:
    response.set_cookie(
        accounts.COOKIE,
        accounts.session_token(user),
        max_age=accounts.SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.post("/logout", dependencies=Posted)
def logout() -> Response:
    response = _redirect("/login")
    response.delete_cookie(accounts.COOKIE)
    return response


# --- Picking products -------------------------------------------------------------------------


@router.get("/")
def home(user: Member) -> Response:
    return _redirect("/picks")


def _members(db: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(wanted))).all()}


def _picks_form(request: Request, db: Session, user: User, status_code: int = 200, **context: Any) -> HTMLResponse:
    recent = db.scalars(select(Job).where(Job.kind.in_(PICK_KINDS.values())).order_by(desc(Job.id)).limit(20)).all()
    form = {"platform": "shopee", "keywords": "", "top": 3, "price_weight": 0.5, "approved_only": True} | context.pop(
        "form", {}
    )
    return _page(
        request,
        "picks.html",
        user,
        status_code,
        recent=recent,
        members=_members(db, {j.created_by for j in recent}),
        form=form,
        **context,
    )


@router.get("/picks")
def picks_page(request: Request, db: Db, user: Member) -> Response:
    return _picks_form(request, db, user)


@router.post("/picks", dependencies=Posted)
def start_picks(
    request: Request,
    db: Db,
    user: Member,
    platform: Annotated[str, Form()],
    keywords: Annotated[str, Form()],
    top: Annotated[int, Form()] = 3,
    price_weight: Annotated[float, Form()] = 0.5,
    min_price: Annotated[str, Form()] = "",
    max_price: Annotated[str, Form()] = "",
    approved_only: Annotated[bool, Form()] = False,
) -> Response:
    form = {
        "platform": platform,
        "keywords": keywords,
        "top": top,
        "price_weight": price_weight,
        "min_price": min_price,
        "max_price": max_price,
        "approved_only": approved_only,
    }
    kind = PICK_KINDS.get(platform)
    params = {
        "keywords": [line for line in keywords.splitlines() if line.strip()],
        "top": top,
        "price_weight": price_weight,
        "approved_only": approved_only,
        "min_price": int(min_price) if min_price.strip().isdigit() else None,
        "max_price": int(max_price) if max_price.strip().isdigit() else None,
    }
    if kind is None:
        return _picks_form(request, db, user, 422, error="Chọn Shopee hoặc TikTok.", form=form)
    try:
        job = jobs.enqueue(db, kind, params, created_by=user.id)
    except jobs.InvalidJob as error:
        return _picks_form(request, db, user, 422, error=str(error), form=form)
    return _redirect(f"/picks/{job.id}")


@router.get("/picks/{job_id}")
def pick_results(request: Request, db: Db, user: Member, job_id: int) -> Response:
    job = db.get(Job, job_id)
    if job is None or job.kind not in PICK_KINDS.values():
        return _page(request, "missing.html", user, 404, what="lượt chọn sản phẩm")
    p = job.params
    platform = jobs.platform_of(job.kind)
    options = {k: p[k] for k in ("top", "price_weight", "approved_only", "min_price", "max_price")}
    results = [(keyword, ranking.picks(db, platform, keyword, **options)) for keyword in p["keywords"]]
    return _page(
        request,
        "pick_results.html",
        user,
        job=job,
        platform=platform,
        results=results,
        creator=_members(db, {job.created_by}).get(job.created_by or 0),
        refresh=job.status in ("queued", "running"),
    )


# --- Jobs, revenue, platform logins -----------------------------------------------------------


@router.get("/jobs")
def jobs_page(request: Request, db: Db, user: Member) -> Response:
    recent = db.scalars(select(Job).order_by(desc(Job.id)).limit(100)).all()
    return _page(
        request,
        "jobs.html",
        user,
        jobs=recent,
        members=_members(db, {j.created_by for j in recent}),
        refresh=any(j.status in ("queued", "running") for j in recent),
    )


@router.get("/revenue")
def revenue_page(request: Request, db: Db, user: Member) -> Response:
    days = routes.summary(days=30, db=db)
    totals = {
        platform: {
            "orders": sum(d.orders for d in days if d.platform == platform),
            "commission": sum((d.commission for d in days if d.platform == platform), Decimal(0)),
        }
        for platform in ("shopee", "tiktok")
    }
    return _page(request, "revenue.html", user, days=days, totals=totals)


@router.get("/sessions")
def sessions_page(request: Request, db: Db, user: Member) -> Response:
    return _page(request, "sessions.html", user, sessions=routes.list_sessions(db=db))


# --- Members and the member's own password -----------------------------------------------------


def _members_page(request: Request, db: Session, user: User, status_code: int = 200, **context: Any) -> HTMLResponse:
    people = db.scalars(select(User).order_by(User.id)).all()
    return _page(request, "members.html", user, status_code, people=people, **context)


@router.get("/members")
def members_page(request: Request, db: Db, user: Admin) -> Response:
    return _members_page(request, db, user)


@router.post("/members", dependencies=Posted)
def add_member(
    request: Request,
    db: Db,
    user: Admin,
    email: Annotated[str, Form()],
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    is_admin: Annotated[bool, Form()] = False,
) -> Response:
    try:
        accounts.create(db, email, name, password, is_admin)
    except accounts.AccountError as error:
        return _members_page(request, db, user, 422, error=str(error), form={"email": email, "name": name})
    return _redirect("/members?notice=member_added")


@router.post("/members/{member_id}/active", dependencies=Posted)
def set_member_active(
    request: Request, db: Db, user: Admin, member_id: int, active: Annotated[bool, Form()] = False
) -> Response:
    member = db.get(User, member_id)
    if member is None:
        return _page(request, "missing.html", user, 404, what="thành viên")
    # The admin doing this stays on, so there is always an admin left.
    if not active and member.id == user.id:
        return _members_page(request, db, user, 422, error="Không thể tự tắt tài khoản của mình.")
    member.active = active
    db.commit()
    return _redirect("/members?notice=member_changed")


@router.get("/account")
def account_page(request: Request, user: Member) -> Response:
    return _page(request, "account.html", user)


@router.post("/account/password", dependencies=Posted)
def change_password(
    request: Request,
    db: Db,
    user: Member,
    current: Annotated[str, Form()],
    new: Annotated[str, Form()],
) -> Response:
    if not accounts.check_password(current, user.password_hash):
        return _page(request, "account.html", user, 422, error="Mật khẩu hiện tại không đúng.")
    try:
        accounts.check_new_password(new)
    except accounts.AccountError as error:
        return _page(request, "account.html", user, 422, error=str(error))
    user.password_hash = accounts.hash_password(new)
    db.commit()
    # The old cookie no longer matches the password (other devices are signed out); give this one a new one.
    return _signed_in(_redirect("/account?notice=password_changed"), user)


def sign_in_required(request: Request, error: Exception) -> Response:
    return _redirect("/login")


def forbidden(request: Request, error: Exception) -> Response:
    return _page(request, "forbidden.html", None, 403)
