"""Edvatiq multi-industry business manager API."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import access, ai, auth, billing, business, client_intelligence, clients, clinic, college, college_placement, dashboard, documents, gym, inventory, misc, notifications, reports, roles, sales, salon, settings as business_settings, super_admin, team, users
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.auth_security import valid_csrf_token
from app.services.realtime import publish_change
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def _is_windows_client_disconnect(context: dict) -> bool:
    """Ignore only the Proactor callback raised when a browser closes a socket."""
    error = context.get("exception")
    callback = str(context.get("handle") or context.get("message") or "")
    return (
        isinstance(error, ConnectionResetError)
        and getattr(error, "winerror", None) == 10054
        and "_ProactorBasePipeTransport._call_connection_lost" in callback
    )


def _install_asyncio_exception_filter():
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def handle_exception(active_loop, context):
        if _is_windows_client_disconnect(context):
            logger.debug("client_connection_reset")
            return
        if previous:
            previous(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)

    def restore():
        loop.set_exception_handler(previous)

    return restore


def init_database():
    from alembic import command
    from alembic.config import Config
    from app.db.seed import create_demo_businesses, seed_client_signal_jobs, seed_platform, seed_welcome_notifications

    backend_dir = Path(__file__).resolve().parent
    command.upgrade(Config(str(backend_dir / "alembic.ini")), "head")
    with SessionLocal() as db:
        seed_platform(db)
        create_demo_businesses(db)
        seed_platform(db)
        seed_welcome_notifications(db)
        seed_client_signal_jobs(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    restore_exception_handler = _install_asyncio_exception_filter()
    try:
        init_database()
        yield
    finally:
        restore_exception_handler()


app = FastAPI(title="Edvatiq Business Manager API", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    cookie_authenticated = bool(request.cookies.get(settings.ACCESS_COOKIE_NAME) or request.cookies.get(settings.REFRESH_COOKIE_NAME))
    bearer_authenticated = bool(request.headers.get("authorization"))
    public_auth_paths = {
        "/api/auth/register", "/api/auth/login", "/api/auth/email/request-code",
        "/api/auth/email/verify", "/api/auth/password/forgot", "/api/auth/password/reset",
        "/api/auth/platform-invite/accept",
    }
    if unsafe and cookie_authenticated and not bearer_authenticated and request.url.path not in public_auth_paths:
        cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
        header_token = request.headers.get("x-csrf-token")
        if not cookie_token or not header_token or cookie_token != header_token or not valid_csrf_token(cookie_token):
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed", "error": {"code": "csrf_failed", "message": "Refresh the page and try again"}})
    return await call_next(request)


@app.middleware("http")
async def publish_tenant_changes(request: Request, call_next):
    response = await call_next(request)
    is_ai_chat = request.url.path in {"/api/ai/chat", "/api/ai/chat/stream"}
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and 200 <= response.status_code < 400:
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id and not is_ai_chat and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
            path = request.url.path.removeprefix("/api")
            try:
                await asyncio.to_thread(publish_change, str(tenant_id), path)
            except Exception as exc:
                logger.warning("realtime_publish_failed path=%s error_type=%s", path, type(exc).__name__)
    return response


api = APIRouter(prefix="/api")
for router in [auth.router, users.router, roles.router, access.router, clients.router, client_intelligence.router, dashboard.router, inventory.router, sales.router, salon.router, business_settings.router, team.router, business.router, gym.router, clinic.router, college.router, college_placement.router, documents.router, notifications.router, ai.router, reports.router, billing.router, super_admin.router, misc.router]:
    api.include_router(router)


@api.get("/")
def root(): return {"service": "Edvatiq Business Manager", "version": "2.0.0"}


@api.get("/health")
def health(): return {"status": "ok"}


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "error": {"code": f"http_{exc.status_code}", "message": exc.detail}})


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
