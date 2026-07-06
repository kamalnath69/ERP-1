"""FastAPI application entrypoint."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.api.v1 import (
    academic,
    ai as ai_router,
    assignments,
    attendance,
    auth,
    billing,
    extra,
    faculty,
    fees,
    marks,
    misc,
    notifications_send,
    parents,
    reports,
    roles,
    students,
    super_admin,
    timetable,
    users,
)
from app.api.v1 import analytics
import app.models  # noqa: F401 register models with metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def _init_db():
    Base.metadata.create_all(engine)
    from app.db.seed import seed_demo_organization, seed_super_admin

    with SessionLocal() as db:
        seed_super_admin(db)
        seed_demo_organization(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="Athena Education ERP API", version="1.0.0", lifespan=lifespan)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(academic.router)
api_router.include_router(students.router)
api_router.include_router(faculty.router)
api_router.include_router(attendance.router)
api_router.include_router(marks.router)
api_router.include_router(ai_router.router)
api_router.include_router(super_admin.router)
api_router.include_router(analytics.router)
api_router.include_router(billing.router)
api_router.include_router(parents.router)
api_router.include_router(assignments.router)
api_router.include_router(timetable.router)
api_router.include_router(fees.router)
api_router.include_router(extra.router)
api_router.include_router(reports.router)
api_router.include_router(notifications_send.router)
api_router.include_router(misc.router)


@api_router.get("/")
async def root():
    return {"service": "Athena Education ERP", "version": "1.0.0"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
