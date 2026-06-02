from __future__ import annotations

from fastapi import APIRouter

from app.api import cases, groups, projects, system

router = APIRouter()

router.include_router(system.router)
router.include_router(projects.router)
router.include_router(groups.router)
router.include_router(cases.router)
