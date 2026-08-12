"""Edvatiq multi-industry business manager API."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import access, ai, auth, billing, business, client_intelligence, clients, clinic, college, college_placement, dashboard, documents, gym, inventory, misc, notifications, reports, roles, sales, salon, settings as business_settings, super_admin, team, users
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.auth_security import valid_csrf_token
from app.services.realtime import publish_change
from app.core.validation_errors import ValidationProblem
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
        "/api/auth/platform-invite/accept", "/api/auth/registration/checkout",
        "/api/auth/registration/payment/verify",
    }
    public_signup_mock = request.url.path.startswith("/api/auth/registration/checkouts/") and request.url.path.endswith("/mock-pay")
    if unsafe and cookie_authenticated and not bearer_authenticated and request.url.path not in public_auth_paths and not public_signup_mock:
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
    message = exc.detail if isinstance(exc.detail, str) else (
        exc.detail.get("message", "The request could not be completed")
        if isinstance(exc.detail, dict) else "The request could not be completed"
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "error": {"code": f"http_{exc.status_code}", "message": message}})


def _validation_payload(errors: list[dict]) -> dict:
    sanitized = []
    field_errors: dict[str, list[str]] = {}
    form_errors: list[str] = []
    for item in errors:
        location = [str(part) if not isinstance(part, int) else part for part in item.get("loc", ())]
        message = str(item.get("msg") or "Invalid value")
        error_type = str(item.get("type") or "value_error")
        sanitized.append({"loc": location, "type": error_type, "msg": message})
        path = ".".join(str(part) for part in location if str(part) not in {"body", "query", "path", "header"})
        if path:
            field_errors.setdefault(path, []).append(message)
        else:
            form_errors.append(message)
    return {
        "detail": sanitized,
        "error": {
            "code": "validation_error",
            "message": "Please correct the highlighted fields.",
            "field_errors": field_errors,
            "form_errors": form_errors,
        },
    }


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=_validation_payload(exc.errors()))


@app.exception_handler(ValidationProblem)
async def domain_validation_error(_request: Request, exc: ValidationProblem):
    detail = []
    for path, messages in exc.field_errors.items():
        for message in messages:
            detail.append({"loc": ["body", *path.split(".")], "type": "value_error", "msg": message})
    detail.extend({"loc": ["body"], "type": "value_error", "msg": message} for message in exc.form_errors)
    return JSONResponse(status_code=exc.status_code, content={
        "detail": detail,
        "error": {
            "code": "validation_error",
            "message": exc.message,
            "field_errors": exc.field_errors,
            "form_errors": exc.form_errors,
        },
    })


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
