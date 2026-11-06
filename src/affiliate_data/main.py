"""The HTTP app: the JSON API under /api (X-API-Key header) and the team's web pages (signed-in cookie)."""

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

from . import config, routes, web


def require_key(x_api_key: str = Header(default="")) -> None:
    if not config.API_KEY or not secrets.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=401, detail="Sai hoặc thiếu API key.")


def create_app() -> FastAPI:
    app = FastAPI(title="Affiliate Data", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in routes.ROUTERS:
        app.include_router(router, prefix="/api", dependencies=[Depends(require_key)])
    app.include_router(web.router)
    app.add_exception_handler(web.SignInRequired, web.sign_in_required)
    app.add_exception_handler(web.Forbidden, web.forbidden)
    return app


app = create_app()
