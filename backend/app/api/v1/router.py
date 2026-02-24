"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import admin, audit, auth, documents, jobs, reviews, rules, ws

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(documents.router)
router.include_router(rules.router)
router.include_router(jobs.router)
router.include_router(reviews.router)
router.include_router(audit.router)
router.include_router(admin.router)
router.include_router(ws.router)
