"""python -m affiliate_data <api|worker|migrate|login|create-user>."""

import argparse
import getpass
import json
import urllib.request
from pathlib import Path

LOGIN_PAGES = {
    # Both the shop and the affiliate dashboard, so the saved state has cookies for each.
    "shopee": ["https://shopee.vn/buyer/login", "https://affiliate.shopee.vn/"],
    "tiktok": ["https://www.tiktok.com/login", "https://affiliate.tiktok.com/"],
}


def login(platform: str, out: Path, upload: str | None, api_key: str | None) -> None:
    """Opens a visible browser; a person logs in by hand (captcha, OTP and all), then presses Enter."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="vi-VN")
        for url in LOGIN_PAGES[platform]:
            context.new_page().goto(url)
        input(f"Đăng nhập {platform} trong cửa sổ trình duyệt (cả trang affiliate), xong thì nhấn Enter ở đây... ")
        state = context.storage_state()
        browser.close()

    out.write_text(json.dumps(state), encoding="utf-8")
    print(f"Đã lưu phiên vào {out} (đừng commit hay gửi file này cho ai).")
    if upload:
        request = urllib.request.Request(
            f"{upload.rstrip('/')}/api/sessions/{platform}",
            data=json.dumps(state).encode(),
            method="PUT",
            headers={"Content-Type": "application/json", "X-API-Key": api_key or ""},
        )
        with urllib.request.urlopen(request) as response:
            print(f"Đã tải phiên lên: HTTP {response.status}")


def create_user(email: str, name: str, is_admin: bool) -> None:
    """Adds a member from the command line; the first admin is made this way, the rest on /members."""
    from . import accounts
    from .db import SessionLocal

    password = getpass.getpass("Mật khẩu: ")
    if password != getpass.getpass("Nhập lại mật khẩu: "):
        raise SystemExit("Hai lần nhập không khớp.")
    with SessionLocal() as db:
        try:
            user = accounts.create(db, email, name or email, password, is_admin)
        except accounts.AccountError as error:
            raise SystemExit(str(error)) from error
    print(f"Đã tạo {'quản trị viên' if is_admin else 'thành viên'} {user.email}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="affiliate_data")
    commands = parser.add_subparsers(dest="command", required=True)

    api = commands.add_parser("api", help="run the HTTP API")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)

    commands.add_parser("worker", help="run the job worker")
    commands.add_parser("migrate", help="upgrade the database to the latest migration")

    login_cmd = commands.add_parser("login", help="log in by hand and save the browser session")
    login_cmd.add_argument("platform", choices=sorted(LOGIN_PAGES))
    login_cmd.add_argument("--out", type=Path, help="where to save the session (default <platform>-session.json)")
    login_cmd.add_argument("--upload", help="API base URL to upload the session to, e.g. http://localhost:8000")
    login_cmd.add_argument("--api-key", help="the API's X-API-Key, for --upload")

    user_cmd = commands.add_parser("create-user", help="add a member who can sign in to the web pages")
    user_cmd.add_argument("email")
    user_cmd.add_argument("--name", default="")
    user_cmd.add_argument("--admin", action="store_true", help="may add and turn off members")

    args = parser.parse_args()
    if args.command == "api":
        import uvicorn

        uvicorn.run("affiliate_data.main:app", host=args.host, port=args.port)
    elif args.command == "worker":
        from .worker import run_forever

        run_forever()
    elif args.command == "migrate":
        from alembic import command
        from alembic.config import Config

        # Run from the project root (the Docker image's WORKDIR), where alembic.ini lives.
        command.upgrade(Config("alembic.ini"), "head")
    elif args.command == "login":
        login(args.platform, args.out or Path(f"{args.platform}-session.json"), args.upload, args.api_key)
    elif args.command == "create-user":
        create_user(args.email, args.name, args.admin)
